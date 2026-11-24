# Follow-up conversation (F06)

Ask a question using the wake word. After the spoken answer finishes, wait for the
LEDs to turn steady green, then ask the next question without the wake word. Each
successful spoken answer opens another short window. Silence ends it quietly and
returns the LEDs to their normal blue wake-word state.

```ini
[recording]
follow_up_window_seconds = 6.0
follow_up_echo_guard_seconds = 0.35
```

Set `follow_up_window_seconds = 0` to restore wake-word-only operation. Environment
equivalents are `RECORDING_FOLLOW_UP_WINDOW` and `RECORDING_FOLLOW_UP_ECHO_GUARD`;
explicit configuration-file values take precedence. Both values must be finite and
nonnegative. Restart the assistant after changing configuration.

The echo guard discards microphone input just after playback; speech during that
brief guard is not recorded. The six-second window starts after the guard. Once
speech begins, the ordinary recording silence/max-duration settings finish the
utterance even if the window deadline passes. Pre-roll retains its first sounds;
at least 400 ms is kept for onset detection when follow-up listening is enabled,
even if ordinary pre-roll is set to zero. Speak naturally after the green
indicator; repeating the wake word is unnecessary during the window.

## Behavior and limits

- Only successful spoken playback opens a window. Failed requests/playback and
  disabled audio output return to the normal wake flow.
- Input during processing/playback is dropped, then queued audio and pre-roll are
  cleared. Connectivity announcements cancel pending/open follow-up windows.
- The pinned 1.8 MB Silero voice-activity model supplied by openWakeWord runs
  locally with one inference thread during follow-up waiting/recording. One confident
  80 ms speech block starts a recording; non-speech ends it using the existing
  silence-hold setting. Quiet windows create no recording and no cloud requests.
  Nearby people or TV speech can still trigger it; this is not speaker identification
  or acoustic echo cancellation.
- Follow-up questions use the existing conversation history and bypass idle/topic
  reset checks for that turn. Ordinary wake-word requests keep their configured
  reset behavior. App routing and active-app state are retained.
- F06 itself does not interrupt playback. F02 adds optional [button interruption](button-interruption.md)
  with its own correction window; spoken interruption remains unsupported.
  After expiry, use the wake word again.

## Validation and rollback

Run `make install-wakeword-models` during setup/update. It verifies the pinned model
checksum and installs `rpi_assistant/models/silero_vad.onnx` in the checkout, alongside
the existing wake-model setup. The downloaded directory is ignored by Git. Startup
never downloads assets; a missing speech model gives an actionable setup error.
No new Python package is required. Setting the window to zero avoids loading it.

Run `python -m unittest discover -s tests -v` for local state/configuration tests.
The explicit paid context check uses synthetic questions and no microphone input:

```sh
python scripts/check-openai-models.py --live --follow-up-only \
  --config rpi_assistant/config.ini
```

On hardware, try manifold → compact manifold → cube with only the first wake word.
Let a window expire without speaking, then start a new wake-word question. Check
that the assistant never answers its own playback. Repeat with the window set to
zero and verify a phrase without the wake word produces no response. API and mock
tests alone do not establish microphone, echo or timing behavior.

The development candidate uses a separate checkout and the unchanged R01 Python
environment. R01 and its configuration remain available. To restore its service:

```sh
sudo cp /var/backups/rpi-assistant-f06/r01.service /etc/systemd/system/rpi-assistant.service
sudo systemctl daemon-reload
sudo systemctl restart rpi-assistant
```

Actual device results and limitations are recorded in TODO.md.
