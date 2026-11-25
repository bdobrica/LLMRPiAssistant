# Set up and check the assistant from your phone

Connect your phone to the same trusted Wi-Fi as the Pi, then open
**`http://<device-IP>/`**. Find the IP in your router's device list or run
`hostname -I` in the Pi terminal. Use a literal IP address, not a hostname.

If you followed the quick start, phone access is already enabled. Otherwise install the current service with `make install-service`, check
`rpi_assistant/config.ini`, and restart with `sudo systemctl restart rpi-assistant`:

```ini
[controls]
enabled = true
host = lan
port = 80
```

With `host = lan`, use the Pi's private IPv4 address from a phone on the same
subnet. The page follows address changes and works over home Wi-Fi even when
Internet access drops. Allow a few seconds after switching networks.

When the Pi starts its setup hotspot, the admin listener detects that network and
closes. To join a new Wi-Fi network, use the [Wi-Fi setup page](wifi-setup.md).
For access only from the Pi itself, set `host = 127.0.0.1`.

## Upgrade or recover access

`make update` installs the port-80 service. For an otherwise current installation,
`make install-service` followed by `sudo systemctl restart rpi-assistant` is enough;
there is no need to reinstall Python packages just to change the port. The installer
migrates the old `0.0.0.0`/`8767` settings, preserving comments, other settings,
disabled controls and custom ports. An explicit loopback-only host stays private.

The service runs as its ordinary user with only the additional permission needed
to bind a low port, using systemd's
[AmbientCapabilities](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html#AmbientCapabilities=).
Do not run the assistant as root. When developing from a terminal, choose
`host = 127.0.0.1` and `port = 8767`, then use `http://127.0.0.1:8767/` locally.

If the page fails, voice continues and the listener retries every five seconds.
Check `sudo journalctl -u rpi-assistant -n 40 --no-pager` and `sudo ss -ltnp`.
“Port occupied” means another program owns port 80; stop/reconfigure that program,
or deliberately choose a different controls port. “Permission denied” means the
service needs reinstalling. Network discovery needs NetworkManager and `iproute2`;
when it cannot confirm a private LAN, administration stays closed.

Before changing configuration, the installer saves private copies under
`/var/backups/rpi-assistant-controls/<timestamp>/`. To undo an installation, restore
`0-rpi-assistant.service` to `/etc/systemd/system/rpi-assistant.service` and, if
present, `1-config.ini` to your checkout's `rpi_assistant/config.ini`. Keep the
configuration readable only by the assistant user. Then run
`sudo systemctl daemon-reload` and `sudo systemctl restart rpi-assistant`.
The known long service-stop delay remains tracked separately; this change does
not claim to fix it.

## Change settings

Open **Settings** to adjust follow-up listening, reminder timezone, home weather
city, API keys or optional conversation logging. Choose **Save & apply** to use
your changes; typing alone changes nothing. The page can work before an OpenAI
key is set, so you can add the key here before your first spoken question.

Key fields are never filled back in. “Configured” means a key is saved, not that
its account has been verified. A blank field keeps the saved key. Optional weather
keys have removal checkboxes. Other AI providers need a code integration first;
entering their key in the OpenAI field does not enable them.

Try a normal question after replacing the OpenAI key. Use **Undo last change** to
restore the previous settings and keys, even after restart. Only the most recent
save is undoable. If another edit changed the file, **Reload settings** before
trying again; this discards unsaved edits. Save may wait for a request or alert to finish.

## Hear whether your hardware works

1. Choose **Play test sound**. You should hear a chime at the selected volume.
2. Choose **Record 3 seconds and play back**. Speak while the lights are green;
   amber marks playback. You should hear your own sentence.
3. Use **Stop** or the button to cancel a check.

Recording stays local, is deleted afterwards and makes no cloud request. Checks
also work without Internet or an API key. Recording is disabled while muted;
unmute deliberately to test. A success message means the software completed the
check—listen yourself to confirm the sound is clear.

## Who can use the page?

**Anyone who can reach this page on your LAN can control the assistant and replace
its keys.** It has no login or HTTPS. Use a trusted private network; do not expose
port 80 to the Internet or shared public Wi-Fi. Use your own private router at a
Maker Faire, or disable the page with `[controls] enabled = false`.

Configuration and its one-step undo file are private files on the Pi. The adjacent
`config.ini.phone-undo.json` can contain old keys: don't share it. Saving from the
page retains other settings but removes INI comments. For conversation-data
controls, see [privacy](conversation-privacy.md).

## Tested on the Zero 2 W

On November 25, 2026, the owner opened the device IP on a phone after a service
restart, changed the volume, and confirmed a wake-word question and follow-up.
The service ran as the ordinary Pi user. Requests with a foreign Host or Origin
were rejected. All 47 focused checks passed locally and on the Pi, including
simulated hotspot transitions and recovery from an occupied port.

The brief Internet block ended before an offline control result was recorded.
Live Wi-Fi onboarding was not repeated for this revision. The [earlier release
check](reference/release-check-2026-11-25.md) records offline behavior on the
previous version.

[Back to the guides](README.md)
