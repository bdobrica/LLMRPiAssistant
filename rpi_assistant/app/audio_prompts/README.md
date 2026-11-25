# Audio Prompts

This directory contains pre-generated audio prompts for system messages.

## Files

- `offline.mp3` - Played when internet connection is lost
- `online.mp3` - Played when internet connection is restored
- `unheard.wav` - Played when transcription returns no words
- `game_repeat.wav` - Asks for the same game answer again before follow-up listening reopens
- `request_failed.wav` - Played when a request cannot finish
- `timer.wav` - Original synthesized three-note local timer chime (24 kHz mono PCM); no API needed
- `new_conversation.wav` - Local acknowledgment for the explicit spoken reset control

## Generating Audio Files

These clips ship with the repository and play without API access. The WAV clips
use the Realtime voice; regenerate them from the repository root with
`python -m scripts.generate_failure_prompts` (three paid API calls). Their exact text
is in that script. Listen to regenerated files before shipping.

The older `generate_prompts.sh` targets the legacy Speech API for the original
online/offline MP3s; it does not generate the failure WAVs. See
[failure feedback and recovery](../../../docs/failure-recovery.md).

The F05 `new_conversation.wav` uses the configured Realtime model/alloy voice,
24 kHz mono PCM WAV. Its text is: “Starting a new conversation. Say my wake word
when you're ready.” It is generated once with `OpenAIClient.generate_speech` and
ships locally; reset never needs a speech-generation API call.
