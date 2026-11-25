# Your conversations and privacy

Wake-word detection runs on the Pi. Answering a spoken request sends the recorded
speech to OpenAI for transcription, then sends text/context for answers and speech
generation. Search and weather contact their providers when used. This is not a
fully offline assistant.

## What stays on the Pi?

Conversation text logging is **off by default**. Recent chat stays in memory for
follow-ups; [memory limits](conversation-retention.md) explain when it leaves context.
Normal diagnostics keep failure categories and usage counts, not your words.

Command recordings and generated replies are deleted after the turn, including
failures and cancellations. Phone audio checks stay local and delete their samples.
Startup also clears abandoned assistant audio. Bundled chimes/prompts are retained.

Timers, reminders, Shopping and your chosen weather city are saved separately so
they survive restarts. API keys and the settings undo file are private too; don't
include them when sharing the project or asking for help.

## Choose whether to save conversation text

On the phone, enable **Save conversation text and source evidence** in Settings,
then choose **Save & apply**. This writes private files, not console/system-journal
content. Turning it off stops new conversation entries but doesn't delete old ones.

By default, logs are limited to seven days and 1 MiB in total; old records are
removed first while the assistant runs. Manual settings are:

```ini
[logging]
conversation_logging = false
retention_days = 7
max_bytes = 1048576
```

Restart after editing the configuration directly. These limits cover interaction
diagnostics too, not just optional conversation text.

## Delete local conversation data

When the assistant is idle, choose **Delete local conversation data** on the phone
and confirm. It clears recent chat memory, this installation's interaction log
and assistant-owned temporary audio. It preserves timers, reminders, Shopping,
weather city, settings, keys and the settings undo file.

**New conversation** only clears chat memory; it does not delete saved logs.
Neither action deletes provider-side records, extension data, backups, other
installations or old system journals. Earlier versions logged text, so review
historical files before sharing a device. File deletion is not secure SD-card erasure.

For actual capture mute and the red indicator, see [everyday controls](local-controls.md).
The [phone page](phone-setup.md#who-can-use-the-page) itself is for a trusted network.

[Back to the guides](README.md)
