# OpenAI workflow upgrade (R01)

The owner selected these defaults after live account/API probes and listening to
the Realtime sample on the Zero 2 W (2026-11-24). OpenAI SDK: 3.58.0.

| Work | Model / workflow | Published standard price |
| --- | --- | --- |
| Recorded speech | `gpt-transcribe`, Audio Transcriptions | $0.0045/minute |
| Answers and app intents | `gpt-6-luna`, Chat Completions, `reasoning_effort=none` | $0.10 input / $0.50 output per million text tokens |
| Spoken answers | `gpt-realtime-2.1-mini`, Realtime WebSocket, `alloy` | $20/million output audio tokens; $0.60 input / $2.40 output per million text tokens |

Sources: [transcription](https://developers.openai.com/api/docs/models/gpt-transcribe),
[Luna](https://developers.openai.com/api/docs/models/gpt-6-luna),
[Realtime mini](https://developers.openai.com/api/docs/models/gpt-realtime-2.1-mini).
Prices and alias behavior can change. A 5.75-second sample used 63 input text,
75 output text (including reasoning), and 115 output audio tokens: approximately
$0.00252. This is a sample cost, not a monthly estimate.

## Existing installations

Preserve the working environment, checkout, configuration and service command.
Install the pinned requirements into a candidate environment; use SD-backed
temporary storage and pause the assistant during substantial installs as described
in [the Python upgrade guide](python-upgrade.md). The only new runtime dependency is
`websockets==15.0.1`: SDK 3.58.0's Realtime extra requires `>=13,<16`, so newer
WebSocket releases are deliberately excluded until the SDK supports them.

Update these settings together in the candidate `config.ini`. Existing explicit
model settings override new defaults; pulling code alone does not migrate them.

```ini
[openai]
whisper_model = gpt-transcribe
chat_model = gpt-6-luna
reasoning_effort = none
tts_backend = realtime
tts_model = gpt-realtime-2.1-mini
tts_voice = alloy
request_timeout_seconds = 20
tts_timeout_seconds = 30

[audio_output]
device = assistant_wm8960
tts_output_path = /tmp/response.wav
```

`whisper_model` retains its historical setting name for compatibility. Keep existing
credentials and other settings. Preserve the device's disabled idle/relevance resets
(`conversation_idle_timeout_seconds=0`, `conversation_relevance_threshold=0`) when
migrating that configuration. Disabled relevance now makes no extra API request.

Chat and JSON intent/relevance requests use `max_completion_tokens`. Luna's Chat
Completions tools require reasoning `none`; a higher effort needs a separately
validated workflow. Existing message history, tool results and app execution remain
in their existing components.

## Speech behavior and limits

The [speech migration guide](https://developers.openai.com/api/docs/guides/text-to-speech)
requires Realtime for this replacement; it cannot use `/v1/audio/speech`.
Each answer opens one short-lived session, sends only the completed answer text,
requests verbatim reading, and closes after completion. It sends no microphone
audio or idle traffic. Audio chunks go to a temporary mono 24 kHz, 16-bit WAV,
bounded to 120 seconds of audio. Only a completed, nonempty response replaces the
output file. Errors/timeouts discard partial output; playback starts only after
successful generation. F03 adds [local failure feedback and bounded waits](failure-recovery.md),
including removal of the preceding generated answer before each generation.

`aplay` converts the WAV through the configured ALSA PCM. Keep `assistant_wm8960`
for this ReSpeaker board: its forced 32-bit hardware format fixes quiet playback
during capture. Bundled online/offline MP3 prompts still use `mpg123`.

This migration buffers the completed response before playback. It does not add
follow-up listening or interruption. Realtime is a generative model: the read-aloud
instruction is not a mathematical guarantee of verbatim speech. The initial sample's
returned transcript matched exactly; review real spoken answers as well.

## Checks and recovery

Offline checks: `python -m unittest discover -s tests -v`.
Explicit paid API check, using synthetic prompts and the bundled online recording:

```sh
python scripts/check-openai-models.py --live \
  --config rpi_assistant/config.ini --speech-output /tmp/r01-check.wav
aplay -D assistant_wm8960 /tmp/r01-check.wav
```

Review the printed manifold/fever follow-ups for contextual meaning. The script
also classifies and executes the repository's dice app in isolated temporary state,
and checks a harmless tool-result round trip. It does not capture household audio.
Then try a real wake-word question, contextual follow-up and app command on the Pi.

For the development device, R01 has a separate checkout/environment. Its environment
adds WebSocket support and reads unchanged U02 packages through a `.pth` file to
avoid reinstalling the inference stack on the small Pi; retain that U02 environment.
Fresh installations use the complete pinned requirements instead. Before switching,
the U02 unit/configuration were saved under `/var/backups/rpi-assistant-r01/`.
Rollback restores the retained U02 checkout/environment and model configuration:

```sh
sudo cp /var/backups/rpi-assistant-r01/u02.service /etc/systemd/system/rpi-assistant.service
sudo systemctl daemon-reload
sudo systemctl restart rpi-assistant
```

Legacy `tts_backend=speech` remains available for short-term recovery, using `tts-1`
and MP3 playback. Restore the entire matching model configuration (including empty
`reasoning_effort` for the old chat model), not just a model name. Legacy provider
shutdowns make this a temporary recovery option; see PLAN.md for the schedule.
