# Audio Prompts

This directory contains pre-generated audio prompts for system messages.

## Files

- `offline.mp3` - Played when internet connection is lost
- `online.mp3` - Played when internet connection is restored
- `unheard.wav` - Played when transcription returns no words
- `request_failed.wav` - Played when a request cannot finish

## Generating Audio Files

These clips ship with the repository and play without API access. The WAV clips
use the Realtime voice; regenerate them from the repository root with
`python -m scripts.generate_failure_prompts` (two paid API calls). Their exact text
is in that script. Listen to regenerated files before shipping.

The older `generate_prompts.sh` targets the legacy Speech API for the original
online/offline MP3s; it does not generate the failure WAVs. See
[failure feedback and recovery](../../../docs/failure-recovery.md).
