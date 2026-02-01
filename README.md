# LLMRPiAssistant

🤖 An open-source voice assistant for Raspberry Pi powered by OpenAI APIs and SeeedStudio reSpeaker HATs.

## Overview

LLMRPiAssistant is a fully-featured voice assistant that brings Alexa-like functionality to your Raspberry Pi. It uses wake word detection, real-time speech recognition, conversational AI, and text-to-speech for natural voice interactions.

### Key Features

- 🎙️ **Wake Word Detection** - Always listening for activation using OpenWakeWord
- 🗣️ **Speech Recognition** - Powered by OpenAI Whisper for accurate transcription
- 🧠 **Conversational AI** - Natural responses using GPT-4o-mini (or any OpenAI chat model)
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

The included Makefile automates the entire installation process:

```bash
# Complete installation and setup
make setup
```

This will:
1. Install system dependencies (portaudio, alsa-utils, ffmpeg)
2. Create Python virtual environment at `/opt/venvs/rpi-assistant`
3. Install Python packages
4. Clone and install seeed-voicecard driver (with patch applied)
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
- **If offline**: Starts an access point named `PiAssistant-Setup`
- **Web UI**: Connect to the AP and visit `http://192.168.4.1:8080` to configure WiFi
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

# 3. Install seeed-voicecard driver
git clone https://github.com/seeed-studio-projects/seeed-voicecard.git
cd seeed-voicecard
git apply ../seeed-voicecard.patch
sudo ./install.sh

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

#### OpenAI API
- **api_key**: Your OpenAI API key (REQUIRED)
- **whisper_model**: Transcription model (default: "whisper-1")
- **chat_model**: Conversation model (default: "gpt-4o-mini")
- **tts_model**: Text-to-speech model (default: "tts-1")
- **tts_voice**: Voice selection (alloy, echo, fable, onyx, nova, shimmer)
- **system_prompt**: Customize assistant personality
- **max_tokens**: Response length limit (default: 500)
- **temperature**: Response creativity (0.0-2.0, default: 0.7)

#### Audio Output
- **enabled**: Enable/disable TTS playback (default: true)
- **device**: ALSA playback device (default: "hw:0,0")
- **tts_output_path**: Temporary file for audio (default: "/tmp/response.mp3")

#### Logging
- **log_file**: Path to interaction log (default: "openai_interactions.log")
- **log_level**: Logging verbosity (DEBUG, INFO, WARNING, ERROR)

### Environment Variables

All settings can also be set via environment variables (config.ini takes precedence):

```bash
export OPENAI_API_KEY="sk-..."
export OPENAI_CHAT_MODEL="gpt-4o"
export WAKEWORD_THRESHOLD="0.6"
export RECORDING_SILENCE_RMS="0.01"
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
4. **Processing**: LED shows thinking pattern while transcribing
5. **Response**: Assistant speaks response with LED speak pattern
6. **Repeat**: Returns to listen mode

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
   - Starts an access point (AP) named `PiAssistant-Setup`
   - Launches a Flask web UI on `http://192.168.4.1:8080`
   - Waits for you to configure WiFi
4. **After Configuration**: 
   - Tries to connect to the new network
   - If successful, stops the AP and continues in client mode
   - If failed, returns to AP mode for reconfiguration

### Using WiFi Provisioning

**First-time setup or new location:**

1. Power on your Raspberry Pi
2. Wait 30-60 seconds for boot
3. Look for WiFi network `PiAssistant-Setup` on your phone/laptop
4. Connect to it (password: `ChangeMe12345` by default)
5. Open browser and go to: `http://192.168.4.1:8080`
6. Select your WiFi network from the dropdown
7. Enter the password and click Connect
8. Wait 10-20 seconds - the Pi will connect and the AP will disappear
9. Your Pi is now connected to your network!

**Moving to a different location:**

The system remembers all configured networks. Simply power on your Pi at the new location:
- If it can connect to any remembered network, it will automatically
- If not, it will start the AP for you to add the new network

No need to reconfigure networks you've already set up - it remembers them all!

### Customizing WiFi Settings

You can customize the AP name, password, and other settings:

```bash
# Edit the environment configuration
sudo nano /etc/default/piwifi

# Settings you can change:
# AP_SSID=MyCustomName
# AP_PASSWORD=MySecurePassword123
# FLASK_PORT=8080
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

# Force AP mode (useful for testing)
sudo systemctl stop piwifi-manager.service
sudo nmcli dev wifi hotspot ifname wlan0 ssid PiAssistant-Setup password ChangeMe12345

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

# Manually start AP mode
sudo nmcli dev wifi hotspot ifname wlan0 ssid PiAssistant-Setup password ChangeMe12345
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
│  • OpenAI API (Whisper, GPT, TTS)      │
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
   - Transcribes audio (Whisper)
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
├── openwakeword.patch      # Bug fix for OpenWakeWord
├── seeed-voicecard.patch   # Kernel module fixes
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
- **OpenAI**: Whisper, GPT, and TTS APIs
- **SeeedStudio**: reSpeaker HAT hardware and drivers
- **Raspberry Pi Foundation**: Amazing single-board computers

## Support

For issues or questions:
1. Check the Troubleshooting section above
2. Review configuration options
3. Check logs in `openai_interactions.log`
4. Verify hardware connections and drivers
