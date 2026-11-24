# Repository Guidelines

## Product Priorities

Prioritize useful features and a usable product over software engineering perfection. Start with the user’s task and deliver the smallest complete improvement they can use. Avoid speculative abstractions, broad refactors, and tooling work unless they directly enable a feature or fix a user-visible problem. Keep essential security and reliability safeguards.

Treat the current assistant as a working prototype, not a proven product. Validate everyday voice interactions on hardware, including responsiveness, understandable feedback, and recovery from failures. A passing unit test alone does not establish usability.

Preserve capabilities the owner has demonstrated. Distinguish observed failures from code-level limitations and untested assumptions; reproduce the specific problem before prescribing a replacement architecture. Useful spoken answers and short follow-ups already work on the owner's device.

Target Raspberry Pi Zero 2 W and Raspberry Pi 3 A+ with 512 MB RAM. Keep local audio and controls lightweight; run reasoning and optional SecondContext storage/retrieval on external services. Validate on baseline hardware before claiming support.

## Planning & Delivery Workflow

Read [PLAN.md](PLAN.md) for product decisions, constraints, and acceptance gates, and [TODO.md](TODO.md) for ordered implementation items before starting feature work. Keep both documents aligned as decisions change. Implement a bounded item, run relevant checks, and record validation evidence and limitations in TODO.md. Mark it complete only when its acceptance criteria are met.

Start with a user-visible feature. Attach necessary setup, tests, and simple measurements to that work; do not introduce a prerequisite milestone for baselines, CI, benchmarking, or general hardening. Fix concrete blockers as they appear. Broader release validation must not prevent the owner from trying a working feature on the available Pi; state any remaining hardware or reliability limitations honestly.

After each successfully implemented item, commit the implementation, relevant tests/configuration/documentation, and TODO update together. Use a short imperative subject and a brief description explaining the behavior change, item ID, and validation. Do not accumulate completed items into an unrelated large commit. Stage only intended files; preserve unrelated user changes and leave incomplete items unchecked. Local commits do not authorize pushing or deployment.

Never commit `CODE_REVIEW_2026_06_27.md`; its actionable findings belong in PLAN.md and TODO.md. Keep the original ignored locally.

## Project Structure & Module Organization

- `rpi_assistant/app/` contains the voice assistant: audio capture, OpenAI interaction, MCP integration, LEDs, configuration, and app management. `__main__.py` is the entry point.
- `rpi_assistant/piwifi/` contains the Flask Wi-Fi provisioning UI and templates.
- `voice_apps/apps/<app_id>/<version>/` holds app bundles; `voice_apps/index.json` is the signed catalog.
- `tests/` contains unit and integration tests; `tests/support/` provides an MCP server fixture.
- `scripts/` and `systemd/` handle deployment. Audio assets live in `rpi_assistant/app/audio_prompts/`; enclosure designs live in `enclosure/`.

## Build, Test, and Development Commands

Run commands from the repository root with your chosen Python environment activated:

- `python -m pip install -r rpi_assistant/requirements.txt` installs dependencies; audio and GPIO packages may require Raspberry Pi system libraries.
- `cp rpi_assistant/config.ini.example rpi_assistant/config.ini` creates local configuration. Set credentials and audio devices before starting.
- `python -m rpi_assistant.app` starts the assistant.
- `python -m unittest discover -s tests -v` runs the full test suite.
- `make test-mcp PYTHON=python` runs MCP, OpenAI client, and configuration tests using the active interpreter.
- `make help` lists installation targets. On the target Pi, `make setup` installs dependencies, drivers, and services and prompts for reboot; `make update` refreshes an existing installation.

## Coding Style & Naming Conventions

Use four-space Python indentation, `snake_case` for modules/functions, `PascalCase` for classes, and `UPPER_SNAKE_CASE` for constants. Follow surrounding code, retaining type annotations and configuration dataclasses. Keep hardware, transport, and application concerns in their existing modules. Pyright configuration is provided; no formatter or lint command is enforced in the repository.

## Testing Guidelines

Use `unittest`, naming files `test_*.py` and methods `test_<behavior>`. Mock external APIs and hardware; use temporary directories for filesystem tests. MCP integration tests launch subprocesses and require the MCP dependency plus the separate `rpiface` package for `rpiface.mcp.server`. Add regression tests for behavior changes. No coverage threshold is configured; report any hardware checks performed separately.

## Commit & Pull Request Guidelines

Follow the history’s short, imperative subjects, such as `Add generic MCP tool manager integration`. Keep commits focused. PRs should explain the behavior change, link relevant issues, and list validation results and hardware limitations. Include screenshots for provisioning UI changes and update configuration examples when adding settings.

## Security & Configuration

Keep API keys, signing private keys, and local `config.ini` files out of commits. Configuration files override environment variables. Preserve catalog signature and bundle checksum verification when changing app installation.

## Development Device

Use a Raspberry Pi on your local network for end-to-end development. Configure SSH key access locally, for example `ssh -i <private-key-path> <user>@<device-address>`, or use an alias in `~/.ssh/config`. Keep device addresses, usernames, key paths, and privilege details in private local notes rather than this guide.

Clone the repository into the device user’s home directory and follow `QUICKSTART.md` for setup. For an existing clone, inspect its branch and uncommitted changes before updating; preserve device configuration. Use `sudo` for installation and service management as needed. Validate wake-word detection, recording, responses, and playback on the device, and report what was actually tested and any remaining usability gaps.
