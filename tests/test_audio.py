import queue
import sys
import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType

import numpy as np

sounddevice_module = ModuleType("sounddevice")
sounddevice_module.query_devices = lambda: [{"name": "fake", "max_input_channels": 1}]
sounddevice_module.InputStream = object
sys.modules.setdefault("sounddevice", sounddevice_module)

openwakeword_module = ModuleType("openwakeword")
openwakeword_module.models = {}
openwakeword_model_module = ModuleType("openwakeword.model")
openwakeword_model_module.Model = object
sys.modules.setdefault("openwakeword", openwakeword_module)
sys.modules.setdefault("openwakeword.model", openwakeword_model_module)

from rpi_assistant.app.audio import WakeWordRecorder
from rpi_assistant.app.config import AudioConfig, RecordingConfig, WakeWordConfig


class FakeWakeModel:
    models = {}


class WakeWordRecorderTests(unittest.TestCase):
    def create_recorder_shell(self, output_path: Path) -> WakeWordRecorder:
        recorder = object.__new__(WakeWordRecorder)
        recorder.audio_config = AudioConfig(sample_rate=16000, chunk_size=160, channels=1)
        recorder.recording_config = RecordingConfig(output_path=str(output_path))
        recorder.on_recording_complete = None
        recorder.pixels = None
        recorder.model = FakeWakeModel()
        recorder.state = "RECORD"
        recorder.last_wake = 0.0
        recorder.resume_listening_at = 0.0
        recorder.skip_chunks = 0
        recorder.audio_queue = queue.Queue(maxsize=1)
        recorder.recording_queue = queue.Queue(maxsize=1)
        recorder.processing_thread = None
        recorder.pre_roll = []
        recorder.rec = np.zeros(160, dtype=np.float32).tolist()
        recorder.rec_start = time.time()
        recorder.silence_run = 0.0
        recorder.device = 0
        recorder.stream = None
        recorder.running = True
        recorder.processing_drain_seconds = 0.01
        recorder.lock = threading.Lock()
        return recorder

    def test_save_recording_hands_slow_callback_to_worker(self):
        with TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "command.wav"
            callback_started = threading.Event()
            callback_finished = threading.Event()
            recorder = self.create_recorder_shell(output_path)

            def slow_callback(path: str) -> None:
                callback_started.set()
                time.sleep(0.2)
                self.assertEqual(path, str(output_path))
                callback_finished.set()

            recorder.on_recording_complete = slow_callback
            recorder.processing_thread = threading.Thread(
                target=recorder._recording_worker,
                daemon=True,
            )
            recorder.processing_thread.start()

            start = time.time()
            recorder._save_recording("timeout")
            elapsed = time.time() - start

            try:
                self.assertLess(elapsed, 0.15)
                self.assertTrue(callback_started.wait(timeout=1))
                self.assertTrue(callback_finished.wait(timeout=1))
                deadline = time.time() + 1
                while recorder.state != "LISTEN_WAKE" and time.time() < deadline:
                    time.sleep(0.01)
                self.assertEqual(recorder.state, "LISTEN_WAKE")
            finally:
                recorder.stop()

    def test_audio_callback_drops_chunks_while_processing(self):
        recorder = self.create_recorder_shell(Path("/tmp/unused.wav"))
        recorder.state = "PROCESSING"

        recorder._audio_callback(
            np.ones((160, 1), dtype=np.float32),
            frames=160,
            time_info=None,
            status=None,
        )

        self.assertEqual(recorder.audio_queue.qsize(), 0)

    def test_audio_callback_drops_when_bounded_queue_is_full(self):
        recorder = self.create_recorder_shell(Path("/tmp/unused.wav"))
        recorder.state = "LISTEN_WAKE"
        recorder.audio_queue.put_nowait(np.zeros(160, dtype=np.float32))

        recorder._audio_callback(
            np.ones((160, 1), dtype=np.float32),
            frames=160,
            time_info=None,
            status=None,
        )

        self.assertEqual(recorder.audio_queue.qsize(), 1)

    def test_recorder_uses_configured_queue_and_drain_seconds(self):
        recorder = WakeWordRecorder(
            AudioConfig(
                sample_rate=16000,
                chunk_size=160,
                channels=1,
                device_match="fake",
                queue_seconds=0.05,
            ),
            WakeWordConfig(),
            RecordingConfig(processing_drain_seconds=0.25),
        )

        try:
            self.assertEqual(recorder.audio_queue.maxsize, 5)
            self.assertEqual(recorder.processing_drain_seconds, 0.25)
        finally:
            recorder.stop()


if __name__ == "__main__":
    unittest.main()
