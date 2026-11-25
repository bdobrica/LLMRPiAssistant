# Local controls (F05)

## Everyday use

- **Short button press:** while an answer plays, stop it and wait for green to
  give a correction, as in F02. At other times, stop the current request or discard
  a partial recording/follow-up. This does not undo an action already dispatched.
- **Hold the same button for 1.5 seconds:** mute/unmute. The initial press still
  stops speech immediately. Steady red confirms the assistant's input stream is
  closed; wake words cannot work while muted. Use the button or local page to
  unmute. If an old request is still finishing, wait and retry unmute.
- **Phone page:** open `http://<device-IP>:8767` after enabling LAN access below.
  Stop, mute/unmute, volume and new conversation work without Internet as long as
  the phone and Pi can communicate on their local network. No external page assets
  or cloud calls are used. Status distinguishes active capture, confirmed mute and
  unavailable/unknown capture; an unreachable page cannot confirm microphone state.
- **Voice:** after a wake word or during green, say “volume up,” “volume down,”
  “set volume to 70 percent,” “stop,” “mute the microphone,” or “start a new
  conversation.” These exact controls run locally after cloud transcription;
  free-form offline recognition and voice interruption during playback are not
  supported. Volume confirmations use normal speech generation; the setting can
  still succeed if that later request fails. New conversation uses a bundled clip.

Volume uses ALSA's mapped percentage, in ten-point steps, clamped to 0–100. It
changes the configured output mixer without altering microphone gain or the working
32-bit WM8960 playback path. Zero speaker volume does **not** mute the microphone.
Startup retains the existing mixer level; persistence across reboot follows the
OS ALSA configuration. Mute is saved separately and survives assistant restart.
This is application capture mute, not an electrical switch: other processes could
still open the microphone.

New conversation clears active and compacted in-memory chat history. During a
pending request, reset happens when that worker returns; stale speech is suppressed.
The page reports the pending state. It does not erase logs, stop a running app or
undo prior actions. Stop/mute/reset cancel work between provider stages and tool
calls; requests/actions already dispatched can finish within their existing limits.
Completed actions are retained unless an explicit reset clears chat context.

## Configuration and access

```ini
[controls]
enabled = true
host = 0.0.0.0
port = 8767
mixer_card = seeed2micvoicec
mixer_control = Speaker
state_path = ~/.local/state/rpi-assistant/controls.json

[recording]
interrupt_button_gpio = 17
```

The default host is `127.0.0.1`; change it to `0.0.0.0` for your trusted private LAN.
**Everyone on that LAN can control the device.** There is no login or TLS. Never
forward this port to the Internet; use an SSH tunnel if the network is untrusted.
Use the literal device IP (or localhost through a tunnel), not a DNS hostname.
Cross-origin browser mutations and DNS-host requests are rejected; these checks
are not authentication. `enabled = false` disables the HTTP page, retaining the
button and spoken controls. Configuration changes require restart.

Choose `Headphone` for the HAT's 3.5 mm output, or the correct card/control for other
hardware. Failed mixer operations report an error rather than claiming success.
Each setting also has a `CONTROLS_<UPPERCASE_NAME>` environment equivalent;
explicit file settings win. Corrupt mute settings keep capture closed. Unmute
failure leaves processing paused; red is shown only when stream closure is confirmed.
The red indication clears synchronously before capture reopens.

## Checks and rollback

Run `python -m unittest discover -s tests -v`. Tests cover capture closure/reopen,
failed mute/unmute, persisted preference, stale output, cancelled tool batches,
deferred context reset, narrow voice routing and local HTTP request boundaries.
Actual capture, playback, button use and offline operation need hardware checks;
see TODO.md for recorded evidence and limitations.

The development device keeps F04's checkout, service/config snapshot and all older
rollback environments. Restore the previous service with:

```sh
sudo cp /var/backups/rpi-assistant-f05/f04.service /etc/systemd/system/rpi-assistant.service
sudo systemctl daemon-reload
sudo systemctl restart rpi-assistant
```

F04 predates microphone mute and does not honor F05's saved mute preference.
