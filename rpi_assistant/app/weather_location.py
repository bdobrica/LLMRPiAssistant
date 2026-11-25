"""Resolve an explicit city or opt-in IP location, retaining only city coordinates."""

import json
import math
import os
from pathlib import Path
import tempfile
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


class LocationError(ValueError):
    """Safe spoken clarification, never raw provider errors."""


def read_json(url, timeout):
    request = Request(url, headers={"User-Agent": "LLMRPiAssistant-weather/1.0", "Accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        raw = response.read(65537)
    if len(raw) > 65536:
        raise ValueError("oversized response")
    return json.loads(raw)


def _text(value):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 160 or any(ord(c) < 32 for c in value):
        raise ValueError("invalid location text")
    return value.strip()


def _location(name, latitude, longitude, zone, source):
    latitude, longitude = float(latitude), float(longitude)
    if not math.isfinite(latitude) or not math.isfinite(longitude) or abs(latitude) > 90 or abs(longitude) > 180:
        raise ValueError("invalid location coordinates")
    ZoneInfo(zone)
    return {"name": _text(name), "latitude": latitude, "longitude": longitude, "timezone": zone, "source": source}


class WeatherLocation:
    def __init__(self, config):
        self.config = config
        self.path = Path(config.state_path).expanduser()
        self.resolved = None
        self.ip_attempted = False

    def _load(self):
        try:
            with self.path.open() as source:
                saved = json.loads(source.read(8193))
            value = _location(saved["name"], saved["latitude"], saved["longitude"], saved["timezone"], saved["source"])
            return value
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def _save(self, value):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, name = tempfile.mkstemp(prefix=".weather-", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w") as target:
                json.dump(value, target)
                target.flush()
                os.fsync(target.fileno())
            os.replace(name, self.path)
            directory = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def geocode(self, city):
        try:
            city = _text(city)
            params = {"name": city, "count": 10, "language": "en", "format": "json"}
            host = "geocoding-api.open-meteo.com"
            if self.config.api_key:
                params["apikey"] = self.config.api_key
                host = "customer-geocoding-api.open-meteo.com"
            data = read_json(f"https://{host}/v1/search?{urlencode(params)}", self.config.timeout_seconds)
            matches = [r for r in data.get("results", []) if r.get("feature_code", "").startswith("PPL")]
            if len(matches) != 1:
                raise LocationError("I couldn't identify one city. Please give the city and country, or the state or region if needed.")
            row = matches[0]
            name = ", ".join(dict.fromkeys(_text(row[k]) for k in ("name", "admin1", "country") if row.get(k)))
            return _location(name, row["latitude"], row["longitude"], row["timezone"], "spoken")
        except LocationError:
            raise
        except Exception:
            raise LocationError("I couldn't look up that city. Please try the city and country again in a moment.") from None

    def resolve(self):
        if self.resolved is not None:
            return self.resolved
        config, saved = self.config, self._load()
        if config.city:
            if str(config.latitude).strip():
                value = _location(config.city, config.latitude, config.longitude, config.timezone, "config")
            else:
                value = self.geocode(config.city)
                value["source"] = "config"
            if config.timezone:
                value["timezone"] = config.timezone
            self.resolved = value
        elif saved and saved["source"] == "spoken":
            self.resolved = saved
        elif config.ipgeolocation_api_key and not self.ip_attempted:
            self.ip_attempted = True
            try:
                params = {"apiKey": config.ipgeolocation_api_key,
                          "fields": "location.city,location.country_name,location.latitude,location.longitude,time_zone.name"}
                data = read_json("https://api.ipgeolocation.io/v3/ipgeo?" + urlencode(params), config.timeout_seconds)
                row = data["location"]
                self.resolved = _location(_text(row["city"]) + ", " + _text(row["country_name"]),
                                          row["latitude"], row["longitude"], data["time_zone"]["name"], "ip")
            except Exception:
                raise LocationError("I couldn't detect your weather city. Which city and country should I use?") from None
        if self.resolved is None:
            raise LocationError("Which city and country should I use for your weather? I'll remember it for next time.")
        return self.resolved

    def set_city(self, city):
        if self.config.city:
            raise LocationError("The home weather city is fixed in config.ini. Change its weather city setting to update it.")
        value = self.geocode(city)
        try:
            self._save(value)
        except OSError:
            raise LocationError("I couldn't save the weather city. Please try again; I can't confirm it is remembered.") from None
        self.resolved = value
        return value
