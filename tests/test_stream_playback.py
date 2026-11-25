import asyncio
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from rpi_assistant.app.config import AudioOutputConfig
from rpi_assistant.app.playback import AudioPlayback, PlaybackInterrupted, PlaybackStopped, stream_playback_command


class StreamPlaybackTests(unittest.TestCase):
    def setUp(self):
        self.player = AudioPlayback(AudioOutputConfig())
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def use_player(self, script):
        self.enterContext(patch("rpi_assistant.app.playback.stream_playback_command",
                                return_value=[sys.executable, "-c", script, str(self.folder)]))

    def test_writes_before_done_preserves_order_and_waits_for_drain(self):
        self.assertIn("assistant_wm8960", stream_playback_command("assistant_wm8960"))
        self.use_player("from pathlib import Path; import sys,time; p=Path(sys.argv[1]); "
                        "f=open(p/'audio','wb',buffering=0); f.write(sys.stdin.buffer.read(2)); "
                        "f.write(sys.stdin.buffer.read()); time.sleep(.08); (p/'drained').touch()")
        async def produce(write):
            await write(b"ab")
            while not (self.folder/"audio").exists() or (self.folder/"audio").stat().st_size < 2:
                await asyncio.sleep(.01)
            await write(b"cd")
        self.assertTrue(self.player.play_stream(produce, timeout=3))
        self.assertEqual((self.folder/"audio").read_bytes(), b"abcd")
        self.assertTrue((self.folder/"drained").exists())

    def test_full_pipe_stalls_producer_and_button_cancels_provider_and_child(self):
        self.use_player("import time; time.sleep(15)")
        started, advanced, closed = threading.Event(), threading.Event(), threading.Event()
        result = []
        async def produce(write):
            try:
                await write(b"ab")
                started.set()
                await write(b"x" * 1048576)
                advanced.set()
            finally:
                closed.set()
        def run():
            with self.assertRaises(PlaybackInterrupted):
                self.player.play_stream(produce, timeout=5)
            result.append(True)
        thread = threading.Thread(target=run)
        generation = self.player.generation
        thread.start()
        try:
            self.assertTrue(started.wait(2))
            child = self.player._process
            self.assertFalse(advanced.wait(.1))
            self.assertTrue(self.player.interrupt())
            thread.join(2)
            self.assertEqual(result, [True])
            self.assertIsNotNone(child.poll())
            self.assertTrue(closed.is_set())
            with self.assertRaises(PlaybackStopped):
                self.player.play_stream(produce, expected_generation=generation)
        finally:
            self.player.stop()
            thread.join(2)

    def test_stop_while_waiting_for_first_delta_never_opens_player(self):
        started = threading.Event()
        cancelled = []
        async def produce(write):
            started.set()
            await asyncio.sleep(15)
        def run():
            try:
                self.player.play_stream(produce, timeout=5)
            except PlaybackStopped:
                cancelled.append(True)
        with patch("rpi_assistant.app.playback.subprocess.Popen") as spawn:
            thread = threading.Thread(target=run)
            thread.start()
            self.assertTrue(started.wait(2))
            self.player.stop()
            thread.join(2)
            self.assertEqual(cancelled, [True])
            spawn.assert_not_called()

    def test_empty_partial_and_stalled_stream_release_the_speaker(self):
        self.use_player("import sys; sys.stdin.buffer.read()")
        async def empty(write):
            pass
        async def partial(write):
            await write(b"ab")
            raise ConnectionError()
        async def stalled(write):
            await write(b"ab")
            await asyncio.sleep(15)
        for producer, error in ((empty, RuntimeError), (partial, ConnectionError), (stalled, TimeoutError)):
            with self.assertRaises(error):
                self.player.play_stream(producer, timeout=.2)
            self.assertIsNone(self.player._process)
            self.assertFalse(self.player.lock.locked())
