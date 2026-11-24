# Product and Implementation Plan

Updated: 2026-11-24. Execution checklist: [TODO.md](TODO.md). Contributor workflow: [AGENTS.md](AGENTS.md).

## Product Goal

Build a useful household voice assistant that answers ordinary questions intelligently and sustains a short conversation. The supported hardware target is Raspberry Pi Zero 2 W and Raspberry Pi 3 A+, both with 512 MB RAM. Improve the already working assistant on the available Zero 2 W; validate the Pi 3 A+ before claiming support for it. Newer boards must not hide problems on the baseline hardware.

Prioritize complete user experiences over architecture expansion. Useful spoken questions and short follow-ups already work according to the owner. The next improvement is reliable use of details the owner supplies, guided by a concrete memory failure rather than an assumed need to rebuild conversation. General questions must not require installing an app or memorizing commands.

The original motivating fever question has now worked on the device, including the open-ended follow-up “What about a 39.5 degrees?” Preserve it as a regression example. Extend answer evaluation with relevant age/symptom clarification and additional context-dependent follow-ups. Evaluate directness, appropriate uncertainty, authoritative grounding, and escalation when warranted. Do not hardcode one reassuring answer or treat every health question as a refusal. Clinical example answers must be checked against current authoritative guidance.

## Observed Baseline

These combine the November 24 source/device review and subsequent owner feedback. Code limitations, observed behavior, and untested expectations are distinct:

- **Owner-confirmed behavior:** useful spoken answers and the two-turn fever exchange work on the device. The owner reports that it does not always remember their answers, but a specific failure sequence is still needed to identify whether the gap is within a conversation or across sessions. The report does not establish wake-word-free listening or persistence after restart.
- Local revision `d725c62` contains audio-worker, bounded queue, app trust-boundary, conversation-context, RPiFace, and generic MCP changes. The inspected device checkout was `6cbd735`, nine commits behind; deployment must preserve configuration and support rollback.
- The device was a Zero 2 W running Debian 13.2 with an active assistant service. Its process showed approximately 102 MiB RSS and 105 MiB swap, with one `hey_jarvis` wake-word model. Swap occupancy is not proof of active swapping; measure activity during use.
- The current pipeline waits for transcription, complete text generation, speech generation, and playback. Audio is discarded during processing. Default post-processing delay plus 30 ignored 80 ms chunks creates approximately 5.4 seconds before wake-word detection resumes.
- Recording uses a fixed RMS silence threshold and a ten-second maximum. Natural pauses, noise, and longer questions need evaluation.
- Conversation relevance adds a model request before follow-ups. “Compaction” archives full turns in RAM and clears active context; neither list has a hard size limit, and no persistent retrieval is connected.
- Processing/playback failures largely reach logs rather than the listener. Full transcripts and replies are written to a file and console without a privacy lifecycle.
- Local configuration tests could not run successfully because `PyNaCl` was absent. The agent did not perform an acoustic benchmark or live answer evaluation; the owner subsequently confirmed the successful two-turn exchange above. Pi 3 A+ validation remains outstanding.

## Hardware and Service Boundaries

| Location | Responsibilities |
| --- | --- |
| 512 MB Pi | One wake-word model, capture/playback, small audio buffers, LEDs, session control, local volume/stop/mute, timers and small persistent lists |
| Hosted model provider | Speech understanding/generation, reasoning, and supported hosted tools |
| Optional separate server | SecondContext gateway, Postgres, Qdrant, reference-document ingestion, and heavier integrations |

Use the existing Python service initially. Avoid a desktop browser, general-purpose local LLM, local document indexing, or the SecondContext database stack on the baseline Pi. Prefer remote HTTP tools over additional heavyweight local MCP processes. Keep optional integrations disabled unless used.

Bound all queues, histories, archives, tool results, and caches. Select one wake-word model explicitly in the shipped low-memory profile. Replace long Python float lists with compact audio storage where profiling shows benefit. Measure inference thread counts and optional-library imports before tuning or changing runtimes; do not rewrite working code merely to change language.

## Voice Architecture Direction

Keep the working voice path for the next memory improvement. GPT-Live is an option for a demonstrated latency, interruption, or turn-taking need, not a prerequisite for useful answers or context retention. Do not replace a working subsystem because a newer API exists. Provider retirements still require timely migration of affected components; keep that maintenance distinct from a wholesale voice redesign.

If later evaluating Live or another streaming path, try it on the Zero 2 W and compare the specific experience being improved. Preserve a recoverable working setup. Check speaker echo, bounded buffers, resource use, and session cost while using the feature; perform deeper profiling only when needed. Keep local wake-word detection and close intentional cloud sessions on explicit completion or inactivity.

Preserve existing app commands and MCP behavior. Interruption must stop stale audio without duplicating or silently undoing an executed action. Physical mute, if advertised, must actually disconnect or disable capture; a software indicator alone is not that guarantee.

## Feature Delivery Sequence

