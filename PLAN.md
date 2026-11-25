# Product and Implementation Plan

Updated: 2026-11-25. Implementation steps: [TODO.md](TODO.md). Contributor workflow: [AGENTS.md](AGENTS.md).

## Product Vision

Build an affordable personal voice assistant that gives useful answers and makes a short conversation feel easy. Deliver features people can use; engineering work should serve that experience. Improve the working product in small, reviewable steps.

Target Raspberry Pi Zero 2 W and Raspberry Pi 3 A+, both with 512 MB RAM. Use the available Zero 2 W for development. Validate the Pi 3 A+ before claiming support; its availability must not block improvements on the Zero 2 W. Keep reasoning in hosted services and local audio/control work lightweight.

The owner has already demonstrated useful spoken answers and contextual follow-ups:

- A fever question followed by an intentionally incomplete question about a higher temperature.
- “What's a manifold?” → “What about a compact manifold?” → “What about a cube?”, with answers linked to preceding turns.

Preserve these capabilities. There is no demonstrated short-term-memory defect to repair. Remembering a preference after restart, listening without another wake word, and interrupting speech are separate additions.

## What the Review Established

The November 24 review compared local runtime changes through `d725c62` with deployed revision `6cbd735`. The deployed checkout was clean and inspected source hashes matched that revision. These versions must not be treated as interchangeable. The following table records the initial findings before U01/U02; completed fixes and current deployment validation are recorded in TODO.md.

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

## First Delivery: Modernize the Working Assistant

Bring the existing product onto a current, supported stack before adding follow-up listening. The older versions reflect the project's initial development, not a requirement to retain them. This is a concrete compatibility and migration delivery: its result is the same useful assistant running on maintained OS components, libraries, and model APIs.

Work through **U01 (OS and audio), U02 (Python dependencies), and R01 (OpenAI models)** in focused commits. Choose current stable versions compatible with the target boards, document any necessary exception, and record the tested combination. A temporary fallback is a recovery option, not the long-term upgrade policy. Keep the existing 512 MB hardware; update software rather than assuming a newer Pi is needed.

### U01 — OS, Kernel, and ReSpeaker Audio

