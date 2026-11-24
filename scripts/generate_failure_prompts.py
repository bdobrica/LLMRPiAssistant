"""Regenerate F03's bundled clips using the configured Realtime voice (paid API calls)."""

import argparse
from pathlib import Path
import wave

from rpi_assistant.app.config import load_config
from rpi_assistant.app.realtime_speech import generate_realtime_speech


PROMPTS = {
    "unheard.wav": "I didn't catch that. Please say my wake word and try again.",
    "request_failed.wav": "Sorry, I couldn't finish the reply. Say my wake word when you're ready.",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="rpi_assistant/config.ini")
    parser.add_argument("--output", type=Path, default=Path("rpi_assistant/app/audio_prompts"))
    args = parser.parse_args()
    config = load_config(args.config).openai
    if config.tts_backend != "realtime":
        parser.error("Select a Realtime speech configuration to generate these WAV clips")
    args.output.mkdir(parents=True, exist_ok=True)
    for filename, text in PROMPTS.items():
        path = args.output / filename
        generate_realtime_speech(config, text, str(path), config.tts_voice)
        with wave.open(str(path)) as audio:
            print(f"{filename}: {audio.getnframes() / audio.getframerate():.2f} seconds")


if __name__ == "__main__":
    main()
