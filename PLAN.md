# Product and Implementation Plan

Updated: 2026-11-24. Implementation steps: [TODO.md](TODO.md). Contributor workflow: [AGENTS.md](AGENTS.md).

## Product Vision

Build an affordable personal voice assistant that gives useful answers and makes a short conversation feel easy. Deliver features people can use; engineering work should serve that experience. Improve the working product in small, reviewable steps.

Target Raspberry Pi Zero 2 W and Raspberry Pi 3 A+, both with 512 MB RAM. Use the available Zero 2 W for development. Validate the Pi 3 A+ before claiming support; its availability must not block improvements on the Zero 2 W. Keep reasoning in hosted services and local audio/control work lightweight.

The owner has already demonstrated useful spoken answers and contextual follow-ups:

- A fever question followed by an intentionally incomplete question about a higher temperature.
- “What's a manifold?” → “What about a compact manifold?” → “What about a cube?”, with answers linked to preceding turns.

Preserve these capabilities. There is no demonstrated short-term-memory defect to repair. Remembering a preference after restart, listening without another wake word, and interrupting speech are separate additions.

## What the Review Established

The November 24 review compared local runtime changes through `d725c62` with deployed revision `6cbd735`. The deployed checkout was clean and inspected source hashes matched that revision. These versions must not be treated as interchangeable.

| Evidence | Meaning for development |
| --- | --- |
| Deployed code sends preceding user/assistant turns with each ordinary chat request; a synthetic three-turn probe confirmed this | Preserve existing context handling; the owner's spoken examples establish actual answer quality |
| Newer code adds relevance checks and idle/topic resets; three turns made five model requests in the probe, versus three on deployed code | Review this behavior before deployment; extra calls are not automatically an improvement |
| “Compaction” copies full messages into an unbounded RAM archive with no retrieval | It is neither persistent memory nor a complete memory-growth fix |
| Current RPiFace module raises NameError on import under Python 3.13.5, even when disabled | Fix before deploying this checkout; the Pi uses Python 3.13.5 |
| A checksum-rejected bundle remains in staging and is imported at the next AppManager startup | Reproduced in both revisions; clean failed staging and exclude it from discovery |
| Device openWakeWord 0.4.0 works; the assistant's lowercase models import fails against 0.6.0 | Preserve a tested dependency set; upgrading requires compatibility work |
| Newer code has an audio worker and bounded queue; deployed code queues audio while a synchronous request runs | Preserve the bounded-buffer improvement when deploying; it is not already deployed |
| Processing errors mostly reach logs; SDK 2.15.0 defaults include a 600-second read timeout and two retries | Bound waits and add audible request-failure feedback; offline/online audio prompts already exist |

The assistant suite produced 64 passes, one RPiFace import error, and one failure from the unavailable separate rpiface integration-test dependency. Audio tests mock wake-word loading and do not establish package compatibility. SecondContext's Go suite passed; PostgreSQL/Qdrant deployment readiness was not established.

The Pi service was active. One snapshot showed about 102 MiB RSS and 105 MiB swap; swap occupancy alone does not prove active swapping or poor responsiveness. The review did not run an acoustic latency benchmark, live model-quality evaluation, or Pi 3 A+ hardware tests.

## Proposed Next Delivery: Easier Follow-Up Conversation

**F06: after answering, briefly listen for the next question without requiring another wake word.** Reuse the existing conversation history and voice pipeline. This adds convenience to a capability that already works.

The intended flow is wake word → question → spoken answer → short follow-up window → another answer, or return to wake-word listening when the window expires. Make the window configurable and disableable. Start listening after playback finishes; silence should end the window quietly. Do not send idle room audio to a provider just to keep the feature alive.

Try the owner's existing conversations on the Zero 2 W. Confirm earlier turns remain available, the assistant does not answer its own playback, and ordinary wake-word use still works afterward. Change drain/flush timing only as needed for this behavior, checking speaker echo. Interruption during playback is separate.

Attach the startup and dependency corrections to delivery of a runnable checkout. Fix the reproduced installation bypass in its own focused commit. These are bounded corrections, not a baseline, infrastructure, or general-hardening milestone. Preserve device configuration and a recoverable working version when deployment is undertaken.

## Subsequent Product Priorities

1. **F03 — Understandable failure and recovery.** Bound provider waits; give a short locally playable failure message; return to listening. Reuse existing connectivity prompts where appropriate.
2. **F02 — Interruption and correction.** Stop stale playback and accept a correction without duplicating an action already executed. Evaluate speech interruption on hardware before promising it.
3. **F04 — Current-information answers.** Add a real lookup source, concise attribution, and honest handling of missing/conflicting evidence. General questions must not require installing an app.
4. **F05 — Simple controls.** Volume, stop, mute with accurate capture indication, and an explicit new-conversation command. Provide local control paths during internet loss without promising offline free-form recognition.
5. **Everyday usefulness.** Restart-safe timers, reminders/shopping lists, local weather, and one enjoyable trivia/story experience. Choose the next complete feature from household use.

Privacy and onboarding improvements should accompany wider household use: opt-in transcript logging, limited retention, protected setup mutations, and credential-safe errors. The Wi-Fi service already has a provisioning lifecycle; extend it rather than rebuilding it.

