# Raspberry Pi OS and ReSpeaker audio

Use this guide when updating an existing Pi or diagnosing its audio. New builders
should follow the [quick start](../QUICKSTART.md).
The supplied installer targets **ReSpeaker 2-Mic Pi HAT v1 / WM8960** on Raspberry
Pi OS Lite 64-bit. It does not configure v2 or AC108/AC101 arrays.

## Use the kernel's audio driver

The project uses the kernel-provided `wm8960-soundcard` overlay, not the old Seeed
vendor installer or `seeed-voicecard.patch`. It keeps the ALSA card name
`seeed2micvoicec` and enables SPI for the HAT LEDs.

For an OS/kernel update, first read [recovery preparation](maintenance.md), then run:

```sh
make upgrade-os
sudo reboot
```

Review APT's proposed changes before confirming. The target saves audio/boot
configuration under `/var/backups/rpi-assistant-audio/`, disables legacy Seeed DKMS
rebuilds, applies OS updates and configures WM8960. Python packages/models are
separate. If the OS is already updated, `make install-voicecard` configures just
the audio path; reboot if the boot overlay changed.

## Check actual sound

After reboot, confirm the card appears:

```sh
arecord -l
aplay -l
modinfo -F filename snd_soc_wm8960
```

The module should be under the kernel's `sound/soc/codecs/`, not `updates/dkms/`.
Use the phone's [speaker and microphone checks](phone-setup.md), then try a real
wake-word question and follow-up. Check LEDs and Wi-Fi too.

If the phone page isn't available, stop the assistant to release the microphone
and record a short local test. Speak during the three-second recording:

```sh
sudo systemctl stop rpi-assistant.service
arecord -D plughw:CARD=seeed2micvoicec,DEV=0 -f S16_LE -r 16000 -c 2 -d 3 /tmp/audio-check.wav
aplay -D assistant_wm8960 /tmp/audio-check.wav
rm /tmp/audio-check.wav
sudo systemctl start rpi-assistant.service
```

## Quiet replies despite normal standalone playback

Keep `[audio_output] device = assistant_wm8960`. The installer creates
`/etc/alsa/conf.d/99-rpi-assistant-wm8960.conf` to force 32-bit stereo playback,
matching live capture. Other automatically negotiated formats caused barely audible
speech on the tested board. Don't compensate by raising microphone gain.
For output volume and fresh-card mixer settings, see [troubleshooting](troubleshooting.md#no-sound-or-very-quiet-sound).

## Recover an older setup

The configuration snapshot is not a full kernel/SD backup. Restoring old boot/audio
settings on a newer kernel does not recreate an older driver build. Use a matching
saved boot/kernel image or working SD card if the new OS cannot boot or use audio.
Inspect the snapshot's `legacy-service-state.txt` before restoring old services.

The existing Zero 2 W passed kernel 6.18.60 audio and spoken checks in November
2026; a fresh-card installation and Pi 3 A+ were not tested. Historical migration
acceptance is preserved in Git history; see [the release check](reference/release-check-2026-11-25.md)
for later device checks and limits. Other HATs need their own driver and hardware checks.

[Back to maintenance](maintenance.md)
