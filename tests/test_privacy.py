from contextlib import redirect_stdout, redirect_stderr
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import io
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import numpy as np
import test_phone_setup
import test_voice_command
from rpi_assistant.app.audio import save_wav
from rpi_assistant.app.config import LoggingConfig
from rpi_assistant.app.logger import InteractionLogger
from rpi_assistant.app.phone_settings import SettingsError
from rpi_assistant.app.privacy import ConversationPrivacy, quiet_provider_logs
from rpi_assistant.app.timers import Timers
from rpi_assistant.app.household import Household


MARKER = 'SYNTHETIC_PRIVATE_LANTERN_493'


class PrivacyTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def logger(self, **options):
        return InteractionLogger(LoggingConfig(log_file=str(self.root/'interactions.log'), **options))

    def test_default_all_log_methods_omit_content_and_keep_useful_diagnostics(self):
        logger = self.logger()
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            logger.log_transcription(MARKER, MARKER, model=MARKER, duration_seconds=2)
            logger.log_chat_completion(MARKER, MARKER, {'model':MARKER,'total_tokens':7})
            logger.log_complete_interaction(MARKER, MARKER, MARKER,
                                            {'total_tokens':8,'lookup':{'query':MARKER},'spoken_response':MARKER})
            logger.log_error(MARKER, {'private': MARKER})
            logger.log_error('speech failed (TimeoutError)')
        self.assertNotIn(MARKER, logger.log_file.read_text()+output.getvalue())
        rows = logger.get_log_summary()
        self.assertEqual(rows[2]['usage']['total_tokens'], 8)
        self.assertEqual(rows[-1]['failure'], {'stage':'speech','category':'TimeoutError'})
        self.assertEqual(logger.log_file.stat().st_mode & 0o777, 0o600)

    def test_opt_in_stores_content_only_in_private_file_and_disable_stops_new_content(self):
        logger = self.logger(conversation_logging=True)
        stream = io.StringIO()
        with redirect_stdout(stream), redirect_stderr(stream):
            logger.log_complete_interaction('input.wav', MARKER, MARKER, {'lookup':{'query':MARKER}})
            logger.config.conversation_logging = False
            logger.log_complete_interaction('input.wav', 'SECOND_PRIVATE', 'SECOND_PRIVATE', {})
        text = logger.log_file.read_text()
        self.assertIn(MARKER, text)
        self.assertNotIn('SECOND_PRIVATE', text)
        self.assertEqual(stream.getvalue(), '')

    def test_age_size_and_record_limits_and_abandoned_log_cleanup(self):
        path = self.root/'interactions.log'
        old = datetime.now(timezone.utc)-timedelta(days=8)
        path.write_text(json.dumps({'timestamp':old.isoformat(),'transcription':MARKER})+'\n')
        (self.root/'.interactions.log.private-abandoned').write_text(MARKER)
        logger = self.logger(conversation_logging=True, max_bytes=4096)
        self.assertNotIn(MARKER,path.read_text())
        self.assertFalse((self.root/'.interactions.log.private-abandoned').exists())
        for i in range(60):
            logger.log_chat_completion('sample '+str(i), 'x'*200, {})
            self.assertLessEqual(path.stat().st_size, 4096)
        self.assertIn('sample 59', path.read_text())
        logger.log_chat_completion(MARKER*10000, MARKER, {})
        self.assertLessEqual(path.stat().st_size, 4096)
        self.assertEqual(logger.get_log_summary()[-1]['content_omitted'], 'record_size_limit')
        with patch('rpi_assistant.app.logger.time.time', return_value=(datetime.now(timezone.utc)+timedelta(days=8)).timestamp()):
            logger.prune()
        self.assertEqual(path.read_bytes(), b'')

    def test_file_failure_does_not_break_conversation_or_echo_error_context(self):
        logger = self.logger()
        stream = io.StringIO()
        with patch.object(logger, '_replace', side_effect=OSError(MARKER)), redirect_stdout(stream):
            logger.log_chat_completion(MARKER, MARKER, {})
        self.assertIsNotNone(logger.error)
        self.assertNotIn(MARKER, stream.getvalue()+logger.error)

    def test_voice_pipeline_never_prints_content_and_cleans_audio_on_success_and_failure(self):
        fixture = test_voice_command.VoiceCommandTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        fixture.handler.logger = self.logger()
        fixture.client.transcribe_audio.return_value = MARKER
        fixture.client.get_chat_response.return_value = (MARKER, {'total_tokens':2})
        audio = self.root/'command.wav'
        for fail in (False, True):
            save_wav(str(audio), np.zeros(160,dtype=np.float32), 16000)
            fixture.output.write_bytes(b'stale')
            fixture.client.transcribe_audio.side_effect = TimeoutError(MARKER) if fail else None
            stream = io.StringIO()
            with redirect_stdout(stream), redirect_stderr(stream):
                fixture.handler.process(str(audio))
            self.assertNotIn(MARKER, stream.getvalue())
            self.assertFalse(audio.exists())
            self.assertFalse(fixture.output.exists())

    def test_audio_is_private_and_symlink_is_not_followed(self):
        path = self.root/'command.wav'
        save_wav(str(path), np.ones(160,dtype=np.float32),16000)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        other = self.root/'other';other.write_text('preserve')
        path.unlink();path.symlink_to(other)
        with self.assertRaises(OSError): save_wav(str(path),np.ones(160,dtype=np.float32),16000)
        self.assertEqual(other.read_text(),'preserve')

    def test_phone_delete_clears_memory_and_owned_files_but_keeps_household_and_keys(self):
        fixture = test_phone_setup.PhoneSetupTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        c, config = fixture.controls, fixture.config
        config.logging = LoggingConfig(log_file=str(self.root/'interactions.log'), conversation_logging=True)
        config.audio_output = replace(config.audio_output, tts_output_path=str(self.root/'reply.wav'))
        logger = InteractionLogger(config.logging)
        c.privacy = ConversationPrivacy(config,logger,c)
        c.timers = Timers(self.root/'timers.sqlite3');self.addCleanup(c.timers.close)
        c.household = Household(self.root/'household.sqlite3','UTC');self.addCleanup(c.household.close)
        c.timers.create(60,'Synthetic timer');c.household.add_item('Synthetic oats')
        c.household.create_reminder('Synthetic reminder',delay_seconds=60)
        before = fixture.path.read_bytes()
        c.client.conversation_history.append({'role':'user','content':MARKER})
        logger.log_chat_completion(MARKER,MARKER,{})
        Path(config.recording.output_path).write_text(MARKER)
        Path(config.audio_output.tts_output_path).write_text(MARKER)
        with self.assertRaises(SettingsError): c.command('privacy_delete', {'confirm':False})
        c.busy=True
        with self.assertRaises(SettingsError): c.command('privacy_delete', {'confirm':True})
        c.busy=False
        c.command('privacy_delete', {'confirm':True})
        self.assertEqual(len(c.client.conversation_history),1)
        self.assertFalse(logger.log_file.exists())
        self.assertFalse(Path(config.recording.output_path).exists())
        self.assertFalse(Path(config.audio_output.tts_output_path).exists())
        self.assertEqual(fixture.path.read_bytes(),before)
        self.assertEqual(len(c.timers.list()),1)
        self.assertEqual(len(c.household.list()),1)
        self.assertEqual(len(c.household.shopping()),1)

    def test_phone_logging_opt_in_requires_save_and_can_be_undone(self):
        fixture = test_phone_setup.PhoneSetupTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        self.assertFalse(fixture.config.logging.conversation_logging)
        fixture.apply(conversation_logging=True)
        self.assertTrue(fixture.config.logging.conversation_logging)
        fixture.controls.command('settings_undo', {'revision':fixture.settings.status()['revision']})
        self.assertFalse(fixture.config.logging.conversation_logging)

    def test_abandoned_audio_cleanup_is_scoped_and_delete_failure_is_honest(self):
        fixture = test_phone_setup.PhoneSetupTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        config = fixture.config
        config.audio_output = replace(config.audio_output,tts_output_path=str(self.root/'reply.wav'))
        privacy = ConversationPrivacy(config,self.logger(),fixture.controls)
        abandoned = self.root/'.assistant-speech-test.wav';abandoned.write_text(MARKER)
        other = self.root/'other.wav';other.write_text('keep')
        self.assertTrue(privacy.clean_audio())
        self.assertFalse(abandoned.exists())
        self.assertTrue(other.exists())
        with patch.object(privacy.logger,'delete',side_effect=PermissionError()):
            with self.assertRaisesRegex(SettingsError,'some local files'):
                privacy.delete({'confirm':True})

    def test_sdk_debug_logs_and_mcp_server_stderr_are_not_forwarded(self):
        stream = io.StringIO()
        provider = logging.getLogger('openai.synthetic')
        provider.addHandler(logging.StreamHandler(stream));provider.setLevel(logging.DEBUG)
        quiet_provider_logs()
        provider.warning(MARKER)
        self.assertNotIn(MARKER,stream.getvalue())
        code = '''from pathlib import Path
from rpi_assistant.app.config import MCPConfig,MCPServerConfig
from rpi_assistant.app.mcp_manager import MCPClientManager
import sys
m=MCPClientManager(MCPConfig(enabled=True,servers=(MCPServerConfig('test','stdio',command=sys.executable,args=(str(Path('tests/support/generic_mcp_server.py').resolve()),)),)))
try:
 m.start()
 assert 'SYNTHETIC_PRIVATE_LANTERN_493' in m.call_tool('test__echo_text',{'text':'SYNTHETIC_PRIVATE_LANTERN_493'})
 print('PASS MCP result retained without stderr leak')
finally:m.close()
'''
        result = subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,timeout=40)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertNotIn(MARKER,result.stdout+result.stderr)
