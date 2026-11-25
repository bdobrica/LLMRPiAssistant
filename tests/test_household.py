from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import threading
import time
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import test_controls
import test_openai_client
from rpi_assistant.app.config import load_config
from rpi_assistant.app.control_server import ControlServer
from rpi_assistant.app.household import Household, HouseholdInputError, household_action
from rpi_assistant.app.timers import Timers, TimerAlerts


class HouseholdTests(unittest.TestCase):
    def setUp(self):
        tmp=TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.path=Path(tmp.name)/'household.sqlite3'
        self.clock=NS(now=datetime(2026,1,1,tzinfo=timezone.utc).timestamp(),mono=10.)
        self.store=self.open();self.addCleanup(self.store.close)

    def open(self, zone='Europe/Bucharest'):
        return Household(self.path,zone,4,wall=lambda:self.clock.now,monotonic=lambda:self.clock.mono,boot='test')

    def test_commit_and_restart_preserve_reminders_and_list(self):
        reminder=self.store.create_reminder('Buy bread','2026-01-02T08:00')
        item=self.store.add_item('Milk')
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM timers').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM shopping').fetchone()[0],1)
        other=self.open();self.addCleanup(other.close)
        self.assertEqual(other.list()[0]['id'],reminder['id'])
        self.assertEqual(other.shopping(),[{'id':item['id'],'item':'Milk'}])

    def test_timezone_change_preserves_instant_and_changes_display(self):
        row=self.store.create_reminder('Bread','2026-01-02T08:00')
        other=self.open('Europe/London');self.addCleanup(other.close)
        changed=other.list()[0]
        self.assertEqual(changed['due'],row['due'])
        self.assertIn('06:00:00',changed['due_local'])
        self.assertIn('08:00:00',row['due_local'])

    def test_config_file_timezone_overrides_environment_and_rejects_typos(self):
        path=self.path.parent/'config.ini'
        path.write_text('[openai]\napi_key=test\n[household]\ntimezone=Europe/London\n')
        with patch.dict('os.environ',{'HOUSEHOLD_TIMEZONE':'UTC'},clear=True):
            self.assertEqual(load_config(str(path)).household.timezone,'Europe/London')
        path.write_text('[openai]\napi_key=test\n[household]\ntimezone=Not/AZone\n')
        with self.assertRaisesRegex(ValueError,'IANA'):load_config(str(path))

    def test_gap_and_repeated_clock_times_require_valid_explicit_choice(self):
        with self.assertRaisesRegex(HouseholdInputError,'does not exist'):
            self.store.create_reminder('Gap','2026-03-29T03:30')
        with self.assertRaisesRegex(HouseholdInputError,'occurs twice'):
            self.store.create_reminder('Fold','2026-10-25T03:30')
        first=self.store.create_reminder('First','2026-10-25T03:30',occurrence='first')
        second=self.store.create_reminder('Second','2026-10-25T03:30',occurrence='second')
        self.assertEqual(second['due']-first['due'],3600)

    def test_vague_spoken_time_cannot_be_scheduled_even_if_model_guesses(self):
        args={'text':'Bread','local_time':'2026-01-02T08:00','delay_seconds':0,'occurrence':'unspecified'}
        for text in ('Remind me tomorrow morning.','Remind me at eight.','Remind me tomorrow.','Remind me every day at 8am.'):
            with self.subTest(text=text):
                result=household_action(self.store,'schedule_reminder',args,'req',text)
                self.assertFalse(result['ok']);self.assertEqual(self.store.list(),[])
        self.assertTrue(household_action(self.store,'schedule_reminder',args,'clear','Tomorrow at 8am.')['ok'])

    def test_short_relative_clarification_works_without_guessing_time(self):
        args={'text':'Bread','local_time':'','delay_seconds':300,'occurrence':'unspecified'}
        self.assertTrue(household_action(self.store,'schedule_reminder',args,'short','five minutes')['ok'])
        self.assertFalse(household_action(self.store,'schedule_reminder',args,'vague','later please')['ok'])

    def test_duplicates_do_not_write_extra_reminders_or_shopping_items(self):
        first=self.store.create_reminder('Buy bread','2026-01-02T08:00',request_id='one')
        duplicate=self.store.create_reminder('  buy   BREAD ','2026-01-02T08:00',request_id='two')
        self.assertEqual(first['id'],duplicate['id']);self.assertTrue(duplicate['already_present'])
        milk=self.store.add_item('Milk')
        writes=self.store.db.total_changes
        self.assertTrue(self.store.add_item('  ＭＩＬＫ  ')['already_present'])
        self.assertEqual(self.store.db.total_changes,writes)
        self.assertEqual(len(self.store.shopping()),1)
        self.store.remove_item(milk['id']);writes=self.store.db.total_changes
        self.assertTrue(self.store.remove_item(milk['id'])['already_removed'])
        self.assertEqual(self.store.db.total_changes,writes)
        self.assertEqual(self.store.add_item('milk')['id'],milk['id'])

    def test_cancel_and_remove_stay_removed_after_restart(self):
        reminder=self.store.create_reminder('Bread',delay_seconds=1)
        item=self.store.add_item('Milk')
        self.store.cancel(reminder['id']);self.store.remove_item(item['id'])
        self.clock.now+=5;self.clock.mono+=5
        other=self.open();self.addCleanup(other.close)
        self.assertEqual(other.tick(),[]);self.assertEqual(other.shopping(),[])

    def test_overdue_reminder_recovers_and_alert_expiry_is_persisted(self):
        self.store.create_reminder('Bread',delay_seconds=1)
        other=self.open();self.addCleanup(other.close)
        self.clock.now+=2;self.clock.mono+=2
        self.assertEqual(other.tick()[0]['state'],'ringing')
        self.clock.now+=5;self.clock.mono+=5
        self.assertEqual(other.tick()[0]['state'],'missed')

    def test_failed_mutations_cannot_return_success_receipts(self):
        reminder=self.store.create_reminder('Bread',delay_seconds=30)
        milk=self.store.add_item('Milk')
        self.store.db.execute('PRAGMA query_only=ON')
        for name,args,text in (
            ('schedule_reminder',{'text':'Other','local_time':'','delay_seconds':20},'In 20 seconds'),
            ('cancel_reminder',{'reminder_id':reminder['id']},''),
            ('add_shopping_item',{'item':'Eggs'},''),
            ('remove_shopping_item',{'item_id':milk['id']},'')):
            with self.subTest(name=name):
                result=household_action(self.store,name,args,name,text)
                self.assertFalse(result['ok']);self.assertIn("can't confirm",result['message'])
        self.assertEqual(len(self.store.shopping()),1);self.assertEqual(len(self.store.list()),1)

    def test_local_http_list_and_writes_work_offline_with_clear_time_errors(self):
        fixture=test_controls.ControlsTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        fixture.controls.household=self.store
        server=ControlServer(NS(host='127.0.0.1',port=0),fixture.controls);self.addCleanup(server.close)
        base=f'http://127.0.0.1:{server.server_port}'
        def post(action,value):
            return urlopen(Request(base+'/control',data=json.dumps({'action':action,'value':value}).encode(),headers={'X-Assistant-Control':'1'}),timeout=3)
        with post('shopping_add','Milk') as response:self.assertEqual(len(json.load(response)['shopping']),1)
        with post('shopping_add','milk') as response:self.assertEqual(len(json.load(response)['shopping']),1)
        with self.assertRaises(HTTPError) as caught:
            post('reminder_create',{'text':'Bread','local_time':'2026-03-29T03:30'})
        self.assertIn('does not exist',caught.exception.read().decode())
        with post('reminder_create',{'text':'Bread','local_time':'2026-01-02T08:00'}) as response:
            self.assertEqual(json.load(response)['timezone'],'Europe/Bucharest')

    def test_combined_alert_dismisses_reminder_and_keeps_shopping_and_future_timer(self):
        fixture=test_controls.ControlsTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        controls=fixture.controls
        timers=Timers(self.path.parent/'timers.sqlite3');self.addCleanup(timers.close)
        future=timers.create(600);controls.timers=timers;controls.household=self.store
        self.store.add_item('Milk');self.store.create_reminder('Bread',delay_seconds=1)
        self.clock.now+=2;self.clock.mono+=2
        played=threading.Event();controls.playback.prompt=Mock(side_effect=lambda *a,**k:played.set())
        alerts=TimerAlerts(timers,controls,reminders=self.store);controls.timer_alerts=alerts
        self.addCleanup(alerts.close)
        with patch('socket.create_connection',side_effect=OSError('offline')):
            alerts.start();self.assertTrue(played.wait(2));controls.button_press()
            deadline=time.monotonic()+2
            while alerts.active and time.monotonic()<deadline:time.sleep(.02)
        self.assertFalse(alerts.active);self.assertEqual(self.store.list(),[])
        self.assertEqual(len(self.store.shopping()),1);self.assertEqual(timers.list()[0]['id'],future['id'])

    def test_model_failure_receipt_is_not_rewritten_as_success(self):
        self.store.db.execute('PRAGMA query_only=ON')
        call=NS(id='a',function=NS(name='add_shopping_item',arguments='{"item":"Milk"}'))
        client=test_openai_client.OpenAIClientConversationTests().create_client([NS(content=None,tool_calls=[call]),'Added milk!'])
        client.household=self.store
        answer,_=client.get_chat_response('Add milk to Shopping.',continue_conversation=True)
        self.assertIn("can't confirm",answer);self.assertEqual(self.store.shopping(),[])
        self.assertEqual(len(client.client.chat.completions.calls),1)

    def test_model_can_read_then_remove_saved_item_without_duplicate_add(self):
        milk=self.store.add_item('Milk')
        calls=[NS(id='list',function=NS(name='list_shopping_items',arguments='{}')),
               NS(id='remove',function=NS(name='remove_shopping_item',arguments=json.dumps({'item_id':milk['id']})))]
        client=test_openai_client.OpenAIClientConversationTests().create_client([NS(content=None,tool_calls=[c]) for c in calls])
        client.household=self.store
        answer,_=client.get_chat_response('Remove milk from Shopping.',continue_conversation=True)
        self.assertIn('no longer on Shopping',answer);self.assertEqual(self.store.shopping(),[])

    def test_failed_read_is_reported_without_model_inventing_list_contents(self):
        self.store.error='Injected unavailable storage'
        call=NS(id='read',function=NS(name='list_shopping_items',arguments='{}'))
        client=test_openai_client.OpenAIClientConversationTests().create_client([NS(content=None,tool_calls=[call]),'Milk is on your list.'])
        client.household=self.store
        answer,_=client.get_chat_response("What's on Shopping?",continue_conversation=True)
        self.assertIn("can't confirm",answer)
        self.assertEqual(len(client.client.chat.completions.calls),1)
