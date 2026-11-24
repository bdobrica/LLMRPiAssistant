import asyncio
import base64
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import wave

from rpi_assistant.app.config import OpenAIConfig
from rpi_assistant.app.playback import speech_playback_command
from rpi_assistant.app.realtime_speech import generate_realtime_speech


def delta(data=b"\x00\x01" * 240):
    return NS(type="response.output_audio.delta", delta=base64.b64encode(data).decode())


def done(status="completed"):
    return NS(type="response.done", response=NS(status=status, usage=None))


class RealtimeSpeechTests(unittest.TestCase):
    def render(self, directory, events, *, stall=False):
        connection = MagicMock()
        connection.session.update = AsyncMock()
        connection.response.create = AsyncMock()

        async def receive():
            for event in events:
                yield event
            if stall:
                await asyncio.sleep(10)

        connection.__aiter__.side_effect = receive
        connection_context = MagicMock()
        connection_context.__aenter__ = AsyncMock(return_value=connection)
        connection_context.__aexit__ = AsyncMock(return_value=False)
        api = MagicMock()
        api.realtime.connect.return_value = connection_context
        client_context = MagicMock()
        client_context.__aenter__ = AsyncMock(return_value=api)
        client_context.__aexit__ = AsyncMock(return_value=False)
        self.connection = connection
        self.connection_context = connection_context
        self.client_context = client_context
        with patch("rpi_assistant.app.realtime_speech.AsyncOpenAI", return_value=client_context):
            return generate_realtime_speech(
                OpenAIConfig(api_key="test", tts_timeout_seconds=0.05),
                "Read this exact answer.", str(Path(directory) / "reply.wav"), "alloy",
            )

    def test_completed_audio_is_valid_wav_and_session_closes(self):
        with TemporaryDirectory() as directory:
            self.render(directory, [delta(), done()])
            with wave.open(str(Path(directory) / "reply.wav")) as audio:
                self.assertEqual((audio.getnchannels(), audio.getsampwidth(), audio.getframerate()), (1, 2, 24000))
                self.assertEqual(audio.readframes(240), b"\x00\x01" * 240)
            self.assertEqual(len(list(Path(directory).iterdir())), 1)
        self.connection_context.__aexit__.assert_awaited_once()
        self.client_context.__aexit__.assert_awaited_once()
        response = self.connection.response.create.call_args.kwargs["response"]
        self.assertEqual(response["conversation"], "none")
        self.assertEqual(response["input"][0]["content"][0]["text"], "Read this exact answer.")
        self.assertIsNone(self.connection.session.update.call_args.kwargs["session"]["audio"]["input"]["turn_detection"])

    def test_failed_incomplete_empty_disconnected_and_bad_audio_never_publish(self):
        for events in ([delta(), done("incomplete")], [done()], [delta()],
                       [NS(type="error")], [delta(b"x"), done()],
                       [delta(b"\x00" * (24000 * 2 * 120 + 2)), done()]):
            with self.subTest(events=events[-1].type), TemporaryDirectory() as directory:
                target = Path(directory) / "reply.wav"
                target.write_bytes(b"previous completed response")
                with self.assertRaises(RuntimeError):
                    self.render(directory, events)
                self.assertEqual(target.read_bytes(), b"previous completed response")
                self.assertEqual(list(Path(directory).iterdir()), [target])
                self.connection_context.__aexit__.assert_awaited_once()

    def test_timeout_closes_session_and_discards_partial_audio(self):
        with TemporaryDirectory() as directory:
            with self.assertRaises(TimeoutError):
                self.render(directory, [delta()], stall=True)
            self.assertEqual(list(Path(directory).iterdir()), [])
        self.connection_context.__aexit__.assert_awaited_once()

    def test_playback_uses_configured_named_device_for_both_workflows(self):
        self.assertEqual(speech_playback_command("realtime", "assistant_wm8960", "reply.wav"),
                         ["aplay", "-D", "assistant_wm8960", "reply.wav"])
        self.assertEqual(speech_playback_command("speech", "assistant_wm8960", "reply.mp3"),
                         ["mpg123", "-a", "assistant_wm8960", "reply.mp3"])
