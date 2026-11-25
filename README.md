# LLMRPiAssistant

🤖 An open-source voice assistant for Raspberry Pi powered by OpenAI APIs and SeeedStudio reSpeaker HATs.

## Overview

LLMRPiAssistant is a fully-featured voice assistant that brings Alexa-like functionality to your Raspberry Pi. It uses wake word detection, real-time speech recognition, conversational AI, and text-to-speech for natural voice interactions.

### Key Features

- 🎙️ **Wake Word Detection** - Always listening for activation using OpenWakeWord
- 🗣️ **Speech Recognition** - Powered by OpenAI GPT-Transcribe
- 🧠 **Conversational AI** - Natural responses using GPT-4o-mini (or any OpenAI chat model)
- 🎲 **Local Voice Apps** - Installable experiences such as Dice, Truth or Dare and Ask! that run before chat fallback
- 🔊 **Text-to-Speech** - Realistic voice output with OpenAI TTS
- 💡 **LED Feedback** - Visual indicators with reSpeaker HAT LED ring
- � **WiFi Provisioning** - Easy network configuration via captive portal when offline
- 🔧 **Highly Configurable** - Extensive configuration options via config.ini or environment variables
- 📊 **Interaction Logging** - Comprehensive JSON logs for all conversations
- 🔄 **Systemd Integration** - Run as a system service with automatic restart

### Hardware Requirements

