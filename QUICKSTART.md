# Quick Start Guide - LLMRPiAssistant

This is a quick reference for common tasks. See [README.md](README.md) for full documentation.

## Initial Setup

```bash
# Complete installation (run once)
make setup

# Install WiFi provisioning (optional but recommended)
make install-wifi

# Reboot to load drivers
sudo reboot
```

## Configuration

```bash
cd rpi_assistant
cp config.ini.example config.ini
nano config.ini  # Add your OPENAI_API_KEY
```

## Running the Assistant

### As a service (recommended):
```bash
sudo systemctl enable rpi-assistant.service
sudo systemctl start rpi-assistant.service
sudo journalctl -u rpi-assistant.service -f  # View logs
```

### From command line:
```bash
rpi-assistant
```

## WiFi Setup

### First time or new location:
1. Look for WiFi: `PiAssistant-Setup`
2. Connect (password: `ChangeMe12345`)
3. Open: http://192.168.4.1:8080
4. Select network and enter password
5. Wait 10-20 seconds

### Commands:
```bash
# Check status
sudo systemctl status piwifi-manager.service

# View logs
sudo journalctl -u piwifi-manager.service -f

# List saved networks
nmcli connection show

# Force AP mode (testing)
sudo systemctl restart piwifi-manager.service
```

## Common Operations

### Service Management
```bash
# Status
sudo systemctl status rpi-assistant.service

# Start/stop
sudo systemctl start rpi-assistant.service
sudo systemctl stop rpi-assistant.service

# Enable/disable autostart
sudo systemctl enable rpi-assistant.service
sudo systemctl disable rpi-assistant.service

# Restart
sudo systemctl restart rpi-assistant.service
```

### Logs
```bash
# Follow assistant logs
sudo journalctl -u rpi-assistant.service -f

# Follow wifi manager logs
sudo journalctl -u piwifi-manager.service -f

# View interaction log
tail -f rpi_assistant/openai_interactions.log
```

### Audio Testing
```bash
# Test speaker
speaker-test -c2

# List audio devices
aplay -L

# Record test (check microphone)
arecord -D hw:2,0 -f cd -d 5 test.wav
aplay test.wav
```

## Troubleshooting

### No wake word detection
- Check LED is showing blue breathing pattern
- Try lowering `wakeword.threshold` in config.ini (0.3 is more sensitive)
- Test different `mic_channel_index` values (0-3)

### Recording cuts off too early
- Increase `silence_hold_seconds` to 1.5
- Increase `silence_rms_threshold` to 0.01

### No audio playback
- Test speaker: `speaker-test -c2`
- List devices: `aplay -L`
- Update `audio_output.device` in config.ini

### WiFi not connecting
- Check NetworkManager: `sudo systemctl status NetworkManager`
- Wait 20 seconds after entering credentials
- Check password was entered correctly
- View logs: `sudo journalctl -u piwifi-manager.service -n 50`

## File Locations

- **Config**: `~/GitHub/LLMRPiAssistant/rpi_assistant/config.ini`
- **Logs**: `~/GitHub/LLMRPiAssistant/rpi_assistant/openai_interactions.log`
- **Virtual env**: `/opt/venvs/rpi-assistant/`
- **Services**: `/etc/systemd/system/rpi-assistant.service`
- **WiFi config**: `/etc/default/piwifi`

## Project Structure

```
LLMRPiAssistant/
├── Makefile                    # make setup, make install-wifi
├── README.md                   # Full documentation
├── QUICKSTART.md              # This file
├── TODO.md                    # Planned features
├── rpi_assistant/             # Python package (note underscore!)
│   ├── config.ini             # Your configuration
│   ├── app/                   # Voice assistant code
│   └── piwifi/                # WiFi provisioning
├── systemd/                   # Service definitions
│   ├── rpi-assistant.service
│   ├── piwifi-manager.service
│   └── piwifi-flask.service
└── scripts/
    ├── piwifi-manager.sh      # Network manager
    └── install-wifi.sh        # WiFi setup
```

## Wake Words

Default models support:
- "hey mycroft"
- "alexa"
- "hey jarvis"
- "timer"

## Next Steps

- Customize system prompt in config.ini for different personalities
- Try different OpenAI models (gpt-4o, gpt-4o-mini)
- Experiment with different TTS voices (alloy, echo, fable, onyx, nova, shimmer)
- See TODO.md for game development features

## Getting Help

1. Check [README.md](README.md) troubleshooting section
2. View logs: `sudo journalctl -u rpi-assistant.service -f`
3. Test hardware: speaker-test, arecord/aplay
4. Check config: verify all required fields in config.ini
