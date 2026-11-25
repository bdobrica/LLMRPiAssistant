# What the assistant remembers

The assistant uses recent conversation to understand follow-ups such as
“What's a manifold?” → “What about a compact manifold?” → “What about a cube?”
You don't need to repeat the whole question each time.

## Recent conversation, not permanent memory

It keeps up to **32 recent exchanges**, also limited to **256 KiB** of conversation
data. An exchange includes your question, its answer and any tool results.
When either limit is reached, the oldest complete exchanges leave context.
Very large individual results may be replaced with an omission notice.

Chat memory does not survive restarting the assistant. **New conversation** on the
phone (or by voice) clears it. Saved timers, reminders, Shopping and weather city
are separate and survive. Optional conversation logs are not used as recall memory.

Starting a new wake-word request may also reset context after an idle period or
a topic change, depending on configuration. Follow-up questions during green
retain the conversation. The example config uses a five-minute idle timeout and
a relevance check; the tested owner's setup disables those resets.

## Adjust it if you need to

In `rpi_assistant/config.ini`, then restart:

```ini
[openai]
conversation_max_turns = 32
conversation_max_bytes = 262144
# Set both to zero to disable automatic idle/topic resets:
conversation_idle_timeout_seconds = 0
conversation_relevance_threshold = 0
```

Larger history can use more RAM and increase API costs on a 512 MB Pi. The limits
bound retained chat, not all memory used by the program. There are no extra
summarisation calls or hidden archive. Keep the defaults unless you have a reason
to change them.

If an old detail has left context, tell the assistant again. Missing memory doesn't
undo an action: check the phone's timer/reminder list before repeating a request
whose result you didn't hear. See [privacy](conversation-privacy.md) for deletion,
and [TODO](../TODO.md) for the measured retention changes.

[Back to the guides](README.md)
