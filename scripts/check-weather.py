#!/usr/bin/env python3
"""Opt-in paid model/provider check using temporary weather-location storage."""

import argparse
from dataclasses import replace
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rpi_assistant.app.config import load_config
from rpi_assistant.app.openai_client import OpenAIClient
from rpi_assistant.app.weather import Weather


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--city", required=True, help="Explicit test city and country, e.g. Berlin, Germany")
    args = parser.parse_args()
    config = load_config(args.config)
    # Avoid RAM-backed /tmp on small boards. Only a tiny location file is written.
    with TemporaryDirectory(prefix="weather-check-") as directory:
        settings = replace(config.weather, city="", latitude="", longitude="", timezone="",
                           ipgeolocation_api_key="", state_path=str(Path(directory)/"city.json"))
        client = OpenAIClient(config.openai)
        client.weather = Weather(settings)
        def ask(text):
            answer, usage = client.get_chat_response(text, continue_conversation=True)
            print(text, "=>", answer, flush=True)
            return usage.get("lookup", {})
        evidence = ask("What's the weather here?")
        assert evidence.get("reason") == "location_needed", evidence
        evidence = ask(args.city)
        assert evidence.get("status") == "ok" and evidence.get("values"), evidence
        assert Path(settings.state_path).exists()
        evidence = ask("And tomorrow?")
        assert evidence.get("period") == "tomorrow" and evidence["status"] == "ok", evidence
        # Reopen storage and conversation as a restart; no repeated city question.
        client.reset_conversation()
        client.weather = Weather(settings)
        evidence = ask("What's the weather here now?")
        assert evidence.get("status") == "ok" and evidence["location_source"] == "spoken", evidence
        # Explicit configuration is a separate supported path.
        client.reset_conversation()
        client.weather = Weather(replace(settings, city=args.city))
        evidence = ask("Will there be precipitation here tomorrow?")
        assert evidence.get("status") == "ok" and evidence["period"] == "tomorrow", evidence
        client.client.close()
        print("PASS live city clarification, saved selection/reopen, context and configured forecast", flush=True)


if __name__ == "__main__":
    main()
