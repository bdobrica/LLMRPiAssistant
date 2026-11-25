# Configure speech and answer models

You need an OpenAI API key with access to the configured models. Enter it through
[phone Settings](phone-setup.md), or in `[openai] api_key` in the private
`rpi_assistant/config.ini`. Normal speech uses paid APIs; local phone audio checks
work without a key and help verify hardware first.

## The supplied configuration

These are the repository's tested settings, not a promise that every account can
use every model. Existing file settings override defaults and environment values.
When migrating an older installation, update the model workflow together:

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
stream_realtime = true
tts_output_path = /tmp/response.wav
```

`whisper_model` is the historical setting name for transcription. Luna's existing
Chat Completions tool flow uses `reasoning_effort = none`. For other audio hardware,
choose its output instead of the WM8960 device. Restart after manual changes.

Speech uses a short Realtime session to read the completed answer. By default the
speaker starts as audio arrives. Press the button during speech to interrupt,
then wait for green before giving a correction. The follow-up window opens after
the player finishes and the echo guard expires.

To compare playback on your own device, open **Settings → Advanced settings →
Speaker** and set **stream realtime** to **Disabled**. This plays a completed WAV
using the same model and voice. Choose **Enabled** to stream again. If the
connection drops during a reply, you hear local failure feedback. The assistant
leaves completed actions in place and waits for another question.

### Measured on the Zero 2 W

The same two synthetic questions went through recording, transcription, chat and
the wired ReSpeaker on November 25, 2026. Each cell below shows two runs. Times
start at the last block of the question and include the recorder's silence wait
(0.92–0.95 seconds). **First sound** is the first microphone block above the
background threshold after the player opened. The probe kept levels and timing.

| Reply and playback | First PCM (s) | First sound (s) | Playback finished (s) | Speech duration (s) | Peak assistant RSS (MiB) |
| --- | --- | --- | --- | --- | --- |
| Short, WAV | 9.19 / 5.04 | 10.81 / 6.48 | 13.43 / 8.99 | 2.55 / 2.50 | 181.8 / 177.6 |
| Short, streamed | 4.78 / 4.93 | 4.88 / 5.04 | 7.01 / 7.86 | 2.15 / 2.85 | 176.8 / 177.6 |
| Longer, WAV | 5.04 / 4.65 | 6.88 / 6.56 | 15.10 / 14.77 | 8.20 / 8.20 | 176.5 / 177.6 |
| Longer, streamed | 4.56 / 4.80 | 4.64 / 4.88 | 17.59 / 18.43 | 12.95 / 13.55 | 178.9 / 178.6 |

Streaming reduced the wait **after the first PCM arrived** from 1.44–1.91 seconds
to 0.08–0.11 seconds. Provider latency and generated answer length varied. The
longer streamed answers started sooner and took longer to finish. ALSA reported
zero underruns across the eight turns. Each opened its follow-up window, with
zero follow-up speech detections from playback. The owner heard the last streamed
answer clearly at normal volume through the final word. The trial covered one
Zero 2 W, one network and one speaker.

## Check availability and cost

Try a short spoken question and follow-up. If it fails while local audio works,
check account access, billing and the saved key before changing audio settings.
Consult the provider's [model documentation](https://developers.openai.com/api/docs/models)
and [pricing](https://developers.openai.com/api/docs/pricing) for your chosen models.
The [dated release check](reference/release-check-2026-11-25.md#observed-api-usage-and-cost)
contains measured sample costs, not a monthly estimate.

For a deliberate paid API check without microphone capture, activate the installed
Python environment and run from the repository root:

```sh
python scripts/check-openai-models.py --live \
  --config rpi_assistant/config.ini --speech-output /tmp/model-check.wav
aplay -D assistant_wm8960 /tmp/model-check.wav
rm /tmp/model-check.wav
```

This uses synthetic prompts and a bundled clip. Its isolated Dice check does not
install Dice into the running assistant; [install the app](voice-apps.md) separately.

## Keep a working combination

Preserve the working private config and [Python environment](python-upgrade.md)
before changing models. Restore the whole tested combination if a candidate fails.
The legacy `speech` backend remains in code for recovery, but availability of old
provider models cannot be assumed. Other providers need an integration, not simply
a different key in the phone UI.

[Back to maintenance](maintenance.md)
