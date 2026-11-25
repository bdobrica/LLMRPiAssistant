"""Small local controls, independent of cloud recognition and speech generation."""

import json
from pathlib import Path
import re
import subprocess
import threading

from .playback import PlaybackStopped
from .household import HouseholdInputError
from .phone_settings import atomic_write


def voice_control(text):
    """Deliberately narrow commands; quoted/incidental mentions remain ordinary chat."""
    text = text.lower().strip().rstrip('.!?').strip()
    commands = {
        "stop": ("stop", None), "stop talking": ("stop", None),
        "mute": ("mute", True), "mute the microphone": ("mute", True),
        "mute microphone": ("mute", True),
        "mute the speaker": ("speaker_mute", True), "mute speaker": ("speaker_mute", True),
        "unmute the speaker": ("speaker_mute", False), "unmute speaker": ("speaker_mute", False),
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
        self.restore_path = Path(config.state_path).expanduser().with_suffix('.speaker.json')

    def _run(self, *arguments):
        result = subprocess.run(
            ["amixer", "-M", "-c", self.config.mixer_card, *arguments],
            capture_output=True, text=True, timeout=2, check=True,
        )
        channels = [line for line in result.stdout.splitlines()
                    if "Playback" in line and re.search(r'\[\d+%\]', line)]
        if not channels:
            raise RuntimeError("Mixer did not report a playback volume")
        levels = [int(re.search(r'\[(\d+)%\]', line)[1]) for line in channels]
        actual = max(level if '[off]' not in line else 0 for level, line in zip(levels, channels))
        raw = [re.search(r'Playback (\d+) ', line) for line in channels]
        restore = ','.join(match[1] for match in raw) if all(raw) else f'{actual}%'
        return actual, restore, any('[off]' in line for line in channels)

    def get(self):
        with self.lock:
            return self._run("sget", self.config.mixer_control)[0]

    def _remember(self, setting):
        data = [self.config.mixer_card, self.config.mixer_control, setting]
        atomic_write(self.restore_path, json.dumps(data).encode())

    def _restore_value(self):
        try:
            card, control, setting = json.loads(self.restore_path.read_text())
            if ((card, control) == (self.config.mixer_card, self.config.mixer_control)
                    and re.fullmatch(r'\d+(?:,\d+)*|\d+%', setting)):
                return setting
        except (OSError, ValueError, TypeError):
            pass
        return "25%"

    def _write(self, setting, unmute=False):
        args = [self.config.mixer_control, setting]
        if unmute:
            args.append('unmute')
        return self._run("sset", *args)[0]

    def mute(self, muted):
        with self.lock:
            current, setting, switched_off = self._run("sget", self.config.mixer_control)
            if muted == (current == 0):
                return current
            if muted:
                self._remember(setting)
                actual = self._write("0%")
            else:
                actual = self._write(self._restore_value(), switched_off)
            if muted != (actual == 0):
                raise RuntimeError("Mixer did not confirm speaker mute change")
            return actual

    def set(self, value, *, relative=False):
        with self.lock:
            current, setting, switched_off = self._run("sget", self.config.mixer_control)
            if relative:
                value += current
            value = max(0, min(100, value))
            if current and not value:
                self._remember(setting)
            return self._write(f"{value}%", bool(value and switched_off))


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
        self.timers = None
        self.household = None
        self.timer_alerts = None
        self.settings = None
        self.audio_checks = None
        self.privacy = None
        self.connection_status = lambda: None
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
            if (self.recorder.capture_paused or getattr(self.recorder, "diagnostic_active", False) or self.recorder.recording_generation != self.recorder.capture_generation):
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
        if self.audio_checks:
            self.audio_checks.stop()
        self.cancelled.set()
        self.playback.stop()
        self.recorder.cancel_capture()

    def command(self, action, value=None):
        with self.lock:
            if action == "privacy_delete":
                if self.privacy is None:
                    raise ValueError("Privacy controls unavailable")
                return self.privacy.delete(value)
            elif action in ("settings_apply", "settings_undo", "settings_advanced"):
                if self.settings is None:
                    raise ValueError("Phone settings unavailable")
                return self.settings.change(value, undo=action == "settings_undo",
                                            advanced=action == "settings_advanced")
            elif action == "audio_check":
                if self.audio_checks is None:
                    raise ValueError("Audio checks unavailable")
                return self.audio_checks.start(value)
            elif action == "stop":
                try:
                    if self.timer_alerts and self.timer_alerts.active:
                        self.timer_alerts.dismiss()
                finally:
                    self._stop()
            elif action == "reminder_create":
                if not self.household or not isinstance(value, dict):
                    raise HouseholdInputError("Reminder text and date/time are required.")
                row = self.household.create_reminder(value.get("text"), value.get("local_time", ""),
                                                     occurrence=value.get("occurrence", "unspecified"))
                return ("Reminder already scheduled for " if row["already_present"] else "Reminder scheduled for ") + row["due_local"]
            elif action == "reminder_cancel":
                if not self.household:
                    raise HouseholdInputError("Reminders are unavailable.")
                self.household.cancel(value)
                if self.timer_alerts and self.timer_alerts.active:
                    self.playback.stop()
                return "Reminder cancelled."
            elif action == "shopping_add":
                if not self.household:
                    raise HouseholdInputError("Shopping is unavailable.")
                item = self.household.add_item(value)
                return (f"{item['item']} is already on Shopping." if item['already_present']
                        else f"Added {item['item']} to Shopping.")
            elif action == "shopping_remove":
                if not self.household:
                    raise HouseholdInputError("Shopping is unavailable.")
                item = self.household.remove_item(value)
                return f"{item['item']} is no longer on Shopping."
            elif action == "timer_create":
                if not self.timers or not isinstance(value, dict):
                    raise ValueError("Timer settings are required")
                timer = self.timers.create(value.get("seconds"), value.get("label", ""))
                return f"{timer['label']} set for {timer['seconds']} seconds."
            elif action == "timer_cancel":
                if not self.timers:
                    raise ValueError("Timers are unavailable")
                self.timers.cancel(value)
                if self.timer_alerts and self.timer_alerts.active:
                    self.playback.stop()
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
            elif action == "speaker_mute":
                if type(value) is not bool:
                    raise ValueError("speaker_mute requires a boolean")
                actual = self.volume.mute(value)
                return "Speaker muted." if value else f"Speaker unmuted at {actual} percent."
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
        if self.timer_alerts and self.timer_alerts.active:
            self.command("stop")
        elif not self.playback.interrupt():
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
        if self.timers:
            try:
                state["timers"] = self.timers.list()
                state["timer_error"] = self.timer_alerts.error if self.timer_alerts else None
            except Exception:
                state["timers"] = []
                state["timer_error"] = "Timer storage is unavailable; no timer change can be confirmed."
        if self.household:
            state["timezone"] = str(self.household.zone)
            try:
                state["reminders"] = self.household.list()
                state["shopping"] = self.household.shopping()
                state["household_error"] = self.timer_alerts.reminder_error if self.timer_alerts else None
            except Exception:
                state["reminders"], state["shopping"] = [], []
                state["household_error"] = "Reminder/Shopping storage is unavailable; changes cannot be confirmed."
        state["online"] = self.connection_status()
        if self.settings:
            state["settings"] = self.settings.status()
        if self.audio_checks:
            state["audio_check"] = {"active": self.audio_checks.active, **self.audio_checks.result}
        if self.privacy:
            state["privacy"] = self.privacy.status()
        return state
