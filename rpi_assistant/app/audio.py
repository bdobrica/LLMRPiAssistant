"""Audio processing, wake word detection, and recording."""
import atexit
import queue
import threading
import time
import wave
from collections import deque
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import sounddevice as sd
from openwakeword.model import Model
from openwakeword.vad import VAD
from openwakeword import MODELS as OWW_models

from .config import AudioConfig, RecordingConfig, WakeWordConfig
from .playback import PlaybackInterrupted


def pick_input_device(match: str) -> int:
    """Find audio input device by name substring.
    
    Args:
        match: Substring to match in device name (case-insensitive).
    
    Returns:
        Device index.
    
    Raises:
        RuntimeError: If no matching device found.
    """
    match = match.lower()
    for i, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0 and match in dev["name"].lower():
            return i
    raise RuntimeError(f"No input device matching '{match}'. Check sd.query_devices().")


def float_to_int16(x: np.ndarray) -> np.ndarray:
    """Convert float32 audio [-1.0, 1.0] to int16 [-32768, 32767]."""
    x = np.clip(x, -1.0, 1.0)
    return (x * 32767.0).astype(np.int16)


def rms(x: np.ndarray) -> float:
    """Calculate root mean square of audio signal."""
    return float(np.sqrt(np.mean(x * x) + 1e-12))


def save_wav(path: str, audio_float: np.ndarray, sample_rate: int) -> None:
    """Save float32 audio to WAV file as int16.
    
    Args:
        path: Output file path.
        audio_float: Audio data in float32 format [-1.0, 1.0].
        sample_rate: Sample rate in Hz.
    """
    audio_i16 = float_to_int16(audio_float)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # int16
        wf.setframerate(sample_rate)
        wf.writeframes(audio_i16.tobytes())


