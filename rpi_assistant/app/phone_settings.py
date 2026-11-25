"""Live phone settings and authenticated, restartable INI changes."""

from collections import deque
from configparser import ConfigParser
from dataclasses import replace
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import signal
import tempfile
import threading
from zoneinfo import ZoneInfo

from openai import OpenAI
from .weather import Weather
from .config import parse_config
from .config_editor import (EditorError as SettingsError, GROUPS, candidate, describe,
                            read_ini, server_options)
from .settings_trial import SettingsTrial


FIELDS = {
    "conversation_logging": ("logging", "conversation_logging"),
    "follow_up_seconds": ("recording", "follow_up_window_seconds"),
    "reminder_timezone": ("household", "timezone"),
    "weather_city": ("weather", "city"),
    "openai_key": ("openai", "api_key"),
    "weather_key": ("weather", "api_key"),
    "ipgeolocation_key": ("weather", "ipgeolocation_api_key"),
    "weather_latitude": ("weather", "latitude"),
    "weather_longitude": ("weather", "longitude"),
    "weather_timezone": ("weather", "timezone"),
}
SECRET_FIELDS = {"openai_key", "weather_key", "ipgeolocation_key"}
PUBLIC_FIELDS = set(FIELDS) - {"weather_latitude", "weather_longitude", "weather_timezone"}


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix=".phone-settings-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as target:
            target.write(data)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def revision(data):
    return hashlib.sha256(data if data is not None else b"<absent>").hexdigest()


