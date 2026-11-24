from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import subprocess
import unittest
from unittest.mock import Mock, patch

from rpi_assistant.app.config import AudioOutputConfig, OpenAIConfig
from rpi_assistant.app.playback import AudioPlayback
from rpi_assistant.app.voice_command import VoiceCommandHandler


class VoiceCommandTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.output = Path(directory.name) / "reply.wav"
        self.config = NS(audio_output=AudioOutputConfig(tts_output_path=str(self.output)),
                         openai=OpenAIConfig(api_key="test"))
        self.client = Mock()
        self.client.transcribe_audio.return_value = "What about a cube?"
        self.client.get_chat_response.return_value = ("A fresh answer.", {"total_tokens": 2})
        self.client.generate_speech.side_effect = lambda *args: self.output.write_bytes(b"new answer")
        self.apps = Mock()
        self.apps.handle.return_value = None
        self.apps.should_classify_app_intent.return_value = False
        self.playback = Mock()
        self.playback.play.return_value = True
        self.face = Mock()
        self.handler = VoiceCommandHandler(self.config, self.client, self.apps, Mock(),
                                           self.playback, self.face)

    def test_empty_transcription_plays_local_feedback_without_chat_or_action(self):
        self.client.transcribe_audio.return_value = "  "
        self.assertFalse(self.handler.process("unused.wav"))
        self.playback.prompt.assert_called_once_with("unheard.wav")
        self.apps.handle.assert_not_called()
        self.client.get_chat_response.assert_not_called()
        self.client.generate_speech.assert_not_called()

    def test_provider_failures_recover_and_next_turn_plays_only_fresh_audio(self):
        for stage in ("transcribe_audio", "get_chat_response", "generate_speech"):
            with self.subTest(stage=stage):
                self.output.write_bytes(b"stale answer")
                operation = getattr(self.client, stage)
                original = operation.side_effect
                operation.side_effect = TimeoutError("injected")
                self.playback.reset_mock()
                self.assertFalse(self.handler.process("unused.wav"))
                self.playback.play.assert_not_called()
                self.playback.prompt.assert_called_once_with("request_failed.wav")
                self.face.set_state.assert_called_with("idle")
                operation.side_effect = original

                def play(path, **kwargs):
                    self.assertEqual(Path(path).read_bytes(), b"new answer")
                    return True

                self.playback.play.side_effect = play
                self.assertTrue(self.handler.process("unused.wav", continue_conversation=True))
                self.assertFalse(self.output.exists())
                self.client.get_chat_response.assert_called_with("What about a cube?", continue_conversation=True)

    def test_partial_speech_is_removed_on_failure(self):
        def fail(*args):
            self.output.write_bytes(b"partial audio")
            raise TimeoutError()

        self.client.generate_speech.side_effect = fail
        self.assertFalse(self.handler.process("unused.wav"))
        self.assertFalse(self.output.exists())
        self.playback.play.assert_not_called()

    def test_classifier_failure_does_not_fall_through_to_chat_or_execute_action(self):
        self.apps.should_classify_app_intent.return_value = True
        self.client.classify_app_intent.side_effect = TimeoutError()
        self.assertFalse(self.handler.process("unused.wav"))
        self.client.get_chat_response.assert_not_called()
        self.apps.handle_classified_intent.assert_not_called()
        self.playback.prompt.assert_called_once_with("request_failed.wav")

    def test_known_offline_uses_existing_local_prompt(self):
        self.handler.is_online = lambda: False
        self.client.transcribe_audio.side_effect = TimeoutError()
        self.assertFalse(self.handler.process("unused.wav"))
        self.playback.prompt.assert_called_once_with("offline.mp3")

    def test_empty_answer_and_missing_speech_fail_without_stale_playback(self):
        for empty_answer in (True, False):
            with self.subTest(empty_answer=empty_answer):
                self.playback.reset_mock()
                self.output.write_bytes(b"old reply")
                self.client.get_chat_response.return_value = ("" if empty_answer else "answer", {"total_tokens": 1})
                self.client.generate_speech.side_effect = None
                self.assertFalse(self.handler.process("unused.wav"))
                self.playback.play.assert_not_called()
                self.playback.prompt.assert_called_once_with("request_failed.wav")

    def test_failed_player_and_failed_feedback_still_finish_turn(self):
        self.playback.play.side_effect = subprocess.TimeoutExpired("aplay", 150)
        self.playback.prompt.side_effect = OSError("speaker unavailable")
        self.assertFalse(self.handler.process("unused.wav"))
        self.assertFalse(self.output.exists())
        self.face.set_state.assert_called_with("idle")
        self.client.mark_response_output_finished.assert_called_once()

    def test_successful_local_action_keeps_existing_spoken_response(self):
        self.apps.handle.return_value = NS(text="You rolled a six.")
        self.assertTrue(self.handler.process("unused.wav"))
        self.client.get_chat_response.assert_not_called()
        self.client.generate_speech.assert_called_once_with("You rolled a six.", str(self.output), "alloy")


class PlaybackTests(unittest.TestCase):
    def test_player_timeout_releases_output_for_next_prompt(self):
        player = AudioPlayback(AudioOutputConfig(device="assistant_wm8960"))
        with patch("rpi_assistant.app.playback.subprocess.run") as run:
            run.side_effect = [subprocess.TimeoutExpired("aplay", 150), None]
            with self.assertRaises(subprocess.TimeoutExpired):
                player.play("reply.wav", backend="realtime")
            self.assertTrue(player.prompt("request_failed.wav"))
            self.assertEqual(run.call_args.kwargs["timeout"], 10)
            self.assertEqual(run.call_args.args[0][:3], ["aplay", "-D", "assistant_wm8960"])
        self.assertFalse(player.lock.locked())

    def test_disabled_playback_does_not_start_player(self):
        with patch("rpi_assistant.app.playback.subprocess.run") as run:
            self.assertFalse(AudioPlayback(AudioOutputConfig(enabled=False)).prompt("unheard.wav"))
            run.assert_not_called()
