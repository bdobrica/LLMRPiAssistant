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
- 🔧 **Highly Configurable** - Extensive configuration options via config.ini or environment variables
- 📊 **Interaction Logging** - Comprehensive JSON logs for all conversations

### Hardware Requirements

- **Raspberry Pi** (3B+, 4, or 5 recommended)
- **SeeedStudio reSpeaker HAT** (2-Mic or 4-Mic Array)
- **Speaker** (3.5mm audio jack or USB/Bluetooth speaker)
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

After installation, **reboot your Raspberry Pi** to load the audio drivers:
```bash
sudo reboot
```

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

### Running the Assistant

After configuration, start the assistant:

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
│                     __main__.py                         │
│                  Main Entry Point                       │
└──────────────────────┬──────────────────────────────────┘
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
rpi-assistant/
├── config.ini.example       # Example configuration
├── requirements.txt         # Python dependencies
└── app/
    ├── __init__.py
    ├── __main__.py         # Main entry point
    ├── audio.py            # Wake word and recording
    ├── openai_client.py    # OpenAI API wrapper
    ├── pixels.py           # LED control
    ├── led_pattern.py      # LED animations
    ├── apa102.py          # SPI LED driver
    ├── config.py          # Configuration management
    └── logger.py          # Interaction logging
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
