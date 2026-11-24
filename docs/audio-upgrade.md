# Raspberry Pi OS and ReSpeaker audio

This path is for the **ReSpeaker 2-Mic Pi HAT v1 with WM8960**, using Raspberry
Pi OS Lite 64-bit. It does not configure the v2 HAT or AC108/AC101 arrays.
Python dependencies and OpenAI models are upgraded separately (U02/R01).

On 2026-11-24 the existing Zero 2 W booted kernel 6.18.60 with the native
WM8960 driver. Wi-Fi reconnected, and a speaker-to-microphone tone check passed
on both capture channels. After the playback-format correction below, the owner
confirmed normal wake detection, LEDs, clear spoken responses and a contextual
follow-up. Fresh-card setup and Pi 3 A+ have not been tested.

## Update an existing device

Preserve a working SD card or image when available. If proceeding without one,
be prepared to reimage the card locally if the Pi cannot boot or reconnect.
The configuration snapshots below are not a complete SD-card backup.

```bash
make upgrade-os
sudo reboot
```

The target runs these steps in order, stopping on failure:

1. Save audio/boot configuration under `/var/backups/rpi-assistant-audio/` and
   disable automatic builds of the old Seeed DKMS module.
2. Refresh APT metadata and apply the distribution's stable updates, including
   matching `linux-image-rpi-v8`/`linux-headers-rpi-v8` packages and system audio
   libraries. Review APT's proposed changes before confirming them.
3. Configure `wm8960-soundcard` in `/boot/firmware/config.txt`, preserving the
   ALSA card name `seeed-2mic-voicecard`. Save existing mixer settings, disable
   the legacy boot service, and remove its forced module-load entries.
   Enable SPI in boot configuration for the HAT LEDs; the retired service
   previously enabled that interface dynamically.
   If the assistant selected this card by number, change that setting to its
   named `assistant_wm8960` PCM before reboot; another deliberately selected
   output is left unchanged. This PCM uses the stable card name and 32-bit
   stereo output to match the assistant’s live microphone stream. The WM8960
   and HDMI card numbers can swap during migration.

The setup leaves existing kernel modules and the driver's source checkout in
place. It does not unload live audio or reboot automatically. It does not run
the obsolete vendor installer, clone a moving driver branch, or apply
`seeed-voicecard.patch`. Kernel updates supply the WM8960/simple-card drivers.

For an already updated OS, run `make install-voicecard` to configure audio only.
On a fresh installation, use the same target and reboot before testing capture
and playback. Set the mixer controls for the connected microphone/speaker and
run `sudo alsactl store` to preserve them. Existing installations retain their
saved mixer state; fresh-card mixer defaults still require hardware checking.

## Check after reboot

```bash
uname -r
arecord -l
aplay -l
modinfo -F filename snd_soc_wm8960
systemctl is-active rpi-assistant.service
nmcli -t -f DEVICE,STATE device
```

The codec module should come from the kernel's `sound/soc/codecs/` directory,
not `updates/dkms/`. The card should appear in both recording and playback
lists. Confirm actual sound, not just device discovery. To test a short local
recording, temporarily stop the assistant so it releases the microphone:

```bash
sudo systemctl stop rpi-assistant.service
arecord -D plughw:CARD=seeed2micvoicec,DEV=0 -f S16_LE -r 16000 -c 2 -d 3 /tmp/audio-check.wav
aplay -D plughw:CARD=seeed2micvoicec,DEV=0 /tmp/audio-check.wav
sudo systemctl start rpi-assistant.service
```

Delete that temporary recording after listening. Try a wake word, a question,
and a contextual follow-up, checking LEDs and intelligible speech. Record the
board, kernel, and outcomes in TODO.md. A service showing “active” is not proof
that the microphone, wake word, or speaker works.

## Quiet speech while the microphone is running

During migration, plain `plughw` negotiated 24-bit playback while the assistant
captured in 32-bit format. Speech became barely audible despite unchanged mixer
levels; a standalone WAV still played normally. The owner confirmed that forcing
32-bit playback restored clear, louder sound. The setup now installs
`/etc/alsa/conf.d/99-rpi-assistant-wm8960.conf` and selects
`device = assistant_wm8960` for this card. ALSA converts playback to `S32_LE`
without changing the application or increasing microphone gain. Reapply
`make install-voicecard` and restart the assistant to migrate an existing named
`hw`/`plughw` selection. Check spoken responses with the microphone running;
standalone playback does not exercise that combination.

## Recovery

If the OS boots but audio fails, inspect the latest configuration snapshot and
its `legacy-service-state.txt`. Restore the **pre-prepare** configuration archive
as root (`sudo tar -xzf <archive> -C /`), re-enable the legacy service if it was
previously enabled, and boot the matching old kernel/modules. Remove any newly
created DKMS override and managed ALSA playback file only if they did not exist
before migration. Restoring old
audio configuration while still running a new kernel does not restore an old
driver build.

Kernel rollback requires the old boot files as well as its modules; a config
archive alone is insufficient. Use the saved full boot/kernel snapshot or
working SD image. If boot/SSH recovery is unavailable, mount the card on another
computer to restore it, or reimage it. Keep private credentials out of commits
when restoring the assistant configuration.

## Source notes

The kernel [WM8960 overlay](https://github.com/raspberrypi/linux/blob/rpi-6.18.y/arch/arm/boot/dts/overlays/wm8960-soundcard-overlay.dts)
uses the same 12.288 MHz clock and routing as the old 2-Mic overlay. Hardware
checks determine whether that path works for the installed card.

The old vendor source is [HinTak/seeed-voicecard](https://github.com/HinTak/seeed-voicecard),
not the stale seeed-studio-projects URL. Its v6.14 revision
`34477ad9e462ed00a7ebc853e4cf1934b9e73e81` does not accept this repository's old
patch. Its installer also assumes old kernel package names and can propose a
kernel downgrade. The new installation path does not invoke it.
