# Product and Implementation Plan

Updated: 2026-11-24. Execution checklist: [TODO.md](TODO.md). Contributor workflow: [AGENTS.md](AGENTS.md).

## Product Goal

Build a useful household voice assistant that answers ordinary questions intelligently and sustains a short conversation. The first release must work well on a Raspberry Pi Zero 2 W and Raspberry Pi 3 A+, both with 512 MB RAM. Newer boards are supported, but must not hide problems on the baseline hardware.

Prioritize complete user experiences over architecture expansion. The first milestone is: wake once, ask a question, hear a concise useful answer, make a correction or follow-up, and end the conversation naturally. General questions must not require installing an app or memorizing commands.

The motivating acceptance scenario is “Is 38.6 degrees Celsius a high fever?” followed by age/symptom clarification and a context-dependent follow-up. Evaluate directness, appropriate uncertainty, authoritative grounding, and escalation when warranted. Do not hardcode one reassuring answer or treat every health question as a refusal. Clinical example answers must be checked against current authoritative guidance.

## Observed Baseline

These are observations from the November 24 review, not release certifications:

- Local revision `d725c62` contains audio-worker, bounded queue, app trust-boundary, conversation-context, RPiFace, and generic MCP changes. The inspected device checkout was `6cbd735`, nine commits behind; deployment must preserve configuration and support rollback.
- The device was a Zero 2 W running Debian 13.2 with an active assistant service. Its process showed approximately 102 MiB RSS and 105 MiB swap, with one `hey_jarvis` wake-word model. Swap occupancy is not proof of active swapping; measure activity during use.
- The current pipeline waits for transcription, complete text generation, speech generation, and playback. Audio is discarded during processing. Default post-processing delay plus 30 ignored 80 ms chunks creates approximately 5.4 seconds before wake-word detection resumes.
- Recording uses a fixed RMS silence threshold and a ten-second maximum. Natural pauses, noise, and longer questions need evaluation.
- Conversation relevance adds a model request before follow-ups. “Compaction” archives full turns in RAM and clears active context; neither list has a hard size limit, and no persistent retrieval is connected.
- Processing/playback failures largely reach logs rather than the listener. Full transcripts and replies are written to a file and console without a privacy lifecycle.
- Local configuration tests could not run successfully because `PyNaCl` was absent. No acoustic benchmark, live answer evaluation, or Pi 3 A+ validation has been completed.

## Hardware and Service Boundaries

| Location | Responsibilities |
| --- | --- |
| 512 MB Pi | One wake-word model, capture/playback, small audio buffers, LEDs, session control, local volume/stop/mute, timers and small persistent lists |
| Hosted model provider | Speech understanding/generation, reasoning, and supported hosted tools |
| Optional separate server | SecondContext gateway, Postgres, Qdrant, reference-document ingestion, and heavier integrations |

Use the existing Python service initially. Avoid a desktop browser, general-purpose local LLM, local document indexing, or the SecondContext database stack on the baseline Pi. Prefer remote HTTP tools over additional heavyweight local MCP processes. Keep optional integrations disabled unless used.

Bound all queues, histories, archives, tool results, and caches. Select one wake-word model explicitly in the shipped low-memory profile. Replace long Python float lists with compact audio storage where profiling shows benefit. Measure inference thread counts and optional-library imports before tuning or changing runtimes; do not rewrite working code merely to change language.

## Voice Architecture Decision

First implement a small selectable GPT-Live prototype on the Zero 2 W, using a supported SDK/transport and the existing audio devices. Keep the current path available during evaluation. GPT-Live supports concurrent listening/speaking and backend delegation, but this does not establish echo cancellation, interruption quality, or performance on our hardware.

Measure capture, resampling, playback buffering, speaker feedback, reconnects, and session cost. Retain local wake-word detection and open cloud sessions only for intentional conversations. Close sessions on explicit completion or inactivity; provide clear listening and microphone-mute indicators. Physical mute, if advertised, must actually disconnect or disable capture; a software indicator alone is not a hardware guarantee.

Select the shipping path using measurements, model availability, and operating cost. If Live fails the device or cost targets, use a supported Realtime or streamed speech/text pipeline. Record the choice and implement one primary path rather than maintaining several speculative providers. Retired speech models cannot be the long-term fallback.

Separate audio transport, short-session state, and tool execution only as needed to deliver this flow. Preserve local app commands and existing MCP behavior. Interruption must stop stale audio and prevent abandoned responses from playing later; it must not silently duplicate or undo an already executed action.

