# Reminders and a Shopping list

## Keep a shared Shopping list

Try **“Add milk to my shopping list.”** Say it again, then ask **“What's on my
shopping list?”** Milk appears once. Say **“Remove milk from Shopping”** to remove it.

There is one shared list. Differences in capitalisation or extra spaces don't
create duplicates, but “milk” and “two litres of milk” are different item texts.
The [phone page](phone-setup.md) also lets you add, read and remove items offline.
Up to 100 items can be active.

## Ask for a reminder

Say **“Remind me to stretch in 30 seconds.”** For a calendar reminder, try
**“Remind me to check the oven tomorrow at 8 PM.”** Vague times such as “tomorrow
morning” or “at eight” prompt for clarification. Use the next green window to answer.

On the phone, enter the reminder text and an exact date/time. Check the displayed
timezone—it belongs to the assistant, and may differ from your phone's timezone.
You can see pending/missed reminders and cancel individual ones. Spoken cancellation
also works: “Cancel my stretch reminder.”

A reminder is acknowledged only after saving succeeds. If the reply was lost,
check the list before trying again. Reminders are one-off, within the next 366 days;
recurring schedules and multiple named shopping lists are not supported.

## When a reminder is due

The Pi plays the same local chime as a timer and shows the reminder text on the
phone page. **It does not read the reminder text aloud.** Use the button or **Stop**
to dismiss all currently ringing alerts. Future reminders remain scheduled.

Chimes and the saved list work without Internet. Voice requests need cloud services.
Microphone mute does not silence the chime; speaker volume does. Schedules, list
contents and cancellations survive restart. Overdue pending reminders ring at startup;
clock and power limits are the same as for [timers](timers.md).

## Choose your timezone

Use **Settings → Reminder timezone** on the phone, or edit this section of
`rpi_assistant/config.ini` and restart:

```ini
[household]
timezone = Europe/Bucharest
```

Use an IANA timezone name such as `Europe/London`. Changing it affects new requests
and displayed times; existing reminders keep the same scheduled instant.
Ambiguous or nonexistent times around daylight-saving changes need clarification.

The Pi keeps up to 32 active reminders. Saved household data lives in
`~/.local/state/rpi-assistant/household.sqlite3`; New conversation and conversation-data
deletion leave it intact.

[Back to the guides](README.md)