Target Raspberry Pi OS Lite 64-bit on the supported stable release. Before U01, the device ran Debian 13/Trixie with kernel 6.12.47; the [current official Lite image](https://www.raspberrypi.com/software/operating-systems/) uses Trixie/kernel 6.18. Refreshing its APT index on November 24 selected kernel and headers 6.18.60; the Zero 2 W now boots that version. Refresh package metadata for subsequent upgrades before selecting exact versions. Include security updates, firmware, matching headers, ALSA/PortAudio, NetworkManager, and required build/system libraries. Use the distribution-supported Python rather than replacing it merely to obtain the highest version number.

The audio path needs explicit work before a kernel switch:

- Before U01, the card was identified as seeed-2mic-voicecard with a WM8960 codec and loaded out-of-tree WM8960/Seeed modules. U01 has now booted the Zero 2 W on kernel 6.18.60 using the kernel-provided codec and overlay; the speaker-to-microphone check passed on both channels. The owner also identified quiet speech during live capture; matching playback to the 32-bit capture format restored clear volume in a direct comparison. Setup now preserves SPI for LEDs and uses a stable, 32-bit ALSA playback PCM. The owner confirmed normal wake detection, LEDs, audible responses and contextual follow-ups after that fix. U01 is complete on this Zero 2 W; see TODO.md for remaining hardware limits.
- The Makefile's seeed-studio driver URL returned repository-not-found. The device's separate driver checkout uses [HinTak/seeed-voicecard](https://github.com/HinTak/seeed-voicecard), at revision 1a07cfa from its v6.13 line.
- A fresh HinTak v6.14 checkout at 34477ad9e462ed00a7ebc853e4cf1934b9e73e81 failed both forward and reverse checks for the old patch. U01 retires that patch and vendor installation path for WM8960; it does not claim compatibility for other ReSpeaker codecs.
- The former installer masked checkout/patch failures and the upstream script assumed older kernel package names. The replacement uses the distribution's kernel/headers and the native overlay, stopping on command errors without invoking the vendor script or downgrading the kernel.
- The migration uses the kernel-provided WM8960 driver and [wm8960-soundcard overlay](https://github.com/raspberrypi/linux/blob/rpi-6.18.y/arch/arm/boot/dts/overlays/README) for this card. Retain hardware checks after future kernel updates; driver availability or a successful build alone does not establish microphone and speaker operation.

Preserve a recoverable image when available and record the recovery approach. The owner explicitly accepted proceeding without a full SD image and rebuilding the card if needed; do not reintroduce that image as an approval gate. Save lightweight boot/audio configuration snapshots where practical, distinguishing them from a complete image. A successful patch application or compilation alone is not hardware validation. Finish with boot, capture, playback, wake detection, Wi-Fi, LEDs, and an ordinary spoken conversation on the selected OS/kernel.

### U02 — Current, Reproducible Python Dependencies

Review every direct requirement and its resolved dependencies: OpenAI SDK, openWakeWord/inference runtime, NumPy, sounddevice, Flask, GPIO/SPI packages, PyNaCl, and MCP. Resolve and test a current stable set in an isolated ARM64 environment before replacing the working environment. Pin the tested result so subsequent installs reproduce it; do not treat today's installed versions as the intended endpoint.

The U02 candidate uses current pinned ARM64 dependencies on Python 3.13, including OpenAI 3.58.0, MCP 2.3.0, NumPy 2.5.5 and LiteRT 2.4.0. Released openWakeWord 0.6.0 still requires tflite-runtime without a CPython 3.13 wheel; use the pinned upstream LiteRT revision rather than bypassing dependencies. Build its mandatory SpeexDSP binding from pinned source, because its published wheels also stop at Python 3.12. Record these source exceptions and replace them with compatible stable releases when available. Full pins, build prerequisites and rollback are in [the Python upgrade guide](docs/python-upgrade.md).

The old site-packages patch is retired. The candidate uses the modern wake-word API, verified setup-time model assets and one selected model by default. A real Zero 2 W probe loaded LiteRT, ran inference at a mean 27 ms per 80 ms input block, captured/played audio and initialized LGPIO LEDs, with about 194 MiB peak probe RSS. This is a short hardware check, not an end-to-end latency or long-running memory result. The owner confirmed normal wake detection, LEDs, audible replies and contextual follow-ups on the candidate; U02 is complete on the Zero 2 W. See TODO.md for limits and measurements. FIX01 and FIX02 are committed; retain their startup and rejected-bundle protections.

Installation must also fit the board: the first bulk install used the 208 MB RAM-backed /tmp, filled swap and lost responsiveness. The owner restored Wi-Fi through provisioning after restarting. Prepare wheels off-device when needed, pause the assistant during installation, and keep pip temporary files on SD-backed /var/tmp. The original environment and service file remain available for rollback after candidate acceptance. Pi 3 A+ and longer-running behavior remain untested.

### R01 — Supported OpenAI Models and API Workflows

Migrate transcription, reasoning/app routing, and speech output together as a tested configuration. The owner selected [GPT-Transcribe for recorded speech](https://developers.openai.com/api/docs/guides/speech-to-text), [GPT-6 Luna for efficient reasoning](https://developers.openai.com/api/docs/models/gpt-6-luna), and `gpt-realtime-2.1-mini`/`alloy` through Realtime after live account/API probes and hearing a clear speaker sample. Luna uses `reasoning_effort=none` for existing Chat Completions tool compatibility. Live synthetic manifold/fever follow-ups, JSON app routing with a real local dice action, and a tool-result round trip passed. See [configuration, costs and recovery](docs/openai-upgrade.md); final device acceptance is recorded in TODO.md.

The [TTS migration guide](https://developers.openai.com/api/docs/guides/text-to-speech) directs tts-1 users to gpt-realtime-2.1-mini through the Realtime API; that model cannot simply replace tts-1 in the existing Speech endpoint call. R01 implements the audio/session adapter with bounded WAV output and cleanup while preserving the current conversation behavior. The owner confirmed normal spoken replies, contextual follow-ups, wake detection and LEDs on the Zero 2 W; R01 is complete. A full redesign of wake detection or input turn-taking is not required solely to migrate speech output. SecondContext and automated judges remain optional.

**Completion:** a reproducible, supported stack preserves the demonstrated contextual conversation on the Zero 2 W, with working ReSpeaker audio and documented recovery. Record versions, live API results, and a short resource/responsiveness check. State Pi 3 A+ validation separately. Then deliver F06; avoid expanding modernization into unrelated refactoring or infrastructure work.

## First New Feature After Modernization: Easier Follow-Up Conversation

**F06: after answering, briefly listen for the next question without requiring another wake word.** Reuse the existing conversation history and voice pipeline. This adds convenience to a capability that already works.

The intended flow is wake word → question → spoken answer → short follow-up window → another answer, or return to wake-word listening when the window expires. The completed F06 implementation uses a six-second window with a configurable 0.35-second echo guard, green readiness LEDs and a small local Silero speech detector; setting the window to zero disables it. Explicit follow-up turns retain context without an idle/topic reset. See [usage and recovery](docs/follow-up-listening.md). The window opens after successful playback and closes quietly on silence, with no idle cloud traffic.

The owner confirmed multi-turn follow-ups without repeated wake words, retained context, and a fresh wake-word question after expiry on the Zero 2 W. Acoustic checks passed speaker-echo rejection, silent expiry and disabled behavior. A missed short utterance led to reducing the required confident speech onset to one 80 ms block; the owner accepted the corrected experience. Interruption during playback remains separate.

F06 builds on the completed modernization without replacing the working Python environments. R01 rollback is retained; see TODO.md for validation and remaining hardware/noise limits.

## Subsequent Product Priorities

1. **F03 — Understandable failure and recovery.** Bound provider waits; give a short locally playable failure message; return to listening. Reuse existing connectivity prompts where appropriate. Use a configurable 20-second HTTP network-operation timeout with no automatic retries, and a 30-second Realtime generation deadline. Empty transcription and failed requests use bundled voice clips; failures return to wake listening without replaying old audio. These are per-operation limits, not a whole-turn deadline. See [behavior and recovery](docs/failure-recovery.md).
2. **F02 — Interruption and correction.** The owner selected physical-button interruption first: press during a spoken answer, wait for green, then supply a contextual correction. Stop stale playback without restarting the original request or replaying its completed actions; preserve app/tool results. This does not undo actions or cancel work during thinking. The owner confirmed the physical-button correction flow on the Zero 2 W. Keep spoken interruption disabled until separately validated against speaker echo. See [button configuration and limits](docs/button-interruption.md).
3. **F04 — Current-information answers.** Use the existing GPT-6 Luna/account with hosted Responses web search, selected as a read-only lookup from the current conversation flow. Bound calls/output, retain cited evidence, name sources aloud and preserve links in displayed/logged answers. Missing evidence produces an explicit inability to verify; unresolved source disagreements remain visible. The lookup reader has no action tools, and co-requested actions are not executed. No extra service, local browser or app installation is required. The owner confirmed sourced speech and a contextual follow-up on the Zero 2 W. See [configuration, evidence and limitations](docs/current-information.md).
4. **F05 — Simple controls.** Preserve immediate button interruption/correction; add a 1.5-second hold for capture mute/unmute and a small, opt-in trusted-LAN phone page for volume, stop, mute and new conversation. Close the microphone stream before showing steady red, preserve mute across restarts, and suppress stale output after local cancellation. Exact spoken controls use existing cloud transcription; phone/button paths work without Internet. New conversation clears chat context, not logs or app state. See [controls, access and limits](docs/local-controls.md).
5. **H03 — Reliable timers.** Persist local countdowns before confirming them. The owner chose a repeating local chime for up to two minutes, with button/phone dismissal; microphone mute preserves alerts, while output volume applies. Recover pending/overdue timers across service restarts; use monotonic deadlines within a boot and OS-clock deadlines across reboots, stating the no-RTC power-loss limitation. Keep missed timers visible and allow offline local creation/cancellation. See [timer behavior and limits](docs/timers.md).
6. **H04 — Reminders and Shopping.** Use one shared local Shopping list with normalized duplicate additions kept once, and one-off reminders in a configurable IANA timezone (owner default: Europe/Bucharest). Clarify vague/ambiguous times before saving; preserve scheduled UTC instants across timezone changes. Reuse the local chime and show reminder text on the phone page, including offline. Commit storage changes before confirming them; retain state/cancellation across restart. See [configuration, semantics and limits](docs/household.md).
7. **Everyday usefulness.** H05 adds on-demand Open-Meteo current/daily weather with source, city and freshness information. The owner's selected location flow is config city override, saved spoken city, optional keyed ipgeolocation.io discovery, then a city question whose answer is saved. IP-derived location is disclosed as approximate; ambiguous cities need clarification. No forecast is invented or reused on failure. See [weather configuration and limits](docs/weather.md). Follow with one enjoyable trivia/story experience; choose subsequent features from household use.
8. **H06 — Manage setup from a phone.** The owner selected follow-up duration, reminder timezone, home weather city and write-only provider keys on the existing trusted-LAN page. Require explicit Save & apply, retain a private one-step undo across restart, and preserve working runtime settings on apply failure. Local test sound and three-second microphone record/playback need no provider; recording is refused while muted. Keep the page available for entering the first OpenAI key. See [phone setup, recovery and access limits](docs/phone-setup.md); Wi-Fi provisioning security remains H02.

H01 keeps conversation logging off by default, with optional private-file content logs limited to seven days and 1 MiB. Console/journal diagnostics omit conversation text even when file logging is enabled. Per-turn audio cleanup and a confirmed phone deletion action clear this installation's logs/audio and chat memory while preserving household data, settings and keys. Historical journals, other installations/backups, app-owned data and provider records remain outside that action; see [privacy and retention](docs/conversation-privacy.md).

H02 protects the existing Wi-Fi provisioning flow with one random, persistent device code used only to join protected setup Wi-Fi. The owner chose a single code entry: no second page login. Serve the page at `http://192.168.4.1` on port 80 and provide Show Wi-Fi password on the home-network form. Retrieve the setup code explicitly for a label/private notes. Bind the page to the setup address/interface and subnet, and require session-token-protected changes; never report submitted passwords or raw command failures. Write credentials only to private files and preserve working saved networks on failed joins. Close setup after Wi-Fi connects even without Internet, and keep associated phones from being disconnected during setup. The ordinary phone controls remain a separate trusted-LAN service. See [onboarding, credential delivery and recovery](docs/wifi-setup.md).

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

R02 bounds retained conversation using the owner's selected defaults: 32 recent complete exchanges and 256 KiB of UTF-8 JSON messages, configurable in `[openai]`. Evict whole exchanges, preserving tool-call/result pairs; disclose missing older context to the model rather than inventing details or replaying actions. Discard the inactive archive, which has no retrieval path. An exceptionally oversized exchange leaves a small omission notice; a pending oversized tool round stops before another provider call. Existing short contextual conversations, follow-up behavior, privacy controls and persisted household data remain intact. No summarization requests or audio/thread changes are needed. See [retention policy and measurements](docs/conversation-retention.md) and TODO.md for hardware acceptance and limits.

Adopt API workflow changes required by supported models during R01, including the speech-output migration. Broader streaming input or turn-taking changes should serve a specific interaction improvement. Keep cloud sessions intentional and avoid unnecessary idle traffic. Advertise physical mute only if the hardware actually disables capture.

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

U02 establishes a current tested ARM64 dependency set; afterward, maintain it with deliberate updates. The openWakeWord export mismatch is documented in its [0.6.0 source](https://raw.githubusercontent.com/dscripka/openWakeWord/v0.6.0/openwakeword/__init__.py). Preserve a recoverable working environment while testing replacements, and document compatibility exceptions rather than silently freezing old versions.

## Review Findings and Delivery Workflow

The local `CODE_REVIEW_2026_06_27.md` must never be committed. Preserve its implemented signature/path/manifest protections and audio-worker improvements. Its assertion that context growth was fixed was incorrect: full archived messages remained in RAM. R02 replaces that retention with the explicit policy above. Classifier compatibility, privacy, and provisioning findings were carried into their respective deliveries; the review also reproduced a password appearing in provisioning exceptions, addressed in H02. Existing LEDs, wake-word selection, apps, and tests are foundations to retain.

The owner's requested order is modernization first (U01, U02, R01), then F06 and the other useful additions. Implement one bounded TODO item, run appropriate checks, and record behavior, evidence, and limitations. Mark it complete only when its acceptance criteria are met. Commit implementation, tests, relevant configuration/docs, and TODO update together with a short imperative subject and brief description of behavior and validation. Keep unrelated changes out of the commit. Local commits do not authorize pushing or deployment.
