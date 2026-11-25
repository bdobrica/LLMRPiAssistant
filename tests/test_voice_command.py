import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import subprocess
import unittest
from unittest.mock import AsyncMock, Mock, patch

from rpi_assistant.app.apps.base import AppResponse
from rpi_assistant.app.config import AudioOutputConfig, OpenAIConfig, RecordingConfig
from rpi_assistant.app.playback import AudioPlayback, PlaybackInterrupted
from rpi_assistant.app.voice_command import VoiceCommandHandler


class VoiceCommandTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.output = Path(directory.name) / "reply.wav"
        self.config = NS(audio_output=AudioOutputConfig(tts_output_path=str(self.output), stream_realtime=False),
                         openai=OpenAIConfig(api_key="test"), recording=RecordingConfig())
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

    def test_game_shares_retry_limit_across_empty_and_ambiguous_answers(self):
        self.apps.handle.return_value = AppResponse("Person or dinosaur?", expect_input=True)
        self.playback.prompt.return_value = True
        self.assertTrue(self.handler.process("unused.wav"))
        self.client.transcribe_audio.return_value = ""
        self.assertTrue(self.handler.process("unused.wav", continue_conversation=True))
        self.playback.prompt.assert_called_with("game_repeat.wav")
        self.apps.handle.assert_called_once()
        self.apps.handle.return_value = AppResponse("Which one?", expect_input=True, retry_input=True)
        self.client.transcribe_audio.return_value = "Both."
        self.assertTrue(self.handler.process("unused.wav", continue_conversation=True))
        self.client.transcribe_audio.return_value = ""
        self.assertTrue(self.handler.process("unused.wav", continue_conversation=True))
        self.assertFalse(self.handler.process("unused.wav", continue_conversation=True))
        self.playback.prompt.assert_called_with("unheard.wav")
        self.assertEqual(self.apps.handle.call_count, 2)
        self.client.get_chat_response.assert_not_called()

    def test_next_game_question_gets_its_own_budget_and_exit_disarms_retry(self):
        self.config.recording.game_answer_retries = 1
        self.apps.handle.return_value = AppResponse("Question?", expect_input=True)
        self.playback.prompt.return_value = True
        for _ in range(2):
            self.client.transcribe_audio.return_value = "A person."
            self.assertTrue(self.handler.process("unused.wav", continue_conversation=True))
            self.client.transcribe_audio.return_value = " "
            self.assertTrue(self.handler.process("unused.wav", continue_conversation=True))
        self.client.transcribe_audio.return_value = "I don't want to play anymore."
        self.apps.handle.return_value = AppResponse("Stopped Trivia.", done=True)
        self.assertTrue(self.handler.process("unused.wav", continue_conversation=True))
        self.client.transcribe_audio.return_value = ""
        self.assertFalse(self.handler.process("unused.wav", continue_conversation=True))
        self.playback.prompt.assert_called_with("unheard.wav")

    def test_disabled_windows_zero_budget_or_failed_clip_do_not_reopen_listening(self):
        for seconds, retries, played in [(0, 3, True), (6, 0, True), (6, 3, False)]:
            with self.subTest(seconds=seconds, retries=retries, played=played):
                self.config.recording.follow_up_window_seconds = seconds
                self.config.recording.game_answer_retries = retries
                self.apps.handle.return_value = AppResponse("Question?", expect_input=True)
                self.client.transcribe_audio.return_value = "Play trivia"
                self.handler.process("unused.wav")
                self.client.transcribe_audio.return_value = ""
                self.playback.prompt.return_value = played
                self.playback.prompt.reset_mock()
                self.assertFalse(self.handler.process("unused.wav", continue_conversation=True))
                self.playback.prompt.assert_called_once_with("unheard.wav" if played else "game_repeat.wav")

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

    def test_stream_failure_after_app_action_uses_local_feedback_without_replay(self):
        self.config.audio_output.stream_realtime = True
        self.apps.handle.return_value = NS(text="You rolled a six.")
        self.playback.play_stream.side_effect = ConnectionError("partial output")
        self.assertFalse(self.handler.process("unused.wav"))
        self.apps.handle.assert_called_once()
        self.playback.play_stream.assert_called_once()
        self.client.remember_app_response.assert_called_once_with("What about a cube?", "You rolled a six.")
        self.playback.prompt.assert_called_once_with("request_failed.wav")
        self.client.generate_speech.assert_not_called()

    def test_stream_recovers_from_offline_and_reads_only_the_attributed_spoken_answer(self):
        self.config.audio_output.stream_realtime = True
        self.handler.is_online = lambda: False
        self.client.stream_speech = AsyncMock(side_effect=ConnectionError())
        sink = AsyncMock()
        def play(produce, **kwargs):
            asyncio.run(produce(sink))
            return True
        self.playback.play_stream.side_effect = play
        self.assertFalse(self.handler.process("unused.wav"))
        self.playback.prompt.assert_called_once_with("offline.mp3")
        self.handler.is_online = lambda: True
        self.client.stream_speech.side_effect = None
        self.client.get_chat_response.return_value = ("Answer with source URL.", {"spoken_response":"According to the source, six."})
        self.assertTrue(self.handler.process("unused.wav", continue_conversation=True))
        self.client.stream_speech.assert_awaited_with("According to the source, six.", "alloy", sink)
        self.assertEqual(self.handler.logger.log_complete_interaction.call_args.args[2], "Answer with source URL.")
        self.client.generate_speech.assert_not_called()
        self.assertFalse(self.output.exists())

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

    def test_sourced_answer_logs_links_but_speaks_the_short_attributed_version(self):
        display = "Version 3.15.2. [Python.org](https://www.python.org/downloads/)"
        spoken = "According to python.org, version 3.15.2."
        self.client.get_chat_response.return_value = (display, {"total_tokens": 2, "spoken_response": spoken})
        self.assertTrue(self.handler.process("unused.wav"))
        self.client.generate_speech.assert_called_once_with(spoken, str(self.output), "alloy")
        self.assertEqual(self.handler.logger.log_complete_interaction.call_args.args[2], display)

    def test_interrupt_keeps_completed_action_result_without_retry_or_failure_prompt(self):
        self.apps.handle.return_value = NS(text="You rolled a six.")
        self.playback.play.side_effect = PlaybackInterrupted()
        with self.assertRaises(PlaybackInterrupted):
            self.handler.process("unused.wav")
        self.apps.handle.assert_called_once_with("What about a cube?")
        self.client.generate_speech.assert_called_once()
        self.client.remember_app_response.assert_called_once_with("What about a cube?", "You rolled a six.")
        self.playback.prompt.assert_not_called()
        self.assertFalse(self.output.exists())
        self.face.set_state.assert_called_with("idle")

        self.apps.handle.return_value = None
        self.client.transcribe_audio.return_value = "Say that result more briefly."
        self.playback.play.side_effect = None
        self.assertTrue(self.handler.process("unused.wav", continue_conversation=True))
        self.assertEqual([call.args[0] for call in self.apps.handle.call_args_list],
                         ["What about a cube?", "Say that result more briefly."])
        self.client.get_chat_response.assert_called_once_with("Say that result more briefly.", continue_conversation=True)
        self.assertEqual(self.client.remember_app_response.call_count, 1)


class PlaybackTests(unittest.TestCase):
    def test_player_timeout_releases_output_for_next_prompt(self):
        player = AudioPlayback(AudioOutputConfig(device="assistant_wm8960"))
        with patch("rpi_assistant.app.playback.subprocess.Popen") as popen:
            process = popen.return_value
            process.communicate.side_effect = [subprocess.TimeoutExpired("aplay", 150), (None, b""), (None, b"")]
            process.returncode = 0
            with self.assertRaises(subprocess.TimeoutExpired):
                player.play("reply.wav", backend="realtime")
            self.assertTrue(player.prompt("request_failed.wav"))
            process.kill.assert_called_once()
            self.assertEqual(process.communicate.call_args.kwargs["timeout"], 10)
            self.assertEqual(popen.call_args.args[0][:3], ["aplay", "-D", "assistant_wm8960"])
        self.assertFalse(player.lock.locked())

    def test_disabled_playback_does_not_start_player(self):
        with patch("rpi_assistant.app.playback.subprocess.Popen") as run:
            self.assertFalse(AudioPlayback(AudioOutputConfig(enabled=False)).prompt("unheard.wav"))
            run.assert_not_called()
