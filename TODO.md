# Implementation TODO

Updated: 2026-11-25. Decisions and scope: [PLAN.md](PLAN.md). Workflow: [AGENTS.md](AGENTS.md).

## Working Agreement

This is the remaining-work list. Delivered capabilities are documented in [the guides](docs/README.md); historical acceptance is retained in Git history and [the release assessment](docs/reference/release-check-2026-11-25.md). Preserve working conversation, offline controls and the 512 MB target.

Work in the order below before optional items. Implement one bounded item, record evidence and limits in its guide and completion update, and commit implementation/tests/config/docs/TODO together. Retire completed entries after that record exists. Keep unfinished items unchecked. Planning edits do not imply implementation or hardware acceptance. Preserve unrelated changes, credentials and rollback environments; do not commit the local code review.

## First: Easier Phone Administration

UI01 delivered port-80 access on the Zero 2 W. The owner confirmed the phone page, volume change and conversation. Offline access and live Wi-Fi onboarding remain unverified on this revision. See [phone access validation](docs/phone-setup.md#tested-on-the-zero-2-w).

UI02 split the phone controls into six linked pages. Thirteen focused tests passed.
A 360px Chromium trial used the local HTTP server and synthetic offline device
status. It exercised direct links, refresh, Back, draft retention across polling,
cancelled navigation, all three household forms and separate Settings/Privacy saves.
All network requests stayed on loopback. Physical phone and Pi use of the new layout
remain untested. See the [phone guide](docs/phone-setup.md#change-settings).

- [ ] **UI03 — Replace awkward controls with practical inputs.**
  - Replace louder/quieter and numeric volume entry with a percentage slider and speaker-mute toggle. Restore the prior audible volume on unmute; keep microphone mute separately labelled and truthful.
  - Reflect actual mixer state, including changes from voice/another phone. Bound slider writes, show errors honestly, and define visible behavior when moving the slider while muted.
  - Review remaining forms for appropriate inputs, readable timezone/date information, empty states, feedback and destructive-action confirmation. Keep existing data semantics.
  - **Accept:** phone volume/mute/unmute, voice-to-page state updates, mixer failure feedback and keyboard/touch controls work. Verify offline operation, microphone capture state and how speaker mute affects replies and timer/reminder chimes on the Zero 2 W.

- [ ] **UI04 — Mirror all supported INI configuration in the UI.**
  - Map every parsed option, including commented alternatives and named `mcp.server.*` sections. Cover audio/output, wake word, recording/buttons, models/provider keys, logging, LEDs, RPiFace, MCP, app sources/trust, controls, timers, household and weather.
  - Group basic/advanced fields with types, units and explanations. Preserve defaults, environment/file precedence and unknown entries; allow optional overrides to be removed deliberately. Keep keys write-only with configured status and explicit replacement/removal.
  - Extend Save & apply and persistent one-step Undo with field/cross-field validation, private atomic persistence, stale-edit detection and runtime recovery. Explain restart requirements before applying; safely handle binding, hardware and storage-path changes. Do not silently abandon existing household state or weaken app trust.
  - **Accept:** an option-to-UI coverage check against the parser/example finds no omissions; save/reload/restart round trips cover all setting groups and dynamic servers. Invalid input, failed apply, stale saves, secret redaction and Undo have focused checks. On the Pi, try representative live/restart settings, key replacement, recovery and a normal conversation. The separate Wi-Fi setup configuration is outside this item.

## Next: Faster Spoken Replies

- [ ] **S01 — Play generated speech incrementally.**
  - Feed existing Realtime audio chunks into playback before generation completes, with bounded buffering/backpressure and the tested WM8960 format. Preserve models, completed answer text, tool receipts and conversation history.
  - Carry cancellation through the provider session, queued chunks and player; never resume stale speech or replay actions. Preserve volume/mute, physical-button correction, local checks and timer/reminder alerts. Open the green follow-up window only after playback and echo guard finish.
  - Keep bounded deadlines and private audio cleanup. Handle empty streams, malformed audio, disconnects and partial playback with local feedback and recovery; do not automatically restart a partly spoken answer. Retain a selectable working fallback during validation.
  - **Accept:** focused chunk/order/bounds/cancellation/failure tests plus live streaming on the Zero 2 W. Compare repeated short/long replies before/after: end-of-question to first audible speech, first audio arrival, completion, memory and audible gaps. Confirm clear volume, interruption without duplicate actions, contextual follow-ups without echo, offline recovery and alert coexistence. Report variability and remaining limits. No fillers or filler-decision calls.

## Known Reliability Follow-Up

- [ ] **FIX05 — Resolve the reproduced shutdown hang.** Diagnose the approximately 90-second audio/service stop before systemd kills the process; do not assume the suspected locking cause is proven. Make shutdown release audio and workers reliably, preserve state, and validate repeated stop/start plus ordinary voice/control use on the Zero 2 W. Bring this fix forward only if it blocks the priority work above; it must be resolved before claiming reliable unattended upgrades.

Before broader distribution, expand validation to fresh-card setup, ordinary multi-day use, repeated router reconnection, power-loss/clock recovery, difficult acoustics and the Pi 3 A+ when available. Record exact scenarios, duration and limits in a dated report. These are release boundaries, not prerequisites to owner trials of the next feature.

## Optional: After the Priorities Above

- [ ] **E01 — Play one enjoyable game.** Extend existing apps with short trivia or collaborative storytelling, pause/resume/stop and bounded state. Try it with someone before expanding the framework.
- [ ] **C01 — Remember one explicit preference across sessions.** Integrate the external SecondContext service through its verified request/ingest contract, with authenticated subject/session identity and deliberate recent context. Demonstrate recall after restart, no duplicate ingestion, subject isolation and ordinary answers during outages.
- [ ] **C02 — Let me correct and forget memories.** Keep retention explicit; implement authorized correction/selective deletion or clearly expose unsupported operations. Verify full purge and completion responses, respect subject fencing and explain external-retention limits.
- [ ] **C03 — Answer questions about a household manual.** Ingest one selected manual externally and answer with cited passages. Keep documentary evidence separate from remembered conversations; handle irrelevant or conflicting evidence.

SecondContext is optional and runs off-device; backend changes belong in its repository. Speaker identification, marketplace expansion, local general-purpose LLMs and broad rewrites remain outside the current scope.
