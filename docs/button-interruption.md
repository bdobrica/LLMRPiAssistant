# Stop an answer and correct it (F02)

Press the ReSpeaker user button **while the assistant is speaking an answer**.
The speaker stops; after the echo guard and model reset, steady green LEDs mean
you can speak a correction without the wake word. For example: ask for a detailed
explanation of a manifold, press the button during the answer, then say “Explain
it for a ten-year-old” after green. The correction uses the existing conversation.
Staying quiet closes the window and returns to normal wake listening.

## Enable the button

```ini
[recording]
interrupt_button_gpio = 17
correction_window_seconds = 6.0
```

The [ReSpeaker 2-Mics HAT user button](https://wiki.seeedstudio.com/ReSpeaker_2_Mics_Pi_HAT/)
uses BCM GPIO17, pulled up and pressed to ground. GPIO numbers here use BCM numbering.
Use `-1` to disable the button (the repository default); choose a different pin only
for appropriately wired hardware. Restart after changing configuration. A button
initialization failure reports a diagnostic and leaves ordinary voice use available.

Environment settings: `RECORDING_INTERRUPT_BUTTON_GPIO` and
`RECORDING_CORRECTION_WINDOW`; explicit file settings take precedence. The correction
window must be finite and positive. It also works with `follow_up_window_seconds=0`.
Enabling either window requires the existing installed Silero speech model; no new
Python dependency is needed.

## What stopping means

- Only spoken answers are interruptible. Presses during thinking, speech generation,
  local status/error clips, or idle listening do nothing. Repeated/bouncing presses
  do not start extra requests.
- The player is stopped and its generated file removed. An older queued answer
  cannot resume. The original request, app action and tools are not automatically
  retried. Completed tool results remain in history; an interrupted local app reply
  is also retained so a correction can refer to its result.
- Stopping speech does **not** undo an action already performed. A correction is a
  new request: explicitly asking for another action can execute another action.
  This does not add persistent transaction deduplication or undo support to apps.
- Input is discarded while playback and its echo guard run. Wait for green before
  speaking; words spoken over the answer are not captured.
- This delivery supports **physical-button interruption**. Spoken interruption
  from across the room is not enabled or validated. There is no acoustic echo
  cancellation; nearby people or TV speech can trigger the window after green.

## Validation and rollback

Run `python -m unittest discover -s tests -v`. Focused tests cover actual player
termination, queued stale audio, repeated/idle presses, correction with ordinary
follow-up disabled, app/tool result preservation and no automatic action replay.
Hardware acceptance also requires pressing the real button during a spoken answer,
giving a contextual correction after green, and trying a fresh wake after quiet expiry.
Record real acoustic and GPIO observations separately from mock tests in TODO.md.

The development candidate uses the existing R01/U02 Python environments. F03's
checkout and configuration remain available, as do earlier rollbacks:

```sh
sudo cp /var/backups/rpi-assistant-f02/f03.service /etc/systemd/system/rpi-assistant.service
sudo systemctl daemon-reload
sudo systemctl restart rpi-assistant
```