- **Raspberry Pi** (Zero 2 W, 3A+, 4, or 5 recommended)
- **SeeedStudio reSpeaker HAT** (2-Mic or 4-Mic Array)
- **Speaker** (3.5mm audio jack, directly connected speaker or USB speaker; Bluetooth should work with BlueZ but haven't tried)
- Internet connection for OpenAI API access

### Software Dependencies

- Python 3.9+
- OpenAI API account and key
- System packages: `portaudio`, `alsa-utils`, `ffmpeg`

## Installation

### Quick Setup

For Python dependency upgrades, use a separate environment and follow
[the Python upgrade guide](docs/python-upgrade.md). The pinned set targets
Raspberry Pi OS 64-bit with Python 3.13; wake models are fetched during setup.

For the WM8960 ReSpeaker 2-Mic v1, use the Raspberry Pi kernel audio driver.
See [OS/audio upgrade and recovery](docs/audio-upgrade.md) before updating an
existing device. Other HAT revisions need their own audio setup.

The included Makefile installs the assistant and configures this audio path:

```bash
# Complete installation and setup
make setup
```

This will:
1. Install system dependencies (portaudio, alsa-utils, ffmpeg)
2. Create Python virtual environment at `/opt/venvs/rpi-assistant`
3. Install Python packages
4. Configure the kernel WM8960 overlay and preserve the ALSA card name
5. Configure the assistant as a CLI command
6. Install rpi-assistant as a systemd service

After installation, **reboot your Raspberry Pi** to load the audio drivers:
```bash
sudo reboot
```

### WiFi Provisioning Setup (Optional but Recommended)

For portable use (taking your assistant to different locations), install the WiFi manager:

```bash
# Install WiFi provisioning system
make install-wifi
```

This enables automatic WiFi management:
- **On boot**: Tries to connect to known WiFi networks
- **Without saved Wi-Fi**: Starts a private setup access point; retrieve its name/code with `sudo piwifi-setup-code`
- **Web UI**: Join setup and visit `http://192.168.4.1` to configure WiFi, with no second login
- **Auto-reconnect**: Remembers multiple networks and reconnects automatically

The system uses NetworkManager and will remember all configured networks, automatically connecting to any available one.

### Manual Installation Steps

If you prefer manual installation or need to customize:

```bash
# 1. Install system dependencies
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip libportaudio2 portaudio19-dev alsa-utils git ffmpeg

# 2. Create Python virtual environment
sudo mkdir -p /opt/venvs
sudo python3 -m venv /opt/venvs/rpi-assistant
sudo /opt/venvs/rpi-assistant/bin/pip install --upgrade pip
sudo /opt/venvs/rpi-assistant/bin/pip install -r rpi-assistant/requirements.txt

# 3. Configure kernel audio (ReSpeaker 2-Mic v1 / WM8960 only)
make install-voicecard

# 4. Reboot
sudo reboot
```

## Configuration

### Create Configuration File

Copy the example configuration and add your OpenAI API key:

```bash
cd rpi-assistant
cp config.ini.example config.ini
nano config.ini  # Edit and add your OPENAI_API_KEY
```

### Configuration Options

The configuration file supports extensive customization:

#### Audio Settings
- **sample_rate**: Audio sample rate (default: 16000 Hz)
- **chunk_size**: Audio chunk size for processing (default: 1280 frames)
- **channels**: Number of input channels (default: 4 for 4-mic HAT)
- **mic_channel_index**: Which microphone channel to use (0-3)
- **device_match**: Substring to match audio device name (default: "seeed")

#### Wake Word Detection
- **threshold**: Detection sensitivity (0.0-1.0, default: 0.5)
  - Lower = more sensitive (more false positives)
  - Higher = less sensitive (might miss wake word)
- **cooldown_seconds**: Minimum time between detections (default: 1.0)

#### Recording Settings
- **max_duration_seconds**: Maximum recording length (default: 10.0)
- **silence_hold_seconds**: Stop after this much silence (default: 0.8)
- **silence_rms_threshold**: Silence detection level (default: 0.007)
  - Lower = more sensitive to silence
  - Adjust based on environment noise
- **pre_roll_seconds**: Audio captured before wake word (default: 0.4)

#### Follow-up conversation
After a spoken answer, steady green LEDs indicate a six-second window for another
question without the wake word. Silence returns to normal wake-word listening.
Set `[recording] follow_up_window_seconds = 0` to disable it. See
[follow-up listening](docs/follow-up-listening.md) for timing, noise limits and checks.

#### OpenAI API
- **api_key**: Your OpenAI API key (REQUIRED)
- **whisper_model**: Recorded-speech model; historical setting name (default: "gpt-transcribe")
- **chat_model**: Conversation and app-intent model (default: "gpt-6-luna")
- **tts_model**: Speech-output model (default: "gpt-realtime-2.1-mini")
- **tts_backend**: `realtime` writes WAV through a short-lived WebSocket session; legacy `speech` uses MP3.
- **reasoning_effort**: `none` for Luna with existing Chat Completions tools.
- **tts_timeout_seconds**: Generation deadline (default: 90 seconds).
- Existing installations must migrate model settings together: see [OpenAI upgrade and recovery](docs/openai-upgrade.md).
- **tts_voice**: Realtime voice (tested default: "alloy")
- **system_prompt**: Customize assistant personality
- **max_tokens**: Response length limit (default: 500)
- **temperature**: Response creativity (0.0-2.0, default: 0.7)

#### Audio Output
- **enabled**: Enable/disable TTS playback (default: true)
- **device**: ALSA playback device (default: "hw:0,0")
- **tts_output_path**: Temporary file for audio (default: "/tmp/response.wav")

#### Logging
- **log_file**: Path to interaction log (default: "openai_interactions.log")
- **log_level**: Logging verbosity (DEBUG, INFO, WARNING, ERROR)

#### RPiFace (Optional)

RPiFace can mirror the assistant's deterministic lifecycle on a local display:

```ini
[rpiface]
enabled = true
base_url = http://127.0.0.1:8765
timeout_seconds = 0.3
```

The feature is disabled by default. Start RPiFace Core separately; the voice
assistant continues normally if it is stopped or unreachable. Face requests
run on a dedicated best-effort worker, never in the real-time audio callback.
The mapped states are `idle`, `listening`, `thinking`, and `speaking`.

#### Generic MCP tools (Optional)

MCP is independent of the deterministic RPiFace lifecycle integration. When
enabled, the assistant initializes every configured server, discovers its tools,
and exposes them to the chat model as namespaced function tools such as
`rpiface__set_mood`. A bounded tool loop routes calls to the owning server and
returns results to the model. One unavailable server does not disable other
servers or normal chat.

```ini
[mcp]
enabled = true
timeout_seconds = 30
max_tool_rounds = 3
servers = rpiface, utility

[mcp.server.rpiface]
transport = stdio
command = /opt/venvs/rpiface/bin/rpiface-mcp
args = []

[mcp.server.utility]
transport = streamable-http
url = https://mcp.example.test/mcp
token_env = UTILITY_MCP_TOKEN
```

The environment equivalents for global settings are `MCP_ENABLED`,
`MCP_TIMEOUT_SECONDS`, and `MCP_MAX_TOOL_ROUNDS`. Define all servers through
`MCP_SERVERS_JSON` when no `servers` option is present in `config.ini`.

```bash
export MCP_ENABLED=true
export MCP_SERVERS_JSON='[{"name":"rpiface","transport":"stdio","command":"/opt/venvs/rpiface/bin/rpiface-mcp"}]'
```

Never put bearer values in the JSON or INI file. `token_env` contains only the
name of an environment variable; its value is read when the HTTP transport is
opened and is never included in tool schemas, prompts, messages, or results.
Stdio children receive only a small safe environment plus names explicitly
listed in `env_vars`.

### Environment Variables

All settings can also be set via environment variables (config.ini takes precedence):

```bash
export OPENAI_API_KEY="sk-..."
export OPENAI_CHAT_MODEL="gpt-4o"
export WAKEWORD_THRESHOLD="0.6"
export RECORDING_SILENCE_RMS="0.01"
export RPIFACE_ENABLED="true"
export RPIFACE_BASE_URL="http://127.0.0.1:8765"
export RPIFACE_TIMEOUT_SECONDS="0.3"
```

## Usage

### Running as a Systemd Service (Recommended)

The assistant can run automatically on boot as a systemd service:

```bash
# Enable and start the service
sudo systemctl enable rpi-assistant.service
sudo systemctl start rpi-assistant.service

# Check status
sudo systemctl status rpi-assistant.service

# View logs
sudo journalctl -u rpi-assistant.service -f

# Stop the service
sudo systemctl stop rpi-assistant.service
```

### Running from Command Line

After configuration, you can also run the assistant manually:

```bash
# If installed with Makefile
rpi-assistant

# Or run directly
cd rpi-assistant
/opt/venvs/rpi-assistant/bin/python -m app
```

### Interaction Flow

1. **Listen Mode**: LED ring shows blue breathing pattern
2. **Wake Word**: Say wake word (e.g., "hey mycroft")
3. **Recording**: LED shows wakeup animation, speak your command
4. **Processing**: Audio is transcribed, then routed to a local voice app if one matches
5. **Fallback Chat**: If no local app handles the request, the transcript is sent to OpenAI chat
6. **Response**: Assistant speaks response with LED speak pattern
7. **Repeat**: Returns to listen mode

### Installable Voice Apps

Catalog entries are available to install, not preinstalled. For Dice, first say
`install app dice`, then `roll a die`. A recognized request for a missing app now
explains how to install it; it does not silently install the app or pretend to run it.

- **Truth or Dare**: Install `truth_or_dare`, then say phrases like `play truth or dare` or `do truth or dare for Alex` to start a short stateful flow that keeps the next utterance inside the game.
- **Ask!**: Install `ask`, then say `play ask` or `ask game` to get a deterministic conversation starter without calling the chat model.
- **Resume / Status**: Say `resume app`, `resume game`, or `what game is active` to continue or inspect the currently active multi-turn app.
- **Cancel**: Say `stop game`, `cancel app`, or `nevermind` to end the active local app and return to normal assistant behavior.
- **App Management**: Say `list installed apps`, `list available apps`, `list app versions truth or dare`, `install app ask`, `install app truth or dare`, `install app dice at 0.1.0` or `install app dice@0.1.0`, `describe app ask`, `upgrade app dice`, `app store health`, or `uninstall app dice` to manage installable apps.

### Dynamic App Discovery

The assistant now discovers apps dynamically instead of relying on a hardcoded list.

- **Built-in apps**: The assistant core no longer ships party games as built-ins; `rpi_assistant/app/apps/` only contains the shared base interfaces.
- **External apps**: Manifest-based app bundles installed under `~/.config/rpi-assistant/apps/` are loaded automatically.
- **Bundle layout**: Each installed app lives in its own directory and must include `manifest.json` plus the Python module named by the manifest entrypoint.
- **Public app store**: The repo now includes a catalog under `voice_apps/`. That directory is designed to work as the public app-store source for named installs such as `install app dice`, and the same format can be served from a remote raw URL.

This now supports local app lifecycle commands directly: installation can copy a bundle from a filesystem path or resolve spoken app names from the repo catalog, repository installs can pin an explicit version, upgrades compare manifest versions, descriptions read manifest metadata, active apps can be restored after a restart, and uninstall removes the installed bundle.

Installed external apps also persist source metadata locally, so `describe app <id>` can distinguish path-based sideloads from repository-managed installs.

Active multi-turn apps also persist their in-progress state in `~/.config/rpi-assistant/active_app_state.json`, so a restart can resume the app that currently owns the conversation.

### Repository App Catalog

The repository-backed catalog uses a small index file at `voice_apps/index.json`:

```json
{
   "apps": [
      {
         "id": "ask",
         "versions": [
            {
               "version": "0.1.0",
               "bundle": "apps/ask/0.1.0",
               "files": ["app.py", "manifest.json"],
               "sha256": "..."
            }
         ]
      },
      {
         "id": "dice",
         "versions": [
            {
               "version": "0.1.0",
               "bundle": "apps/dice/0.1.0",
               "files": ["app.py", "manifest.json"],
               "sha256": "..."
            }
         ]
      },
      {
         "id": "truth_or_dare",
         "versions": [
            {
               "version": "0.1.0",
               "bundle": "apps/truth_or_dare/0.1.0",
               "files": ["app.py", "manifest.json"],
               "sha256": "..."
            }
         ]
      }
   ]
}
```

Each release points to a manifest-based app bundle inside the repo, declares the files that belong to that release, and includes a SHA-256 checksum for bundle verification. That makes the catalog easy to host directly from the public main branch later without changing the app bundle format.

Optionally, the catalog can be wrapped in signed metadata:

```json
{
   "catalog": {
      "apps": []
   },
   "signing": {
      "algorithm": "ed25519",
      "key_id": "default",
      "signature": "..."
   }
}
```

When you configure a trusted Ed25519 public key, the assistant verifies the catalog signature before using the repository.

### External App Manifest

Installable apps must include a `manifest.json` file with at least these fields:

```json
{
   "id": "dice",
   "name": "Dice",
   "version": "0.1.0",
   "entrypoint": "app:DiceApp",
   "triggers": ["roll test die"]
}
```

Minimal bundle layout:

```text
dice/
   0.1.0/
      manifest.json
      app.py
```

The manifest `entrypoint` uses the format `module_path:ClassName`. For the example above, `app.py` must define a `DiceApp` class that subclasses `VoiceApp`.

For a remote repository, point the assistant at the raw directory root that contains `index.json`. Each release is downloaded file-by-file from the declared bundle path and verified against the catalog checksum before installation.

### App Store Configuration

The assistant now supports a dedicated `[app_store]` config section:

```ini
[app_store]
default_repository_url = https://raw.githubusercontent.com/bdobrica/LLMRPiAssistant/main/voice_apps/
use_local_repository_fallback = true
trusted_public_key =
require_signature = true
```

- `default_repository_url` is the default remote store used for named installs.
- `use_local_repository_fallback` keeps the checked-out `voice_apps/` directory available while developing locally.
- `trusted_public_key` enables Ed25519 signature verification for signed catalogs. If left empty, the assistant loads the shipped key from `voice_apps/public_key.txt`.
- `require_signature` rejects unsigned catalogs for the configured repositories. Remote repositories require signed catalogs by default; set this to `false` only for trusted development repositories.

The same settings can be provided with environment variables: `APP_STORE_DEFAULT_REPOSITORY_URL`, `APP_STORE_USE_LOCAL_FALLBACK`, `APP_STORE_TRUSTED_PUBLIC_KEY`, and `APP_STORE_REQUIRE_SIGNATURE`.

### Signing Catalogs

Use [scripts/sign-app-store.py](scripts/sign-app-store.py) to wrap a catalog in signed metadata:

```bash
/home/bogdan/.venvs/py-rpia/bin/python scripts/sign-app-store.py voice_apps/index.json <base64-private-key>
```

The script prints the matching Base64-encoded public key, which can be shipped in `voice_apps/public_key.txt`.

Recommended local setup:

- Keep the private signing key only on your machine in an ignored file such as `.secrets/app-store-signing-private.key`.
- Commit only the public key in `voice_apps/public_key.txt`.
- Re-sign `voice_apps/index.json` whenever the app catalog changes.

### GitHub Actions Signing

The repo now includes [sign-app-store.yml](.github/workflows/sign-app-store.yml), which re-signs `voice_apps/index.json` on pushes to `main` when the app store changes.

To enable it:

1. Open your GitHub repository settings.
2. Go to `Settings > Secrets and variables > Actions`.
3. Add a new repository secret named `APP_STORE_SIGNING_PRIVATE_KEY`.
4. Paste the Base64-encoded private key from your local `.secrets/app-store-signing-private.key` file.

The workflow derives the matching public key during signing and verifies that it matches `voice_apps/public_key.txt` before pushing the updated signed catalog commit.

### Wake Words

The default OpenWakeWord model supports these wake words:
- "hey mycroft"
- "alexa"
- "hey jarvis"
- "timer"

Check loaded models on startup to see available wake words.

## WiFi Provisioning

The WiFi provisioning system makes your assistant portable and easy to move between networks without needing a monitor or keyboard.

### How It Works

1. **On Boot**: The `piwifi-manager` service checks for network connectivity
2. **Connected**: If connected to a known network, nothing happens - normal operation
3. **Offline**: If no known networks are available:
   - Starts a device-specific setup access point (existing custom names are retained)
   - Launches a local web UI on `http://192.168.4.1`
   - Waits for you to configure WiFi
4. **After Configuration**: 
   - Tries to connect to the new network
   - If successful, stops the AP and setup page and continues in client mode, even without Internet
   - If failed, returns to AP mode for reconfiguration

### Using WiFi Provisioning

**First-time setup or new location:**

1. Power on your Raspberry Pi
2. Wait 30-60 seconds for boot
3. Use the setup network name/code saved during installation with `sudo piwifi-setup-code`
4. Join that network using the device-specific code as its Wi-Fi password
5. Open `http://192.168.4.1` — no second code entry is needed
6. Select or enter your home network name
7. Enter its Wi-Fi password, use **Show Wi-Fi password** if needed, and click **Save & connect**
8. The setup network disconnects while joining; reconnect your phone to home Wi-Fi after success
9. If it fails, rejoin setup and retry; existing saved networks are preserved

Save the code on a device label before moving it. There is no common default password.
See [private credentials, recovery and limitations](docs/wifi-setup.md).

**Moving to a different location:**

The system remembers all configured networks. Simply power on your Pi at the new location:
- If it can connect to any remembered network, it will automatically
- If not, it will start the AP for you to add the new network

No need to reconfigure networks you've already set up - it remembers them all!

### Customizing WiFi Settings

You can customize the AP name and network settings. The device code is stored separately in a private file:

```bash
# Edit the environment configuration
sudo nano /etc/default/piwifi

# Settings you can change:
# AP_SSID=MyCustomName
# Device code: sudo piwifi-setup-code (not an AP_PASSWORD environment variable)
# FLASK_PORT=80
# IFACE=wlan0

# Apply changes
sudo systemctl restart piwifi-manager.service
```

### WiFi Manager Commands

```bash
# Check WiFi manager status
sudo systemctl status piwifi-manager.service

# View live logs
sudo journalctl -u piwifi-manager.service -f

# Restart WiFi manager
sudo systemctl restart piwifi-manager.service

# Retrieve the saved setup name/code privately
sudo piwifi-setup-code

# List saved WiFi networks
nmcli connection show

# Delete a saved network
nmcli connection delete "NetworkName"
```

### Troubleshooting

#### Audio Device Not Found
```bash
# List available audio devices
python -c "import sounddevice as sd; print(sd.query_devices())"

# Update device_match in config.ini to match your device name
```

#### No Audio Playback
```bash
# Test speaker
speaker-test -c2

# List ALSA devices
aplay -L

# Update audio_output.device in config.ini
```

#### WiFi Manager Not Working
```bash
# Check if NetworkManager is running
sudo systemctl status NetworkManager

# Check piwifi-manager status
sudo systemctl status piwifi-manager.service

# View piwifi logs
sudo journalctl -u piwifi-manager.service -f

# Verify the device setup code is available (do not paste it into logs)
sudo piwifi-setup-code
```

#### Cannot Connect to WiFi After Configuration
- Wait 10-20 seconds for connection to establish
- Refresh the web UI to see current status
- Check if password was entered correctly
- Try moving closer to the router
- Check router logs for connection attempts

#### Wake Word Not Detecting
- Adjust `wakeword.threshold` (lower = more sensitive)
- Check microphone channel: try different `mic_channel_index` values (0-3)
- Verify LED feedback shows listening mode

#### Recording Cuts Off Too Early
- Increase `silence_hold_seconds` (allow longer pauses)
- Increase `silence_rms_threshold` (less sensitive to quiet sounds)

## Architecture

### Component Overview

```
┌─────────────────────────────────────────────────────────┐
│                  LLMRPiAssistant                        │
│                                                         │
│  ┌─────────────────┐        ┌──────────────────┐      │
│  │  rpi-assistant  │        │   piwifi         │      │
│  │  (voice app)    │        │   (wifi mgr)     │      │
│  │                 │        │                  │      │
│  │  • __main__.py  │        │  • webapp.py     │      │
│  │  • audio.py     │        │  • templates/    │      │
│  │  • app_loader.py │       │                  │      │
│  │  • app_manager.py│       │                  │      │
│  │  • apps/        │        │                  │      │
│  │  • openai_client│        │                  │      │
│  │  • pixels.py    │        └──────────────────┘      │
│  │  • config.py    │                                   │
│  └─────────────────┘                                   │
│                                                         │
│  ┌─────────────────────────────────────────────────┐  │
│  │  systemd/                                       │  │
│  │  • rpi-assistant.service (voice assistant)     │  │
│  │  • piwifi-manager.service (network manager)    │  │
│  │  • piwifi-flask.service (web UI)               │  │
│  └─────────────────────────────────────────────────┘  │
│                                                         │
│  ┌─────────────────────────────────────────────────┐  │
│  │  scripts/                                       │  │
│  │  • piwifi-manager.sh (network state machine)   │  │
│  │  • install-wifi.sh (wifi setup script)         │  │
│  └─────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┬──────────────┐
        │              │              │              │
        ▼              ▼              ▼              ▼
┌─────────────┐ ┌──────────┐ ┌──────────────┐ ┌─────────┐
│   audio.py  │ │openai_   │ │   pixels.py  │ │ logger  │
│             │ │client.py │ │              │ │   .py   │
│ WakeWord    │ │          │ │ LED Control  │ │         │
│ Recorder    │ │ OpenAI   │ │              │ │ JSON    │
│             │ │ Client   │ │              │ │ Logs    │
└─────────────┘ └──────────┘ └──────────────┘ └─────────┘
      │                │            │
      │                │            │
      ▼                ▼            ▼
┌─────────────────────────────────────────┐
│        Hardware & External APIs         │
│  • reSpeaker HAT (microphone array)    │
│  • LED ring (APA102 via SPI)           │
│  • Speaker (ALSA audio output)         │
│  • OpenAI API (STT, GPT, Realtime)      │
│  • NetworkManager (WiFi control)       │
└─────────────────────────────────────────┘
```

### State Machine

The assistant uses a three-state FSM:

1. **LISTEN_WAKE**: Monitoring for wake word
   - Feeds audio to OpenWakeWord model
   - Maintains pre-roll buffer
   - Transitions to RECORD on wake word detection

2. **RECORD**: Capturing user command
   - Records audio until silence or timeout
   - Real-time silence detection
   - Transitions to PROCESSING when done

3. **PROCESSING**: Handling API calls
   - Blocks new wake word detection
   - Transcribes recorded audio (GPT-Transcribe)
   - Gets AI response (GPT)
   - Generates speech (TTS)
   - Plays audio response
   - Drains audio buffer and returns to LISTEN_WAKE

### Key Design Decisions

- **Thread-Safe Audio Queue**: Audio callback pushes to queue, main thread processes
- **Buffer Overflow Protection**: Drops frames when queue full, clears on state transitions
- **Model State Flushing**: Skips prediction for 30 chunks after PROCESSING to clear internal buffers
- **Graceful Degradation**: Continues without LED support if hardware unavailable
- **Context Manager Pattern**: Ensures proper resource cleanup on exit

## Development

### Project Structure

```
LLMRPiAssistant/
├── LICENSE
├── Makefile                # Installation and setup automation
├── README.md
├── QUICKSTART.md
├── TODO.md
│
├── rpi_assistant/          # Main voice assistant application (Python package)
│   ├── __init__.py
│   ├── config.ini.example
│   ├── requirements.txt
│   ├── app/                # Voice assistant core
│   │   ├── __init__.py
│   │   ├── __main__.py     # Main entry point
│   │   ├── audio.py        # Wake word and recording
│   │   ├── openai_client.py # OpenAI API wrapper
│   │   ├── pixels.py       # LED control
│   │   ├── led_pattern.py  # LED animations
│   │   ├── apa102.py       # SPI LED driver
│   │   ├── config.py       # Configuration management
│   │   └── logger.py       # Interaction logging
│   └── piwifi/             # WiFi provisioning module
│       ├── __init__.py
│       ├── webapp.py       # Flask web UI
│       └── templates/
│           └── index.html  # WiFi configuration UI
│
├── systemd/                # Systemd service definitions
│   ├── rpi-assistant.service    # Voice assistant service
│   ├── piwifi-manager.service   # Network manager service
│   └── piwifi-flask.service     # Web UI service
│
├── scripts/                # Installation and management scripts
│   ├── piwifi-manager.sh   # Network state machine
│   └── install-wifi.sh     # WiFi setup installer
│
└── tests/                  # Test suite (future)
```

### Testing

Test the assistant without hardware LEDs:
```bash
# LEDs are optional - system works without them
python -m app
```

### Extending the Assistant

The modular architecture makes it easy to extend:

1. **Custom Wake Words**: Add models to OpenWakeWord
2. **Different LLM Providers**: Replace OpenAIClient with local models
3. **Additional LED Patterns**: Extend LedPattern class
4. **Custom Commands**: Add command parsing before OpenAI call
5. **Multi-User Support**: Track conversation history per user

## Game Development

This assistant provides an excellent foundation for voice-controlled games! See [TODO.md](TODO.md) for planned game-oriented features including:

- Multi-player support with turn management
- Game state persistence
- Local command parsing for low-latency responses
- Trivia, adventure, and word game templates
- Scoring and leaderboard systems

## License

See [LICENSE](LICENSE) for details.

## Contributing

Contributions welcome! This project is designed to be a flexible foundation for voice-controlled applications on Raspberry Pi.

## Acknowledgments

- **OpenWakeWord**: Local wake word detection
- **OpenAI**: Transcriptions, Chat Completions, and Realtime APIs
- **SeeedStudio**: reSpeaker HAT hardware and drivers
- **Raspberry Pi Foundation**: Amazing single-board computers

## Support

For issues or questions:
1. Check the Troubleshooting section above
2. Review configuration options
3. Check logs in `openai_interactions.log`
4. Verify hardware connections and drivers
