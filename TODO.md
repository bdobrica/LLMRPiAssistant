# Implementation TODO

Updated: 2026-11-24. [PLAN.md](PLAN.md) defines scope, architecture, hardware constraints, and release gates. [AGENTS.md](AGENTS.md) defines the contributor workflow.

## How to Use This Checklist

Work in milestone order unless a dependency or imminent provider shutdown requires an explicitly documented change. Each ID is a bounded implementation item; split it into smaller IDs if it cannot be delivered and validated in one focused change. Future milestones are backlog, not prerequisites for starting the conversation demo.

Mark an item complete only after its acceptance criteria pass. Add a short validation note with the environment and remaining limitations, then commit the implementation and documentation together. Mention the item ID in the commit description; never mark untested hardware acceptance complete. Do not stage the local June code review.

## M0 — Establish the Baseline

- [ ] **B01 — Make local tests reproducible.** Document/install the development dependencies, including PyNaCl and the separate RPiFace prerequisite for the relevant integration test. Run the existing suite; distinguish missing dependencies, integration prerequisites, and actual failures. Add a lightweight automated check using the same commands.
- [ ] **B02 — Record a device baseline.** Capture revision, ARM64 OS/Python/package versions, audio configuration, RSS, swap I/O, CPU, and end-to-end timing on the Zero 2 W. Keep credentials and household transcripts out of results. Record the Pi 3 A+ as untested until measured.
- [ ] **B03 — Make device updates reversible.** Preserve local configuration and uncommitted work, retain a known-good dependency set/revision, deploy the newer fixes, and prove service startup plus rollback. A dependency refresh must not silently replace the working wake-word stack.
- [ ] **B04 — Establish acceptance scenarios.** Add at least 20 repeatable question/conversation/failure cases from PLAN.md, including the fever scenario, five-turn context, corrections, and local app commands. Record expected behavior and critical failures, not exact wording.
- [ ] **B05 — Add private diagnostics.** Record per-stage/first-audio latency, failures, buffer drops, resource snapshots, and provider usage without message content by default. Make transcript/response logging opt-in in both file logs and console/journal output; add bounded retention, restrictive permissions, and deletion checks. Audio artifacts must have a bounded lifecycle too.

## M1 — Ship the Conversation Demo

Prerequisite: reproducible baseline and acceptance cases. Start migration work early enough to meet the provider deadlines in PLAN.md. Retain existing app trust-boundary regression tests throughout.

- [ ] **V01 — Prototype supported streaming voice on the Zero 2 W.** Add a selectable GPT-Live path using existing capture/playback hardware, a compatible SDK, and bounded buffers. Measure resampling, echo, latency, memory, reconnects, and cost; preserve the existing path for comparison.
- [ ] **V02 — Select the primary voice path.** Compare the prototype with the PLAN.md targets and document the decision. If it fails, evaluate a supported Realtime or streamed pipeline; do not claim hardware compatibility from documentation alone. Avoid maintaining multiple production paths without a demonstrated need.
- [ ] **V03 — Migrate models and SDK requests.** Replace retiring chat, speech, and transcription models as applicable to the chosen path. Validate request parameters, structured output, tool calls, and ARM64 dependencies; update configuration examples and record the tested versions.
- [ ] **V04 — Make app-intent compatibility explicit.** Configure a supported intent model/capability path. Test unsupported response formats, malformed JSON, unknown app IDs, and API failure. Failed classification must never become a claim that an install/launch succeeded.
- [ ] **V05 — Implement a conversation session.** Add clear idle/listening/thinking/speaking/follow-up transitions, a configurable follow-up window, and explicit completion/inactivity closure. Demonstrate five turns after one wake word with visible/audible listening feedback.
- [ ] **V06 — Bound short-term context.** Remove the routine relevance-model call; limit recent messages/tokens and archived data, preserving complete tool exchanges. Add a new-conversation command and tests for long same-topic sessions, topic changes, and retention expiry.
- [ ] **V07 — Fix turn boundaries and re-listening.** Replace the fixed drain/30-chunk dead period with measured handling of playback tail and stale audio. Evaluate lightweight VAD/noise handling, natural pauses, silence-only input, and questions exceeding ten seconds. Verify that the assistant does not transcribe its own reply.
- [ ] **V08 — Support interruption and cancellation.** Stop playback promptly, discard stale queued output, and handle corrections during a response. Define what happens to in-flight tools; never duplicate an action on retry or treat interrupted speech as proof the action was cancelled.
- [ ] **V09 — Provide failure feedback and recovery.** Add packaged local prompts for unheard speech, lost connection, provider timeout/rate limit, and playback failure. Set bounded request/retry budgets, return to a usable state, and test reconnects without replaying obsolete answers.
- [ ] **V10 — Tune spoken answer behavior.** Prefer concise useful answers, offer elaboration, and ask relevant clarification without interrogating the user. Evaluate the fever scenario against current authoritative guidance, including different ages/symptoms, uncertainty, and appropriate escalation.
- [ ] **V11 — Add grounded information lookup.** Wire a supported search tool for current questions and authoritative evidence where needed. Retain source metadata, speak brief attribution when useful, and test unavailable/conflicting sources plus malicious instructions embedded in retrieved text.
- [ ] **V12 — Add local control and session limits.** Implement volume, stop, microphone mute, accurate capture indicators, inactivity closure, and configurable session/usage limits. Verify local/physical controls during internet loss and report limits of offline voice commands.
- [ ] **V13 — Ship a low-memory device profile.** Explicitly select one wake model, bound audio/context/tool buffers, and reduce measured allocation/import/inference overhead. Test openWakeWord upgrades and patch compatibility separately. Record peak RSS, MemAvailable, and swap activity during conversation.
- [ ] **V14 — Validate and document the demo.** Run the PLAN.md scenarios, latency/cost measurements, 100-turn endurance, and overnight idle/reconnect checks on the Zero 2 W and Pi 3 A+. Update setup/troubleshooting instructions. Leave this item open if a required board or gate has not been tested.

