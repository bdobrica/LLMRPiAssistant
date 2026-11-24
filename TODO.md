# Implementation TODO

Updated: 2026-11-24. [PLAN.md](PLAN.md) defines scope, architecture, hardware constraints, and release gates. [AGENTS.md](AGENTS.md) defines the contributor workflow.

## How to Use This Checklist

The owner already gets useful spoken answers and successful short follow-ups on the Zero 2 W. Preserve that working experience. Start with **F01** to address the reported difficulty remembering user-provided details, using a concrete failure example before choosing a fix. Install required dependencies, inspect the device revision, preserve configuration, and run relevant checks as part of that feature. There is no separate baseline, CI, benchmarking, or infrastructure milestone to finish first.

The order below expresses product priorities, not a requirement to finish every earlier task before delivering another useful feature. Fix a prerequisite only when it blocks the feature being implemented. Keep the 512 MB constraint and existing security safeguards throughout.

After each successfully implemented item, record a short validation note and commit the implementation with its tests/docs and checklist update. Keep incomplete items unchecked. Do not stage the local June code review.

## Now — Remember What I Tell You

- [ ] **F01 — Reliably use details I give during a conversation.** Reproduce a reported memory failure on the deployed version; distinguish same-session recall from recall after inactivity or restart. Use a harmless example with information the model cannot know independently, such as “My screwdriver is in the blue kitchen drawer,” then ask where it is and correct the location. Inspect which turns reach the model and fix the demonstrated context/routing/reset problem in the existing path. Verify both recall and correction, preserve the successful question/follow-up behavior, and add a focused regression test. Keep context bounded on the 512 MB Pi. If the expectation is recall across sessions, use C01 instead of assuming a short-term-context bug. GPT-Live, a voice-stack rewrite, and benchmark infrastructure are not prerequisites.

## Next — Make Conversation Pleasant and Useful

- [ ] **F02 — Let me interrupt or correct the assistant.** Stop stale playback, accept a correction, and avoid answering its own speaker output. Fix turn-boundary delays or premature cutoffs exposed by actual conversations. If repeating the wake word is a reported nuisance, add a short follow-up listening window; the successful follow-up report does not establish whether the wake word was repeated. Keep already executed actions distinct from cancelled speech.
- [ ] **F03 — Tell me when something goes wrong.** Give short, locally playable feedback for unheard speech, lost connectivity, and provider failures. Bound waits/retries and return to listening. Verify recovery after a failed request without replaying old answers.
- [ ] **F04 — Answer questions that need current information.** Connect search, retain evidence, and give concise attribution. Check consequential answers against authoritative guidance and handle unavailable/conflicting sources honestly. Detailed citation UI can come later.
- [ ] **F05 — Give me simple controls.** Add volume, stop, mute with truthful capture indication, and a new-conversation command. Close idle cloud sessions and show enough usage information to understand operating cost. Make local controls usable during internet loss without promising offline free-form speech recognition.

## Before Sharing More Widely

These protect household use; develop them alongside feature work using synthetic/non-sensitive questions where appropriate.

- [ ] **H01 — Keep conversations private.** Make transcript/reply logging opt-in across files and console/journal, retain content-free failure diagnostics, and bound log/audio retention with restrictive permissions and deletion. Do not commit household recordings.
- [ ] **H02 — Protect Wi-Fi onboarding.** Add per-device setup credentials and authenticated, CSRF-protected changes. Preserve automatic provisioning-service shutdown. Test malformed input, wrong passwords, and NetworkManager failure without exposing credentials.

## Then — Add Everyday Features

Choose the next feature from real use; these need not wait for every conversation refinement.

- [ ] **H03 — Set and cancel reliable timers.** Persist acknowledged timers, ring through internet loss, handle restart/overdue timers, and provide local cancellation. Announce creation only when scheduling succeeds.
- [ ] **H04 — Remember reminders and shopping-list items.** Persist changes, clarify ambiguous times using the configured timezone, and prevent duplicate writes. Test restart and failure behavior.
- [ ] **H05 — Tell me the weather here.** Use an explicitly configured location and a real data source. Handle stale/unavailable information without inventing forecasts.
- [ ] **H06 — Make setup manageable from a phone.** Add lightweight settings/status and microphone/speaker checks, recoverable configuration changes, and optional detailed citations. Do not require a browser on the Pi.
- [ ] **E01 — Play one enjoyable game.** Extend the existing apps with short trivia or collaborative storytelling, pause/resume/stop, and bounded state. Try it with someone before expanding the game framework.

