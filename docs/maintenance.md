# Maintain a working assistant

You don't need these steps for everyday use. For a new build, use the
[quick start](../QUICKSTART.md); for a problem, start with [troubleshooting](troubleshooting.md).
Run maintenance commands from your repository folder on the Pi.

## Know what you are changing

| Change | Read first |
| --- | --- |
| Raspberry Pi OS/kernel or ReSpeaker driver | [OS and audio](audio-upgrade.md) |
| Python packages or wake-word runtime | [Python environment](python-upgrade.md) |
| Speech/answer models or API behaviour | [Model configuration](openai-upgrade.md) |
| Everyday settings or an API key | [Phone settings and Undo](phone-setup.md) |

Before replacing a working installation, keep its checkout, Python environment,
private configuration and service file. A working spare SD card/image offers recovery
if the Pi no longer boots; configuration copies alone do not. Keep backups private.

You can inspect the running command and service settings with:

```sh
systemctl cat rpi-assistant.service
```

Paths vary by installation. Never copy a rollback command naming a backup you
haven't created. The phone's **Undo last change** restores settings only, not software
or OS updates. Avoid running multiple assistant instances against the same audio device.

## Update with a way back

For the easiest software rollback, prepare a separate checkout and Python environment
as described in the Python guide. Keep the working service file before switching.
`make update` exists, but changes the existing environment in place; it is not an
isolated trial or automatic rollback mechanism. Review local changes before pulling code.

After an update, test one wake-word question, a contextual follow-up, the button,
phone audio checks and a short timer. Try a normal reply with capture active;
standalone playback can miss the WM8960 quiet-audio problem.

The tested service can take about 90 seconds to stop during restart. Allow that to
finish and inspect status before assuming the new version failed.

## Evidence for experimenters

The [dated release check](reference/release-check-2026-11-25.md) records what worked
on a 512 MB Zero 2 W, measured API costs and known gaps. It is not proof of fresh-card
setup, Pi 3 A+ compatibility or multi-day reliability. [TODO](../TODO.md) contains
feature-level acceptance records; no new hardware test is implied by editing a guide.

[Back to the guides](README.md)
