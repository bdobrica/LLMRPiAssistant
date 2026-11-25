# Bounded release check — 2026-11-25

## Scope

This is a development-device assessment, not certification for general release.
The observed board is a Raspberry Pi Zero 2 W Rev 1.0 with 512 MB RAM
(415 MiB usable), the existing WM8960 ReSpeaker audio setup and ARM64 environment.
The initial voice revision is `7466ca2`; the focused app fix is `8e6db42` and
provisioning remains `19db050`. The bounded assessment is complete; continued
owner evaluation is supported, while the release boundaries below remain open.
No Pi 3 A+ was available for this pass. Its support remains unverified.

Keep the assistant usable during checks. Use synthetic prompts and temporary
SQLite/location files for API exercises; do not read household conversations or
export private configuration. A status sampler retains only state, timing and
resource counters, never the household records returned by the phone endpoint.
No new monitoring service, dashboard, dependency or CI platform is installed.

## Scenarios and evidence

| Scenario | Exact exercise | Evidence / limitation |
| --- | --- | --- |
| Everyday conversation | A one-sentence joke about fictional robot Pippin, then “What is its name?” | Live API retained the detail; owner also confirmed ordinary joke/follow-up speech |
| Shopping | Add synthetic blue marbles, add them again, remove them | Live tool calls left one item after duplicate addition and no active item after removal; isolated database |
| Reminder ambiguity | “Remind me to stretch at eight,” then “Instead, remind me to stretch in 90 seconds,” then cancel | First request wrote nothing and asked for AM/PM; second scheduled one reminder; cancellation removed it |
| Timers | Set a synthetic tea timer for 90 seconds, then cancel | Live model/tool path scheduled once and cancelled; isolated database |
| Local weather | Bucharest today, then “And tomorrow?” | Real Open-Meteo data, correct period/location, checked-at time and attribution |
| Current information | Latest stable Python and its release date, then ask which source was used | Real hosted lookup cited Python.org; response agreed with the independently opened [downloads page](https://www.python.org/downloads/) on this date |
| Transcription | Submit the bundled 4.05-second `unheard.wav` three times | All three transcripts preserved “wake” and “again”; synthetic clip, no household capture |
| Speech generation | Three short synthetic sentences | Completed WAVs of 2.65, 3.20 and 3.55 seconds; generation tested separately from acoustic acceptance |
| App action | Isolated explicit Dice bundle plus launch-intent classification | Passed, but initially missed the actual device's empty installed-app directory; see failure below |
| Physical controls | Owner tried button correction and long-hold mute/unmute | Joke/context and mute worked; after the Dice fix/install, the owner confirmed Dice and contextual correction without rerolling |
| Internet outage | Drop public IPv4/IPv6 output for the assistant UID for 180 seconds, preserving local/LAN traffic | Automatic restoration removed the rule; owner confirmed local timer/chime/Stop, mute/unmute and resumed spoken answers without restart |
| Abrupt process exit | Commit a one-second timer/reminder and Shopping item, exit without cleanup, open in another process, then cancel/remove and reopen again | Passed in a network namespace with no external route and temporary databases on the Pi; overdue records became `ringing`, cancellation/removal persisted, duplicate writes were prevented |
| Storage failure | Set those temporary databases read-only and attempt new timer/Shopping writes | Returned failure receipts, with no extra saved records; no actual SD power-loss test |

The API exercise produced 21 successful checks, including 18 Chat Completions
requests, one Responses lookup, three transcriptions and three Realtime outputs.
That count is this exercise's result, not a required future suite size.

Connectivity diagnostics recorded offline at 16:54:03 and restored at 16:57:08
Europe/Bucharest. The observer started after the rule was installed and made 202
successful local status requests over 209.45 seconds: median 39.795 ms, maximum
251.84 ms, zero failures. It saw the offline→online transition with capture active,
without a service restart. It sampled wake listening only; owner confirmation is
the evidence for the actual spoken/offline-control trial, not this polling trace.
The temporary firewall table was verified absent afterwards. This tests Internet
loss with Wi-Fi retained, not a fresh router association or Wi-Fi provisioning.

## Observed app failure and focused fix

The owner reported that “Roll a die” answered that no tool was available. A probe
using the actual app-discovery paths found **zero installed apps**, while the signed
catalog offered Dice, Ask and Truth or Dare. The plain request returned no local
response, and a classified launch of an uninstalled app also fell through to chat.
Earlier isolated tests explicitly supplied a Dice bundle, so they did not establish
that the actual service had it installed. There is no evidence that R02 uninstalled it.

The focused correction makes known-but-uninstalled app requests say which app is
missing and how to install it. It does not silently install or execute a catalog
entry. Existing installed-app routing, signature verification and bundle checksum
checks stay intact. Dice 0.1.0 was installed through the verified catalog for the
device retry. The owner confirmed “Yes, Dice and correction work.” This is recorded
with the focused fix `8e6db42` in TODO.md. The software gives guidance rather than
automatically installing a missing app; the test-device installation was explicit.

The fix passed 80 focused app/voice/context checks both locally and on the Pi.
The full local suite ran 242 tests: 241 passed and one optional external RPiFace
integration skipped. New checks cover a plain missing-app trigger, classified
missing/unknown launches and the same plain command after verified installation.

## Longer observation

The initial `7466ca2` service ran throughout a **1,204.30-second** observation
(20 minutes 4.3 seconds), with 239 samples at approximately five-second intervals.
It covered `LISTEN_WAKE`, `RECORD`, `PROCESSING` and `FOLLOW_UP`; all status requests
succeeded and the PID stayed unchanged with zero service restarts. This was a mixed
development workload: the voice trials, separate live SDK probe, native regression
tests and outage check overlapped. It is not a clean idle benchmark or a multi-day soak.

| Measurement | Result |
| --- | ---: |
| Assistant RSS range | 74.29–154.62 MiB |
| Minimum system available RAM | 89.77 MiB |
| Final assistant swap | 132.31 MiB |
| System swap-in / swap-out | 113,608 / 208,540 KiB |
| Assistant major page faults | 20,497 |
| Mean CPU, percentage of one core | 62.96% |
| Thread count | 19–20 |
| Local status median / p95 / maximum | 37.43 / 47.31 / 173.77 ms |

Paging occurred; separate probe/test processes contribute to system pressure.
Do not equate the lower RSS at the end with freed assistant memory. No responsiveness
failure was reported except the unrelated missing-app routing problem. One thermal
snapshot during the pass was 64.45°C with `get_throttled=0x0`; no thermal time series
was collected. Future ordinary-use observations should avoid concurrent developer
processes before attributing paging or latency to assistant allocations.

## Observed API usage and cost

Prices were checked against the official model/pricing pages on this date. These
are calculated sample charges, not an invoice or a prediction of household usage.
The counts exclude the owner's separate spoken trials, taxes, other account traffic
and any provider billing adjustments. Cache writes are included at their published
rate; this sample had no cache hits.

| Work | Observed usage | Estimated USD | Request latency |
| --- | --- | ---: | --- |
| GPT-6 Luna chat/routing/tools | 24,211 input, 442 output; 23,974 cache-write tokens | 0.00324145 | Median 1.149 s; range 0.722–1.820 s |
| GPT-6 Luna lookup | 8,681 input, 90 output; 4,495 cache-write tokens; one web search | 0.01102547 | 5.603 s |
| GPT-Transcribe | 12.15 seconds of input across three calls | 0.00091125 | Median 0.482 s; range 0.454–0.775 s |
| Realtime mini speech | 159 input text, 117 output text, 188 output audio tokens; 9.4 seconds of audio | 0.00413620 | Median 4.271 s; range 4.269–5.966 s |
| **Total** | This synthetic sample only | **0.01931437** | Not an end-to-end acoustic measurement |

Sources: [Luna pricing](https://developers.openai.com/api/docs/models/gpt-6-luna),
[transcription pricing](https://developers.openai.com/api/docs/models/gpt-transcribe),
[Realtime pricing](https://developers.openai.com/api/docs/models/gpt-realtime-2.1-mini),
[web-search pricing](https://developers.openai.com/api/docs/pricing).
Output text includes billed reasoning tokens; do not add them a second time.

Speech generation was the largest measured non-lookup stage in these short samples.
The current implementation waits for the entire audio response before playback.
If the owner finds waits intrusive, first measure wake-to-answer timing during real
use, then evaluate earlier playback; do not infer a guaranteed speedup or redesign
turn-taking from these isolated timings.

## Release boundaries

Prior completed items provide focused hardware evidence for boot/audio, contextual
conversation, interruption, timers/reminders, weather, privacy, phone settings and
provisioning. This pass supplements those records; it does not silently count their
old trials as rerun. The previous observed shutdown timeout still needs a focused
diagnosis before unattended upgrade reliability can be claimed.

This transition reproduced the delay: SIGTERM at 17:07:00 reached audio cleanup,
then systemd killed the old process at 17:08:30 before the corrected service started.
The new service became ready with capture active. A subsequent 60.39-second sample
covered wake listening, recording and processing: RSS 144.16–164.12 MiB, minimum
available RAM 126.06 MiB, median/p95 status latency 37.19/48.25 ms and zero failed
status requests. It recorded 13,272 KiB system swap-in and 33,184 KiB swap-out.
This is a short post-change check, not another 20-minute observation of the fix.

Remaining areas include Pi 3 A+, multi-day operation, abrupt power loss/clock
recovery, repeated router/AP changes, noisy rooms and far-field speech, multiple
users/languages, unsupported onboarding network types, and real provider quota or
regional failures. Existing trusted-LAN phone-control and privacy boundaries remain
as documented. Do not describe this device check as broad production readiness.
