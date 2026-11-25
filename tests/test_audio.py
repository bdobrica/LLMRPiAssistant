import queue
import sys
import threading
import time
import unittest
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType
from collections import deque
from dataclasses import replace

import numpy as np

sounddevice_module = ModuleType("sounddevice")
sounddevice_module.query_devices = lambda: [{"name": "fake", "max_input_channels": 1}]
sounddevice_module.InputStream = object
sys.modules.setdefault("sounddevice", sounddevice_module)

openwakeword_module = ModuleType("openwakeword")
openwakeword_module.MODELS = {"hey_jarvis": {}, "alexa": {}}
openwakeword_model_module = ModuleType("openwakeword.model")
openwakeword_model_module.Model = lambda **kwargs: object()
sys.modules.setdefault("openwakeword", openwakeword_module)
sys.modules.setdefault("openwakeword.model", openwakeword_model_module)

class FakeSpeechVAD:
    def __init__(self, **kwargs):
        self.prediction_buffer = deque()

    def reset_states(self):
        pass

    def predict(self, audio):
        return 0.9 if np.mean(np.abs(audio)) > 1000 else 0.0


openwakeword_vad_module = ModuleType("openwakeword.vad")
openwakeword_vad_module.VAD = FakeSpeechVAD
sys.modules.setdefault("openwakeword.vad", openwakeword_vad_module)

from rpi_assistant.app.audio import WakeWordRecorder
from rpi_assistant.app.config import AudioConfig, RecordingConfig, WakeWordConfig
from rpi_assistant.app.playback import PlaybackInterrupted


class FakeWakeModel:
    models = {}

    def reset(self):
        pass

    def predict(self, audio):
        return {"hey_jarvis": 1.0}


