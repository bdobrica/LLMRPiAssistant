# Implementation TODO

Updated: 2026-11-24. Product decisions: [PLAN.md](PLAN.md). Contributor workflow: [AGENTS.md](AGENTS.md).

## Working Agreement

Useful spoken answers and contextual follow-ups already work on the owner's Zero 2 W. Preserve them. No short-term-memory defect has been demonstrated; no conversational-memory rebuild is scheduled.

**Proposed next feature: F06, follow-up listening without another wake word.** Keep the 512 MB target throughout. Handle concrete prerequisites within delivery, with no separate baseline, CI, benchmarking, or evaluation-platform milestone. The order below is a recommendation for review, not a requirement to finish every earlier item before another useful feature.

For each completed item, record validation evidence and commit implementation, relevant tests/config/docs, and checklist update together. Keep unfinished items unchecked. Never stage the local June code review or credentials. Planning changes do not count as runtime implementation; a local commit is not deployment approval.

## Next Feature: Natural Follow-Up Listening

- [ ] **F06 — Ask a follow-up without repeating the wake word.**
  - Add a configurable, disableable listening window after playback finishes, reusing existing conversation history.
  - Capture a follow-up during that window; expire quietly back to wake-word detection on silence. Avoid idle cloud traffic and reacting to the assistant's own playback.
  - Review drain/flush timing and the newer topic/idle resets against this experience. Preserve demonstrated context behavior; do not silently introduce additional context loss when deploying newer code.
  - **Acceptance:** on the Zero 2 W, try manifold → compact manifold → cube without another wake word, let the window expire, and start a fresh interaction normally. Check silence, disabled-window behavior, and speaker echo. Record observations and limitations; interruption belongs to F02.
  - **Testing:** focused state-transition tests and an explicit live OpenAI test for contextual answers. Keep API quality checks separate from microphone/playback checks. Judges are optional; SecondContext is not required.

## Concrete Fixes Accompanying Delivery

These are reproduced defects or compatibility failures, not a general hardening phase. FIX01 is required to run the current checkout on the Pi. Resolve FIX02 before relying on app-installation rejection. FIX03 protects the working environment during installation/update work.

- [ ] **FIX01 — Start successfully with RPiFace disabled.** Fix the self-referential annotation that raises NameError under Python 3.13.5. Add an import regression check independent of whether RPiFace is enabled. Run lifecycle client tests; separately identify the optional rpiface MCP test prerequisite.
- [ ] **FIX02 — Never load a rejected app bundle.** Clean staging after checksum/download failure and exclude incomplete/staging directories from discovery. **Acceptance:** a validly signed catalog with an altered bundle is rejected, and restarting AppManager neither imports it nor disrupts a previously installed app. Retain signature, path, and manifest checks.
- [ ] **FIX03 — Preserve a working wake-word dependency set.** Record/constrain tested versions for the Pi; deployed openWakeWord is 0.4.0, while the import fails against 0.6.0. Keep the working version unless deliberately testing newer exports, assets, inference dependencies, and patch behavior. **Acceptance:** actual package import/model loading and wake detection on the Pi; mocked audio tests alone are insufficient.

## Next Experience Improvements

- [ ] **F03 — Tell me when a request fails, then recover.** Bound provider timeouts/retries and give short locally playable feedback for unheard speech or a failed request. Reuse existing offline/online prompts where appropriate. **Acceptance:** inject transcription/model/TTS failure, return to listening, and handle a subsequent request without replaying stale audio.
- [ ] **F02 — Let me interrupt or correct the assistant.** Stop stale playback and accept a correction without responding to speaker echo or duplicating an executed action. **Acceptance:** interrupt an answer on the Pi, give a correction, and hear an answer using the updated context. Report physical-control and speech-interruption support separately.
- [ ] **F04 — Answer questions requiring current information.** Connect a real lookup source, retain evidence, and give concise attribution. **Acceptance:** answer using retrieved evidence and handle unavailable/conflicting sources honestly. Treat retrieved text as evidence, not executable instructions; detailed citation UI can follow.
- [ ] **F05 — Give me simple controls.** Add volume, stop, mute with truthful capture indication, and explicit new-conversation control. Provide local control paths during internet loss. **Acceptance:** verify advertised controls on hardware, including whether capture actually stops; do not promise offline free-form recognition.

## Everyday Use and Entertainment

Choose the next complete feature from actual use; these can proceed independently of optional memory work.

