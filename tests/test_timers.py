import asyncio
import json
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory
import threading
import time
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

import test_audio
import test_controls
import test_openai_client
from rpi_assistant.app.timers import Timers, TimerAlerts, timer_action
from rpi_assistant.app.playback import PlaybackStopped


class TimerTests(unittest.TestCase):
    def setUp(self):
        temp=TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.path=Path(temp.name)/'timers.sqlite3'
        self.clock=NS(wall=1000., mono=10.)
        self.store=self.open()
        self.addCleanup(self.store.close)

    def open(self, boot='one'):
        return Timers(self.path, 120, wall=lambda:self.clock.wall, monotonic=lambda:self.clock.mono, boot=boot)

    def test_creation_is_visible_to_separate_connection_before_receipt(self):
        result=timer_action(self.store,'create_timer',{'seconds':60,'label':'Tea'},'request1')
        self.assertTrue(result['ok'])
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM timers').fetchone()[0],1)
        self.assertIn('Tea set',result['message'])

    def test_commit_failure_cannot_become_success_and_next_attempt_recovers(self):
        self.store.db.execute('PRAGMA query_only=ON')
        result=timer_action(self.store,'create_timer',{'seconds':60,'label':'Tea'},'failure')
        self.assertFalse(result['ok']);self.assertIn("can't confirm",result['message'])
        self.assertEqual(self.store.list(),[])
        self.store.db.execute('PRAGMA query_only=OFF')
        self.assertTrue(timer_action(self.store,'create_timer',{'seconds':60},'recovery')['ok'])

    def test_restart_and_clock_jump_use_same_boot_monotonic_deadline(self):
        timer=self.store.create(60,'Tea');self.store.close()
        self.clock.wall+=9000;self.clock.mono+=20
        self.store=self.open()
        self.assertEqual(self.store.list()[0]['remaining_seconds'],40)
        self.clock.mono+=40
        self.assertEqual(self.store.tick()[0]['state'],'ringing')
        self.store.cancel(timer['id']);self.store.close()

    def test_reboot_overdue_pending_timer_rings_then_stays_missed_after_expiry(self):
        self.store.create(60);self.store.close()
        self.clock.wall+=90;self.clock.mono=1
        self.store=self.open('two')
        self.assertEqual(self.store.tick()[0]['state'],'ringing')
        self.clock.wall+=121;self.clock.mono+=121
        self.assertEqual(self.store.tick()[0]['state'],'missed')
        self.store.close();self.store=self.open('three')
        self.assertEqual(self.store.tick()[0]['state'],'missed');self.store.close()

    def test_restart_during_alert_keeps_original_alert_deadline(self):
        self.store.create(1);self.clock.mono+=2;self.clock.wall+=2
        self.store.tick();self.store.close()
        self.clock.mono+=121;self.clock.wall+=121
        self.store=self.open()
        self.assertEqual(self.store.tick()[0]['state'],'missed');self.store.close()

    def test_persisted_cancel_never_rings_after_restart(self):
        timer=self.store.create(1)
        self.assertEqual(self.store.cancel(timer['id']),1)
        self.store.close();self.clock.wall+=100;self.clock.mono+=100
        self.store=self.open();self.assertEqual(self.store.tick(),[]);self.store.close()

    def test_duplicate_request_is_idempotent_and_validation_is_bounded(self):
        first=self.store.create(5,'Tea','same')
        self.assertEqual(self.store.create(5,'Tea','same')['id'],first['id'])
        self.assertEqual(len(self.store.list()),1)
        for seconds in (0,-1,604801,True,1.5,'5',float('nan')):
            with self.subTest(seconds=seconds),self.assertRaises(ValueError):self.store.create(seconds)
        with self.assertRaises(ValueError):self.store.create(5,'x'*65)

    def test_terminal_retention_does_not_drop_active_timers(self):
        active=self.store.create(100)
        for _ in range(40):
            timer=self.store.create(1);self.store.cancel(timer['id'])
        count=self.store.db.execute('SELECT count(*) FROM timers').fetchone()[0]
        self.assertEqual(count,33);self.assertEqual(self.store.list()[0]['id'],active['id'])

    def test_corrupt_store_is_not_replaced_or_acknowledged(self):
        self.store.close();self.path.write_bytes(b'not a database')
        broken=self.open();self.addCleanup(broken.close)
        self.assertFalse(timer_action(broken,'create_timer',{'seconds':1},'x')['ok'])
        self.assertEqual(self.path.read_bytes(),b'not a database')

    def test_model_cannot_rewrite_failed_receipt_and_duplicate_calls_create_once(self):
        call=NS(id='1',function=NS(name='create_timer',arguments='{"seconds":60,"label":"Tea"}'))
        for fail in (False,True):
            with self.subTest(fail=fail):
                self.store.db.execute('PRAGMA query_only='+('ON' if fail else 'OFF'))
                client=test_openai_client.OpenAIClientConversationTests().create_client([
                    NS(content=None,tool_calls=[call,NS(id='2',function=call.function)]),
                    'Your timer was definitely set!'])
                client.timers=self.store
                answer,_=client.get_chat_response('Set a tea timer for a minute.',continue_conversation=True)
                self.assertEqual(len(client.client.chat.completions.calls),1)
                self.assertIn("can't confirm" if fail else 'Tea set',answer)
        self.assertEqual(len(self.store.list()),1)

    def test_model_can_list_then_cancel_by_real_id(self):
        timer=self.store.create(60,'Tea')
        calls=[NS(id='a',function=NS(name='list_timers',arguments='{}')),
               NS(id='b',function=NS(name='cancel_timer',arguments=json.dumps({'timer_id':timer['id']})))]
        client=test_openai_client.OpenAIClientConversationTests().create_client([NS(content=None,tool_calls=[c]) for c in calls])
        client.timers=self.store
        answer,_=client.get_chat_response('Cancel the tea timer.',continue_conversation=True)
        self.assertEqual(answer,'Cancelled 1 timer.');self.assertEqual(self.store.list(),[])

    def test_offline_alert_and_button_dismiss_use_only_local_playback(self):
        fixture=test_controls.ControlsTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        controls=fixture.controls;controls.timers=self.store
        recorder=fixture.recorder;recorder.alert_active=False
        played=threading.Event();controls.playback.prompt=Mock(side_effect=lambda *a,**k:played.set())
        runner=TimerAlerts(self.store,controls);controls.timer_alerts=runner
        self.addCleanup(runner.close)
        timer=self.store.create(1);self.clock.mono+=2;self.clock.wall+=2
        with patch('socket.create_connection',side_effect=OSError('offline')):
            runner.start();self.assertTrue(played.wait(2))
            self.assertEqual(recorder.state,'ALERT')
            self.assertTrue(recorder.alert_active)
            controls.button_press()
            deadline=time.monotonic()+2
            while runner.active and time.monotonic()<deadline:time.sleep(.02)
            self.assertFalse(runner.active)
            self.assertEqual(recorder.state,'LISTEN_WAKE')
            self.assertEqual(self.store.list(),[])
        controls.playback.prompt.assert_called_with('timer.wav',expected_generation=unittest.mock.ANY)

    def test_muted_alert_never_opens_capture_or_overwrites_red(self):
        fixture=test_controls.ControlsTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        recorder=fixture.recorder;recorder.alert_active=False
        fixture.controls.command('mute',True)
        recorder.begin_alert();recorder._finish_processing(allow_follow_up=True)
        self.assertIsNone(recorder.stream);self.assertTrue(recorder.muted)
        self.assertEqual(recorder.state,'MUTED')
        recorder.end_alert();self.assertTrue(recorder.muted)
        recorder.pixels.set_muted.assert_called_with(True)

    def test_timer_preempts_a_partly_spoken_stream_and_releases_for_chime(self):
        fixture = test_controls.ControlsTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        controls = fixture.controls
        controls.recorder.alert_active = False
        started, closed, chime = threading.Event(), threading.Event(), threading.Event()
        stopped = []
        async def produce(write):
            try:
                await write(b"ab" * 2400)
                started.set()
                await asyncio.sleep(10)
            finally:
                closed.set()
        def speak():
            try:
                controls.playback.play_stream(produce, timeout=5)
            except PlaybackStopped:
                stopped.append(True)
        def prompt(*args, **kwargs):
            with controls.playback.lock:
                if closed.is_set():
                    chime.set()
        controls.playback.prompt = prompt
        runner = TimerAlerts(self.store, controls)
        controls.timer_alerts = runner
        self.addCleanup(runner.close)
        with patch("rpi_assistant.app.playback.stream_playback_command",
                   return_value=[sys.executable, "-c", "import sys; sys.stdin.buffer.read()"]):
            worker = threading.Thread(target=speak)
            worker.start()
            try:
                self.assertTrue(started.wait(2))
                self.store.create(1)
                self.clock.mono += 2
                runner.start()
                self.assertTrue(chime.wait(2))
                worker.join(2)
                self.assertEqual(stopped, [True])
                controls.button_press()
            finally:
                controls.playback.stop()
                worker.join(2)

    def test_alert_capture_never_submits_a_recording_or_followup(self):
        fixture=test_controls.ControlsTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        recorder=fixture.recorder;recorder.alert_active=False
        recorder.begin_alert()
        import numpy as np
        recorder._audio_callback(np.ones((160,1),dtype=np.float32),160,None,None)
        recorder._process_chunk(np.ones(160,dtype=np.float32))
        recorder._finish_processing(allow_follow_up=True)
        self.assertEqual(recorder.state,'ALERT')
        self.assertTrue(recorder.audio_queue.empty())
        self.assertTrue(recorder.recording_queue.empty())

    def test_failed_cancel_is_not_acknowledged_and_keeps_schedule(self):
        timer=self.store.create(60)
        self.store.db.execute('PRAGMA query_only=ON')
        result=timer_action(self.store,'cancel_timer',{'timer_id':timer['id']},'cancel')
        self.assertFalse(result['ok'])
        self.assertIn("can't confirm",result['message'])
        self.assertEqual(self.store.list()[0]['state'],'pending')

    def test_timer_mutation_does_not_silently_execute_co_requested_action(self):
        call=NS(id='timer',function=NS(name='create_timer',arguments='{"seconds":60,"label":"Tea"}'))
        other=NS(id='action',function=NS(name='utility__roll',arguments='{}'))
        client=test_openai_client.OpenAIClientConversationTests().create_client([NS(content=None,tool_calls=[call,other])])
        client.timers=self.store
        manager=Mock();manager.config.max_tool_rounds=3;manager.openai_tools.return_value=[]
        client.mcp_manager=manager
        answer,_=client.get_chat_response('Set a timer and roll a die.',continue_conversation=True)
        manager.call_tool.assert_not_called()
        self.assertIn("haven't performed any other action",answer)
        self.assertEqual(len(self.store.list()),1)