class WakeWordRecorder:
    """Manages wake word detection and voice recording.
    
    States:
    - LISTEN_WAKE: Listening for wake word
    - FOLLOW_UP: Locally waiting for speech after successful playback
    - RECORD: Recording audio after wake word or follow-up speech detected
    - PROCESSING: Processing recorded audio (blocks new wake word detection)
    """

    def __init__(
        self,
        audio_config: AudioConfig,
        wake_word_config: WakeWordConfig,
        recording_config: RecordingConfig,
        on_recording_complete: Optional[Callable[[str], bool | None]] = None,
        pixels = None,
        on_state_change: Optional[Callable[[str], None]] = None,
    ):
        """Initialize wake word recorder.
        
        Args:
            audio_config: Audio device configuration.
            wake_word_config: Wake word detection configuration.
            recording_config: Recording behavior configuration.
            on_recording_complete: Callback when recording is saved. Return True after successful playback.
            pixels: Optional Pixels instance for LED feedback.
            on_state_change: Best-effort callback for lifecycle state transitions.
        """
        self.audio_config = audio_config
        self.wake_word_config = wake_word_config
        self.recording_config = recording_config
        self.on_recording_complete = on_recording_complete
        self.on_state_change = on_state_change
        self.pixels = pixels
        
        # One wake word by default keeps inference small on 512 MB boards.
        model_names = wake_word_config.models or ["hey_jarvis"]
        unknown = set(model_names) - OWW_models.keys()
        if unknown:
            raise ValueError(f"Unknown wake word model(s): {', '.join(sorted(unknown))}")
        self.model = Model(
            wakeword_models=list(model_names),
            inference_framework="tflite",
            ncpu=1,
        )

        self.follow_up_vad = None
        if recording_config.follow_up_window_seconds > 0 or recording_config.interrupt_button_gpio >= 0:
            try:
                self.follow_up_vad = VAD(
                    model_path=str(Path(__file__).resolve().parents[1] / "models/silero_vad.onnx"),
                    n_threads=1,
                )
            except Exception as exc:
                raise RuntimeError(
                    "Follow-up speech model unavailable; run make install-wakeword-models "
                    "or disable both follow-up listening and button interruption"
                ) from exc

        # State management
        self.state = "LISTEN_WAKE"
        self.last_wake = 0.0
        self.resume_listening_at = 0.0  # Timestamp when to resume listening after processing
        self.follow_up_deadline = 0.0
        self.follow_up_speech_seconds = 0.0
        self.follow_up_peak_score = 0.0
        self.recording_is_follow_up = False
        self.follow_up_cancelled = False
        self.skip_chunks = 0  # Number of chunks to skip feeding to model after resuming
        
        # Thread-safe bounded queues. Audio chunks are intentionally dropped when
        # processing falls behind instead of allowing unbounded memory growth.
        chunk_seconds = audio_config.chunk_size / audio_config.sample_rate
        queue_seconds = max(chunk_seconds, audio_config.queue_seconds)
        audio_queue_size = max(1, int(queue_seconds / chunk_seconds))
        self.audio_queue = queue.Queue(maxsize=audio_queue_size)
        self.recording_queue = queue.Queue(maxsize=1)
        self.processing_thread: Optional[threading.Thread] = None
        
        # Pre-roll buffer
        pre_roll_frames = int(recording_config.pre_roll_seconds * audio_config.sample_rate)
        if recording_config.follow_up_window_seconds > 0 or recording_config.interrupt_button_gpio >= 0:
            pre_roll_frames = max(pre_roll_frames, int(0.4 * audio_config.sample_rate))
        self.pre_roll = deque(maxlen=pre_roll_frames)
        
        # Recording buffers
        self.rec = []
        self.rec_start = 0.0
        self.silence_run = 0.0
        
        # Audio device
        self.device = pick_input_device(audio_config.device_match)
        self.stream = None
        self.running = False
        self.processing_drain_seconds = max(0.0, recording_config.processing_drain_seconds)
        
        # Thread synchronization
        self.lock = threading.RLock()
        self.stream_lock = threading.Lock()
        self.capture_paused = False
        self.muted = False
        self.capture_generation = 0
        self.recording_generation = 0
        self.processing_active = False
        self.alert_active = False
        
        # Register cleanup on exit as a safety net
        atexit.register(self.stop)
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - ensures cleanup."""
        self.stop()
        return False  # Don't suppress exceptions
    
    def start(self) -> None:
        """Start listening for wake word and recording."""
        print("Using input device:", sd.query_devices()[self.device]["name"])
        print("Loaded wakeword models:", list(self.model.models.keys()))
        print(f"Wake threshold: {self.wake_word_config.threshold}")
        print(f"Silence threshold (RMS): {self.recording_config.silence_rms_threshold}")
        print("Listening... Ctrl+C to stop.\n")
        
        if self.pixels:
            self.pixels.set_muted(self.muted)
            if not self.muted:
                self.pixels.listen()
        
        self.running = True
        self.processing_thread = threading.Thread(
            target=self._recording_worker,
            name="recording-worker",
            daemon=True,
        )
        self.processing_thread.start()
        
        try:
            with self.stream_lock:
                if not self.capture_paused:
                    self._open_stream()
                elif self.pixels:
                    self.pixels.set_muted(True)

            # Process audio chunks from queue in main thread
            while self.running:
                try:
                    # Get chunk from queue with timeout
                    mono = self.audio_queue.get(timeout=0.1)
                    self._process_chunk(mono)
                except queue.Empty:
                    self._expire_follow_up()
                    # No audio available, just continue
                    continue
        except Exception as e:
            print(f"\n❌ Audio stream error: {e}")
            raise
        finally:
            self.stop()
    
    def _open_stream(self):
        stream = sd.InputStream(
            device=self.device, channels=self.audio_config.channels,
            samplerate=self.audio_config.sample_rate, blocksize=self.audio_config.chunk_size,
            dtype="float32", callback=self._audio_callback,
        )
        self.stream = stream
        try:
            stream.start()
        except Exception:
            stream.close()
            if stream.closed:
                self.stream = None
            raise

    def set_muted(self, muted: bool):
        """Close capture, not just recognition. Never confirm mute before close succeeds."""
        with self.stream_lock:
            with self.lock:
                self.capture_paused = True
                self.follow_up_cancelled = True
                self.pre_roll.clear()
                self.rec = []
                self._clear_audio_queue()
            if self.stream is not None:
                self.stream.abort()
                self.stream.close()
                if not self.stream.closed:
                    raise RuntimeError("Microphone stream did not close")
                self.stream = None
            with self.lock:
                self.muted = True
                self.state = "MUTED"
                if self.pixels:
                    self.pixels.set_muted(True)
            if not muted:
                # Clear the closed-capture indication BEFORE PortAudio starts capture.
                # On failure restore red only if the new stream is confirmed closed.
                self.muted = False
                self.state = "OPENING"
                if self.pixels:
                    self.pixels.set_muted(False)
                try:
                    if self.running:
                        self._open_stream()
                except Exception:
                    self.muted = self.stream is None
                    self.state = "MUTED" if self.muted else "CAPTURE_ERROR"
                    if self.pixels:
                        self.pixels.set_muted(self.muted)
                        if not self.muted:
                            self.pixels.offline()
                    raise
                with self.lock:
                    self._reset_model_state()
                    self._clear_audio_queue()
                    self.muted = False
                    self.capture_paused = False
                    self.state = "ALERT" if self.alert_active else "LISTEN_WAKE"
                    self.last_wake = time.time()
                    self.skip_chunks = 30
                    if self.pixels:
                        self.pixels.set_muted(False)
                        (self.pixels.timer_alert if self.alert_active else self.pixels.listen)()

    def begin_alert(self):
        """Discard microphone input while the local chime plays; preserve real mute."""
        with self.lock:
            self.alert_active = True
            self.cancel_capture()
            if not self.capture_paused:
                self.state = "ALERT"
                if self.pixels:
                    self.pixels.timer_alert()

    def end_alert(self):
        with self.lock:
            self.alert_active = False
            self._clear_audio_queue()
            self.pre_roll.clear()
            if not self.capture_paused:
                self.state = "PROCESSING" if self.processing_active else "LISTEN_WAKE"
                self.last_wake = time.time()
                self.skip_chunks = 30  # discard chime tail, then wait for a fresh wake word
                if self.pixels:
                    self.pixels.listen()

    def cancel_capture(self):
        """Discard a partial command/follow-up; never submit it after a local stop."""
        with self.lock:
            self.capture_generation += 1
            self.follow_up_cancelled = True
            self.rec = []
            self.pre_roll.clear()
            self._clear_audio_queue()
            if self.state in ("RECORD", "FOLLOW_UP"):
                self.state = "LISTEN_WAKE"
                self.skip_chunks = 30
                if self.pixels:
                    self.pixels.listen()

    def stop(self) -> None:
        """Stop and cleanup audio stream."""
        # First, signal that we're stopping
        with self.lock:
            was_running = self.running
            self.running = False
        
        # Don't proceed if already stopped
        if not was_running and self.stream is None:
            return
        
        # Close the stream with robust error handling
        if self.stream is not None:
            try:
                if self.stream.active:
                    self.stream.stop()
            except Exception as e:
                print(f"Warning: Error stopping audio stream: {e}")
            
            try:
                self.stream.close()
            except Exception as e:
                print(f"Warning: Error closing audio stream: {e}")
            finally:
                self.stream = None
        
        # Clear audio queue
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break

        self._stop_recording_worker()
        
        # Turn off LEDs
        if self.pixels:
            self.pixels.off()
    
    def _reset_model_state(self) -> None:
        """Clear prediction and feature buffers using the installed model API."""
        try:
            self.model.reset()
        except Exception as exc:
            print(f"Wake model reset failed: {type(exc).__name__}")

    def _audio_callback(self, indata, frames, time_info, status):
        """Callback for audio stream processing."""
        try:
            if status:
                print("Audio status:", status)

            with self.lock:
                if not self.running or getattr(self, "capture_paused", False) or self.state in ("PROCESSING", "ALERT"):
                    return
            
            # Just enqueue the audio chunk - processing happens in main thread
            # Extract mono channel
            mono = indata[:, self.audio_config.mic_channel_index].copy()
            
            # Use non-blocking put with immediate drop if queue is full
            # This prevents blocking the audio callback
            try:
                self.audio_queue.put_nowait(mono)
            except queue.Full:
                # Drop frame if queue is full (overflow condition)
                pass
        except Exception as e:
            print(f"\n⚠️  Error in audio callback: {e}")
            # Don't crash the callback thread - just log and continue
    
    def _process_chunk(self, mono: np.ndarray) -> None:
        with self.lock:
            if getattr(self, "capture_paused", False) or getattr(self, "alert_active", False):
                return
            self._process_active_chunk(mono)

    def _process_active_chunk(self, mono: np.ndarray) -> None:
        """Process single audio chunk for wake word or recording.
        
        Args:
            mono: Mono audio chunk in float32 format.
        """
        with self.lock:
            current_state = self.state
            
            # Always maintain pre-roll buffer (but only when not processing)
            if current_state != "PROCESSING":
                self.pre_roll.extend(mono.tolist())
        
        if current_state == "LISTEN_WAKE":
            self._check_wake_word(mono)
        elif current_state == "FOLLOW_UP":
            self._check_follow_up(mono)
        elif current_state == "RECORD":
            self._record_audio(mono)
        # PROCESSING state: skip all processing to avoid buffer overflow
    
    def _check_wake_word(self, mono: np.ndarray) -> None:
        """Check for wake word in audio chunk.
        
        Args:
            mono: Mono audio chunk in float32 format.
        """
        with self.lock:
            if not self.running:
                return
            
            # Skip checking wake word for first N chunks after resuming
            # This lets the model's internal state flush with fresh audio
            if self.skip_chunks > 0:
                self.skip_chunks -= 1
                # Still feed to model to flush its state, but ignore predictions
                mono_i16 = float_to_int16(mono)
                self.model.predict(mono_i16)
                return
            
            queue_size = self.audio_queue.qsize()
        
        # openwakeword requires INT16 input (no lock needed for read-only operation)
        mono_i16 = float_to_int16(mono)
        preds = self.model.predict(mono_i16)
        now = time.time()
        
        for name, score in preds.items():
            if score >= self.wake_word_config.threshold:
                with self.lock:
                    if (now - self.last_wake) > self.wake_word_config.cooldown_seconds:
                        self.last_wake = now
                        print(f"\n🔥 Wakeword: {name} ({score:.3f}) [queue: {queue_size}] -> recording...")
                        if self.pixels:
                            self.pixels.wakeup()
                        self._start_recording(mono)
                        break
    
    def _start_recording(self, current_chunk: np.ndarray, *, follow_up: bool = False) -> None:
        """Start recording audio.
        
        Args:
            current_chunk: Current audio chunk to include in recording.
        
        Note: Must be called with lock held.
        """
        self.state = "RECORD"
        self.recording_is_follow_up = follow_up
        self.follow_up_cancelled = False
        self.rec_start = time.time()
        self.silence_run = 0.0
        # Seed recording with pre-roll + current chunk
        self.rec = list(self.pre_roll)
        if not follow_up:
            self.rec += current_chunk.tolist()
        self._notify_state("listening")
    
    def _record_audio(self, mono: np.ndarray) -> None:
        """Continue recording audio and check for stop conditions.
        
        Args:
            mono: Mono audio chunk in float32 format.
        """
        level = rms(mono)
        chunk_s = len(mono) / self.audio_config.sample_rate
        speech = (self._follow_up_voice(mono) if self.recording_is_follow_up
                  else level >= self.recording_config.silence_rms_threshold)
        
        with self.lock:
            self.rec.extend(mono.tolist())
            
            # Update silence tracking
            if not speech:
                self.silence_run += chunk_s
            else:
                self.silence_run = 0.0
            
            elapsed = time.time() - self.rec_start
            should_save_silence = self.silence_run >= self.recording_config.silence_hold_seconds
            should_save_timeout = elapsed >= self.recording_config.max_duration_seconds
        
        # Visual feedback during recording (outside lock to minimize hold time)
        if int(elapsed * 4) % 2 == 0:  # pulse every 0.5s
            print(
                f"🎙️  Recording... {elapsed:.1f}s "
                f"(silence: {self.silence_run:.1f}s, level: {level:.4f})\r",
                end=""
            )
        
        # Check stop conditions
        if should_save_silence:
            self._save_recording("silence")
        elif should_save_timeout:
            self._save_recording("timeout")
    
    def _save_recording(self, reason: str) -> None:
        """Save recorded audio to file and reset state.
        
        Args:
            reason: Reason for stopping recording ('silence' or 'timeout').
        """
        with self.lock:
            audio = np.array(self.rec, dtype=np.float32)
            
            # Clear recording buffers
            self.rec = []
            self.silence_run = 0.0
            
            # Set to PROCESSING state to block new wake word detection
            self.state = "PROCESSING"
            self.processing_active = True
            
            self.recording_generation = getattr(self, "capture_generation", 0)
            should_callback = self.running
        
        # File I/O outside lock to minimize hold time
        save_wav(self.recording_config.output_path, audio, self.audio_config.sample_rate)
        
        duration = len(audio) / self.audio_config.sample_rate
        print(f"\n✅ Saved {self.recording_config.output_path} ({duration:.2f}s, stop={reason})\n")
        
        # Show processing/thinking animation
        if self.pixels:
            self.pixels.think()
        self._notify_state("thinking")

        if should_callback:
            try:
                self.recording_queue.put_nowait(self.recording_config.output_path)
                return
            except queue.Full:
                print("\n⚠️  Recording worker is busy; dropping completed recording.")

        self._finish_processing()

    def _recording_worker(self) -> None:
        """Run slow recording completion work off the audio processing loop."""
        while True:
            recording_path = self.recording_queue.get()
            allow_follow_up = False
            correction = False
            try:
                if recording_path is None:
                    return

                if self.on_recording_complete:
                    try:
                        allow_follow_up = self.on_recording_complete(recording_path) is True
                    except PlaybackInterrupted:
                        correction = True
                    except Exception as e:
                        print(f"\n⚠️  Error processing recording: {e}")
            finally:
                if recording_path is not None:
                    try:
                        self._finish_processing(allow_follow_up=allow_follow_up, correction=correction)
                    finally:
                        self.processing_active = False
                self.recording_queue.task_done()

    def _finish_processing(self, *, allow_follow_up: bool = False, correction: bool = False) -> None:
        """Discard playback audio, then open a follow-up window or resume wake detection."""
        # Serialize resets with local mute/unmute and audio inference.
        with self.lock:
            if getattr(self, "capture_paused", False) or getattr(self, "alert_active", False):
                return
            self._reset_model_state()
        
        # Clear the audio queue to drop all buffered overflow chunks
        cleared = self._clear_audio_queue()
        
        print(f"Cleared {cleared} buffered audio chunks from queue.")

        window = (self.recording_config.correction_window_seconds if correction
                  else self.recording_config.follow_up_window_seconds)
        follow_up = (allow_follow_up or correction) and window > 0
        delay = (self.recording_config.follow_up_echo_guard_seconds
                 if follow_up else self.processing_drain_seconds)
        print(f"Waiting {delay:g} seconds for fresh audio...\n")
        drain_until = time.monotonic() + delay
        while time.monotonic() < drain_until:
            with self.lock:
                if not self.running or getattr(self, "capture_paused", False) or getattr(self, "alert_active", False):
                    return
            time.sleep(0.1)

        cleared = self._clear_audio_queue()

        with self.lock:
            if not self.running or getattr(self, "capture_paused", False) or getattr(self, "alert_active", False):
                return
            self.pre_roll.clear()
            if follow_up and not self.follow_up_cancelled:
                self.follow_up_vad.reset_states()
                self.follow_up_vad.prediction_buffer.clear()
                self.state = "FOLLOW_UP"
                self.follow_up_deadline = time.monotonic() + window
                self.follow_up_speech_seconds = 0.0
                self.follow_up_peak_score = 0.0
                print(f"{'Correction' if correction else 'Follow-up'} listening for {window:g} seconds.")
                if self.pixels:
                    self.pixels.follow_up()
                self._notify_state("listening")
                return
            self.state = "LISTEN_WAKE"
            self.resume_listening_at = 0.0
            self.last_wake = time.time()
            self.skip_chunks = 30

        print(
            f"\nResuming wake word detection "
            f"(cleared {cleared} chunks, skipping next 30 for model flush).\n"
        )
        if self.pixels:
            self.pixels.listen()
        self._notify_state("idle")

    def _follow_up_voice(self, mono: np.ndarray) -> bool:
        score = float(self.follow_up_vad.predict(float_to_int16(mono)))
        self.follow_up_peak_score = max(self.follow_up_peak_score, score)
        return score >= 0.5

    def _check_follow_up(self, mono: np.ndarray) -> None:
        """Use local voice activity detection; silence never creates a recording."""
        if self._expire_follow_up():
            return
        with self.lock:
            if not self.running or self.state != "FOLLOW_UP":
                return
            if self._follow_up_voice(mono):
                self.follow_up_speech_seconds += len(mono) / self.audio_config.sample_rate
            else:
                self.follow_up_speech_seconds = 0.0
            # VAD rejects noise; one normal block allows brief replies without clipping onset.
            if self.follow_up_speech_seconds >= 0.08:
                print("Follow-up speech detected -> recording...")
                self._start_recording(mono, follow_up=True)
                if self.pixels:
                    self.pixels.wakeup()

    def _expire_follow_up(self) -> bool:
        with self.lock:
            expired = self.running and self.state == "FOLLOW_UP" and time.monotonic() >= self.follow_up_deadline
        if expired:
            self.cancel_follow_up()
        return expired

    def cancel_follow_up(self) -> None:
        """Quietly return to wake listening, also before connectivity prompts play."""
        with self.lock:
            self.follow_up_cancelled = True
            if self.state != "FOLLOW_UP":
                return
            self.state = "LISTEN_WAKE"
            self.follow_up_deadline = 0.0
            self.follow_up_speech_seconds = 0.0
            self.pre_roll.clear()
            self.skip_chunks = 0
            self.last_wake = 0.0
            self._clear_audio_queue()
            if self.pixels:
                self.pixels.listen()
            self._notify_state("idle")
        print(f"Follow-up window closed; listening for wake word (peak speech score {self.follow_up_peak_score:.3f}).")

    def _notify_state(self, state: str) -> None:
        """Report a lifecycle transition without affecting audio operation."""
        if self.on_state_change is None:
            return
        try:
            self.on_state_change(state)
        except Exception as exc:
            print(f"\n⚠️  RPiFace lifecycle update skipped: {type(exc).__name__}")

    def _clear_audio_queue(self) -> int:
        cleared = 0
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
                cleared += 1
            except queue.Empty:
                break
        return cleared

    def _stop_recording_worker(self) -> None:
        worker = self.processing_thread
        if worker is None or threading.current_thread() is worker:
            return

        while not self.recording_queue.empty():
            try:
                self.recording_queue.get_nowait()
                self.recording_queue.task_done()
            except queue.Empty:
                break

        try:
            self.recording_queue.put_nowait(None)
        except queue.Full:
            pass

        worker.join(timeout=2)
        self.processing_thread = None
