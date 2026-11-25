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

On **Home**, drag **Speaker volume** or use the arrow keys. Release the slider
to apply the level. The displayed percentage follows the mixer, including changes
from another phone or a spoken command such as “set volume to 70 percent.”

**Mute speaker** sets output to zero for replies, timers and reminders. The
microphone can still hear you. **Unmute speaker** restores the channel levels
saved when you muted. Moving the slider above zero chooses a new audible level.
If the mixer was already at zero and there is no saved level, unmute starts at 25%.
The phone works offline. Spoken controls, including “unmute the speaker,” require
Internet for transcription.

Steady red means the assistant has closed microphone capture. Wake words cannot
work while muted: unmute with the phone or button. Mute survives an assistant restart.
It is a software mute for this assistant, not a physical microphone disconnect.

Muting the microphone still allows timer and reminder chimes. Volume across
reboots follows the Pi's ALSA mixer settings.

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

On the Zero 2 W, an isolated copy of the controls exercised the WM8960 mixer
without an Internet route. Mute took both channels from 117 (68%) to zero.
A bundled spoken clip and both alert types played with the channels at zero
and microphone capture running. Unmute restored both channels to 117. These
were device readings. Room sound and a physical phone were not measured.

[Back to the guides](README.md)
