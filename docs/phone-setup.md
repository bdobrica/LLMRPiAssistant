# Set up and check the assistant from your phone

Connect your phone to the same trusted Wi-Fi as the Pi, then open
**`http://<device-IP>:8767`**. Find the IP in your router's device list or run
`hostname -I` in the Pi terminal. Use a literal IP address, not a hostname.

If you followed the quick start, phone access is already enabled. Otherwise edit
`rpi_assistant/config.ini` and restart the assistant:

```ini
[controls]
enabled = true
host = 0.0.0.0
port = 8767
```

The default `127.0.0.1` allows access only from the Pi itself.
Joining a new Wi-Fi network uses a [different setup page](wifi-setup.md).

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
port 8767 to the Internet or shared public Wi-Fi. Use your own private router at a
Maker Faire, or disable the page with `[controls] enabled = false`.

Configuration and its one-step undo file are private files on the Pi. The adjacent
`config.ini.phone-undo.json` can contain old keys: don't share it. Saving from the
page retains other settings but removes INI comments. For conversation-data
controls, see [privacy](conversation-privacy.md).

[Back to the guides](README.md)