## Optional — Personal Memory with SecondContext

Ordinary conversation must remain useful without this service. Run it on a separate host and commit sibling-repository changes separately.

- [ ] **C01 — Remember one explicit preference across sessions.** Add an optional adapter to SecondContext's actual non-streaming Responses/ingest contract, with authenticated subject identity and deliberate recent context. Update backend dependencies only as required for deployment. Demonstrate explicit remember/recall after restart, no duplicate ingestion, subject isolation, and ordinary answers when the service is down.
- [ ] **C02 — Let me correct and forget memories.** Do not silently retain all transcripts or sensitive facts. Implement authorized selective deletion or clearly expose its absence; confirm full purge and verify completion. Respect permanent subject fencing and document external-retention limits.
- [ ] **C03 — Answer questions about a household manual.** Ingest one selected manual on the backend and answer with cited passages. Keep documentary evidence separate from remembered conversations; handle irrelevant or conflicting evidence.

## Follow Up When a Working Feature Justifies It

- [ ] **R01 — Keep deployed models and dependencies supported.** Meet PLAN.md's provider shutdown deadlines, including legacy paths still in use. Test app-intent structured output and tool compatibility when changing models; never claim an app action succeeded after routing failure. Record tested ARM64 versions and verify openWakeWord API/patch compatibility before upgrading it.
- [ ] **R02 — Fix measured performance problems.** Keep one wake model and bounded buffers/context; optimize allocations, imports, or inference threads when observed latency/memory warrants it. Record simple before/after results on 512 MB hardware. Do not build a monitoring platform first.
- [ ] **R03 — Validate broader release readiness.** After the owner can use the features, expand to the PLAN.md scenarios, endurance checks, cost measurements, and both Zero 2 W and Pi 3 A+. Add lightweight CI if it prevents regressions encountered during development. Update setup and rollback guidance from actual deployments; record unsupported/untested configurations honestly.

## Existing Work to Preserve

D01–D06 describe source implementation, not a claim that every device has received or validated it. D07 records the owner’s actual device experience.

- [x] **D01 — Signed remote app catalogs** (`b5ccf23`) and bundle checksum verification.
- [x] **D02 — Safe bundle paths and manifest IDs** (`1b83125`, `61a5ddd`), with rejection tests.
- [x] **D03 — Audio processing worker and bounded configurable queue** (`43af12f`, `ee99660`). This does not yet provide interruption or natural follow-up listening.
- [x] **D04 — Idle/topic context reset** (`8876e8c`). Partial context management only; F01 must bound the context it uses; R02 addresses further measured resource problems.
- [x] **D05 — Optional RPiFace lifecycle and generic MCP integration** (`59b97c9`, `d725c62`); optional and not yet deployed on the inspected device.
- [x] **D06 — Existing Wi-Fi provisioning, LED driver, wake-word selection, app framework, and unit tests.** Retain these foundations; do not recreate them from stale TODO descriptions.
- [x] **D07 — Useful spoken answers and a short follow-up work on the device.** Owner report, 2026-11-24: “Is a 38.5 degrees C considered a fever?” followed by “What about a 39.5 degrees?” both produced answers the owner judged correct. Preserve this behavior; do not describe ordinary conversation as unimplemented. Reliable recall of supplied details, restart persistence, and wake-word-free continuation were not established by this report.

## Deferred Until There Is User Demand

Multiplayer speaker identification, leaderboards, achievements, marketplace expansion, local general-purpose LLMs, elaborate dashboards, broad refactors, and automatic extraction of every conversation. Revisit only when household use demonstrates a concrete benefit within the hardware and cost constraints.

## Completion Record

The initial B/V milestone checklist was replaced before implementation to prioritize deliverable features. Its useful testing, deployment, privacy, and compatibility work is included with those features or in H01/H02/R01–R03.

For each newly completed item, append a concise entry here: `ID — behavior delivered; checks and device/revision used; remaining limitations.` The implementation commit should mention the same ID. No new implementation milestones have been completed by creating these planning documents.