## Lightweight Testing That Supports Delivery

Attach a small set of checks to each feature. There is no prerequisite evaluation platform, fixed 20-case suite, leaderboard, or benchmarking milestone.

- **Deterministic tests:** exercise state transitions, deadlines, cancellation, truthful action acknowledgements, startup imports, and rejected-bundle cleanup/discovery. Mock hardware and network failures to reproduce concrete behavior.
- **Live OpenAI integration tests:** use real API calls for answer quality, contextual follow-ups, and model compatibility. Provide an explicit command using locally configured credentials; keep paid calls out of the default offline suite. Record model/configuration and a brief result. Never commit keys or private household conversations.
- **Conversation examples:** start with the owner's manifold and fever exchanges, adding corrections/failures relevant to the feature. Check meaning and use of prior context, not an exact response string. The synthetic probe verified transmitted history, not answer quality. Use current authoritative guidance when judging medical content; the primary regression here is contextual understanding.
- **Optional judges:** use one only when semantic assessment materially helps. OpenAI Decisions API or Jev may be evaluated for that role; neither is selected or required. Use explicit criteria and inspect disputed results. Keep credentials, cost, and data handling deliberate. Do not build a judging framework as a prerequisite.
- **Pi checks:** API tests cannot establish microphone quality, speaker echo, wake-word behavior, follow-up timing, or memory pressure. Try the changed interaction on the Zero 2 W and record observations. Add measurements when they resolve a concrete concern.

Before broader distribution, expand scenarios, test longer use/reconnection, check operating cost, and repeat core flows on both boards. Set numeric performance targets from actual use and measurements; arbitrary budgets should not prevent the owner from trying a useful improvement.

## Hardware and Architecture Boundaries

| Location | Responsibilities |
| --- | --- |
| 512 MB Pi | One selected wake-word model, capture/playback, bounded buffers, LEDs, session control, local controls, timers and small persistent lists |
| Hosted provider | Speech transcription/generation, reasoning, and supported hosted tools |
| Optional external server | SecondContext and storage/retrieval services, document ingestion, heavier integrations |

Keep the existing Python service. Use measured problems to justify allocation, thread, import, or runtime changes. Preserve app commands, catalog signatures, checksums, safe bundle paths, and manifest validation. Avoid heavyweight local MCP processes unless their benefit and resource use justify them.

A streaming/realtime voice path is an option if it solves an observed interaction problem. A newer API alone is not a reason to replace the working pipeline. Keep cloud sessions intentional and avoid unnecessary idle traffic. Advertise physical mute only if the hardware actually disables capture.

## Optional SecondContext Integration

SecondContext is not required for ordinary conversation, OpenAI integration tests, or the next feature. Its existing `POST /v1/responses` supports non-streaming requests; its TODO marks that implementation complete. The assistant currently calls Chat Completions, so integration needs an explicit request/response adapter. Coordinate fuller Responses compatibility or streaming when a feature needs them.

Start when explicit cross-session remember/recall or manual-based answers become a chosen feature. Run the backend elsewhere. Carry authenticated user/session identity and recent context deliberately, avoid duplicate ingestion, and keep ordinary answers available during outages. Follow its actual authorization/deletion contracts; do not assume every memory operation is available to a service token. Keep retention deliberate, with correction/deletion controls. Backend changes belong in that repository.

## Model and Dependency Maintenance

Provider retirements are time-sensitive maintenance even when existing behavior works. The [OpenAI deprecation schedule](https://developers.openai.com/api/docs/deprecations), checked on 2026-11-24, lists:

| Existing model | Announced shutdown |
| --- | --- |
| tts-1 | 2027-01-06 |
| GPT-4o mini family | 2027-01-14 |
| whisper-1 | 2027-02-26 |

Recheck dates and replacement compatibility when implementing R01. Test transcription, speech output, ordinary answers, structured app-intent output, token parameters, and tool calls affected by the change. Do not replace a model by name alone or let a routing failure become a false action-success claim.

Record a tested ARM64 dependency set. The openWakeWord export mismatch is documented in its [0.6.0 source](https://raw.githubusercontent.com/dscripka/openWakeWord/v0.6.0/openwakeword/__init__.py). Preserve the working environment while testing compatibility separately. Upgrade SDK/MCP components when required by features or support needs, not simply to match the newest version.

## Review Findings and Delivery Workflow

The local `CODE_REVIEW_2026_06_27.md` must never be committed. Preserve its implemented signature/path/manifest protections and audio-worker improvements. Correct its overstatement that context growth is fixed: full archived messages remain in RAM. Carry forward classifier compatibility, privacy, and provisioning issues; the new review also reproduced a password appearing in provisioning exceptions. Existing LEDs, wake-word selection, apps, and tests are foundations to retain.

Implement one bounded TODO item, run appropriate checks, and record behavior, evidence, and limitations. Mark it complete only when its acceptance criteria are met. Commit implementation, tests, relevant configuration/docs, and TODO update together with a short imperative subject and brief description of behavior and validation. Keep unrelated changes out of the commit. Local commits do not authorize pushing or deployment.
