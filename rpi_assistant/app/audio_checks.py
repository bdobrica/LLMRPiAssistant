"""Explicit local audio checks; no recognition, cloud call or retained recording."""

from pathlib import Path
from tempfile import TemporaryDirectory
import threading

import numpy as np

from .audio import save_wav
from .phone_settings import SettingsError
from .playback import PlaybackStopped


class AudioChecks:
    def __init__(self, controls):
        self.controls = controls
        self.cancelled = threading.Event()
        self.active = False
        self.result = {"state": "idle", "message": "Choose a local microphone or speaker check."}
        self.thread = None

    def stop(self):
        if self.active:
            self.cancelled.set()

    def start(self, kind):
        c = self.controls
        if kind not in ("microphone", "speaker"):
            raise SettingsError("Choose microphone or speaker.")
        if self.active or c.busy or c.recorder.processing_active or c.recorder.alert_active or c.recorder.state == "RECORD":
            raise SettingsError("Wait for the current request, alert or audio check to finish.")
        if kind == "microphone" and (c.recorder.capture_paused or c.recorder.stream is None or not c.recorder.stream.active):
            raise SettingsError("Unmute an available microphone before recording a check.")
        c._stop()
        c.recorder.begin_diagnostic(kind == "microphone")
        self.cancelled.clear()
        self.active = True
        self.result = {"state": "recording" if kind == "microphone" else "playing",
                       "message": "Speak now for three seconds; then listen to the playback." if kind == "microphone" else "Playing the local test sound. Check that you can hear it clearly."}
        generation = c.playback.generation
        self.thread = threading.Thread(target=self._run, args=(kind, generation), name="audio-check", daemon=True)
        self.thread.start()
        return self.result["message"]

    def _run(self, kind, generation):
        c = self.controls
        result = None
        try:
            if kind == "microphone":
                if self.cancelled.wait(3.1):
                    raise PlaybackStopped()
                audio = c.recorder.take_diagnostic_audio()
                rate = c.recorder.audio_config.sample_rate
                if len(audio) < rate * 2.5:
                    raise RuntimeError("Capture did not supply enough samples")
                peak = float(np.max(np.abs(audio)))
                level = float(np.sqrt(np.mean(audio * audio)))
                with c.lock:
                    self.result = {"state": "playing", "message": "Playing your microphone check back locally."}
                with TemporaryDirectory(prefix="assistant-mic-check-") as directory:
                    path = Path(directory) / "check.wav"
                    save_wav(str(path), audio, rate)
                    path.chmod(0o600)
                    if self.cancelled.is_set():
                        raise PlaybackStopped()
                    if not c.playback.play(str(path), backend="realtime", timeout=8, expected_generation=generation):
                        raise RuntimeError("Playback disabled")
                message = ("Very little sound was detected. Try speaking closer to the microphone." if peak < .01 else
                           "The microphone signal clipped. Try speaking further away." if peak >= .99 else
                           "Recording and playback completed. Was your voice clear? This does not test speech recognition.")
                result = {"state": "complete", "message": message, "peak": round(peak, 4), "rms": round(level, 4)}
            else:
                if not c.playback.prompt("timer.wav", expected_generation=generation):
                    raise RuntimeError("Playback disabled")
                result = {"state": "complete", "message": "Test sound finished. Confirm it was audible; playback success alone cannot confirm speaker wiring or volume."}
            if self.cancelled.is_set():
                raise PlaybackStopped()
        except PlaybackStopped:
            result = {"state": "cancelled", "message": "Audio check stopped; its recording was discarded."}
        except Exception:
            result = {"state": "error", "message": "Audio check failed. Check microphone availability, speaker volume and wiring, then retry."}
        finally:
            with c.lock:
                try:
                    c.recorder.end_diagnostic()
                except Exception:
                    result = {"state": "error", "message": "Audio check ended, but restoring listening failed. Check capture status."}
                finally:
                    self.result = result
                    self.active = False

    def close(self):
        self.stop()
        if self.active:
            self.controls.playback.stop()
        if self.thread:
            self.thread.join(timeout=5)