## Release Sequence

### M0 — Establish a Reproducible Device Baseline

Restore a usable test environment, record a known-good revision and dependency set, and measure the existing device. Prepare an update and rollback procedure without copying credentials into Git. Confirm the newer source on hardware before evaluating architecture changes. Add minimal timing/resource/cost instrumentation with content-free logging by default.

### M1 — Deliver Useful Short Conversations

Choose the voice path, migrate retiring models, and implement explicit idle/listening/thinking/speaking/follow-up states. Open a configurable short follow-up window without another wake word, tolerate natural pauses, support corrections and cancellation, and close on “thanks,” “stop,” or inactivity as appropriate to the context.

Keep a bounded recent context and remove the routine relevance-classifier round trip. Default to short spoken answers with optional elaboration and one useful clarification at a time. Provide local, pre-recorded failure prompts that work when model APIs or connectivity fail. Test input/output device selection, timeouts, and recovery after an interrupted network session.

Add web retrieval for freshness-sensitive questions and authoritative evidence for consequential advice. Speak a concise source attribution when useful; expose detailed citations through a lightweight optional companion view. Treat retrieved content as evidence, not executable instructions. Report tool failures honestly and announce action success only after confirmation from the executing code.

### M2 — Make It Useful Every Day

Add restart-safe timers/reminders and shopping lists, then location-aware weather. Timers should continue during internet loss; do not promise offline free-form speech recognition merely because timers are local. Provide physical/local cancellation and clear offline limitations.

Complete Wi-Fi onboarding protection and a small phone-accessible settings/status page. Avoid a permanent heavy dashboard on the Pi. Support device selection, volume, privacy controls, and recoverable configuration changes. A household pilot requires M1 acceptance plus provisioning and log-privacy protections.

### M3 — Add Optional Personal Memory

Integrate SecondContext on another host for explicit “remember,” recall, and deletion, with stable subject identity and time-bounded fallback to ordinary answering. Start with preferences and household facts. Add source-backed appliance/manual questions after memory basics work. Sensitive information must not be silently promoted from every conversation into permanent memory.

### M4 — Add Lightweight Entertainment

Use existing app interfaces for one polished trivia or collaborative-story experience with short turns, pause/resume, and cancellation. Expand only after household use demonstrates value. Multiplayer profiles, voice identification, leaderboards, marketplace expansion, and local LLMs remain deferred.

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

## Validation and Release Gates

Create a repeatable set of at least 20 scenarios: ordinary questions, the fever example and relevant follow-ups, corrections, ambiguous audio, long pauses, current-information lookup, local app commands, cancellation, and network/API failures. Include English and, if required by the household, Romanian. Use synthetic or explicitly approved recordings rather than committing household conversations.

The following are initial engineering targets, not observed results. Record hardware, revision, model, audio devices, distance/noise conditions, network, sample count, and costs. Revise targets only with an explicit explanation in this plan.

| Measure | Initial target |
| --- | --- |
| Conversation | Five coherent turns after one wake word; at least 18/20 baseline scenarios pass; no critical unsafe advice or false action-success claims |
| Simple answers | End-of-user-speech to meaningful first audio: median <=2 seconds, p95 <=5 seconds; report tool-assisted answers separately |
| Stop | Playback stops within 500 ms of a recognized stop/interrupt event; separately measure speech-to-recognition delay |
| Memory | Aim for <=200 MiB peak assistant-process-tree RSS and >=80 MiB system MemAvailable; report swap separately and check for sustained swap I/O during conversation |
| Endurance | 100 turns plus an overnight idle/reconnect run without OOM, service failure, accumulating buffers, or persistent monotonic memory growth |
| Operating cost | Measure a standard 20-question session, idle cloud-session time, and projected daily usage; expose configurable session/cost limits before the pilot |
| Hardware | Repeat core acceptance on both Zero 2 W and Pi 3 A+; do not substitute a newer board or claim an untested board passes |

Use mocks for unit tests and real audio/network checks for experience validation. An active systemd service or a passing unit suite alone does not meet the product gate. Record unavailable hardware or missing dependencies as incomplete validation.

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

Implement one bounded TODO item at a time, respecting milestone prerequisites. Update its checkbox and validation evidence only after it meets its acceptance criteria. Commit the implementation, relevant tests/config/docs, and checklist update together with an imperative subject and a short description of behavior and validation. Keep unfinished work unchecked. See AGENTS.md for staging and privacy rules.