## M2 — Make It Useful in a Household

Prerequisite: M1 conversation acceptance. Provisioning protection may be implemented earlier and is required before a shared household pilot.

- [ ] **H01 — Protect Wi-Fi setup.** Generate per-device setup credentials, authenticate configuration changes, add CSRF protection, and restrict the provisioning lifecycle. Preserve and test existing service shutdown after connection. Test invalid SSIDs, wrong passwords, command failures, and recovery without leaking credentials in exceptions/logs.
- [ ] **H02 — Simplify setup and audio selection.** Provide a lightweight phone-accessible settings/status interface with microphone/speaker checks, device selection, volume, model settings, and privacy controls. Validate changes and recover from bad configuration; expose citations from V11 without requiring a browser on the Pi.
- [ ] **H03 — Implement persistent timers.** Support create/list/cancel, reliable alarms during internet loss, restart recovery, and local cancellation. Define overdue-timer behavior and test it; announce creation only after successful scheduling.
- [ ] **H04 — Implement reminders and shopping lists.** Persist acknowledged changes, clarify ambiguous times using the configured timezone, prevent duplicate writes, and recover after restart. Test rejected writes and unavailable speech services.
- [ ] **H05 — Add location-aware weather.** Use an explicit user-configured location and a real provider/tool. State freshness, handle unavailable data, and avoid fabricated forecasts.
- [ ] **H06 — Run a household pilot.** Have someone other than the developer complete setup and representative daily tasks. Record practical failures, latency, cost, and privacy feedback; fix the highest-impact blockers before expanding scope.

## M3 — Optional SecondContext Integration

Prerequisite: M1; keep this off the critical path for ordinary conversation. Use a separate server, and commit changes to the sibling repository separately.

- [ ] **C01 — Verify and prepare the backend.** Update SecondContext's supported Go/model dependencies, configure authentication and deployment separately, and measure latency/availability. Verify its current contract rather than assuming full OpenAI API compatibility.
- [ ] **C02 — Add an optional adapter.** Support the non-streaming Responses contract, voice instructions, stable subject/session identity, and deliberate recent-turn input without duplicate ingestion. Preserve local tools and fall back to normal answers on bounded backend failure.
- [ ] **C03 — Implement explicit remember and recall.** Start with user-approved preferences/household facts. Verify persistence across restart, subject isolation, source provenance, and correction of stale facts. Do not automatically retain health discussions or all transcripts.
- [ ] **C04 — Implement truthful memory deletion.** Confirm destructive requests and verify backend completion. Resolve selective deletion with an authorized endpoint change if needed: current service scope does not grant individual-memory deletion. Handle permanent subject fencing after full purge and document backup/provider-retention boundaries.
- [ ] **C05 — Add household reference knowledge.** Ingest selected manuals on the backend, retrieve cited passages, and distinguish documentary sources from remembered conversations. Test irrelevant, stale, and conflicting evidence plus backend outages.

## M4 — Lightweight Entertainment

- [ ] **E01 — Ship one polished conversational game.** Use existing app interfaces for short trivia or collaborative storytelling, with pause/resume/stop and bounded state. Test interruptions and game-to-general-question transitions on the baseline Pi before adding more games.

## Existing Work to Preserve

These describe source implementation, not a claim that every device has received or validated it.

- [x] **D01 — Signed remote app catalogs** (`b5ccf23`) and bundle checksum verification.
- [x] **D02 — Safe bundle paths and manifest IDs** (`1b83125`, `61a5ddd`), with rejection tests.
- [x] **D03 — Audio processing worker and bounded configurable queue** (`43af12f`, `ee99660`). This does not yet provide interruption or natural follow-up listening.
- [x] **D04 — Idle/topic context reset** (`8876e8c`). Partial context management only; V06 handles remaining unbounded histories/archives.
- [x] **D05 — Optional RPiFace lifecycle and generic MCP integration** (`59b97c9`, `d725c62`); optional and not yet deployed on the inspected device.
- [x] **D06 — Existing Wi-Fi provisioning, LED driver, wake-word selection, app framework, and unit tests.** Retain these foundations; do not recreate them from stale TODO descriptions.

## Deferred Until There Is User Demand

Multiplayer speaker identification, leaderboards, achievements, marketplace expansion, local general-purpose LLMs, elaborate dashboards, broad refactors, and automatic extraction of every conversation. Revisit only when household use demonstrates a concrete benefit within the hardware and cost constraints.

## Completion Record

For each newly completed item, append a concise entry here: `ID — behavior delivered; checks and device/revision used; remaining limitations.` The implementation commit should mention the same ID. No new implementation milestones have been completed by creating these planning documents.
