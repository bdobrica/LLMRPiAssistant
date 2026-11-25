# Reliable local timers (H03)

Say “Set a tea timer for five minutes,” “How much time is left on my tea timer?”
or “Cancel the tea timer.” Use a name when several timers are running. A missing
or invalid duration prompts for a duration. Countdown durations range from one
second to seven days; calendar reminders are a separate feature.

The existing [local phone page](local-controls.md) also creates, lists and cancels
timers without Internet. Use minutes/seconds and an optional name. It shows pending,
ringing and missed timers. Cancel a specific timer, or use Stop/the device button
to dismiss currently ringing timers. Pending timers continue when ordinary speech
is stopped, the microphone is muted, or a new conversation starts. Spoken commands
still need the existing cloud transcription/model services; the phone and button do not.

## Alerts and interaction

Timers repeat a bundled, locally generated chime for up to two minutes by default.
The owner selected this behavior. Steady amber indicates an alert; microphone mute
retains its steady red indication. Muting the microphone does not silence timers.
Speaker volume and disabled audio output apply, so a zero-volume timer is silent.
There is no automatic volume boost.

An alert stops stale speech/partial recording and temporarily suppresses audio
capture processing to avoid recording its own chime. It never opens a muted input
stream. Press the button or phone Stop to dismiss the alert; after the chime tail
clears, use a fresh wake word. Voice interruption over a ringing chime is not
supported. An already dispatched app/API action may finish; timer interruption does
not undo it. Multiple due timers share the chime; Stop dismisses all currently
ringing timers, leaving future timers scheduled.

## Persistence and restart

A SQLite transaction with full synchronous writes stores the deadline before any
success confirmation. Voice mutation responses use deterministic receipts from the
save/cancel result; the model cannot rewrite a failed save as success. Identical
creation calls within one model turn share a request ID, avoiding duplicate timers.
A fresh spoken request or new phone submission intentionally creates a new timer.
If an acknowledgment is lost, check the timer list before submitting again.

An assistant-service restart uses the saved monotonic deadline from the same Linux
boot, so wall-clock adjustments cannot shift that countdown. Across device reboots,
timers use their saved UTC deadline and the OS clock. A pending timer already due
rings after startup; an alert already exhausted before restart remains a visible
missed timer and does not ring again. Cancelling is persisted before acknowledging
it. Up to 32 timers may be active, with the latest 32 missed/cancelled records retained.

**Clock limitation:** these inexpensive Pis have no battery-backed clock by default.
After power loss, an accurate reboot deadline requires a correct OS clock, usually
restored by network time or an added RTC. Offline service restarts work without time
synchronization; elapsed powered-off time cannot be guaranteed without a reliable
clock. Timers also cannot ring while the Pi is powered off or the service is stopped.
Storage/player failures are shown on the page; no software can guarantee an alert
through a failed SD card or speaker. A failed durable dismissal may recur after restart.

## Configuration and validation

```ini
[timers]
state_path = ~/.local/state/rpi-assistant/timers.sqlite3
alert_seconds = 120
```

Alert duration accepts 1–600 seconds. Environment equivalents are `TIMERS_STATE_PATH`
and `TIMERS_ALERT_SECONDS`; explicit file configuration wins. The database is kept
outside the checkout with restrictive file permissions. Corrupt/unavailable storage
is preserved and reported; ordinary assistant features remain available. No new
package, service, cloud polling or local language model is needed.

Run `python -m unittest discover -s tests -v`. Focused tests cover committed creation,
failed persistence receipts, monotonic/UTC recovery, overdue/expired alerts, durable
cancellation, bounded retention, duplicate model calls, offline playback, muted
capture and chime suppression. TODO.md records actual API and hardware evidence.

The development device keeps F05 and all older environments. Roll back with:

```sh
sudo cp /var/backups/rpi-assistant-h03/f05.service /etc/systemd/system/rpi-assistant.service
sudo systemctl daemon-reload
sudo systemctl restart rpi-assistant
```

F05 does not run timers. The H03 database remains intact for returning to H03.
