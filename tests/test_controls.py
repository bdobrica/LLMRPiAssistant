import importlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import threading
import unittest
from unittest.mock import Mock, patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import numpy as np
import test_audio
import test_openai_client
from rpi_assistant.app.config import ControlsConfig, AudioOutputConfig, RecordingConfig
from rpi_assistant.app.controls import LocalControls, MixerVolume, voice_control
from rpi_assistant.app.control_server import ControlServer
from rpi_assistant.app.playback import AudioPlayback, PlaybackStopped
from rpi_assistant.app.voice_command import VoiceCommandHandler
from rpi_assistant.app.interrupt_button import open_interrupt_button


class ControlsTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.directory = Path(tmp.name)
        self.recorder = test_audio.WakeWordRecorderTests().create_recorder_shell(self.directory / 'command.wav')
        self.recorder.state = 'LISTEN_WAKE'
        self.recorder.stream_lock = threading.Lock()
        self.recorder.capture_paused = False
        self.recorder.muted = False
        self.recorder.capture_generation = self.recorder.recording_generation = 0
        self.recorder.processing_active = False
        self.recorder.pixels = Mock()
        self.stream = Mock(active=True, closed=False)
        self.stream.close.side_effect = lambda: setattr(self.stream, 'closed', True)
        self.recorder.stream = self.stream
        self.player = AudioPlayback(AudioOutputConfig())
        self.client = test_openai_client.OpenAIClientConversationTests().create_client(['A new answer.'])
        self.controls = LocalControls(ControlsConfig(state_path=str(self.directory / 'state.json')),
                                      self.recorder, self.player, self.client)
        self.controls.volume = Mock()
        self.controls.volume.get.return_value = 70
        self.controls.volume.set.return_value = 60

    def test_mute_closes_stream_clears_audio_and_survives_restart(self):
        self.recorder.audio_queue.put(np.zeros(160, dtype=np.float32))
        self.controls.command('mute', True)
        self.stream.abort.assert_called_once()
        self.stream.close.assert_called_once()
        self.assertEqual(self.recorder.rec, [])
        self.assertTrue(self.recorder.audio_queue.empty())
        self.assertTrue(self.controls.status()['muted'])
        self.assertFalse(self.controls.status()['capture_active'])
        self.recorder._process_chunk(np.ones(160, dtype=np.float32))
        self.recorder._finish_processing(allow_follow_up=True)
        self.assertEqual(self.recorder.state, 'MUTED')
        self.recorder.pixels.set_muted.assert_called_with(True)
        restart = Mock()
        LocalControls(self.controls.config, restart, self.player, self.client)
        restart.set_muted.assert_called_once_with(True)

    def test_close_failure_never_claims_muted(self):
        self.stream.close.side_effect = OSError('device failure')
        with self.assertRaises(OSError):
            self.controls.command('mute', True)
        self.assertFalse(self.controls.status()['muted'])
        self.recorder.pixels.set_muted.assert_not_called()
        self.assertTrue(self.recorder.capture_paused)

    def test_unmute_reopens_stream_and_failure_stays_red(self):
        self.controls.command('mute', True)
        with patch('rpi_assistant.app.audio.sd.InputStream', return_value=Mock()) as stream:
            self.controls.command('mute', False)
            stream.return_value.start.assert_called_once()
            self.assertFalse(self.recorder.muted)
            self.assertEqual(self.recorder.state, 'LISTEN_WAKE')
        self.recorder.stream = None
        self.controls.command('mute', True)
        with patch('rpi_assistant.app.audio.sd.InputStream', side_effect=OSError()):
            with self.assertRaises(OSError):
                self.controls.command('mute', False)
        self.assertTrue(self.recorder.muted)
        self.assertTrue(json.loads(self.controls.state_path.read_text())['muted'])

    def test_reset_during_request_waits_then_clears_all_chat_context(self):
        self.client.remember_app_response('Roll', 'six')
        self.controls.begin_turn()
        self.controls.command('new_conversation')
        self.assertTrue(self.controls.reset_pending)
        self.assertGreater(len(self.client.conversation_history), 1)
        with self.assertRaises(PlaybackStopped):
            self.controls.check()
        self.controls.end_turn()
        self.assertEqual(len(self.client.conversation_history), 1)
        self.assertFalse(self.controls.reset_pending)

    def test_cancelled_saved_recording_is_not_submitted(self):
        self.controls.command('stop')
        with self.assertRaises(PlaybackStopped):
            self.controls.begin_turn()

    def test_stopped_generation_cannot_start_late_playback(self):
        generation = self.player.generation
        self.player.stop()
        with patch('rpi_assistant.app.playback.subprocess.Popen') as popen:
            with self.assertRaises(PlaybackStopped):
                self.player.play('stale.wav', backend='realtime', expected_generation=generation)
            popen.assert_not_called()

    def test_pending_request_blocks_unmute_without_changing_persisted_mute(self):
        self.controls.begin_turn()
        self.controls.command('mute', True)
        with self.assertRaises(RuntimeError):
            self.controls.command('mute', False)
        self.assertTrue(json.loads(self.controls.state_path.read_text())['muted'])

    def test_stop_during_transcription_or_generation_drops_stale_output(self):
        for stage in ('transcribe_audio', 'generate_speech'):
            with self.subTest(stage=stage):
                self.recorder.recording_generation = self.recorder.capture_generation
                client = Mock()
                output = self.directory / 'reply.wav'
                client.transcribe_audio.return_value = 'What about a cube?'
                client.get_chat_response.return_value = ('Answer', {'total_tokens': 1})
                def cancel(*args):
                    self.controls.command('stop')
                    output.write_bytes(b'stale')
                    return 'What about a cube?'
                getattr(client, stage).side_effect = cancel
                apps = Mock()
                apps.handle.return_value = None
                apps.should_classify_app_intent.return_value = False
                player = Mock()
                handler = VoiceCommandHandler(NS(audio_output=AudioOutputConfig(tts_output_path=str(output)),
                                                 openai=NS(tts_voice='alloy', tts_backend='realtime')),
                                               client, apps, Mock(), player, Mock(), controls=self.controls)
                self.assertFalse(handler.process('unused.wav'))
                player.play.assert_not_called()
                player.prompt.assert_not_called()
                if stage == 'transcribe_audio':
                    apps.handle.assert_not_called()
                else:
                    self.assertFalse(output.exists())

    def test_tool_batch_cancellation_preserves_completed_result_and_skips_next_action(self):
        calls = [NS(id=str(i), function=NS(name='utility__roll', arguments='{}')) for i in range(2)]
        client = test_openai_client.OpenAIClientConversationTests().create_client([NS(content=None, tool_calls=calls)])
        manager = Mock()
        manager.config.max_tool_rounds = 2
        manager.openai_tools.return_value = [{'type':'function', 'function':{'name':'utility__roll'}}]
        def first_action(*args):
            self.controls.command('stop')
            return '{"result":6}'
        manager.call_tool.side_effect = first_action
        client.mcp_manager = manager
        client.cancel_check = self.controls.check
        self.controls.begin_turn()
        with self.assertRaises(PlaybackStopped):
            client.get_chat_response('Roll', continue_conversation=True)
        manager.call_tool.assert_called_once()
        results = [m['content'] for m in client.conversation_history if m['role'] == 'tool']
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0], '{"result":6}')
        self.assertIn('Cancelled', results[1])

    def test_button_preserves_immediate_interrupt_and_adds_single_hold(self):
        controls = Mock()
        import sys
        with patch.dict(sys.modules, {'gpiozero': NS(Button=Mock())}):
            button = open_interrupt_button(RecordingConfig(interrupt_button_gpio=17), self.player, controls)
            button.when_pressed()
            button.when_held()
        controls.button_press.assert_called_once()
        controls.button_hold.assert_called_once()
        self.assertEqual(button.hold_time, 1.5)
        self.assertFalse(button.hold_repeat)

    def test_narrow_voice_commands_do_not_hijack_questions(self):
        self.assertEqual(voice_control('Set the volume to 35 percent.'), ('volume', 35))
        self.assertEqual(voice_control('New conversation!'), ('new_conversation', None))
        self.assertIsNone(voice_control('What is the volume of a cube?'))
        self.assertIsNone(voice_control('Explain the phrase mute the microphone'))
        self.assertIsNone(voice_control('volume 999'))

    def test_volume_uses_local_mixer_and_reports_actual_quantized_value(self):
        volume = MixerVolume(ControlsConfig())
        with patch('rpi_assistant.app.controls.subprocess.run') as run:
            run.side_effect = [NS(stdout='Playback [90%]'), NS(stdout='Playback [100%]')]
            self.assertEqual(volume.set(20, relative=True), 100)
            self.assertEqual(run.call_args.args[0][-1], '100%')
            self.assertEqual(run.call_args.kwargs['timeout'], 2)

    def test_speaker_mute_restores_raw_channels_after_restart(self):
        config = self.controls.config
        def reading(left, lp, right, rp):
            return NS(stdout=f'Front Left: Playback {left} [{lp}%]\nFront Right: Playback {right} [{rp}%]')
        audible = reading(117, 68, 100, 30)
        silent = reading(0, 0, 0, 0)
        with patch('rpi_assistant.app.controls.subprocess.run') as run:
            run.side_effect = [audible, silent, silent, silent, audible]
            self.controls.volume = MixerVolume(config)
            self.controls.command('speaker_mute', True)
            self.controls.command('speaker_mute', True)
            self.controls.volume = MixerVolume(config)
            self.controls.command('speaker_mute', False)
            self.assertEqual(run.call_args.args[0][-1], '117,100')
            self.assertTrue(self.recorder.stream.active)
            self.assertFalse(self.recorder.muted)

    def test_unconfirmed_mute_reports_failure_and_levels_follow_external_changes(self):
        volume = MixerVolume(self.controls.config)
        with patch('rpi_assistant.app.controls.subprocess.run') as run:
            run.side_effect = [NS(stdout='Playback 80 [34%]')] * 2 + [NS(stdout='Playback 92 [45%]')]
            with self.assertRaisesRegex(RuntimeError, 'did not confirm'):
                volume.mute(True)
            self.assertEqual(volume.get(), 45)
        self.assertEqual(voice_control('unmute the speaker'), ('speaker_mute', False))
        self.assertEqual(voice_control('mute'), ('mute', True))

    def test_local_http_controls_work_without_provider_and_reject_cross_origin(self):
        server = ControlServer(NS(host='127.0.0.1', port=0), self.controls)
        self.addCleanup(server.close)
        url = f'http://127.0.0.1:{server.server_port}'
        with urlopen(url, timeout=3) as response:
            self.assertIn(b'Assistant controls', response.read())
        data = json.dumps({'action':'mute', 'value':True}).encode()
        for headers in ({}, {'X-Assistant-Control':'1', 'Origin':'https://untrusted.example'},
                        {'X-Assistant-Control':'1', 'Host':'rebinding.example'}):
            with self.assertRaises(HTTPError) as caught:
                urlopen(Request(url+'/control', data=data, headers=headers), timeout=3)
            self.assertEqual(caught.exception.code, 403)
        with urlopen(Request(url+'/control', data=data, headers={'X-Assistant-Control':'1', 'Origin':url}), timeout=3) as response:
            self.assertTrue(json.load(response)['muted'])

    def test_spoken_controls_bypass_apps_and_chat_and_reset_uses_local_clip(self):
        for text, expected in (("start a new conversation", "new_conversation.wav"),
                               ("mute the microphone", None), ("volume down", "speech")):
            with self.subTest(text=text):
                self.recorder.capture_paused = self.recorder.muted = False
                self.recorder.recording_generation = self.recorder.capture_generation
                self.recorder.stream = None
                client, apps, player = Mock(), Mock(), Mock()
                client.transcribe_audio.return_value = text
                output = self.directory / 'reply.wav'
                client.generate_speech.side_effect = lambda *args: output.write_bytes(b'volume confirmation')
                handler = VoiceCommandHandler(NS(audio_output=AudioOutputConfig(tts_output_path=str(output)),
                                                 openai=NS(tts_voice='alloy',tts_backend='realtime')),
                                              client, apps, Mock(), player, Mock(), controls=self.controls)
                handler.process('unused.wav')
                apps.handle.assert_not_called()
                client.get_chat_response.assert_not_called()
                if expected == "speech":
                    client.generate_speech.assert_called_once()
                else:
                    client.generate_speech.assert_not_called()
                    if expected:
                        player.prompt.assert_called_once_with(expected, expected_generation=player.generation)
                    else:
                        player.prompt.assert_not_called()
                self.assertFalse(self.controls.busy)

    def test_mute_during_completed_app_action_preserves_result_without_replay(self):
        client, apps, player = Mock(), Mock(), Mock()
        client.transcribe_audio.return_value = 'roll a die'
        def action(*args):
            self.controls.command('mute', True)
            return NS(text='You rolled six.')
        apps.handle.side_effect = action
        handler = VoiceCommandHandler(NS(audio_output=AudioOutputConfig()), client, apps,
                                      Mock(), player, Mock(), controls=self.controls)
        self.assertFalse(handler.process('unused.wav'))
        apps.handle.assert_called_once()
        client.remember_app_response.assert_called_once_with('roll a die', 'You rolled six.')
        player.play.assert_not_called()
        client.generate_speech.assert_not_called()

    def test_stop_during_speech_generation_does_not_allow_later_local_prompt_to_revive_answer(self):
        generation = self.player.generation
        self.player.stop()
        with patch('rpi_assistant.app.playback.subprocess.Popen') as popen:
            popen.return_value.communicate.return_value = (None, b'')
            popen.return_value.returncode = 0
            self.player.prompt('online.mp3')
            with self.assertRaises(PlaybackStopped):
                self.player.play('old-answer.wav', backend='realtime', expected_generation=generation, interruptible=True)
            self.assertEqual(popen.call_count, 1)

    def test_red_is_cleared_before_capture_restarts_and_unknown_failure_never_shows_mute(self):
        self.controls.command('mute', True)
        stream = Mock(active=True, closed=False)
        def starting():
            self.recorder.pixels.set_muted.assert_called_with(False)
            self.assertFalse(self.recorder.muted)
            raise OSError('start failed')
        stream.start.side_effect = starting
        stream.close.side_effect = OSError('close failed too')
        with patch('rpi_assistant.app.audio.sd.InputStream', return_value=stream):
            with self.assertRaises(OSError):
                self.controls.command('mute', False)
        self.assertFalse(self.controls.status()['muted'])
        self.assertEqual(self.recorder.state, 'CAPTURE_ERROR')
        self.recorder.pixels.set_muted.assert_called_with(False)

    def test_muted_led_overrides_animation_and_stale_cue_cannot_restore_red(self):
        import queue
        import sys
        with patch.dict(sys.modules, {"gpiozero": NS(LED=Mock()), "spidev": NS()}):
            Pixels = importlib.import_module('rpi_assistant.app.pixels').Pixels
        pixels = object.__new__(Pixels)
        pixels.PIXELS_N = 3
        pixels.dev, pixels.pattern = Mock(), Mock()
        pixels.queue = queue.Queue()
        pixels._indicator_lock = threading.Lock()
        pixels.muted = False
        pixels.set_muted(True)
        old_cue = pixels.queue.get_nowait()
        pixels.show([0, 0, 32, 0] * 3)
        self.assertEqual(pixels.dev.set_pixel.call_args.args, (2, 32, 0, 0))
        pixels.set_muted(False)
        self.assertEqual(pixels.dev.set_pixel.call_args.args, (2, 0, 0, 0))
        old_cue()
        pixels.pattern.listen.assert_called_once()
        self.assertEqual(pixels.dev.set_pixel.call_args.args, (2, 0, 0, 0))
