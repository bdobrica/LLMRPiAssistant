import json
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import numpy as np
import test_controls
from rpi_assistant.app.audio_checks import AudioChecks
from rpi_assistant.app.config import load_config, ControlsConfig
from rpi_assistant.app.control_server import ControlServer
from rpi_assistant.app.phone_settings import PhoneSettings, SettingsError
from rpi_assistant.app.weather import Weather


class PhoneSetupTests(unittest.TestCase):
    def setUp(self):
        fixture = test_controls.ControlsTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.controls, self.recorder = fixture.controls, fixture.recorder
        self.path = fixture.directory / 'config.ini'
        self.path.write_text('[openai]\napi_key=old-private-key\n[household]\ntimezone=UTC\n[custom]\npreserve=yes\n')
        self.config = load_config(str(self.path))
        self.config.weather.state_path = str(fixture.directory / 'weather.json')
        self.config.recording = self.recorder.recording_config
        self.config.audio = self.recorder.audio_config
        self.controls.client.config = self.config.openai
        self.controls.client.client = Mock()
        self.controls.client.weather = Weather(self.config.weather)
        self.controls.household = Mock(zone=ZoneInfo('UTC'))
        self.controls.household.list.return_value = []
        self.controls.household.shopping.return_value = []
        self.settings = PhoneSettings(self.config, self.path, self.controls)
        self.controls.settings = self.settings
        self.checks = AudioChecks(self.controls)
        self.controls.audio_checks = self.checks
        self.addCleanup(self.checks.close)

    def apply(self, **values):
        return self.controls.command('settings_apply', {'revision': self.settings.status()['revision'], **values})

    def test_explicit_apply_preserves_unknown_config_and_undo_survives_reopen(self):
        before = self.path.read_bytes()
        self.apply(follow_up_seconds=0, reminder_timezone='Europe/Bucharest', weather_city='Berlin, Germany')
        self.assertEqual(self.recorder.recording_config.follow_up_window_seconds, 0)
        self.assertEqual(str(self.controls.household.zone), 'Europe/Bucharest')
        self.assertIn('preserve = yes', self.path.read_text())
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.settings.backup.stat().st_mode & 0o777, 0o600)
        reopened = PhoneSettings(self.config, self.path, self.controls)
        self.assertTrue(reopened.status()['can_undo'])
        reopened.change({'revision': reopened.status()['revision']}, undo=True)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.recorder.recording_config.follow_up_window_seconds, 6)
        self.assertFalse(reopened.status()['can_undo'])

    def test_keys_are_write_only_blank_preserves_and_undo_restores(self):
        sdk = Mock()
        with patch('rpi_assistant.app.phone_settings.OpenAI', return_value=sdk):
            self.apply(openai_key='new-private-key', ipgeolocation_key='location-private-key')
            self.assertIs(self.controls.client.client, sdk)
            self.assertEqual(self.config.openai.api_key, 'new-private-key')
            self.apply(openai_key='', weather_key='', ipgeolocation_key='')
            status = json.dumps(self.controls.status())
            for value in ('old-private-key', 'new-private-key', 'location-private-key'):
                self.assertNotIn(value, status)
            self.assertTrue(self.settings.status()['keys_configured']['openai_key'])
            self.controls.command('settings_undo', {'revision': self.settings.status()['revision']})
            self.assertEqual(self.config.openai.api_key, 'old-private-key')

    def test_invalid_values_and_stale_page_do_not_write_or_mutate(self):
        before = self.path.read_bytes()
        for values in ({'follow_up_seconds': -1}, {'follow_up_seconds': float('nan')}, {'follow_up_seconds': True},
                       {'reminder_timezone': 'not/a/zone'}, {'weather_city': 'city\n[openai]'},
                       {'openai_key': 'secret with spaces'}, {'unlisted': 'anything'}):
            with self.assertRaises(SettingsError): self.apply(**values)
            self.assertEqual(self.path.read_bytes(), before)
        old_revision = self.settings.status()['revision']
        self.path.write_bytes(before+b'\n# external edit\n')
        with self.assertRaisesRegex(SettingsError, 'changed since'):
            self.controls.command('settings_apply', {'revision': old_revision, 'follow_up_seconds': 4})
        self.assertEqual(self.recorder.recording_config.follow_up_window_seconds, 6)

    def test_apply_failure_restores_runtime_and_config(self):
        before = self.path.read_bytes()
        install = self.settings._install
        attempts = []
        def fail_once(values, prepared):
            install(values, prepared)
            if not attempts:
                attempts.append(True)
                raise RuntimeError('private diagnostic')
        with patch.object(self.settings, '_install', side_effect=fail_once):
            with self.assertRaisesRegex(SettingsError, 'previous configuration was restored'):
                self.apply(follow_up_seconds=4, reminder_timezone='Europe/Bucharest')
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.recorder.recording_config.follow_up_window_seconds, 6)
        self.assertEqual(str(self.controls.household.zone), 'UTC')
        self.assertNotIn('private diagnostic', json.dumps(self.controls.status()))

    def test_file_failure_and_busy_state_do_not_claim_apply(self):
        before = self.path.read_bytes()
        with patch.object(self.settings, '_write_config', side_effect=[OSError(), None]):
            with self.assertRaises(SettingsError): self.apply(follow_up_seconds=4)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.recorder.recording_config.follow_up_window_seconds, 6)
        self.controls.busy = True
        with self.assertRaisesRegex(SettingsError, 'Wait'): self.apply(follow_up_seconds=4)

    def test_no_api_key_can_open_setup_but_voice_does_not_make_api_calls(self):
        self.path.write_text('[household]\ntimezone=UTC\n')
        with patch.dict('os.environ', {}, clear=True):
            with self.assertRaises(ValueError): load_config(str(self.path))
            config = load_config(str(self.path), allow_missing_api_key=True)
        self.controls.client.config = config.openai
        with self.assertRaisesRegex(RuntimeError, 'phone page'):
            self.controls.client.transcribe_audio('does-not-exist.wav')
        self.controls.client.client.audio.transcriptions.create.assert_not_called()

    def test_http_status_never_returns_keys_and_cross_origin_cannot_apply(self):
        server = ControlServer(NS(host='127.0.0.1', port=0), self.controls)
        self.addCleanup(server.close)
        base = f'http://127.0.0.1:{server.server_port}'
        with urlopen(base+'/status') as response:
            text = response.read().decode()
        self.assertNotIn('old-private-key', text)
        data = json.dumps({'action':'settings_apply','value':{'revision':self.settings.status()['revision'],'follow_up_seconds':4}}).encode()
        with self.assertRaises(HTTPError) as caught:
            urlopen(Request(base+'/control',data=data,headers={'X-Assistant-Control':'1','Origin':'http://elsewhere.invalid'}))
        self.assertEqual(caught.exception.code, 403)
        with urlopen(Request(base+'/control',data=data,headers={'X-Assistant-Control':'1','Origin':base})) as response:
            self.assertEqual(json.load(response)['settings']['follow_up_seconds'], 4)

    def test_microphone_check_is_bounded_and_never_enters_recognition_queue(self):
        self.recorder.begin_diagnostic(True)
        block = np.full((160,1), .2, dtype=np.float32)
        for _ in range(400): self.recorder._audio_callback(block,160,None,None)
        self.assertTrue(self.recorder.audio_queue.empty())
        audio = self.recorder.take_diagnostic_audio()
        self.assertEqual(len(audio), 48000)
        self.recorder._audio_callback(block,160,None,None)
        self.assertTrue(self.recorder.audio_queue.empty())
        self.recorder.end_diagnostic()
        self.assertEqual(self.recorder.state, 'LISTEN_WAKE')

    def test_muted_check_is_refused_and_stop_discards_recording(self):
        self.controls.command('mute', True)
        with self.assertRaisesRegex(SettingsError, 'Unmute'):
            self.controls.command('audio_check','microphone')
        self.assertFalse(self.checks.active)
        self.recorder.capture_paused = self.recorder.muted = False
        self.recorder.stream = Mock(active=True)
        self.controls.command('audio_check','microphone')
        self.controls.command('stop')
        self.checks.thread.join(timeout=2)
        self.assertEqual(self.checks.result['state'], 'cancelled')
        self.assertIsNone(self.recorder.diagnostic_audio)
        self.assertFalse(self.recorder.diagnostic_active)

    def test_microphone_feedback_and_temp_recording_cleanup(self):
        paths = []
        def play(path, **kwargs):
            paths.append(Path(path))
            self.assertTrue(Path(path).exists())
            self.assertEqual(Path(path).stat().st_mode & 0o777, 0o600)
            return True
        with patch.object(self.checks.cancelled, 'wait', return_value=False), patch.object(self.recorder, 'take_diagnostic_audio', return_value=np.zeros(48000,dtype=np.float32)), patch.object(self.controls.playback, 'play', side_effect=play):
            self.controls.command('audio_check','microphone')
            self.checks.thread.join(timeout=2)
        self.assertEqual(self.checks.result['state'], 'complete')
        self.assertIn('little sound', self.checks.result['message'])
        self.assertTrue(paths and all(not path.exists() for path in paths))
        self.controls.client.client.audio.transcriptions.create.assert_not_called()

    def test_playback_failure_returns_feedback_and_restores_capture_flow(self):
        with patch.object(self.controls.playback, 'prompt', side_effect=OSError('private detail')):
            self.controls.command('audio_check', 'speaker')
            self.checks.thread.join(timeout=2)
        self.assertEqual(self.checks.result['state'], 'error')
        self.assertNotIn('private', self.checks.result['message'])
        self.assertEqual(self.recorder.state, 'LISTEN_WAKE')
        self.assertFalse(self.checks.active)
