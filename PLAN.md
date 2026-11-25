# Product and Implementation Plan

Updated: 2026-11-25. Ordered work: [TODO.md](TODO.md). Contributor workflow: [AGENTS.md](AGENTS.md).

## Product Direction

Build an affordable voice assistant that gives useful answers and makes short conversations easy. Prioritize complete improvements people can use over broad refactors or engineering infrastructure. Write for curious makers, including Maker Faire participants without deep software experience.

Target Raspberry Pi Zero 2 W and Pi 3 A+ with 512 MB RAM. Develop and validate on the available Zero 2 W; do not claim Pi 3 A+ support without testing it. Keep audio, controls and small household stores local and lightweight; use hosted services for reasoning and speech. No browser or general-purpose language model runs on the Pi.

This plan describes remaining work. Delivered behavior belongs in [the capability guides](docs/README.md); dated measurements and release limits are in [the release assessment](docs/reference/release-check-2026-11-25.md). Earlier implementation and acceptance records remain in Git history, rather than a growing completed checklist.

## Next Priority: A Practical Phone Interface

Complete **UI01–UI04**, then **S01 streaming playback**, before optional entertainment or SecondContext work. Improve the existing interface and voice pipeline in bounded deliveries.

### UI01 — Open the device IP, without a port number

Serve normal administration at `http://<device-IP>/` on port 80. Make installation and upgrades configure this reliably without running the assistant as root. Keep the current trusted-LAN access model explicit; port 80 does not add authentication or HTTPS.

Preserve Wi-Fi onboarding at `http://192.168.4.1`: one device code to join the protected setup network, no second page login, network selection/manual entry, and shutdown after joining Wi-Fi. Normal administration must not conflict with its listener or become available to setup clients accidentally. Choose a lightweight binding or forwarding arrangement after checking both service lifecycles. Test normal LAN operation, setup handoff and recovery; leave a recoverable configuration if binding fails.

### UI02 — Separate pages for separate tasks

Use a small router-style interface with consistent navigation and distinct URLs:

| Page | Purpose |
| --- | --- |
| Home | Understand connection/listening status; volume, speaker mute, microphone mute, Stop and New conversation |
| Timers | Create, inspect, cancel and dismiss countdowns |
| Reminders | Schedule and manage reminders, with the active timezone visible |
| Shopping | Add, remove and read the shared list |
| Settings | Everyday settings, provider keys, audio checks and advanced configuration |
| Privacy | Conversation logging, retention and deliberate deletion |

Keep pages usable on a phone, with readable labels, keyboard-accessible controls and clear success/error feedback. Preserve edits during status refreshes and explain unsaved changes when navigating away. Use local assets; household pages and controls must remain usable without Internet. Do not redesign the working Wi-Fi setup page.

### UI03 — Controls that fit their purpose

Replace louder/quieter buttons and numeric volume entry with a labelled slider showing the current percentage and a speaker-mute button. Unmuting restores the previous audible volume. Keep microphone mute visibly separate: it stops capture, while speaker mute silences replies and alerts. Show actual device state, including changes made by voice or another phone; failed mixer operations must not appear successful.

Review the other pages for avoidable typing, unclear action names, missing feedback and accidental destructive actions. Use suitable input controls and empty states, preserving timer, reminder, Shopping and privacy semantics. Keep this a focused usability pass, not a new UI framework.

### UI04 — All configuration available from the phone

Mirror every supported option in `rpi_assistant/config.ini` in the UI, including advanced settings and named MCP server sections. Inventory the actual parser and [example configuration](rpi_assistant/config.ini.example), not just the current phone whitelist. Group settings by purpose; explain units, defaults and practical effects. Everyday users should not need to understand audio device identifiers or model parameters to get started.