### First — Reliable Recall of User-Provided Details (F01)

Start from the owner's reported memory difficulty. Obtain or reproduce a concrete exchange and identify the expected lifetime of the information: the next turn, after a topic change/inactivity, or after a restart. These are different requirements. Successful short follow-ups are already a capability to preserve.

Use a harmless explicit fact that cannot be answered from general knowledge, then ask for it and correct it. For example, give the location of a screwdriver, ask where it is, change the location, and ask again. Inspect the deployed code and actual context path before choosing a fix; the newer local context-reset code is not necessarily running on the device. Address the smallest demonstrated issue in history, app routing, or reset behavior. If the desired behavior is cross-session memory, deliver C01 instead.

Keep recent context bounded, retain existing safeguards, and add a focused regression check for the actual failure. There is no preliminary baseline milestone, mandatory voice-provider migration, or broad benchmark required to improve memory. Preserve configuration and run relevant checks as part of the feature. If the reported failure cannot yet be reproduced, leave it open and document the uncertainty instead of inventing a defect or doing a speculative rewrite.

### Next — Better Conversation (F02–F05)

Support interruption and corrections, fix pauses or echo problems found in use, and provide local spoken failure feedback with bounded waits/retries. Add current-information and authoritative-source lookup, then simple volume/mute/new-conversation controls and usage limits. Implement each as an improvement to the already usable assistant. Add wake-word-free continuation if repeated wake words are an actual friction point; do not infer its status from a successful answer follow-up.

Treat retrieved content as evidence, not executable instructions. Speak concise source attribution where useful. Report tool failures honestly and announce action success only after confirmation from the executing code. Detailed citation UI can follow later.

### Before Wider Household Use — Privacy and Provisioning (H01–H02)

Make full transcript logging opt-in, bound retention, and protect setup credentials and Wi-Fi mutations. These are required before inviting other household users to rely on the device. Develop them alongside useful features rather than treating the existing assistant as unusable until a hardening phase is complete.

### Then — Useful Daily Actions and Entertainment (H03–H06, E01)

Choose the next feature based on actual use: restart-safe timers/reminders, shopping lists, location-aware weather, simpler phone-based setup, or one enjoyable trivia/story experience. Timers should continue during internet loss; do not promise offline free-form speech recognition merely because timers are local. Provide local cancellation and truthful action acknowledgements.

Keep setup/status pages lightweight and reuse existing app interfaces. Multiplayer profiles, speaker identification, leaderboards, marketplace expansion, and local LLMs remain deferred until they have a demonstrated product benefit.

### Optional — Personal Memory (C01–C03)

Integrate SecondContext on another host when remembering a preference or household fact is the desired next feature. Demonstrate explicit remember/recall across sessions, then correction/deletion and manual-based answers. Keep ordinary conversation usable during backend outages. Do not silently promote sensitive conversations into permanent memory.

## SecondContext Integration Contract

The sibling repository already implements structured memory, hybrid retrieval, reference knowledge, identity isolation, and subject purge. It is optional: ordinary conversation must work without it.

Its current external interface is non-streaming `POST /v1/responses`; streaming is rejected. The assistant currently uses Chat Completions. A base-URL change is insufficient, and the gateway does not expose the existing assistant tool-call contract. Use a small explicit adapter or delegated backend operation and keep local tools independently usable.

The adapter must carry recent turns deliberately: stored messages do not automatically become replayed session context or extracted durable memories. Prevent duplicate transcript ingestion when replaying history. Supply concise voice instructions and preserve source provenance.

Service authentication requires a bearer credential and `X-SecondContext-Subject: <namespace>:<uuid>`. The current service scope allows only `/v1/responses`, `/memory/ingest`, and `/v1/subjects/purge`; do not assume it grants `/memory/search` or individual-memory deletion. Design selective “forget” against an authorized API extension or explicitly document that limitation. Full purge requires user confirmation and a verified matching completion response; it permanently fences the subject and does not erase external backups or provider retention.

Start with an explicitly selected household/user profile; do not infer identity from voices. Keep memory optional, support memory-service outages, and avoid retaining sensitive conversational material by default. Changes to SecondContext belong in its own repository and commit history.

## Component Migration Priorities

The upstream documentation checked on 2026-11-24 lists these dates. Recheck availability, prices, API parameters, and dates when implementing; this table is not a permanent model catalog.

| Current component | Action |
| --- | --- |
| `tts-1` | Replace before its announced 2027-01-06 shutdown; `gpt-4o-mini-tts` has the same announced deadline |
| `gpt-4o-mini`; SecondContext's `gpt-4.1-mini` | Replace before announced 2027-01-14 shutdown; evaluate supported models on the acceptance set |
| `whisper-1` | Replace before announced 2027-02-26 shutdown if the selected voice architecture still uses separate transcription |
| Device `openai==2.15.0` | Select a tested SDK with the required voice support; published version at review was 3.58.0 |
| Device `openwakeword==0.4.0` | Evaluate 0.6.0 on ARM64, including loading API, model assets, resource use, and the repository patch |
| Local `mcp>=2.1,<2.2` | Evaluate newer compatible releases when shipping tools; published version at review was 2.3.0 |
| SecondContext Go 1.24 builder | Upgrade to a supported toolchain before backend deployment |

