# Implementation TODO

Updated: 2026-11-24. Product decisions: [PLAN.md](PLAN.md). Contributor workflow: [AGENTS.md](AGENTS.md).

## Working Agreement

Useful spoken answers and contextual follow-ups already work on the owner's Zero 2 W. Preserve them. No short-term-memory defect has been demonstrated; no conversational-memory rebuild is scheduled.

**Next delivery: modernize the existing working assistant through U01, U02, and R01. Then add F06, follow-up listening without another wake word.** The owner requested upgrading the software stack before adding features. Keep the 512 MB target and existing conversation behavior throughout. Modernization delivers a supported, reproducible working installation; it must not grow into a separate CI, benchmarking, evaluation-platform, or broad-refactoring project.

For each completed item, record validation evidence and commit implementation, relevant tests/config/docs, and checklist update together. Keep unfinished items unchecked. Never stage the local June code review or credentials. Planning changes do not count as runtime implementation; a local commit is not deployment approval.

## First: Modernize the Working Stack

- [x] **U01 — Update the OS and validate ReSpeaker audio.**
  - Target current stable Raspberry Pi OS Lite 64-bit, including kernel/firmware, matching headers, security updates, ALSA/PortAudio, NetworkManager, and required system libraries. The Pi is already on Trixie; kernel 6.18 is the current release line. Refresh metadata before choosing exact package versions.
  - Record recovery options and preserve the actual card, driver binding, overlays, and mixer configuration. The owner accepted SD-card reimaging if needed and explicitly waived a full-image prerequisite; save lightweight configuration snapshots without treating them as a full backup.
  - Correct the stale driver URL and installer assumptions. The current patch fails forward/reverse checks against HinTak v6.14 revision 34477ad; do not interpret that as already applied or continue after failure.
  - Test the kernel-provided WM8960/overlay path for this card, or port the patch against an exact vendor revision and build against the selected kernel headers. Remove obsolete patch/install steps only when their replacement works. Avoid an installer that forces an older kernel.
  - **Acceptance:** reboot on the selected kernel; verify microphone capture, playback, wake detection, Wi-Fi, LEDs, and a spoken conversation. Record exact versions and recovery instructions. Patch applicability, successful compilation, and working audio are distinct checks; none proves the next.
  - **Completed/checked 2026-11-24:** Zero 2 W upgraded to Debian 13.8; kernel/headers `1:6.18.60-1+rpt1`, firmware `1:1.20260915-1`, NetworkManager `1.52.1-1+rpt4`, ALSA utils `1.2.14-1+rpt1`, PortAudio `19.6.0-1.2+b3`. Two reboots passed; Wi-Fi reconnected, native kernel WM8960 loaded, both capture channels recorded the played tone, SPI devices appeared, and the service initialized three LEDs. `dpkg --audit` was clean. Nine focused audio-setup tests pass. Deployed app remains `6cbd735`; its Python environment/models were preserved.
  - **Regression found and addressed:** card indices swapped, requiring a named output; SPI previously depended on the retired vendor service. The owner then reported quiet speech despite normal standalone WAV playback. With the live 32-bit microphone stream, plain `plughw` negotiated 24-bit playback; the owner confirmed forced 32-bit playback was louder and clear. Setup now selects the named `assistant_wm8960` PCM with `S32_LE` output. After applying it and restarting the assistant, simultaneous capture/playback both reported `S32_LE`, playback exited successfully, and the service stayed active without restarts. The owner then confirmed a normal wake-word question and contextual follow-up with clearly audible responses, normal wake detection, and LEDs. U01 acceptance passed on this Zero 2 W.
  - **Recovery/limits:** root-only boot/kernel/driver/config snapshot retained under `/var/backups/rpi-assistant-u01/`, with per-apply configuration snapshots under `/var/backups/rpi-assistant-audio/`; these are not a full SD image or a tested rollback. See [audio setup/recovery](docs/audio-upgrade.md). Fresh-card mixer settings and Pi 3 A+ remain untested.
- [ ] **U02 — Upgrade and record the Python dependency set.**
  - Review all direct requirements and resolved dependencies; select current stable ARM64-compatible versions in a separate environment, including OpenAI SDK, wake-word/inference libraries, audio, NumPy, Flask, GPIO/SPI, signing, and MCP.
  - Adapt changed APIs and resolve real inference-runtime packaging. openWakeWord 0.6.0's Linux tflite-runtime dependency has no published CPython 3.13 wheel at review time; explicitly resolve this compatibility issue. Do not declare success from a no-dependencies install or mocked test alone.
  - Complete FIX01/FIX03, retain FIX02, and retire obsolete patches. Pin the tested set and document any justified older-version exception with a follow-up path.
  - **Acceptance:** reproduce installation, run relevant tests, load the actual wake model, and exercise capture/playback, GPIO/LEDs, local apps, signatures, and configured MCP tools. Check the assistant still fits 512 MB hardware. Resolve optional integration-test prerequisites or report them explicitly.
