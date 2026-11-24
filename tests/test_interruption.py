import subprocess
import sys
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from rpi_assistant.app.config import AudioOutputConfig, RecordingConfig
from rpi_assistant.app.interrupt_button import open_interrupt_button
from rpi_assistant.app.playback import AudioPlayback, PlaybackInterrupted


class InterruptionTests(unittest.TestCase):
    def test_actual_player_stops_once_and_queued_old_answer_cannot_resume(self):
        player = AudioPlayback(AudioOutputConfig())
        waiting = threading.Event()

        class TrackingLock:
            def __init__(self):
                self.lock = threading.Lock()
                self.calls = 0

            def acquire(self, **kwargs):
                self.calls += 1
                if self.calls == 2:
                    waiting.set()
                return self.lock.acquire(**kwargs)

            def release(self):
                self.lock.release()

        player.lock = TrackingLock()
        outcomes = {}

        def play(path):
            try:
                outcomes[path] = player.play(path, backend="realtime", interruptible=True)
            except Exception as exc:
                outcomes[path] = exc

        def command(_backend, _device, path):
            return [sys.executable, "-c", "pass" if path == "fresh" else "import time; time.sleep(30)"]

        with patch("rpi_assistant.app.playback.speech_playback_command", side_effect=command) as commands:
            active = threading.Thread(target=play, args=("active",))
            queued = threading.Thread(target=play, args=("queued",))
            active.start()
            try:
                deadline = time.monotonic() + 3
                while player._process is None and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertIsNotNone(player._process)
                queued.start()
                self.assertTrue(waiting.wait(2))
                start = time.monotonic()
                self.assertTrue(player.interrupt())
                self.assertFalse(player.interrupt())
                active.join(2)
                queued.join(2)
                self.assertFalse(active.is_alive() or queued.is_alive())
                self.assertLess(time.monotonic() - start, 2)
                self.assertIsInstance(outcomes["active"], PlaybackInterrupted)
                self.assertIsInstance(outcomes["queued"], PlaybackInterrupted)
                self.assertFalse(player.interrupt())
                self.assertTrue(player.play("fresh", backend="realtime", interruptible=True))
            finally:
                player.interrupt()
                active.join(2)
                if queued.ident is not None:
                    queued.join(2)

    def test_local_prompts_and_finished_players_are_not_interruptible(self):
        player = AudioPlayback(AudioOutputConfig())
        with patch("rpi_assistant.app.playback.subprocess.Popen") as popen:
            process = popen.return_value
            process.returncode = 0
            process.poll.return_value = None

            def communicate(**kwargs):
                self.assertFalse(player.interrupt())
                return None, b""

            process.communicate.side_effect = communicate
            self.assertTrue(player.prompt("unheard.wav"))
            process.kill.assert_not_called()
            self.assertFalse(player.interrupt())

    def test_disabled_button_does_not_import_or_claim_gpio(self):
        with patch.dict(sys.modules, {"gpiozero": None}):
            self.assertIsNone(open_interrupt_button(RecordingConfig(), Mock()))

    def test_button_is_pull_up_debounced_and_calls_only_playback_interruption(self):
        button_factory = Mock()
        playback = Mock()
        with patch.dict(sys.modules, {"gpiozero": SimpleNamespace(Button=button_factory)}):
            button = open_interrupt_button(RecordingConfig(interrupt_button_gpio=17), playback)
            button.when_pressed()
        button_factory.assert_called_once_with(17, pull_up=True, bounce_time=.1)
        playback.interrupt.assert_called_once_with()
