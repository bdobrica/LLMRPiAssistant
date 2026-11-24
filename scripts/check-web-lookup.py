#!/usr/bin/env python3
"""Explicit paid lookup/context checks; no household recording or automatic playback."""

import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rpi_assistant.app.config import load_config
from rpi_assistant.app.openai_client import OpenAIClient
from rpi_assistant.app.web_lookup import READER_INSTRUCTIONS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Allow paid OpenAI calls")
    parser.add_argument("--config", default="rpi_assistant/config.ini")
    parser.add_argument("--speech-output", help="Optionally generate a WAV for manual playback")
    args = parser.parse_args()
    if not args.live:
        parser.error("Pass --live to explicitly allow paid API calls")
    config = load_config(args.config)
    if not config.openai.web_search_enabled:
        parser.error("Enable web_search_enabled in the test configuration")
    client = OpenAIClient(config.openai)
    try:
        start = time.monotonic()
        answer, usage = client.get_chat_response(
            "What is the latest stable Python release listed by python.org today? Exclude preview releases."
        )
        evidence = usage.get("lookup", {})
        assert evidence.get("status") == "ok" and evidence.get("sources"), "No sourced lookup completed"
        print(answer)
        print(json.dumps({"seconds": round(time.monotonic() - start, 2), "lookup": evidence}, ensure_ascii=False))
        if args.speech_output:
            client.generate_speech(usage["spoken_response"], args.speech_output, config.openai.tts_voice)
        followup, _ = client.get_chat_response("When was that version released?", continue_conversation=True)
        print("CONTEXT CHECK:", followup)
        client.reset_conversation()
        _, ordinary = client.get_chat_response("In one sentence, what is a manifold?")
        assert "lookup" not in ordinary, "Unexpected lookup for a timeless question"
        # Controlled semantic check, explicitly synthetic: no claim about real opening hours.
        conflict = client.client.responses.create(
            model=config.openai.chat_model, reasoning={"effort": "none"}, store=False,
            instructions=READER_INSTRUCTIONS, max_output_tokens=350,
            input=("Synthetic evaluation, not real-world facts. Use only these supplied evidence excerpts; "
                   "no tools are available. Two equally authoritative notices dated today disagree about "
                   "Example Library: notice A says it opens at 9 am, notice B says it opens at 10 am. "
                   "Neither supersedes the other. What time does it open?"),
        )
        print("SYNTHETIC CONFLICT CHECK (review meaning):", conflict.output_text)
    finally:
        client.client.close()


if __name__ == "__main__":
    main()
