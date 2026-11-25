# Update Python dependencies without losing your working setup

This is an optional maintenance task. The pinned environment targets **ARM64
Raspberry Pi OS / Python 3.13**. Don't replace individual packages with their newest
versions and assume microphone, GPIO and wake detection will remain compatible.

## Prepare a separate environment

Keep the current checkout, private config and service file. Use a separate checkout
for the new code so the old one stays usable, then run the following there on the Pi.
Choose an unused environment path; the example uses `rpi-assistant-next`.

```sh
sudo systemctl stop rpi-assistant.service
make install-deps
make create-venv VENV_DIR=/opt/venvs/rpi-assistant-next
make install-wakeword-models VENV_DIR=/opt/venvs/rpi-assistant-next
/opt/venvs/rpi-assistant-next/bin/python -m pip check
```

If preparation fails, start the existing service again; it still points to the old
environment. On 512 MB boards, dependency builds can use more memory than normal
assistant operation. Keep temporary files on SD-backed `/var/tmp`, as the Makefile
does. Bulk installation into RAM-backed `/tmp` previously exhausted memory.

## Check before switching

Copy your private configuration to the candidate checkout and preserve its file
permissions. Run tests in the new environment:

```sh
/opt/venvs/rpi-assistant-next/bin/python -m unittest discover -s tests -v
```

An optional RPiFace integration test needs that separate package. Mocked audio tests
don't establish hardware compatibility. With the old service stopped, run the
candidate from its repository root:

```sh
/opt/venvs/rpi-assistant-next/bin/python -m rpi_assistant.app
```

Try wake detection, clear playback, LEDs and a contextual follow-up. Stop the foreground
process before starting a service. If old configuration lacked idle/topic-reset
settings, explicitly set both to zero to preserve that behaviour; see
[conversation memory](conversation-retention.md).

## Switch or go back

Save the existing service file privately before replacing it. From the candidate
checkout, `make install-service VENV_DIR=/opt/venvs/rpi-assistant-next` points the
service at that checkout/environment. Start it and repeat the spoken check.
To go back, restore your saved unit and matching private configuration, run
`sudo systemctl daemon-reload`, then restart the service. Preserve any custom service
user override. Keep the old checkout/environment until you're happy with the new one.

## Why some dependencies use source revisions

The pinned set in [requirements.txt](../rpi_assistant/requirements.txt) records the
resolved dependencies; [requirements.in](../rpi_assistant/requirements.in) lists direct
selections. openWakeWord uses pinned revision `368c03716d1e92591906a84949bc477f3a834455`
with LiteRT because the released 0.6.0 dependency lacks a Python 3.13 wheel.
SpeexDSP uses pinned source `8af784a230e23f4eeaa4a58111774ad0864b1f0b` for the same
wheel-availability reason. `make install-deps` supplies the build libraries.

Setup downloads and verifies wake assets. Startup loads one `hey_jarvis` model by
default and does not download or patch installed packages. Keep this small on the
512 MB boards. The pinned requirements record the dependency versions; see
[the release check](reference/release-check-2026-11-25.md) for device checks and hardware limits.

[Back to maintenance](maintenance.md)
