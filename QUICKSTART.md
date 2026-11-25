# Build your first talking assistant

This guide takes you from a Raspberry Pi to a spoken question and follow-up.
Commands go in a **terminal on the Pi**, either through SSH (a remote terminal)
or a connected keyboard and screen. Run them one block at a time.

Already have a working installation? Start with [the phone page](docs/phone-setup.md)
or [things to try](docs/README.md). For software updates, use the
[maintenance guide](docs/maintenance.md).

## 1. Gather the parts

- Raspberry Pi Zero 2 W with its 40-pin header fitted.
- ReSpeaker **2-Mic Pi HAT v1 / WM8960**. The installer does not configure the v2
  or 4-mic boards.
- A compatible speaker for the HAT's speaker connector, or wired headphones.
- A microSD card, a suitable Pi power supply, and a computer with a card reader.
- A 2.4 GHz Wi-Fi network and an OpenAI API account with billing/model access.
  Create a private key in the [API dashboard](https://platform.openai.com/api-keys);
  it lets the assistant make paid requests using your account.

Power off before fitting the HAT or connecting its speaker. Match the GPIO header
orientation to the board markings. An enclosure is optional; designs are in [enclosure/](enclosure/).

## 2. Prepare Raspberry Pi OS

Use [Raspberry Pi Imager](https://www.raspberrypi.com/software/) to write
**Raspberry Pi OS Lite (64-bit)** to the card. The pinned Python setup targets
Trixie with Python 3.13. A desktop environment is unnecessary.

In Imager's customisation settings, set:

- Hostname: `assistant`.
- Username: `pi`, with your own password. The supplied assistant service uses this name.
- Your Wi-Fi name/password and country.
- SSH enabled, so you can use a terminal from your computer.

Insert the card, power on and allow it to join Wi-Fi. From your computer's terminal:

```sh
ssh pi@assistant.local
```

If that name does not resolve, find the Pi's IP address in your router's connected
devices and use `ssh pi@<device-IP>`. Enter the password you chose in Imager.

## 3. Download and configure

In the Pi terminal:

```sh
sudo apt-get update
sudo apt-get install -y git make
git clone https://github.com/bdobrica/LLMRPiAssistant.git
cd LLMRPiAssistant
cp rpi_assistant/config.ini.example rpi_assistant/config.ini
chmod 600 rpi_assistant/config.ini
nano rpi_assistant/config.ini
```

For this 2-mic HAT, **change the existing entries** below in their matching
sections. Do not paste duplicate sections at the end of the file.

```ini
[audio]
channels = 2
mic_channel_index = 0
device_match = seeed

[led]
count = 3

[recording]
interrupt_button_gpio = 17

[controls]
host = lan
mixer_control = Speaker
```

Use `mixer_control = Headphone` if using the HAT's 3.5 mm output. Keep
`[audio_output] device = assistant_wm8960`; it avoids quiet playback while recording.
Set `[household] timezone` to your timezone, for example `Europe/London`.
Leave other entries as supplied. You can enter `[openai] api_key` now or from your
phone later. Keep the file private.

In nano, press **Ctrl+O**, **Enter** to save, then **Ctrl+X** to exit.
Phone access is for a **trusted home network**: anyone on that network can control
the assistant. Do not forward port 80 to the Internet or expose it on public event Wi-Fi.

## 4. Install and start

From the repository folder:

```sh
make setup
```

This installs dependencies, downloads wake models, configures the HAT and creates
the background service. Installation can take a while on a Zero 2 W. Wait for it
to finish; at the final prompt, press Enter to reboot. If a step fails, stop and
read the error rather than continuing. The [installation help](docs/troubleshooting.md)
explains the common checks.

Reconnect over SSH after reboot, then start the assistant automatically at boot:

```sh
sudo systemctl enable --now rpi-assistant.service
hostname -I
```

Note the Pi's Wi-Fi IP address from the last command. If you already use a username
other than `pi`, see [service user setup](docs/troubleshooting.md#the-service-wont-start)
before starting it.

## 5. Check sound and add your key

Connect your phone to the same Wi-Fi and open **`http://<device-IP>/`**, replacing
`<device-IP>` with the address above. Use the address, not `assistant.local`, for this page.

1. Open **Settings**, enter your OpenAI API key and choose **Save & apply**.
   A blank key field keeps the saved key; the page only shows whether it is configured.
2. Set a comfortable volume on **Home**, then open **Settings** and choose **Play test sound**.
3. Choose **Record 3 seconds and play back**, and say a short sentence.
   You should hear yourself. This check stays on the Pi and needs no API key.

If nothing plays, follow [audio troubleshooting](docs/troubleshooting.md#no-sound-or-very-quiet-sound).
Settings include **Undo last change** if you need to go back.

## 6. Have a conversation

Wait for the blue listening lights, then say **“Hey Jarvis”** and ask a short
question, such as **“What's a manifold?”**

After the reply, wait for **steady green** and ask **“What about a cube?”**
You have about six seconds to begin a follow-up. Stay quiet to finish; blue returns.
Press the HAT button to stop a reply, or hold it for 1.5 seconds to mute/unmute.
Steady red means the assistant microphone is muted.

## Take it further

Try [timers](docs/timers.md), [Shopping and reminders](docs/household.md),
[weather](docs/weather.md) or [Dice](docs/voice-apps.md).
For moving between networks, install the optional [phone Wi-Fi setup](docs/wifi-setup.md)
while you still have terminal access. The [guide index](docs/README.md) has the rest.

This walkthrough follows the installer and the tested Zero 2 W setup. A complete
fresh-card trial has not yet been recorded; the [release notes](docs/reference/release-check-2026-11-25.md)
distinguish hardware checks from remaining gaps.
