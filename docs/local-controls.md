# Volume, mute and a fresh conversation

The [phone page](phone-setup.md) gives you volume, **Stop**, microphone mute and
**New conversation**. It works without Internet while your phone and Pi remain
on the same local network.

## Use the HAT button

| Gesture | What happens |
| --- | --- |
| Short press during a reply | Stops speech; wait for green to give a correction |
| Short press at other times | Stops pending output or discards partial recording |
| Hold for 1.5 seconds | Mutes or unmutes the microphone |
| Short press during a chime | Dismisses all currently ringing timers/reminders |

The button needs enabling as described in [button interruption](button-interruption.md).

## Change volume or mute

Use the phone's volume control, or say “volume down” or “set volume to 70 percent”
after the wake word or during green. Spoken commands still require cloud transcription;
use the phone or button when Internet is unavailable.

Steady red means the assistant has closed microphone capture. Wake words cannot
work while muted: unmute with the phone or button. Mute survives an assistant restart.
It is a software mute for this assistant, not a physical microphone disconnect.

Speaker volume and microphone mute are separate. Muting the microphone does not
silence timer/reminder chimes; setting speaker volume to zero does. Volume persistence
across reboot follows the Pi's ALSA mixer settings.

## Start a new topic

Choose **New conversation** or say “start a new conversation.” This clears recent
chat context. Timers, reminders, Shopping, settings and saved logs stay intact;
use the separate [privacy deletion](conversation-privacy.md) action to remove logs.
An active voice game is separate too—say “cancel app” to leave it.

Stop and reset suppress stale replies, but an action already sent may finish.
If the page reports a pending reset, wait for the current request to finish.

## Match the volume control to your speaker

For the tested HAT, `rpi_assistant/config.ini` uses:

```ini
[controls]
mixer_card = seeed2micvoicec
mixer_control = Speaker
```

Use `Headphone` for the 3.5 mm output. Restart after manual edits.
Keep the [phone page's network access limits](phone-setup.md#who-can-use-the-page)
in mind when taking the assistant to an event.

[Back to the guides](README.md)
