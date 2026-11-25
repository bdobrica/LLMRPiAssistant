# Conversation retention on 512 MB devices

The assistant retains recent conversation in RAM. R02 preserves ordinary contextual
follow-ups while preventing long sessions and inactive conversations from growing
indefinitely. It does not add persistent personal memory or repair a demonstrated
short-conversation failure.

## Policy and configuration

The owner selected these defaults in `[openai]` in `rpi_assistant/config.ini`:

```ini
conversation_max_turns = 32
conversation_max_bytes = 262144
```

Restart the assistant after editing these settings. Environment fallbacks are
`OPENAI_CONVERSATION_MAX_TURNS` and `OPENAI_CONVERSATION_MAX_BYTES`; the file takes
precedence. Limits must be positive integers, with at least 1 turn and 1024 bytes.

An exchange includes a user question, assistant answer and any intervening tool
calls/results. The oldest exchanges leave context together when either limit is
reached. Bytes measure UTF-8 JSON of retained messages, excluding the fixed system
prompt and tool definitions. During a request, the current exchange occupies one
turn. The model is told when older context is unavailable, including that absent
receipts do not mean an action never happened. No summarization calls are added.

If one exchange alone exceeds the byte limit, a small omission notice replaces it.
An oversized final answer can still be spoken, but is not retained verbatim. An
oversized input or intermediate tool round stops before another model request and
uses the existing failure feedback. An action may already have run; its missing
result must not cause automatic replay. Interrupted/failed tool rounds retain an
explicit unknown-result receipt so the next request has paired tool messages.

Inactive context is discarded instead of copied into the former unused archive.
Existing idle/topic reset settings still apply; the owner's deployment keeps them
disabled. Explicit follow-ups still bypass those resets. New conversation and
Delete local conversation data clear history and the retention notice. Timers,
reminders, Shopping and other persisted settings are unaffected.

This bounds retained chat data, not every transient provider response or Python
allocation. Raising the limits increases RAM use and prompt cost. There is no
cross-restart chat memory; privacy logging remains a separate opt-in feature.

## Measurement method

On the Zero 2 W, a separate SDK client with a synthetic completion transport made
1,000 exchanges using unique questions and approximately 2 KiB answers. It made no
API calls, captured no household speech and did not retain fake request objects.
A second pass reset every ten exchanges. Values below include JSON punctuation;
the retained-byte measurement also includes the system prompt and empty archive
container for comparison with the old implementation.

| Synthetic check | Before | R02 |
| --- | ---: | ---: |
| Retained bytes at 1,000 active exchanges | 2,264,858 | 72,556 |
| Last-20 median request serialization | 55.25 ms | 1.92 ms |
| Probe RSS: start → 1,000 exchanges | 49.73 → 56.48 MiB | 50.88 → 50.89 MiB |
| Available RAM at 1,000 exchanges | 127.82 MiB | 134.28 MiB |
| Retained bytes after 100 resets | 2,276,632 | 75 |

These are short synthetic measurements, not an extended-use soak or a guarantee of
cloud response latency. Python may retain freed allocator pages. The running
service's RSS also depends on how many pages are swapped out; compare available
memory and paging activity alongside RSS. Running-service and spoken validation
are recorded in [TODO.md](../TODO.md).

Audio remains unchanged: one `hey_jarvis` model, five-second bounded capture queue,
one pending recording, 0.4-second pre-roll and ten-second maximum recording on the
tested device. No new imports, background threads, inference models or idle cloud
traffic are introduced. Pi 3 A+ and extended-duration behavior remain untested.

## Checks and rollback

Run the focused regressions with `PYTHONPATH=tests python -m unittest
test_openai_client test_config test_controls test_privacy`. The existing
`scripts/check-openai-models.py --live --config <config.ini> --follow-up-only`
performs paid synthetic contextual checks; microphone/speaker acceptance is separate.

The candidate uses an independent checkout and the existing ARM64 environment.
The previous voice checkout and provisioning service remain intact. On the tested
device, the private service snapshot is
`/var/backups/rpi-assistant-r02/h01.service`; restoring that unit, running
`sudo systemctl daemon-reload`, then `sudo systemctl restart rpi-assistant` restores
the previous voice implementation. Preserve current configuration changes when
rolling back. The old version retains its previous unbounded-history behavior.
