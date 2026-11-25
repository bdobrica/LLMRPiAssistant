"""Small local controls, independent of cloud recognition and speech generation."""

import json
from pathlib import Path
import re
import subprocess
import threading

from .playback import PlaybackStopped


def voice_control(text):
    """Deliberately narrow commands; quoted/incidental mentions remain ordinary chat."""
    text = text.lower().strip().rstrip('.!?').strip()
    commands = {
        "stop": ("stop", None), "stop talking": ("stop", None),
        "mute": ("mute", True), "mute the microphone": ("mute", True),
        "mute microphone": ("mute", True),
        "new conversation": ("new_conversation", None),
        "start a new conversation": ("new_conversation", None),
        "volume up": ("volume_up", None), "turn it up": ("volume_up", None),
        "volume down": ("volume_down", None), "turn it down": ("volume_down", None),
    }
    match = re.fullmatch(r'(?:set (?:the )?)?volume (?:to )?(\d{1,3})(?: percent|%)?', text)
    if match and 0 <= int(match[1]) <= 100:
        return "volume", int(match[1])
    return commands.get(text)


class MixerVolume:
    def __init__(self, config):
        self.config = config
        self.lock = threading.Lock()

    def _run(self, *arguments):
        result = subprocess.run(
            ["amixer", "-M", "-c", self.config.mixer_card, *arguments],
            capture_output=True, text=True, timeout=2, check=True,
        )
        values = re.findall(r'\[(\d+)%\]', result.stdout)
        if not values:
            raise RuntimeError("Mixer did not report a playback volume")
        return int(values[0])

    def get(self):
        with self.lock:
            return self._run("sget", self.config.mixer_control)

    def set(self, value, *, relative=False):
        with self.lock:
            if relative:
                value += self._run("sget", self.config.mixer_control)
            value = max(0, min(100, value))
            return self._run("sset", self.config.mixer_control, f"{value}%")


class LocalControls:
    def __init__(self, config, recorder, playback, client):
        self.config, self.recorder, self.playback, self.client = config, recorder, playback, client
        self.volume = MixerVolume(config)
        self.lock = threading.RLock()
        self.cancelled = threading.Event()
        self.busy = False
        self.reset_pending = False
        self.state_path = Path(config.state_path).expanduser()
        self.error = None
        self.client.cancel_check = self.check
        # Fail closed for corrupt/unreadable persisted mute settings.
        try:
            state = json.loads(self.state_path.read_text())
            if type(state.get("muted")) is not bool:
                raise ValueError("Invalid mute state")
            if state["muted"]:
                self.recorder.set_muted(True)
        except FileNotFoundError:
            pass
        except Exception:
            self.recorder.set_muted(True)
            self.error = "Mute settings could not be read; microphone remains closed."

    def begin_turn(self):
        with self.lock:
            if (self.recorder.capture_paused or self.recorder.recording_generation != self.recorder.capture_generation):
                raise PlaybackStopped()
            self.cancelled.clear()
            self.busy = True
            return self.playback.generation

    def check(self):
        if self.cancelled.is_set():
            raise PlaybackStopped()

    def end_turn(self):
        with self.lock:
            if self.reset_pending:
                self.client.reset_conversation()
                self.reset_pending = False
            self.busy = False

    def _stop(self):
        self.cancelled.set()
        self.playback.stop()
        self.recorder.cancel_capture()

    def command(self, action, value=None):
        with self.lock:
            if action == "stop":
                self._stop()
            elif action == "new_conversation":
                self._stop()
                self.reset_pending = self.busy
                if not self.busy:
                    self.client.reset_conversation()
            elif action == "mute":
                if type(value) is not bool:
                    raise ValueError("mute requires a boolean")
                self._stop()
                if not value and (self.busy or self.recorder.processing_active):
                    raise RuntimeError("Previous request is finishing; try unmute again shortly")
                # Persist intention before unmuting; failure never silently opens capture.
                # Muting closes first, even if the disk cannot save the preference.
                if value:
                    self.recorder.set_muted(True)
                self.state_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                temporary = self.state_path.with_suffix('.tmp')
                temporary.write_text(json.dumps({"muted": value}) + '\n')
                temporary.chmod(0o600)
                temporary.replace(self.state_path)
                if not value:
                    try:
                        self.recorder.set_muted(False)
                    except Exception:
                        temporary.write_text(json.dumps({"muted": True}) + "\n")
                        temporary.chmod(0o600)
                        temporary.replace(self.state_path)
                        raise
                self.error = None
            elif action in ("volume", "volume_up", "volume_down"):
                if action == "volume" and (type(value) is not int or not 0 <= value <= 100):
                    raise ValueError("volume must be an integer from 0 to 100")
                actual = self.volume.set(value if action == "volume" else (10 if action == "volume_up" else -10),
                                         relative=action != "volume")
                return f"Volume {actual} percent."
            else:
                raise ValueError("Unknown control")
        return None

    def button_press(self):
        # Preserve F02's immediate stop + contextual correction during a spoken answer.
        if not self.playback.interrupt():
            self.command("stop")

    def button_hold(self):
        try:
            self.command("mute", not self.recorder.muted)
        except Exception as exc:
            self.error = f"Microphone control failed ({type(exc).__name__}); check capture status."
            print(self.error)

    def status(self):
        with self.lock:
            stream = self.recorder.stream
            capture_active = bool(stream is not None and stream.active)
            confirmed_muted = self.recorder.muted and stream is None
            state = {
                "muted": confirmed_muted, "capture_active": capture_active,
                "state": self.recorder.state, "busy": self.busy or self.recorder.processing_active,
                "reset_pending": self.reset_pending, "error": self.error,
            }
        try:
            state["volume"] = self.volume.get()
        except Exception:
            state["volume"] = None
        return state