class PhoneSettings:
    def __init__(self, config, path, controls):
        self.config, self.path, self.controls = config, Path(path), controls
        self.backup = self.path.with_name(self.path.name + ".phone-undo.json")
        self.trial = SettingsTrial(self.path)
        self.error = None

    def options(self):
        with self.controls.lock:
            before = self._read()
            parser = read_ini(before)
            undo = json.loads(self.backup.read_bytes()) if self.backup.exists() else {}
            return {"options": describe(parser), "groups": GROUPS, "revision": revision(before),
                    "live": list(FIELDS.values()), "server": server_options(parser, "mcp.server."),
                    "undo_restart": bool(undo.get("restart")),
                    "undo_groups": sorted({s for s, _ in undo.get("fields", [])}),
                    "can_undo": self.status()["can_undo"]}

    def _restart(self, before, after, fields, undo=False):
        if not os.environ.get("INVOCATION_ID") or not os.environ.get("CREDENTIALS_DIRECTORY"):
            raise SettingsError("Restart changes need the installed systemd service. Reinstall the service and try again.")
        config = self.trial.arm(before, after, fields, undo=undo)
        # Exit after sending the HTTP acknowledgement. Restart=on-failure relaunches
        # the service without granting it systemctl privileges.
        timer = threading.Timer(1, os.kill, args=(os.getpid(), signal.SIGUSR1))
        timer.daemon = True
        timer.start()
        if not config.controls.enabled:
            destination = "Phone controls will close."
        elif config.controls.host in ("lan", "0.0.0.0"):
            destination = f"Reconnect at the device IP on port {config.controls.port}."
        else:
            destination = f"Configured address: http://{config.controls.host}:{config.controls.port}/."
        return f"Restart requested. {destination} Failed startup restores the previous settings."

    def _read(self):
        try:
            return self.path.read_bytes()
        except FileNotFoundError:
            return None

    def _values(self):
        c = self.config
        return {
            "conversation_logging": c.logging.conversation_logging,
            "follow_up_seconds": c.recording.follow_up_window_seconds,
            "reminder_timezone": c.household.timezone, "weather_city": c.weather.city,
            "openai_key": c.openai.api_key, "weather_key": c.weather.api_key,
            "ipgeolocation_key": c.weather.ipgeolocation_api_key,
            "weather_latitude": c.weather.latitude, "weather_longitude": c.weather.longitude,
            "weather_timezone": c.weather.timezone,
        }

    def status(self):
        with self.controls.lock:
            values = self._values()
            status = {key: value for key, value in values.items() if key in PUBLIC_FIELDS - SECRET_FIELDS}
            status["keys_configured"] = {key: bool(values[key]) for key in SECRET_FIELDS}
            try:
                status["revision"] = revision(self._read())
                saved = json.loads(self.backup.read_text()) if self.backup.exists() else {}
                status["can_undo"] = saved.get("applied_revision") == status["revision"]
            except Exception:
                status.update(revision=None, can_undo=False)
            status["error"] = self.error
            if self.trial.journal.exists():
                status["restart_status"] = "Testing settings during restart."
            elif self.trial.result.exists():
                status["restart_status"] = self.trial.result.read_text()
            location = self.controls.client.weather.location
            saved = location.resolved or (location._load() if not self.config.weather.city else None)
            status["weather_location"] = saved["name"] if saved else None
            return status

    def _validate(self, payload):
        if not isinstance(payload, dict) or set(payload) - (PUBLIC_FIELDS | {"revision", "clear_weather_key", "clear_ipgeolocation_key"}):
            raise SettingsError("Unsupported settings. Reload the page and try again.")
        values = self._values()
        for key in PUBLIC_FIELDS:
            if key in payload:
                value = payload[key]
                if key in SECRET_FIELDS:
                    if value == "":
                        continue  # A blank input never erases a key.
                    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9._-]{8,512}", value):
                        raise SettingsError("A provider key has an invalid format. Paste the key without spaces.")
                values[key] = value
        for key in ("weather_key", "ipgeolocation_key"):
            clear = payload.get("clear_" + key, False)
            if type(clear) is not bool:
                raise SettingsError("Invalid key removal choice.")
            if clear:
                if payload.get(key):
                    raise SettingsError("Choose either replacing or removing that key.")
                values[key] = ""
        seconds = values["follow_up_seconds"]
        if type(values["conversation_logging"]) is not bool:
            raise SettingsError("Conversation logging must be explicitly enabled or disabled.")
        if type(seconds) not in (int, float) or not math.isfinite(seconds) or not 0 <= seconds <= 15:
            raise SettingsError("Follow-up listening must be between 0 and 15 seconds; zero disables it.")
        try:
            ZoneInfo(values["reminder_timezone"])
        except Exception:
            raise SettingsError("Use an IANA reminder timezone, for example Europe/Bucharest.") from None
        city = values["weather_city"]
        if not isinstance(city, str) or len(city) > 160 or any(ord(char) < 32 for char in city):
            raise SettingsError("Enter a city and country on one line, up to 160 characters.")
        values["weather_city"] = city.strip()
        if values["weather_city"] != self.config.weather.city:
            for key in ("weather_latitude", "weather_longitude", "weather_timezone"):
                values[key] = ""
        return values

    def _prepare(self, values):
        c = self.config
        sdk = self.controls.client.client
        if values["openai_key"] != c.openai.api_key:
            sdk = OpenAI(api_key=values["openai_key"] or "not-configured",
                         timeout=c.openai.request_timeout_seconds, max_retries=0)
        try:
            weather = Weather(replace(c.weather, city=values["weather_city"], api_key=values["weather_key"],
                                      ipgeolocation_api_key=values["ipgeolocation_key"],
                                      latitude=values["weather_latitude"], longitude=values["weather_longitude"],
                                      timezone=values["weather_timezone"]))
            zone = ZoneInfo(values["reminder_timezone"])
            vad = self.controls.recorder.prepare_follow_up(values["follow_up_seconds"])
            return sdk, weather, zone, vad
        except Exception:
            if sdk is not self.controls.client.client:
                sdk.close()
            raise

    def _install(self, values, prepared):
        sdk, weather, zone, vad = prepared
        c, controls = self.config, self.controls
        c.recording.follow_up_window_seconds = values["follow_up_seconds"]
        c.logging.conversation_logging = values["conversation_logging"]
        c.household.timezone = values["reminder_timezone"]
        c.openai.api_key = values["openai_key"]
        c.weather = weather.config
        controls.client.client, controls.client.weather = sdk, weather
        if controls.household is not None:
            controls.household.zone = zone
        controls.recorder.follow_up_vad = vad
        if values["follow_up_seconds"] > 0:
            size = max(int(c.recording.pre_roll_seconds * c.audio.sample_rate), int(.4 * c.audio.sample_rate))
            controls.recorder.pre_roll = deque(maxlen=size)
        controls.recorder.cancel_capture()

    def _write_config(self, data):
        if data is None:
            self.path.unlink(missing_ok=True)
        else:
            atomic_write(self.path, data)

    def change(self, payload, *, undo=False, advanced=False):
        """Caller holds controls.lock; block capture transitions through the transaction."""
        controls = self.controls
        with controls.recorder.lock:
            if controls.busy or controls.recorder.processing_active or controls.recorder.alert_active or getattr(controls.recorder, "diagnostic_active", False) or controls.recorder.state == "RECORD":
                raise SettingsError("Wait for the current request, alert or audio check to finish before applying settings.")
            before = self._read()
            if not isinstance(payload, dict) or payload.get("revision") != revision(before):
                raise SettingsError("Settings changed since this page was loaded. Reload settings before saving.")
            old = self._values()
            if self.trial.journal.exists():
                raise SettingsError("Wait for the settings restart to finish.")
            if undo:
                try:
                    backup = json.loads(self.backup.read_text())
                    if backup["applied_revision"] != revision(before):
                        raise ValueError()
                    after = backup["config_text"].encode() if backup["config_text"] is not None else None
                    values = old.copy()
                    if not backup.get("restart"):
                        restored = parse_config(read_ini(after), allow_missing_api_key=True)
                        # Older undo files stored absolute values. Resolve the
                        # original INI against today's service environment.
                        for name in backup.get("changed", backup.get("values", {})):
                            section, key = FIELDS[name]
                            values[name] = getattr(getattr(restored, section), key)
                except Exception:
                    raise SettingsError("No matching saved change is available to undo.") from None
                if backup.get("restart"):
                    if not payload.get("confirm_restart"):
                        raise SettingsError("Open Advanced settings to confirm Undo and restart.")
                    if any(s == "app_store" for s, _ in backup["fields"]) and payload.get("confirm_trust") is not True:
                        raise SettingsError("Confirm restoration of the previous app trust policy.")
                    return self._restart(before, after, backup["fields"], undo=True)
            elif advanced:
                after, config, touched = candidate(before, payload.get("edits"))
                if touched - set(FIELDS.values()):
                    if payload.get("confirm_restart") is not True:
                        raise SettingsError("Confirm the service restart before applying these settings.")
                    if config.app_store != self.config.app_store and payload.get("confirm_trust") is not True:
                        raise SettingsError("Confirm the change to trusted app sources and signatures.")
                    return self._restart(before, after, touched)
                values = old.copy()
                for name, (section, key) in FIELDS.items():
                    if (section, key) in touched:
                        values[name] = getattr(getattr(config, section), key)
            else:
                values = self._validate(payload)
                if values == old:
                    return "No settings changed."
                parser = ConfigParser(interpolation=None)
                if before:
                    parser.read_string(before.decode())
                for key, (section, name) in FIELDS.items():
                    if values[key] != old[key]:
                        if not parser.has_section(section):
                            parser.add_section(section)
                        parser.set(section, name, str(values[key]).replace("%", "%%"))
                text = io.StringIO()
                parser.write(text)
                after = text.getvalue().encode()
            previous = (controls.client.client, controls.client.weather,
                        controls.household.zone if controls.household else ZoneInfo(old["reminder_timezone"]),
                        controls.recorder.follow_up_vad)
            previous_backup = self.backup.read_bytes() if self.backup.exists() else None
            try:
                prepared = self._prepare(values)
            except Exception:
                raise SettingsError("Could not prepare the new settings. Previous settings are still active.") from None
            if self._read() != before:
                if prepared[0] is not previous[0]:
                    prepared[0].close()
                raise SettingsError("Settings changed while preparing the update. Reload before saving.")
            try:
                if not undo:
                    changed = ([name for name, pair in FIELDS.items() if pair in touched] if advanced
                               else [name for name in values if values[name] != old[name]])
                    atomic_write(self.backup, json.dumps({"config_text": before.decode() if before is not None else None,
                                                        "changed": changed, "applied_revision": revision(after)}).encode())
                self._write_config(after)
                self._install(values, prepared)
            except Exception:
                try:
                    self._write_config(before)
                    self._install(old, previous)
                    if previous_backup is None:
                        self.backup.unlink(missing_ok=True)
                    else:
                        atomic_write(self.backup, previous_backup)
                    self.error = "Settings were not applied; the previous configuration was restored."
                except Exception:
                    self.error = "Settings recovery needs attention. The private phone undo file retains the previous configuration."
                if prepared and prepared[0] is not previous[0]:
                    prepared[0].close()
                raise SettingsError(self.error) from None
            if prepared[0] is not previous[0]:
                try:
                    previous[0].close()
                except Exception:
                    pass
            self.error = None
            if undo:
                self.backup.unlink(missing_ok=True)
            return "Previous settings restored." if undo else "Settings saved and applied. Provider keys are checked when you use their service."
