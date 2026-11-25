# Stop an answer and correct it

Ask for an explanation, then **press the ReSpeaker button while the answer plays**.
When the lights turn steady green, say **“Explain it for a ten-year-old.”**
The assistant uses the conversation so far to answer your correction.

Stay quiet to leave the correction window. Blue returns and the next question
needs the wake word. A correction window also works when ordinary follow-ups are off.

## Enable the button

The quick start enables the user button on the ReSpeaker 2-Mic HAT. For an existing
installation, set these entries in `rpi_assistant/config.ini`, then restart:

```ini
[recording]
interrupt_button_gpio = 17
correction_window_seconds = 6.0
```

`17` is the HAT button's BCM GPIO number. `-1` disables it. Don't select another
pin unless you know how your hardware is wired.

## What stopping does

The speaker stops and the old answer will not resume. Stopping does **not** undo
an action: a timer may already be saved or a die already rolled. Ask “What was the
result?” to refer to that result; asking for another roll requests a new action.

Outside speech playback, a short press stops pending output or discards a partial
recording. Holding for 1.5 seconds toggles [microphone mute](local-controls.md).

This is button interruption. Calling out “stop” across the room during playback
does not interrupt it. Wait for green before speaking your correction; there is
no acoustic echo cancellation, and nearby speech can enter that window.

[Back to the guides](README.md)