- [ ] **R01 — Migrate to supported OpenAI models and workflows.**
  - Evaluate current transcription, reasoning, intent-routing, and speech models with real API calls; initial candidates and shutdown dates are in PLAN.md. Confirm endpoint/parameter support, account access, cost, and spoken quality before selecting defaults.
  - Implement the required TTS workflow change: OpenAI's recommended gpt-realtime-2.1-mini replacement uses Realtime, not the existing Speech endpoint. Test audio format/playback, session cleanup, failure recovery, and tool/structured-output compatibility.
  - **Acceptance:** the fever/manifold follow-ups still use prior context; transcription, spoken replies, and existing app actions work on the updated configuration. Record model IDs, SDK version, API results, resource observations, and rollback. No SecondContext integration or automated judge is required.

## Next Feature After Modernization: Natural Follow-Up Listening

- [ ] **F06 — Ask a follow-up without repeating the wake word.**
  - Add a configurable, disableable listening window after playback finishes, reusing existing conversation history.
  - Capture a follow-up during that window; expire quietly back to wake-word detection on silence. Avoid idle cloud traffic and reacting to the assistant's own playback.
  - Review drain/flush timing and the newer topic/idle resets against this experience. Preserve demonstrated context behavior; do not silently introduce additional context loss when deploying newer code.
  - **Acceptance:** on the Zero 2 W, try manifold → compact manifold → cube without another wake word, let the window expire, and start a fresh interaction normally. Check silence, disabled-window behavior, and speaker echo. Record observations and limitations; interruption belongs to F02.
  - **Testing:** focused state-transition tests and an explicit live OpenAI test for contextual answers. Keep API quality checks separate from microphone/playback checks. Judges are optional; SecondContext is not required.

## Concrete Fixes Included in Modernization

These are reproduced defects or compatibility failures. FIX01 is required to run the current checkout on the Pi. Resolve FIX02 before relying on app-installation rejection. FIX03 is the wake-word compatibility work within U02; each fix can be committed independently.

- [x] **FIX01 — Start successfully with RPiFace disabled.** Fix the self-referential annotation that raises NameError under Python 3.13.5. Quoted the self-referential context-manager return annotation. Four lifecycle tests pass on Python 3.13.5, including a fresh-interpreter import with RPiFace disabled, localhost delivery and unavailable-server handling. The optional external rpiface MCP test prerequisite remains part of U02 validation.
- [ ] **FIX02 — Never load a rejected app bundle.** Clean staging after checksum/download failure and exclude incomplete/staging directories from discovery. **Acceptance:** a validly signed catalog with an altered bundle is rejected, and restarting AppManager neither imports it nor disrupts a previously installed app. Retain signature, path, and manifest checks.
- [ ] **FIX03 — Update wake-word integration for the chosen modern runtime.** Adapt the old model-registry import and verify assets, inference dependencies, and patch behavior. Resolve openWakeWord/Python compatibility during U02; the installed 0.4.0 is a recovery reference, not a permanent target. **Acceptance:** actual package import/model loading and wake detection on the Pi; mocked audio tests alone are insufficient.

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

U01 — OS/audio migration completed on the Zero 2 W, including reboot, capture/playback, Wi-Fi, and owner-confirmed wake, LEDs, clear speech and contextual follow-up. Nine focused tests pass; see exact versions and recovery/hardware limitations above. U02/R01 and new features have not been implemented. F01 remains retired: the presumed memory defect was not demonstrated. F06 describes a separate convenience feature. U01/U02/R01 implement the owner's requested modernization priority; the former baseline milestones remain removed.

For each newly completed item, append: `ID — behavior delivered; checks, model/device/revision where relevant; remaining limitations.` Mention the same item and validation in its focused commit.

Deferred until there is a concrete need: speaker identification, leaderboards, achievements, marketplace expansion, local general-purpose LLMs, broad rewrites, elaborate dashboards, and automatic extraction of every conversation. Judges through OpenAI Decisions API or Jev remain optional tools for specific semantic checks, not a separate deliverable.
