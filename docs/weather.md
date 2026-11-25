# Ask about the weather

Say **“What's the weather here?”** If asked where you are, answer with your city
and country: **“Bucharest, Romania.”** After the answer and green light, try
**“And tomorrow?”**

Answers name the city, relevant time/date and source, Open-Meteo. Current conditions
include temperature, feels-like temperature and wind. Daily forecasts include a
temperature range and rain probability. Units are Celsius and km/h.

## Set your home city

You have three choices:

- **Tell it by voice.** The first weather question asks for a city and saves it.
  Later, say “Use Berlin, Germany for my home weather” to change it.
- **Set it yourself.** Use the phone's **Settings → Home weather city**, or set
  `[weather] city = Berlin, Germany` in `rpi_assistant/config.ini` and restart.
  This overrides the saved spoken choice. Clear it to use the saved choice again.
- **Opt into IP location.** Add an ipgeolocation.io key in phone Settings or
  `[weather] ipgeolocation_api_key`. With no configured or saved city, the assistant
  tries to find an approximate city from your Internet connection. It tells you
  when that location is approximate. A VPN or your ISP can make it inaccurate.

No IP-location key is needed for normal weather questions. If detection fails,
the assistant asks for a city. Your saved city survives a restart and New conversation.
Reminder timezone and weather location are separate settings.

## Know the forecast's limits

The assistant fetches weather when asked, rather than polling in the background.
It supports current conditions and daily forecasts through six days ahead, not
hourly detail, past weather or alerts. These are model estimates, not a sensor
on your Pi. The Pi's date/time must be correct.

If data is missing, stale or unavailable, it says it cannot verify the weather.
It does not fall back to an old forecast. Forecast age checks cannot establish
exactly when the provider's underlying model run was created.

Weather comes from [Open-Meteo](https://open-meteo.com/), with place lookup based
on GeoNames. Check the provider's [terms](https://open-meteo.com/en/terms) for your
use, especially a commercial build. Its optional paid key is separate from the
optional IP-location key and your OpenAI key. See the
[configuration example](../rpi_assistant/config.ini.example) for precise coordinates
and provider settings; you don't need these for a city-based setup.

[Back to the guides](README.md)
