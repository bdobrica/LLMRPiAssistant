# Set a timer

Try **“Set a tea timer for five minutes.”** Then ask **“How much time is left on
my tea timer?”** or **“Cancel the tea timer.”** Giving timers names helps when
several are running. Durations can be one second to seven days.

On the [phone page](phone-setup.md), enter minutes/seconds and an optional name.
You can see pending, ringing and missed timers, and cancel individual timers.
The phone route works without Internet; spoken requests need it.

## When time is up

A local chime repeats for up to two minutes. Press the button or phone **Stop**
to dismiss all currently ringing alerts. Future timers keep running. After the
chime stops, use the wake word for your next question.

Amber indicates an alert unless the microphone is muted, when red remains.
Microphone mute does not silence timers. Speaker volume applies: at zero volume,
you won't hear the chime. Calling out over the chime is not a supported stop control.

## What survives a restart?

A timer is saved before the assistant confirms creation. Saved timers and
cancellations survive a restart; an overdue pending timer rings on startup.
An alert that already finished remains visible as missed rather than ringing again.
If you lost the spoken confirmation, check the phone list before creating it again.

Timers cannot ring while the Pi is off. After power loss, these boards need a
correct clock—usually from network time or an added battery-backed clock—to know
how much time passed. Don't rely on this prototype as your only critical alarm.

## Change the chime duration

Edit `rpi_assistant/config.ini` and restart:

```ini
[timers]
alert_seconds = 120
```

The range is 1–600 seconds. Up to 32 timers can be active. State is stored outside
the code folder in `~/.local/state/rpi-assistant/timers.sqlite3`. Starting a new
conversation or deleting conversation logs does not erase timers.
For a task at a particular date/time, use [reminders](household.md).

[Back to the guides](README.md)
