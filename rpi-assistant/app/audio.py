"""Audio processing, wake word detection, and recording."""
import atexit
import queue
import threading
import time
import wave
from collections import deque
from typing import Callable, Optional

import numpy as np
import sounddevice as sd
from openwakeword.model import Model

from .config import AudioConfig, RecordingConfig, WakeWordConfig


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
    - RECORD: Recording audio after wake word detected
    - PROCESSING: Processing recorded audio (blocks new wake word detection)
    """
    
    def __init__(
        self,
        audio_config: AudioConfig,
        wake_word_config: WakeWordConfig,
        recording_config: RecordingConfig,
        on_recording_complete: Optional[Callable[[str], None]] = None,
        pixels = None,
    ):
        """Initialize wake word recorder.
        
        Args:
            audio_config: Audio device configuration.
            wake_word_config: Wake word detection configuration.
            recording_config: Recording behavior configuration.
            on_recording_complete: Callback when recording is saved. Receives file path.
            pixels: Optional Pixels instance for LED feedback.
        """
        self.audio_config = audio_config
        self.wake_word_config = wake_word_config
        self.recording_config = recording_config
        self.on_recording_complete = on_recording_complete
        self.pixels = pixels
        
        # Initialize wake word model
        if wake_word_config.models:
            self.model = Model(wakeword_models=wake_word_config.models)
        else:
            self.model = Model()  # Load all default models
        
        # State management
        self.state = "LISTEN_WAKE"
        self.last_wake = 0.0
        self.resume_listening_at = 0.0  # Timestamp when to resume listening after processing
        self.skip_chunks = 0  # Number of chunks to skip feeding to model after resuming
        
        # Thread-safe audio queue for callback -> processing thread
        self.audio_queue = queue.Queue()
        
        # Pre-roll buffer
        pre_roll_frames = int(recording_config.pre_roll_seconds * audio_config.sample_rate)
        self.pre_roll = deque(maxlen=pre_roll_frames)
        
        # Recording buffers
        self.rec = []
        self.rec_start = 0.0
        self.silence_run = 0.0
        
        # Audio device
        self.device = pick_input_device(audio_config.device_match)
        self.stream = None
        self.running = False
        
        # Thread synchronization
        self.lock = threading.Lock()
        
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
            self.pixels.listen()
        
        self.running = True
        
        try:
            self.stream = sd.InputStream(
                device=self.device,
                channels=self.audio_config.channels,
                samplerate=self.audio_config.sample_rate,
                blocksize=self.audio_config.chunk_size,
                dtype="float32",
                callback=self._audio_callback,
            )
            self.stream.start()
            
            # Process audio chunks from queue in main thread
            while self.running:
                try:
                    # Get chunk from queue with timeout
                    mono = self.audio_queue.get(timeout=0.1)
                    self._process_chunk(mono)
                except queue.Empty:
                    # No audio available, just continue
                    continue
        except Exception as e:
            print(f"\n❌ Audio stream error: {e}")
            raise
        finally:
            self.stop()
    
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
        
        # Turn off LEDs
        if self.pixels:
            self.pixels.off()
    
    def _reset_model_state(self) -> None:
        """Reset openwakeword model internal state to clear buffers."""
        try:
            # Reset prediction state for all models
            for model in self.model.models.values():
                if hasattr(model, 'prediction_buffer'):
                    model.prediction_buffer.reset()
        except Exception:
            # If reset fails, just continue - not critical
            pass
    
    def _audio_callback(self, indata, frames, time_info, status):
        """Callback for audio stream processing."""
        try:
            if status:
                print("Audio status:", status)
            
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
        """Process single audio chunk for wake word or recording.
        
        Args:
            mono: Mono audio chunk in float32 format.
        """
        with self.lock:
            current_state = self.state
            
            # Auto-transition from PROCESSING to LISTEN_WAKE after drain period
            if current_state == "PROCESSING" and time.time() >= self.resume_listening_at:
                # Clear queue one more time right before resuming to ensure fresh audio
                cleared = 0
                while not self.audio_queue.empty():
                    try:
                        self.audio_queue.get_nowait()
                        cleared += 1
                    except queue.Empty:
                        break
                
                self.state = "LISTEN_WAKE"
                current_state = "LISTEN_WAKE"
                # Skip feeding 30 chunks to model to flush its internal prediction buffers
                # This allows the model's sliding window state to fill with fresh audio
                self.skip_chunks = 30
                print(f"\nResuming wake word detection (cleared {cleared} chunks, skipping next 30 for model flush).\n")
                if self.pixels:
                    self.pixels.listen()
            
            # Always maintain pre-roll buffer (but only when not processing)
            if current_state != "PROCESSING":
                self.pre_roll.extend(mono.tolist())
        
        if current_state == "LISTEN_WAKE":
            self._check_wake_word(mono)
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
    
    def _start_recording(self, current_chunk: np.ndarray) -> None:
        """Start recording audio.
        
        Args:
            current_chunk: Current audio chunk to include in recording.
        
        Note: Must be called with lock held.
        """
        self.state = "RECORD"
        self.rec_start = time.time()
        self.silence_run = 0.0
        # Seed recording with pre-roll + current chunk
        self.rec = list(self.pre_roll) + current_chunk.tolist()
    
    def _record_audio(self, mono: np.ndarray) -> None:
        """Continue recording audio and check for stop conditions.
        
        Args:
            mono: Mono audio chunk in float32 format.
        """
        level = rms(mono)
        chunk_s = len(mono) / self.audio_config.sample_rate
        
        with self.lock:
            self.rec.extend(mono.tolist())
            
            # Update silence tracking
            if level < self.recording_config.silence_rms_threshold:
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
            
            should_callback = self.running
        
        # File I/O outside lock to minimize hold time
        save_wav(self.recording_config.output_path, audio, self.audio_config.sample_rate)
        
        duration = len(audio) / self.audio_config.sample_rate
        print(f"\n✅ Saved {self.recording_config.output_path} ({duration:.2f}s, stop={reason})\n")
        
        # Show processing/thinking animation
        if self.pixels:
            self.pixels.think()
        
        # Trigger callback if provided (only if still running)
        # This may take several seconds (OpenAI API call)
        if should_callback and self.on_recording_complete:
            try:
                self.on_recording_complete(self.recording_config.output_path)
            except Exception as e:
                print(f"\n⚠️  Error processing recording: {e}")
                # Continue with cleanup even if callback fails
        
        # Reset model state to clear any buffered audio from overflow
        self._reset_model_state()
        
        # Clear the audio queue to drop all buffered overflow chunks
        cleared = 0
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
                cleared += 1
            except queue.Empty:
                break
        
        print(f"Cleared {cleared} buffered audio chunks from queue.")
        
        with self.lock:
            if self.running:
                # Stay in PROCESSING state for 3 seconds
                # This gives time for a few fresh chunks to accumulate
                self.resume_listening_at = time.time() + 3.0
                self.last_wake = time.time()
        
        # Visual indicator
        print("Waiting 3 seconds for fresh audio...\n")