class WakeWordRecorderTests(unittest.TestCase):
    def test_default_loads_only_one_model_with_modern_api(self):
        with patch("rpi_assistant.app.audio.Model") as model:
            recorder = WakeWordRecorder(AudioConfig(device_match="fake"), WakeWordConfig(), RecordingConfig())
        model.assert_called_once_with(wakeword_models=["hey_jarvis"], inference_framework="tflite", ncpu=1)
        recorder.stop()

    def test_configured_model_selection_is_preserved(self):
        with patch("rpi_assistant.app.audio.Model") as model:
            recorder = WakeWordRecorder(AudioConfig(device_match="fake"), WakeWordConfig(models=["alexa"]), RecordingConfig())
        model.assert_called_once_with(wakeword_models=["alexa"], inference_framework="tflite", ncpu=1)
        recorder.stop()

    def test_unknown_model_does_not_silently_load_defaults(self):
        with patch("rpi_assistant.app.audio.Model") as model:
            with self.assertRaisesRegex(ValueError, "Unknown wake word"):
                WakeWordRecorder(AudioConfig(), WakeWordConfig(models=["typo"]), RecordingConfig())
        model.assert_not_called()

    def test_disabled_followup_does_not_load_speech_model(self):
        with patch("rpi_assistant.app.audio.Model"), patch("rpi_assistant.app.audio.VAD") as vad:
            recorder = WakeWordRecorder(
                AudioConfig(device_match="fake"), WakeWordConfig(),
                RecordingConfig(follow_up_window_seconds=0),
            )
        vad.assert_not_called()
        recorder.stop()

    def test_button_loads_speech_detector_when_normal_followup_is_disabled(self):
        with patch("rpi_assistant.app.audio.Model"), patch("rpi_assistant.app.audio.VAD") as vad:
            recorder = WakeWordRecorder(AudioConfig(device_match="fake"), WakeWordConfig(),
                                        RecordingConfig(follow_up_window_seconds=0, interrupt_button_gpio=17))
        vad.assert_called_once()
        recorder.stop()

    def create_recorder_shell(self, output_path: Path) -> WakeWordRecorder:
        recorder = object.__new__(WakeWordRecorder)
        recorder.audio_config = AudioConfig(sample_rate=16000, chunk_size=160, channels=1)
        recorder.recording_config = RecordingConfig(output_path=str(output_path))
        recorder.wake_word_config = WakeWordConfig()
        recorder.on_recording_complete = None
        recorder.on_state_change = None
        recorder.pixels = None
        recorder.model = FakeWakeModel()
        recorder.state = "RECORD"
        recorder.last_wake = 0.0
        recorder.resume_listening_at = 0.0
        recorder.skip_chunks = 0
        recorder.follow_up_deadline = 0.0
        recorder.follow_up_speech_seconds = 0.0
        recorder.follow_up_peak_score = 0.0
        recorder.recording_is_follow_up = False
        recorder.follow_up_cancelled = False
        recorder.follow_up_vad = FakeSpeechVAD()
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
        recorder.lock = threading.RLock()
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

    def test_lifecycle_hooks_run_outside_audio_callback(self):
        recorder = self.create_recorder_shell(Path("/tmp/unused.wav"))
        states = []
        recorder.on_state_change = states.append

        recorder._audio_callback(
            np.ones((160, 1), dtype=np.float32),
            frames=160,
            time_info=None,
            status=None,
        )
        self.assertEqual(states, [])

        with recorder.lock:
            recorder._start_recording(np.ones(160, dtype=np.float32))
        self.assertEqual(states, ["listening"])

    def follow_up_recorder(self, path):
        recorder = self.create_recorder_shell(path)
        recorder.state = "PROCESSING"
        recorder.processing_drain_seconds = 0
        recorder.recording_config = replace(recorder.recording_config, follow_up_echo_guard_seconds=0)
        recorder.pre_roll = deque(maxlen=6400)
        recorder.audio_config = AudioConfig(sample_rate=16000, chunk_size=1280, channels=1)
        return recorder

    def test_successful_playback_opens_window_and_discards_stale_audio(self):
        recorder = self.follow_up_recorder(Path("/tmp/unused.wav"))
        recorder.pre_roll.extend([0.9] * 1280)
        recorder.audio_queue.put(np.ones(1280, dtype=np.float32))
        with patch("rpi_assistant.app.audio.time.monotonic", return_value=100):
            recorder._finish_processing(allow_follow_up=True)
        self.assertEqual(recorder.state, "FOLLOW_UP")
        self.assertEqual(recorder.follow_up_deadline, 106)
        self.assertEqual(list(recorder.pre_roll), [])
        self.assertTrue(recorder.audio_queue.empty())

    def test_zero_configured_preroll_still_keeps_followup_onset(self):
        with patch("rpi_assistant.app.audio.Model", return_value=FakeWakeModel()):
            recorder = WakeWordRecorder(
                AudioConfig(device_match="fake", chunk_size=1280), WakeWordConfig(),
                RecordingConfig(pre_roll_seconds=0, follow_up_echo_guard_seconds=0),
            )
        recorder.running = True
        recorder.state = "PROCESSING"
        try:
            recorder._finish_processing(allow_follow_up=True)
            speech = np.full(1280, 0.2, dtype=np.float32)
            recorder._process_chunk(speech)
            recorder._process_chunk(speech)
            self.assertEqual(recorder.state, "RECORD")
            np.testing.assert_array_equal(recorder.rec, np.concatenate([speech, speech]))
        finally:
            recorder.stop()

    def test_steady_room_noise_does_not_trigger_and_ends_followup_speech(self):
        with TemporaryDirectory() as directory:
            recorder = self.follow_up_recorder(Path(directory) / "command.wav")
            recorder._finish_processing(allow_follow_up=True)
            noise = np.full(1280, 0.015, dtype=np.float32)
            for _ in range(10):
                recorder._process_chunk(noise)
            self.assertEqual(recorder.state, "FOLLOW_UP")
            self.assertTrue(recorder.recording_queue.empty())
            for _ in range(2):
                recorder._process_chunk(np.full(1280, 0.2, dtype=np.float32))
            self.assertEqual(recorder.state, "RECORD")
            for _ in range(11):
                recorder._process_chunk(noise)
                if recorder.state == "PROCESSING":
                    break
            self.assertEqual(recorder.state, "PROCESSING")
            self.assertEqual(recorder.recording_queue.qsize(), 1)

    def test_silence_expires_without_file_or_callback_and_fresh_wake_works(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "command.wav"
            recorder = self.follow_up_recorder(path)
            recorder._finish_processing(allow_follow_up=True)
            recorder._process_chunk(np.zeros(1280, dtype=np.float32))
            self.assertEqual(recorder.state, "FOLLOW_UP")
            with patch("rpi_assistant.app.audio.time.monotonic", return_value=recorder.follow_up_deadline):
                recorder._expire_follow_up()
            self.assertEqual(recorder.state, "LISTEN_WAKE")
            self.assertFalse(path.exists())
            self.assertTrue(recorder.recording_queue.empty())
            recorder._process_chunk(np.ones(1280, dtype=np.float32))
            self.assertEqual(recorder.state, "RECORD")
            self.assertFalse(recorder.recording_is_follow_up)

    def test_short_click_is_ignored_and_speech_preserves_first_samples(self):
        recorder = self.follow_up_recorder(Path("/tmp/unused.wav"))
        recorder._finish_processing(allow_follow_up=True)
        click = np.zeros(1280, dtype=np.float32)
        click[0] = 1.0
        recorder._process_chunk(click)
        recorder._process_chunk(np.zeros(1280, dtype=np.float32))
        self.assertEqual(recorder.state, "FOLLOW_UP")
        first = np.full(1280, 0.2, dtype=np.float32)
        second = np.full(1280, 0.3, dtype=np.float32)
        recorder._process_chunk(first)
        recorder._process_chunk(second)
        self.assertEqual(recorder.state, "RECORD")
        self.assertTrue(recorder.recording_is_follow_up)
        np.testing.assert_array_equal(recorder.rec[-2560:], np.concatenate([first, second]))
        self.assertEqual(len(recorder.rec), 5120)  # no duplicated onset block

    def test_brief_reply_with_one_confident_block_is_captured(self):
        with TemporaryDirectory() as directory:
            recorder = self.follow_up_recorder(Path(directory) / "command.wav")
            recorder._finish_processing(allow_follow_up=True)
            recorder._process_chunk(np.full(1280, 0.2, dtype=np.float32))
            self.assertEqual(recorder.state, "RECORD")
            for _ in range(11):
                recorder._process_chunk(np.zeros(1280, dtype=np.float32))
                if recorder.state == "PROCESSING":
                    break
            self.assertEqual(recorder.recording_queue.qsize(), 1)

    def test_started_followup_finishes_even_after_window_deadline(self):
        with TemporaryDirectory() as directory:
            recorder = self.follow_up_recorder(Path(directory) / "command.wav")
            recorder._finish_processing(allow_follow_up=True)
            for _ in range(2):
                recorder._process_chunk(np.full(1280, 0.1, dtype=np.float32))
            with patch("rpi_assistant.app.audio.time.monotonic", return_value=recorder.follow_up_deadline + 1):
                for _ in range(11):
                    recorder._process_chunk(np.zeros(1280, dtype=np.float32))
                    if recorder.state == "PROCESSING":
                        break
            self.assertEqual(recorder.state, "PROCESSING")
            self.assertTrue(Path(directory, "command.wav").exists())
            self.assertEqual(recorder.recording_queue.qsize(), 1)

    def test_disabled_or_failed_playback_returns_to_normal_wake_flow(self):
        for seconds, successful in ((0, True), (6, False)):
            recorder = self.follow_up_recorder(Path("/tmp/unused.wav"))
            recorder.recording_config = replace(recorder.recording_config, follow_up_window_seconds=seconds)
            recorder._finish_processing(allow_follow_up=successful)
            self.assertEqual(recorder.state, "LISTEN_WAKE")
            self.assertEqual(recorder.skip_chunks, 30)

    def test_echo_guard_drops_input_until_window_opens(self):
        recorder = self.follow_up_recorder(Path("/tmp/unused.wav"))
        recorder.recording_config = replace(recorder.recording_config, follow_up_echo_guard_seconds=0.1)
        observed = []

        def during_guard(_seconds):
            observed.append(recorder.state)
            recorder._audio_callback(np.ones((1280, 1), dtype=np.float32), 1280, None, None)
            self.assertTrue(recorder.audio_queue.empty())

        with patch("rpi_assistant.app.audio.time.monotonic", side_effect=[0, 0, 1, 1]), \
             patch("rpi_assistant.app.audio.time.sleep", side_effect=during_guard):
            recorder._finish_processing(allow_follow_up=True)
        self.assertEqual(observed, ["PROCESSING"])
        self.assertEqual(recorder.state, "FOLLOW_UP")

    def test_connectivity_prompt_cancels_pending_and_open_followup(self):
        for already_open in (False, True):
            recorder = self.follow_up_recorder(Path("/tmp/unused.wav"))
            if already_open:
                recorder._finish_processing(allow_follow_up=True)
            recorder.cancel_follow_up()
            if not already_open:
                recorder._finish_processing(allow_follow_up=True)
            self.assertEqual(recorder.state, "LISTEN_WAKE")

    def test_worker_waits_for_successful_callback_before_opening_window(self):
        recorder = self.follow_up_recorder(Path("/tmp/unused.wav"))
        started, release = threading.Event(), threading.Event()

        def playback(_path):
            started.set()
            release.wait(timeout=1)
            return True

        recorder.on_recording_complete = playback
        recorder.processing_thread = threading.Thread(target=recorder._recording_worker, daemon=True)
        recorder.processing_thread.start()
        recorder.recording_queue.put("/tmp/unused.wav")
        try:
            self.assertTrue(started.wait(timeout=1))
            self.assertEqual(recorder.state, "PROCESSING")
            release.set()
            recorder.recording_queue.join()
            self.assertEqual(recorder.state, "FOLLOW_UP")
        finally:
            release.set()
            recorder.stop()

    def test_interrupt_opens_correction_window_without_replaying_callback(self):
        recorder = self.follow_up_recorder(Path("/tmp/unused.wav"))
        recorder.recording_config = replace(recorder.recording_config, follow_up_window_seconds=0,
                                            interrupt_button_gpio=17, correction_window_seconds=2)
        calls = []

        def interrupted(path):
            calls.append(path)
            raise PlaybackInterrupted()

        recorder.on_recording_complete = interrupted
        recorder.processing_thread = threading.Thread(target=recorder._recording_worker, daemon=True)
        recorder.processing_thread.start()
        recorder.recording_queue.put("/tmp/unused.wav")
        try:
            recorder.recording_queue.join()
            self.assertEqual(calls, ["/tmp/unused.wav"])
            self.assertEqual(recorder.state, "FOLLOW_UP")
            self.assertLessEqual(recorder.follow_up_deadline - time.monotonic(), 2)
            recorder._check_follow_up(np.ones(1280, dtype=np.float32) * 0.2)
            self.assertEqual(recorder.state, "RECORD")
            self.assertTrue(recorder.recording_is_follow_up)
        finally:
            recorder.stop()


if __name__ == "__main__":
    unittest.main()
