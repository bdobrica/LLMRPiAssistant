# Conversation privacy (H01)

Conversation text is **not logged by default**. The assistant keeps content-free
events, token counts, audio duration and failure categories for troubleshooting.
Transcripts, replies, queries, source URLs and retrieved evidence stay out of these
records and console output. Provider debug logs and MCP subprocess stderr are
suppressed because they can contain request data. Conversation history remains in
RAM to support follow-ups; cloud requests still send the necessary audio/text to
the configured providers.

## Optional private logs

In the phone page's Settings, enable **Save conversation text and source evidence**
and choose **Save & apply**. Undo restores the prior setting. Alternatively use:

```ini
[logging]
conversation_logging = false
retention_days = 7
max_bytes = 1048576
```

Opting in writes content only to the configured `log_file`, never the console or
system journal. Files use owner-only permissions (0600). Disabling stops new content
records; existing records expire or can be deleted. The age limit applies to all
interaction records, including diagnostics; the default size cap is 1 MiB. Oldest
records are discarded first. Individual oversized records omit content. Maintenance
runs on startup, writes and every minute while running; an inactive installation
does not run cleanup. Atomic replacement can temporarily require another file of
up to the same cap. Allowed limits are 1–30 days and 4 KiB–16 MiB. The legacy
`log_level` setting does not enable conversation logging or provider debug output.

## Audio and deletion

Command recordings and generated speech are removed after each turn, including
failed or cancelled turns. Audio checks remove their local samples after playback.
Files are created owner-only; startup removes abandoned assistant recordings and
speech, and idle maintenance retries stale temporary cleanup. Bundled chimes and
prompts are retained. Cleanup failures appear in the phone privacy status.

Choose **Delete local conversation data** and confirm while no request or audio
check is running. This clears active/archived conversation memory, this installation's
interaction log and assistant-owned temporary audio. Timers, reminders, Shopping,
saved weather city, settings, keys and the configuration undo snapshot are preserved.
Useful content-free diagnostics may be written again on the next turn.

The button does **not** erase historical system-journal entries, files in other
installations/backups, extension-owned data or provider-side records. Older versions
logged conversation text: review those archives separately before sharing logs or
devices. File deletion is not secure media erasure. New conversation clears memory
only; it is distinct from this deletion action. The phone page retains its trusted-LAN
access model; see [phone setup](phone-setup.md).

## Validation and recovery

Run `python -m unittest discover -s tests -v`; privacy checks use synthetic text,
temporary storage, failure injection and a subprocess that attempts to echo tool
arguments. Pi and owner checks are recorded in TODO.md. Pi 3 A+ and extended operation
remain untested. The H06 checkout and private service/configuration remain available:

```sh
sudo cp /var/backups/rpi-assistant-h01/h06.service /etc/systemd/system/rpi-assistant.service
sudo systemctl daemon-reload
sudo systemctl restart rpi-assistant
```

Rolling back also restores the old logging behavior; it cannot restore deleted data.
