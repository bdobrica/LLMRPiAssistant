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
tts_output_path = /tmp/response.wav
```

`whisper_model` is the historical setting name for transcription. Luna's existing
Chat Completions tool flow uses `reasoning_effort = none`. For other audio hardware,
choose its output instead of the WM8960 device. Restart after manual changes.

Speech uses a short Realtime WebSocket session to read the completed answer.
This is not a model-name swap into the legacy Speech endpoint. The assistant waits
for the generated audio before playing it, so longer answers can mean a longer pause.
It sends no idle microphone stream to Realtime; wake detection remains local.

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
