# Reminders and Shopping (H04)

Use the assistant by voice or the existing [local phone page](local-controls.md).
The owner selected one shared **Shopping** list, one-off reminders, and
`Europe/Bucharest` as the initial reminder timezone.

## Everyday use

- “Add milk to my shopping list.” Repeating the same item keeps one entry. Case,
  whitespace and Unicode compatibility variants are normalized; quantities stay
  in the item text. “Milk” and “two litres of milk” are separate entries.
- “What's on my shopping list?” and “Remove milk from Shopping.” Reads use saved
  contents/IDs; changes are confirmed only after persistence succeeds. The phone
  page provides the same add/read/remove operations without Internet.
- “Remind me to check the oven tomorrow morning.” The assistant asks for an exact
  time. “At 8 PM” resolves that reminder using the current conversation. “Remind me
  to stretch in 30 seconds” creates a relative reminder. “Cancel that reminder”
  cancels the saved reminder; names/IDs distinguish multiple reminders.
- The phone page takes reminder text and an exact local date/time in the displayed
  configured timezone. It does **not** silently use the phone's timezone. It shows
  pending, ringing and missed reminders, with individual cancellation/dismissal.

At the scheduled instant, a reminder uses the existing local timer chime and shows
its text on the phone page. The reminder text is not read aloud by this version.
Alerts work without Internet; microphone mute keeps capture closed while alerts
remain audible at the configured speaker volume. Stop/the physical button dismisses
currently ringing timers and reminders, leaving future ones and Shopping intact.
The existing chime duration, capture suppression and fresh-wake behavior apply.

Spoken commands need the existing cloud transcription/model services. Dates are
interpreted by the model with an explicit current local timestamp; common vague
phrases and bare “at eight” requests are additionally blocked before scheduling.
Missing/invalid times, past dates, daylight-saving gaps and repeated clock times
require clarification. For a repeated clock time, choose the first or second
occurrence explicitly. Only one-off reminders within the next 366 days are
supported; recurring schedules and multiple named lists are outside H04.

## Timezone and persistence

```ini
[household]
timezone = Europe/Bucharest
state_path = ~/.local/state/rpi-assistant/household.sqlite3
```

**You can change the timezone in `config.ini`.** Use an installed IANA name such as
`Europe/London`, then restart the assistant. New interpretations and displayed
reminder times use the new zone. Already-saved reminders keep their UTC instant;
they are not rescheduled when the timezone changes. Invalid names are rejected
rather than silently falling back to another zone. Environment equivalents are
`HOUSEHOLD_TIMEZONE` and `HOUSEHOLD_STATE_PATH`; explicit file settings win.

The new SQLite file lives outside the checkout with restrictive permissions and
uses the existing timer transaction pattern. The H03 timer database is unchanged.
Creation/cancellation/list changes commit before a success receipt. Repeated tool
creation within a turn shares a request ID; identical active reminder text/instants
also deduplicate. Repeating an active Shopping item performs no extra write; removal
is idempotent while its retained record exists. After removal, a new add restores
one entry. Separate relative reminder requests can intentionally schedule different
instants. Check the saved list before retrying a request whose reply was lost.

Up to 32 reminders and 100 active shopping items are allowed; terminal reminder
records are bounded to 32 and removed-item records to 100. Restart retains schedules,
list contents and cancellations. Overdue pending reminders ring after startup;
previously exhausted alerts remain missed. Shopping remains available offline.
Reminder accuracy depends on the OS clock; after power loss these Pi boards need
network time or an RTC for reliable clock recovery. Alerts cannot ring while the
Pi/service is off. See [timer limitations](timers.md) for volume and storage failures.
Existing voice interaction logs and chat reset behavior remain unchanged; resetting
a conversation does not delete reminders or Shopping.

## Checks and rollback

Run `python -m unittest discover -s tests -v`. Focused tests cover restart,
cancellation, failed reads/writes and truthful receipts, duplicate prevention,
configuration precedence, timezone changes, daylight-saving gaps/repeated times,
offline HTTP controls and combined timer/reminder dismissal. TODO.md records real
model and Zero 2 W observations separately from simulated tests.

The development device preserves H03 and earlier environments:

```sh
sudo cp /var/backups/rpi-assistant-h04/h03.service /etc/systemd/system/rpi-assistant.service
sudo systemctl daemon-reload
sudo systemctl restart rpi-assistant
```

H03 does not expose Shopping or run reminders. The separate household database
remains available when returning to H04.
