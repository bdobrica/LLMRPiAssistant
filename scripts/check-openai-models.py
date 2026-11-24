#!/usr/bin/env python3
"""Explicit paid R01 smoke check; synthetic input only, no microphone recording."""

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rpi_assistant.app.app_manager import AppManager
from rpi_assistant.app.config import load_config
from rpi_assistant.app.openai_client import OpenAIClient


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Authorize paid OpenAI calls")
    parser.add_argument("--config", required=True)
    parser.add_argument("--follow-up-only", action="store_true", help="Only test contextual continuation; no audio or app calls")
    parser.add_argument("--speech-output", help="Generated WAV path; does not play it")
    args = parser.parse_args()
    if not args.live:
        parser.error("Pass --live to authorize paid API calls")
    if not args.follow_up_only and not args.speech_output:
        parser.error("--speech-output is required for the full smoke check")
    config = replace(load_config(args.config).openai,
                     conversation_idle_timeout_seconds=0, conversation_relevance_threshold=0)
    client = OpenAIClient(config)
    client.client = client.client.with_options(timeout=45, max_retries=0)
    root = Path(__file__).resolve().parents[1]

    def report(label, operation):
        start = time.monotonic()
        result = operation()
        print(json.dumps({"check": label, "seconds": round(time.monotonic() - start, 2),
                          "result": result}), flush=True)
        return result

    try:
        if args.follow_up_only:
            for index, question in enumerate(("What is a manifold?", "What about a compact manifold?", "What about a cube?")):
                report(question, lambda: client.get_chat_response(question, continue_conversation=index > 0))
            assert len(client.conversation_history) == 7
            print("Three contextual API turns complete; acoustic follow-up checks remain separate.")
            return
        report("transcription", lambda: client.transcribe_audio(
            str(root / "rpi_assistant/app/audio_prompts/online.mp3")))
        for questions in (("What's a manifold?", "What about a compact manifold?", "What about a cube?"),
                          ("Is 38.5 degrees C considered a fever?", "What about 39.5 degrees?")):
            client.reset_conversation()
            for question in questions:
                report(question, lambda: client.get_chat_response(question))
            assert len(client.conversation_history) == 1 + 2 * len(questions)

        with TemporaryDirectory() as directory:
            manager = AppManager(
                app_dirs=[root / "voice_apps/apps/dice"],
                repository_roots=[], active_state_path=Path(directory) / "active.json",
            )
            request = "Please launch the dice app and roll one die"
            intent, _ = report("app classification", lambda: client.classify_app_intent(
                request, manager.app_intent_context()))
            assert intent and intent["intent"] == "launch_app" and intent["app_id"] == "dice"
            action = manager.handle_classified_intent(intent, request)
            assert action is not None
            report("local app action", lambda: action.text)

        called = []

        def status(name, arguments):
            called.append(name)
            return '{"test_value":42}'

        client.reset_conversation()
        client.mcp_manager = SimpleNamespace(
            config=SimpleNamespace(max_tool_rounds=2), call_tool=status,
            openai_tools=lambda: [{"type": "function", "function": {
                "name": "fixture_status", "description": "Read the synthetic test value",
                "parameters": {"type": "object", "properties": {}},
            }}],
        )
        reply, _ = report("tool result roundtrip", lambda: client.get_chat_response(
            "Call fixture_status and tell me the test value it returns."))
        assert called == ["fixture_status"] and "42" in reply
        report("speech usage", lambda: client.generate_speech(
            "The assistant is online. A cube surface is a topological manifold, even at its corners.",
            args.speech_output, config.tts_voice))
        print("API checks complete. Review the contextual answers; hardware speech needs a separate check.")
    finally:
        client.client.close()


if __name__ == "__main__":
    main()
