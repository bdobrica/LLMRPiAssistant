# Local weather (H05)

Ask “What's the weather here?”, then “And tomorrow?” during green. Answers name
Open-Meteo, the city and the applicable time/date. Current conditions include
temperature, feels-like temperature and wind; daily forecasts include conditions,
temperature range and precipitation probability. Units are Celsius and km/h.

## Choosing your city

1. `[weather] city` in `config.ini` overrides other choices. Use a city and country
   or region, for example `city = Berlin, Germany`. Restart after configuration edits.
2. Otherwise, reuse the city you previously gave the assistant. When it asks where
   you are, answer with your city and country. The resolved location is saved before
   it confirms remembering it. “Use Berlin, Germany for my home weather” changes it.
   An ambiguous place name prompts for clarification without overwriting the old city.
3. If neither exists, a configured `ipgeolocation_api_key` enables approximate city
   detection from the device's public Internet connection. Answers disclose that
   approximation. A VPN or ISP exit point can give the wrong city; choose one by voice
   or config to override it. IP detection runs on demand once per process, not at boot
   or while idle. Failure falls back to asking for a city; restart to retry detection.
4. Without that key, the first home-weather question asks for a city and remembers
   your answer. No IP-location service is contacted.

```ini
[weather]
city =
ipgeolocation_api_key =
api_key =
timezone =
latitude =
longitude =
timeout_seconds = 8
state_path = ~/.local/state/rpi-assistant/weather-location.json
```

Blank timezone uses the resolved city's IANA zone, independently of reminders.
For exact coordinates, supply **both** latitude and longitude plus city and timezone.
City-only config is geocoded once on its first weather request after each restart.
It does not overwrite a spoken city; removing the config override restores that choice.
The spoken choice survives restart in a small atomic, mode-0600 JSON file. Remove
that file and restart to forget it. Conversation reset preserves the saved city.
Environment equivalents use `WEATHER_` plus the uppercase setting name; file wins.

## Providers, evidence and limits

The [Open-Meteo forecast API](https://open-meteo.com/en/docs) supplies numeric weather
data; its [geocoding API](https://open-meteo.com/en/docs/geocoding-api) uses GeoNames
location data. Attribution is spoken and retained as a link. The free endpoints
cover personal home automation; commercial products need an Open-Meteo subscription
under its [terms](https://open-meteo.com/en/terms). Setting `api_key` selects its customer
forecast/geocoding endpoints. No new Python dependency or local model is needed.

Optional [ipgeolocation.io v3](https://ipgeolocation.io/documentation/ip-location-api.html)
uses its separate key and current account allowance. It receives the public source
IP and returns city coordinates/timezone; the assistant neither saves nor logs the
returned IP. Only the resolved city/coordinates are passed to the weather provider.
Keep keys in private config/environment. City and weather evidence enter private
interaction logs only with explicit opt-in; see [privacy and retention](conversation-privacy.md).

Weather is fetched per request, without polling or a cached forecast fallback. Each
HTTP operation has an eight-second default socket timeout, no automatic retries and
a 64 KiB response cap; discovery plus forecast are separate requests, not one total
turn deadline. Existing cloud transcription/reasoning/speech still require Internet.

Only current conditions and daily forecasts from today through six days ahead are
supported. These are **weather-model estimates**, not a local sensor or guaranteed
observations. Current valid-time must be within 90 minutes in the past and no more
than ten minutes ahead; daily dates must start today. Invalid units, missing values,
stale data and provider failures yield explicit inability to verify, without reusing
an earlier answer. Retrieval time is not a model initialization timestamp; the API
does not provide that timestamp here, so these checks cannot prove model-run freshness.
The Pi's clock must be correct. Hourly timing, historic weather, warnings, air quality
and whole-week summaries are outside this item.

Answers are formatted directly from validated numbers. Provider strings never
become executable instructions or app actions. Conversation history and the existing
opt-in `lookup` log retain values, source, validity/retrieval times and selected date. Model
selection of a tool, city intent and relative dates still needs correct interpretation.
An explicitly named other city can use F04 web lookup without changing home location;
that route retains F04's source-quality limits. Co-requested actions are not executed.

## Validation and recovery

Run `python -m unittest discover -s tests -v`. The opt-in live check uses temporary
location storage and paid chat calls, leaving your saved city unchanged:

```sh
python scripts/check-weather.py --live --config rpi_assistant/config.ini --city 'Berlin, Germany'
```

On hardware, try the first-use city question, current weather and a contextual
tomorrow forecast. Confirm audible source/city/time and recovery to listening.
Actual evidence and outstanding limitations are in TODO.md.

The development device retains the accepted H04 checkout/configuration and earlier
environments. Restore its service if necessary:

```sh
sudo cp /var/backups/rpi-assistant-h05/h04.service /etc/systemd/system/rpi-assistant.service
sudo systemctl daemon-reload
sudo systemctl restart rpi-assistant
```
