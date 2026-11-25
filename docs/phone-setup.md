# Phone setup and audio checks (H06)

Open `http://<device-IP>:8767` on the same trusted Wi-Fi. The existing controls
must be enabled with `[controls] host = 0.0.0.0`; the default localhost binding is
not reachable from a phone. No browser or extra web service runs on the Pi.
Wi-Fi joining still uses the existing provisioning page; this item does not change
its credentials or network configuration.

## Settings

Expand **Settings** to edit:

- Follow-up listening: 0–15 seconds; zero disables the ordinary follow-up window.
- Reminder timezone: an IANA name such as `Europe/Bucharest`. Existing reminder
  instants stay unchanged; interpretation and display use the new timezone.
- Home weather city and country: overrides the saved/IP-derived city. Changing it
  clears manual weather coordinates/timezone so a new city cannot accidentally use
  the old coordinates. Leave blank to restore the saved or detected city flow.
- OpenAI key, optional Open-Meteo paid key, and optional ipgeolocation.io key.
  Keys are write-only. Blank fields keep existing values; optional keys have explicit
  removal checkboxes. Other reasoning providers require an integration first.
- Optional conversation logging, off by default. Content goes only to private,
  bounded files; see [retention and deletion](conversation-privacy.md).

Typing does nothing until **Save & apply**. The settings apply without restarting
capture or clearing conversation history. The page never returns a key, only whether
one is configured. New keys receive local format validation; account access is checked
when using the provider, so try a normal voice question after replacing OpenAI's key.
The local phone page can start without an OpenAI key; voice requests remain unavailable
until one is supplied. Local audio checks and controls work without a key or Internet.

Settings changes wait until the assistant is not handling a request, alert or audio
check. Unsupported fields and invalid values are rejected before saving. A stale
page cannot overwrite a newer config file: choose **Reload settings** and retry.
Reloading discards unsaved edits. Background status polling does not erase edits.

**Undo last change** restores the previous settings and keys, including after restart.
It is available only while the file matches that last applied change; later manual
edits prevent undo from overwriting them. Each successful apply replaces the single
undo snapshot. Unrelated INI settings are retained, though saving reformats the file
and removes comments. Environment-derived settings become file overrides when edited.

## Recovery and secrets

Configuration writes are atomic with mode 0600. A private `config.ini.phone-undo.json`
beside the config retains the previous file and effective settings before applying
the new values. Runtime/application failures attempt to restore both the file and
live settings; the page reports if recovery itself fails. The undo file can contain
old API keys and is ignored by Git. Treat it as secret. If manual recovery is needed,
restore its `config_text` to `config.ini` locally, then restart the assistant; a null
`config_text` means there was originally no config file. Do not paste this file into
logs, tickets or chat.

The existing page is **trusted-LAN HTTP with no authentication or TLS**. Everyone
with access to that LAN can control the device and replace keys; traffic is not
encrypted. Use it only on your own trusted network and never forward its port to
the Internet. Cross-origin browser requests remain rejected. No secret is placed in
status responses, rendered HTML, browser storage or application error messages.
Broader onboarding security remains H02. H01 adds local conversation-data deletion
and private, opt-in content logs; see [privacy boundaries](conversation-privacy.md).

## Microphone and speaker checks

**Play test sound** plays the bundled local chime using the configured speaker and
volume. It works while microphone capture is muted. The result reports player success,
not proof that the speaker is audible—listen to confirm wiring and volume.

**Record 3 seconds and play back** records the device microphone locally while you
speak, then plays that sample back. Green marks recording; amber marks playback.
The existing capture stream is reused, with wake detection/recognition bypassed during
the check. No recording is uploaded or sent to speech recognition. A bounded temporary
WAV is removed after success, cancellation or failure. The page reports weak/clipped
signal or unavailable capture; a successful recording is not proof of recognition quality.
Use **Stop** or the button to cancel. Muting also cancels and closes actual capture.
Recording checks are refused while muted; they never silently unmute the microphone.
After a check, residual speaker audio is discarded before normal wake listening.

Status also distinguishes Internet reachability, actual capture state, active checks
and whether provider keys exist. Internet reachability is not provider-account validation.

## Checks and rollback

Run `python -m unittest discover -s tests -v`. On the Pi, verify save/apply/undo from
a phone, a clearly audible test sound, recognizable microphone playback, refusal while
muted, and a fresh wake-word question afterwards. Offline checks and configuration
failures are recorded separately in TODO.md.

The development device retains H05 and its private configuration:

```sh
sudo cp /var/backups/rpi-assistant-h06/h05.service /etc/systemd/system/rpi-assistant.service
sudo systemctl daemon-reload
sudo systemctl restart rpi-assistant
```

The software rollback uses H05's preserved configuration, not phone edits made in
the H06 checkout. Household databases and saved weather city remain outside checkouts.
