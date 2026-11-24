# Request failure and recovery (F03)

If transcription returns no words, the assistant plays a bundled “I didn't catch
that” clip. A failed transcription, answer, app-intent request or speech generation
plays “Sorry, I couldn't finish the reply.” Both ask you to use the wake word again.
If the connectivity monitor already reports an outage, the existing offline clip
is used instead. The online announcement remains unchanged.

These clips play locally; no API call is needed to explain a failure. Wait for the
normal blue wake indicator before retrying. Failure feedback never opens the green
follow-up window. Successful answers retain ordinary contextual follow-up listening.

## Limits and configuration

```ini
[openai]
request_timeout_seconds = 20
tts_timeout_seconds = 30
```

Environment equivalents: `OPENAI_REQUEST_TIMEOUT` and `OPENAI_TTS_TIMEOUT`. Explicit
file settings win; update an existing `tts_timeout_seconds = 90` if adopting the new
default. Values must be finite and positive. Restart after changing them.

- HTTP transcription, chat, classification and legacy Speech requests use the SDK's
  20-second network-operation timeout, with **zero automatic retries**. This bounds
  stalled network operations, not total turn duration: uploads, optional relevance
  checks and tool rounds can involve multiple operations/calls.
- Realtime speech has a 30-second overall generation deadline; partial output is
  discarded. A slow successful answer may need a larger configured deadline.
- Local players have a 150-second reply limit or a 10-second prompt limit. Playback
  is serialized; waiting for the output lock has the same limit. Player timeouts
  terminate that player and release the output for the next request.
- Generated output is cleared before generation and after playback/failure. Failed
  turns cannot replay an earlier answer. Failed app-intent routing does not fall
  through to a general answer that might imply an action happened.
- An action may already have completed before a later speech failure. Feedback
  deliberately makes no claim about its outcome; there is no automatic action retry.
- Failure recovery retains the existing audio drain/model reset. Blue indicates
  wake listening, with the existing 30-block model flush before detection resumes.
  If the speaker itself fails, audible feedback is impossible; the worker still
  returns to listening and records a diagnostic.

## Checks and bundled audio

Run `python -m unittest discover -s tests -v`. Failure-injection tests cover empty
speech, transcription/chat/TTS/classifier errors, player failure, stale output and
the next successful request. An actual SDK/local HTTP server check exercises stalled
responses and HTTP 503 without retries. Realtime tests check cancellation and cleanup.

The WAV clips were generated once with the configured Realtime/alloy voice. They
ship with the repository; normal operation never regenerates them. To deliberately
regenerate them (two paid API calls), run from the repository root:

```sh
python -m scripts.generate_failure_prompts --config rpi_assistant/config.ini
```

Their exact text is in that script. Listen to regenerated files before shipping.
On the Pi, inject failures while real capture/playback runs, check the local clips
and wake recovery, then try a normal question and contextual follow-up. Mock tests
do not establish audibility or microphone behavior. See TODO.md for actual evidence.

## Development-device rollback

F03 uses a separate checkout and the unchanged R01/U02 Python environments. The
working F06 unit and configuration are retained; R01's earlier rollback is untouched.

```sh
sudo cp /var/backups/rpi-assistant-f03/f06.service /etc/systemd/system/rpi-assistant.service
sudo systemctl daemon-reload
sudo systemctl restart rpi-assistant
```