Keep explicit **Save & apply** and **Undo last change**. Validate fields and combinations before saving; label changes that need a restart and recover the previous working configuration if applying fails. Preserve file-over-environment precedence, unknown entries and private file permissions. Show whether a value is saved, inherited or a default where that affects editing. Keys remain write-only with configured status, deliberate replacement/removal and no disclosure through responses or errors. Exposing a provider setting does not implement a new provider.

Advanced changes to control binding, hardware, storage paths, app trust or MCP commands need clear consequences and recoverable application. Moving a state path must not silently make household data appear deleted. Do not extend this work into Wi-Fi provisioning's separate configuration. Verify complete coverage against the parser, including optional/commented settings and dynamic sections; no silently omitted fields.

## S01 — Start Speaking While Audio Arrives

The current Realtime adapter receives audio chunks but writes a complete WAV before playback. Feed those chunks to playback as they arrive, using a small bounded buffer. Retain the current transcription, reasoning, tool actions and conversation history; text-generation streaming and continuous cloud microphone sessions are separate work.

Start playback before generation finishes, with clear speech and no gaps under normal conditions. Preserve the WM8960 playback format/volume fix, speaker controls, button interruption and stale-output cancellation. Cancellation must stop both queued audio and the provider stream without replaying an executed action. Open follow-up listening only after actual playback ends and the echo guard completes. Timer/reminder alerts and local audio checks must still coexist with speech.

Handle a disconnect before audio and a failure after partial speech honestly: stop, give appropriate local feedback, and recover to listening without replaying the answer. Keep timeouts, buffer limits, audio cleanup and content-free diagnostics. Retain a working fallback while validating the change.

Compare the current and streaming paths on the Zero 2 W using short and longer synthetic replies: end-of-question to first audible speech, first audio arrival, playback completion, memory and audible continuity. Report repeated observations and cloud variability; do not claim that faster playback removes transcription or reasoning delays. No fillers, hesitation sounds or filler-selection API calls are planned.

## Boundaries to Preserve

- Useful spoken answers, contextual follow-ups, app results and physical-button correction already work. Do not schedule a memory rebuild or voice interruption without a demonstrated need and acoustic validation.
- Preserve offline controls, persistent timers/reminders/Shopping, truthful microphone capture status, opt-in conversation logging and private keys. Keep app catalog signatures, checksums and safe paths intact.
- Keep one wake model, bounded audio queues and the configured recent-context limits. Do not add idle cloud traffic or heavyweight local services.
- Preserve working checkouts, environments and configuration during device trials. The owner accepted rebuilding an SD card if necessary; a full-image backup is not a renewed approval gate.

## Later Work and Known Limits

After the priorities above, retain optional **E01** (one enjoyable game) and **C01–C03** (explicit personal memory, correction/deletion and a household manual). SecondContext runs externally and is not required for ordinary conversation. Verify its actual API, identity and deletion contracts when integration begins; preserve ordinary answers during outages.

The reproduced approximately 90-second shutdown hang remains unresolved. Track it as **FIX05**, and fix it sooner if it blocks safe application of a planned change; do not silently treat reliable restarts as established. Before broader distribution, extend fresh-card setup, longer household use, router reconnection, power-loss/clock recovery and difficult-acoustic checks. Pi 3 A+ remains untested. These gaps do not prevent trying useful improvements on the available Zero 2 W.

## Delivery and Documentation

Implement one bounded item at a time. Use focused regression checks and real phone/voice trials for changed behavior; tests alone do not establish usability. Keep measurements attached to the feature rather than creating a prerequisite benchmark or judging platform. Record exact evidence and limits when completing an item, update its component guide, and commit code, relevant tests/config/docs and TODO together. Remove completed entries from active planning once their evidence is recorded in documentation and Git history. Local commits do not authorize pushing or deployment.

Keep README short, QUICKSTART a path to the first reply, and the guide index focused on things to try. Update usage instructions when behavior ships, not merely when it is planned. Never commit credentials or `CODE_REVIEW_2026_06_27.md`; preserve unrelated user edits.
