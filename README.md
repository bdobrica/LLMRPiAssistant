# LLMRPiAssistant

Build a small Raspberry Pi assistant you can talk to. Ask a question, hear an
answer, then keep the conversation going without repeating the wake word.
The Pi handles the microphone, speaker and controls; OpenAI handles speech
recognition and answers over the Internet.

**Start here: [Build your assistant](QUICKSTART.md).** Already have one running?
[Explore what it can do](docs/README.md).

## Try a conversation

Say **“Hey Jarvis, what's a manifold?”** After the answer, wait for steady green
lights and ask **“What about a cube?”** The assistant uses the earlier conversation
to understand your follow-up. Prefer something lighter? Ask for a short joke.

You can also:

- Set a tea timer, save a reminder or add milk to your Shopping list.
- Ask for the weather, or look up a fact that needs current information.
- Press the HAT button to stop an answer, then give a correction after green.
- Use your phone to change volume, mute the microphone, adjust settings and test audio.
- Install a small voice game. [Try Dice](docs/voice-apps.md) when you're ready.

Timers, reminders and the phone controls work without Internet. Spoken requests
need a connection and an OpenAI API key with access to the configured models;
API usage costs money. Conversation text logging is off by default, but answering
questions still sends audio/text to cloud providers. See [privacy](docs/conversation-privacy.md).

## What to build with

The tested combination is a **Raspberry Pi Zero 2 W**, a **ReSpeaker 2-Mic Pi HAT
v1 (WM8960)** and a speaker connected to that HAT, running Raspberry Pi OS Lite
64-bit. You'll also need a microSD card, suitable power supply, Wi-Fi and a computer
for the initial installation. The [quick start](QUICKSTART.md) walks through it.

The project targets affordable 512 MB boards. The Pi 3 A+ is also a target, but
has not been hardware-tested here. Other Pi boards, HAT revisions and audio outputs
need their own checks; the supplied audio installer is specifically for WM8960.

## Explore and make it your own

The [guide index](docs/README.md) starts with everyday activities, then leads to
settings, troubleshooting and optional extensions. You don't need to understand
Python or the app catalog to try the assistant.

This is a working maker project, still being improved. Noisy rooms, long unattended
runs and fresh-card setup need more testing. A known shutdown delay can make a
service restart take about 90 seconds. See the [tested limits](docs/reference/release-check-2026-11-25.md)
before relying on it unattended.

Want to contribute? [AGENTS.md](AGENTS.md) describes the repository workflow;
[PLAN.md](PLAN.md) and [TODO.md](TODO.md) track decisions and progress.
Share what you tried, your board/HAT, and what happened—leave out keys and private conversations.

## License and credits

See [LICENSE](LICENSE). Built with openWakeWord, OpenAI, Raspberry Pi and
Seeed Studio ReSpeaker hardware, with weather from Open-Meteo.
