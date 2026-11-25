# Keep the conversation going

Start with **“Hey Jarvis, what's a manifold?”** After the answer, wait for steady
green lights and say **“In mathematics.”** After the next answer and green light,
try **“What about a cube?”** Only the first question needs the wake word.

## Watch the lights

Steady green means the assistant is ready for your next sentence. There is a short
pause after playback before green appears, so it does not record its own speaker.
Words spoken during that pause or over the answer are discarded.

The window lasts six seconds by default. Once you start speaking, you can finish
your sentence within the normal recording limit. Staying quiet closes the window
without a reply and returns to blue wake listening. Say “Hey Jarvis” to begin again.

## Make the window suit you

On the [phone page](phone-setup.md), change **Follow-up listening** and choose
**Save & apply**. Zero turns it off; every question then needs the wake word.
For a manual configuration change:

```ini
[recording]
follow_up_window_seconds = 6.0
```

Restart the service after editing `rpi_assistant/config.ini` directly.
A quiet window makes no cloud request. Speech detection runs locally, but a nearby
TV or another person can trigger it; the assistant does not identify your voice.

## If a follow-up is missed

Wait for steady green before speaking. If blue has returned, use the wake word.
In a busy room, shorten or disable the window. To cut an answer short, use the
[button](button-interruption.md); speaking over playback is not supported.
Follow-ups reuse [recent conversation](conversation-retention.md), not permanent memory.

[Back to the guides](README.md)
