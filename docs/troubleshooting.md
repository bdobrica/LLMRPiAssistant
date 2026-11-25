# Get the assistant talking again

Start with the [phone audio checks](phone-setup.md). They separate microphone and
speaker problems from cloud/account problems without sending a recording online.

## The phone page won't open

Check that phone and Pi are on the same network and that `[controls] host = 0.0.0.0`
is saved in `rpi_assistant/config.ini`. Restart after a manual edit. Use
`http://<device-IP>:8767`, with a literal IP from `hostname -I` on the Pi or your
router's device list. Guest Wi-Fi may prevent devices from reaching each other.
The Wi-Fi onboarding page at `192.168.4.1` is separate and only runs during setup.

## No sound or very quiet sound

Check the speaker connection and phone volume first. For the WM8960 HAT, keep
`[audio_output] device = assistant_wm8960`. It forces the playback format needed
for clear speech while the microphone is active; a file playing normally on its
own doesn't establish that simultaneous playback works.

The phone mixer setting must match the connector: `[controls] mixer_control = Speaker`
for the wired speaker or `Headphone` for 3.5 mm. If a fresh card has muted mixer
channels, inspect them in the Pi terminal:

```sh
alsamixer -c seeed2micvoicec
```

Use arrow keys to select/change the appropriate output and **M** to toggle mute.
Keep the volume low initially. After sound works, save the mixer state:

```sh
sudo alsactl store
```

If the card is missing, follow [audio checks](audio-upgrade.md). Don't run a vendor
driver installer for a different HAT revision.

## It doesn't hear me

Steady red means muted; unmute with the button or phone. Say **“Hey Jarvis”** when
blue, or speak after steady green during a follow-up. Try the phone recording
check. For the tested HAT, `[audio] channels = 2`, `mic_channel_index = 0` and
`[led] count = 3` are the intended settings.

A TV or another person can trigger a follow-up window. Test in a quiet room before
tuning sensitivity. If recording cuts off during natural pauses, modestly increase
`[recording] silence_hold_seconds` and restart. Increasing the silence threshold
can discard quiet speech; don't change it blindly.

## It hears me but cannot answer

Check Internet status and that the OpenAI key is configured. A saved key still
needs a working API account and access to the configured models. The local sound
check can succeed even when API requests fail. Use [failure feedback](failure-recovery.md)
and [model settings](openai-upgrade.md) to narrow it down.

If “Roll a die” says the app is missing, first say **“install app dice.”**
If a game keeps answering instead of chat, say **“cancel app.”**

## The service won't start

Read status and recent diagnostics from the Pi terminal:

```sh
sudo systemctl status rpi-assistant.service --no-pager
sudo journalctl -u rpi-assistant.service -n 50 --no-pager
```

The installer uses `User=pi`. If your OS account has another name, run
`sudo systemctl edit rpi-assistant.service` and add an override using your actual
username (not the placeholder):

```ini
[Service]
User=YOUR_USERNAME
```

That account must own/read its configuration, reach the checkout, and have audio,
GPIO and SPI access. Reload and start:

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now rpi-assistant.service
```

For an already running service after configuration edits, use
`sudo systemctl restart rpi-assistant.service`. A known audio-cleanup shutdown
issue can delay restart by about 90 seconds. Don't repeatedly power-cycle during it.

## Installation stopped partway through

Check the first failing command. Use Raspberry Pi OS **64-bit**, Python **3.13**
and the pinned requirements. Dependencies build on the small board, so allow time
and free SD space. The installer uses `/var/tmp` for build files; using RAM-backed
`/tmp` for large installs previously exhausted memory. For an existing device,
stop the assistant during dependency work; see [Python maintenance](python-upgrade.md).

For missing wake-model assets, run `make install-wakeword-models` from the repository.
Don't bypass dependency or checksum failures. When reporting a problem, include
board/HAT, OS, the step that failed and a redacted error. Never share `config.ini`,
its undo file, Wi-Fi credentials or private conversation logs.

[Back to the guides](README.md)