Model changes must cover chat, app-intent classification, structured output, token limits, temperature/reasoning options, and tool calls. Use a separately configured compatible intent model if needed; never let classification failure cause a conversational claim that an app operation succeeded. Preserve a tested dependency set for ARM64 rather than blindly upgrading the running device.

References: [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations), [Live architecture](https://developers.openai.com/api/docs/guides/live), [voice WebSockets](https://developers.openai.com/api/docs/guides/voice-websockets?api=live), [OpenAI SDK](https://pypi.org/project/openai/), [openWakeWord](https://pypi.org/project/openwakeword/), [MCP](https://pypi.org/project/mcp/), [Go support](https://go.dev/doc/devel/release).

## Feature Checks and Broader Release Validation

For the memory improvement, reproduce the reported failure, verify recall and correction of an explicit user-provided detail, and preserve the already successful question/follow-up flow. Run tests relevant to the changed behavior on the available Zero 2 W and report simple responsiveness/resource observations. Resolve missing test dependencies only as needed for those checks. Do not claim a board, interruption behavior, or failure mode was tested when it was not.

For broader release validation, expand to at least 20 scenarios: ordinary questions, the fever example and relevant follow-ups, corrections, ambiguous audio, long pauses, current-information lookup, local app commands, cancellation, and network/API failures. Include English and, if required by the household, Romanian. Use synthetic or explicitly approved recordings rather than committing household conversations.

The following are provisional broader-release targets, not prerequisites for developing or showing F01, and not observed results. Use them to find actual product problems without discounting successful owner use. Record hardware, revision, model, test conditions, and costs as relevant; explain adjustments without creating a separate approval process.

| Measure | Initial target |
| --- | --- |
| Conversation | Five coherent turns after one wake word; at least 18/20 baseline scenarios pass; no critical unsafe advice or false action-success claims |
| Simple answers | End-of-user-speech to meaningful first audio: median <=2 seconds, p95 <=5 seconds; report tool-assisted answers separately |
| Stop | Playback stops within 500 ms of a recognized stop/interrupt event; separately measure speech-to-recognition delay |
| Memory | Aim for <=200 MiB peak assistant-process-tree RSS and >=80 MiB system MemAvailable; report swap separately and check for sustained swap I/O during conversation |
| Endurance | 100 turns plus an overnight idle/reconnect run without OOM, service failure, accumulating buffers, or persistent monotonic memory growth |
| Operating cost | Measure a standard 20-question session, idle cloud-session time, and projected daily usage; expose configurable session/cost limits before the pilot |
| Hardware | Repeat core acceptance on both Zero 2 W and Pi 3 A+; do not substitute a newer board or claim an untested board passes |

Use mocks for focused unit tests and real audio/network checks for experience validation. A running systemd service alone does not prove a usable conversation. Deliver tested improvements on the available board while recording broader validation separately; an unavailable second board does not block improvements on the working Zero 2 W.

## Findings Carried Forward from the June Review

The original `CODE_REVIEW_2026_06_27.md` remains local and must not be committed. Its useful findings are incorporated here and in TODO:

- Preserve signed remote catalogs (`b5ccf23`), validated bundle paths (`1b83125`), and safe manifest IDs (`61a5ddd`); retain regression coverage.
- Preserve the audio worker (`43af12f`) and bounded/configurable queue (`ee99660`), while improving interruption and follow-up behavior.
- Treat context compaction (`8876e8c`) as partial progress: active and archived histories still need hard limits and an explicit retention policy.
- Fix model/classifier compatibility and add mocked malformed/unsupported-response tests.
- Protect provisioning mutations with per-device setup credentials and CSRF controls. The manager already stops the Flask service when leaving provisioning; verify that lifecycle instead of treating shutdown as entirely missing. Handle malformed input and NetworkManager failures without exposing passwords in errors.
- Make transcript logging opt-in across both files and systemd output, with restrictive permissions, rotation, retention, and deletion. Preserve useful content-free diagnostics.

The old TODO's missing LED driver, absent tests, absent wake-word configuration, and absent plugin framework are stale descriptions. Those components exist; validate and extend them when they serve a product feature.

## Execution and Commit Workflow

Implement the next useful TODO feature, handling only its concrete prerequisites. Attach setup, relevant testing, and measurement to delivery; avoid separate preparation milestones. Update its checkbox and validation evidence only after it meets its acceptance criteria. Commit the implementation, relevant tests/config/docs, and checklist update together with an imperative subject and a short description of behavior and validation. Keep unfinished work unchecked. See AGENTS.md for staging and privacy rules.