- [ ] **H03 — Set and cancel reliable timers.** Persist acknowledged timers, ring through internet loss, handle restart/overdue timers, and provide local cancellation. Announce creation only after scheduling succeeds.
- [ ] **H04 — Keep reminders and shopping lists.** Persist changes, clarify ambiguous times using the configured timezone, and prevent duplicate writes. Test restart, cancellation, and failure behavior.
- [ ] **H05 — Tell me the weather here.** Use an explicitly configured location and real data source. Handle stale/unavailable information without inventing forecasts.
- [ ] **E01 — Play one enjoyable game.** Extend existing apps with short trivia or collaborative storytelling, pause/resume/stop, and bounded state. Try the experience with someone before expanding the framework.
- [ ] **H06 — Make setup manageable from a phone.** Add lightweight settings/status and microphone/speaker checks with recoverable configuration changes. No browser is required on the Pi.

## Before Wider Household Use

Develop these alongside useful features, using synthetic/non-sensitive conversations for testing.

- [ ] **H01 — Keep conversations private.** Make transcript/reply logging opt-in across files and console/journal. Retain content-free diagnostics; bound log/audio retention and provide deletion and restrictive permissions. Verify default logs omit conversation contents.
- [ ] **H02 — Protect Wi-Fi onboarding.** Redact submitted passwords from command errors, add per-device setup credentials and authenticated/CSRF-protected changes, and preserve provisioning-service shutdown. Test malformed input, wrong passwords, and NetworkManager failures without exposing credentials.

## Maintenance Tied to Working Features

- [ ] **R01 — Replace models before provider shutdowns.** Recheck PLAN.md's announced dates: TTS and chat in January 2027, transcription in February 2027. Use live OpenAI tests to compare affected behavior, including contextual follow-ups and app/tool compatibility. Record models and tested SDK versions; preserve a recoverable configuration. This maintenance must not wait for optional features.
- [ ] **R02 — Address measured performance and retained-state growth.** Keep one wake model and bounded audio buffers. Replace unbounded active/archive retention with a deliberate policy preserving the agreed conversation experience; the RAM archive is not persistent memory. Optimize allocations/imports/threads when measurements justify it, recording before/after observations on 512 MB hardware.
- [ ] **R03 — Validate broader release readiness.** After features are usable, expand everyday scenarios, longer-use/reconnection checks, cost observations, and validation on both boards. Derive useful targets from actual results. Record untested configurations; add lightweight CI if it prevents encountered regressions. Do not build a monitoring or judging platform as a prerequisite.

## Optional Personal Memory with SecondContext

Ordinary conversation and OpenAI integration tests must work without this service. Its non-streaming Responses endpoint already exists. Coordinate further compatibility when the integration needs it; backend changes belong in their own repository.

- [ ] **C01 — Remember one explicit preference across sessions.** Add an optional adapter to the actual Responses/ingest contract, with authenticated subject/session identity and deliberate recent context. Run the backend elsewhere. Demonstrate recall after restart, no duplicate ingestion, subject isolation, and ordinary answers during outages.
- [ ] **C02 — Let me correct and forget memories.** Keep retention explicit. Implement authorized selective deletion or clearly expose its absence; confirm full purge and verify the matching completion response. Respect permanent subject fencing and explain external-retention limits.
- [ ] **C03 — Answer questions about a household manual.** Ingest one selected manual on the backend and answer with cited passages. Keep documentary evidence separate from remembered conversations; handle irrelevant/conflicting evidence.

## Evidence and Existing Work to Preserve

These are status notes, not newly completed implementation tasks:

| Item | Verified status and limitation |
| --- | --- |
| Contextual conversation | Owner demonstrated fever/manifold exchanges; synthetic probes confirmed transmitted history in both revisions |
| Signed catalogs, safe paths, manifest IDs | Implemented; preserve checks while fixing rejected staging in FIX02 |
| Audio worker and bounded queue | Present in newer source, not inspected deployed revision 6cbd735 |
| Idle/topic resets | Present in newer source; archives are unbounded and not retrieved; review before changing deployed behavior |
| RPiFace and generic MCP | Present in newer source; RPiFace has FIX01's startup defect; the separate rpiface test dependency was unavailable |
| Provisioning, LEDs, wake-word selection, apps | Already implemented; extend rather than recreate |
| Assistant test run | 64 passes, one import error, one missing-dependency integration failure; no acoustic benchmark or agent-run live answer-quality test |
| SecondContext test run | Go suite passed; PostgreSQL/Qdrant deployment readiness remains unvalidated |

## Completion Record

No new runtime feature has been implemented by revising these documents. F01 remains retired: the presumed memory defect was not demonstrated. F06 describes a separate convenience feature. The former baseline milestones remain removed.

For each newly completed item, append: `ID — behavior delivered; checks, model/device/revision where relevant; remaining limitations.` Mention the same item and validation in its focused commit.

Deferred until there is a concrete need: speaker identification, leaderboards, achievements, marketplace expansion, local general-purpose LLMs, broad rewrites, elaborate dashboards, and automatic extraction of every conversation. Judges through OpenAI Decisions API or Jev remain optional tools for specific semantic checks, not a separate deliverable.
