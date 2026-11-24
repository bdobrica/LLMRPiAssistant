# Python runtime on 512 MB Raspberry Pis

U02 targets Raspberry Pi OS 64-bit / CPython 3.13. Keep the working environment
until the candidate passes real wake detection, audio and spoken interaction.
The Zero 2 W candidate passed these checks on 2026-11-24; Pi 3 A+ remains untested.
Dependency installation itself can use more memory than the running assistant.

## Prepare a separate environment

Stop the assistant during installation on 512 MB boards. Use `/var/tmp` or a
folder under the device user's home for build files: Trixie's `/tmp` is a RAM-backed
filesystem (208 MB on the tested Zero 2 W). Bulk downloading/unpacking there
filled swap and made the device unresponsive during U02. The Makefile now sets
`TMPDIR=/var/tmp` for pip. Preparing ARM64 wheels on another machine also avoids
resolver/download work on the Pi.

```bash
sudo systemctl stop rpi-assistant
make create-venv VENV_DIR=/opt/venvs/rpi-assistant-next
make install-wakeword-models VENV_DIR=/opt/venvs/rpi-assistant-next
/opt/venvs/rpi-assistant-next/bin/python -m pip check
/opt/venvs/rpi-assistant-next/bin/python -m unittest discover -s tests -v
```

If preparation fails, restart the existing service; its environment is unchanged.
The runtime requirements file records the tested resolution; `requirements.in`
records direct selections. Do not regenerate the lock by silently dropping
unsatisfied dependencies.

## Wake-word compatibility

The released openWakeWord 0.6.0 requires `tflite-runtime`, which lacks a CPython
3.13 wheel. The candidate pins upstream commit
`368c03716d1e92591906a84949bc477f3a834455`, using LiteRT instead. Its mandatory
SpeexDSP binding also lacks a CPython 3.13 wheel, so build pinned source revision
`8af784a230e23f4eeaa4a58111774ad0864b1f0b` with SWIG and `libspeexdsp-dev`.
The GPIO binding also needs `liblgpio-dev`; all required build libraries are
listed in `make install-deps`. These are explicit source exceptions; replace them with compatible stable
releases when available and repeat actual model checks.

Use the modern `wakeword_models` API and LiteRT with one inference thread.
An empty model selection now loads only `hey_jarvis`; explicit selections remain
supported. Model assets are downloaded during setup and verified against
`rpi_assistant/wakeword-models.json`. Startup requires no model download or
site-packages patch.

Check a real model in the candidate environment before hardware testing:

```python
import numpy as np
from openwakeword.model import Model
model = Model(wakeword_models=["hey_jarvis"], inference_framework="tflite", ncpu=1)
for _ in range(25):
    result = model.predict(np.zeros(1280, dtype=np.int16))
print(result, type(model.models["hey_jarvis"]).__module__)
```

Then try the configured wake word, capture/playback, LEDs and a contextual spoken
follow-up on the device. Record measured memory and failures in TODO.md. Unit
checks mock audio and do not replace this acceptance. Generic MCP subprocess
tests always run; the separate RPiFace integration is explicitly skipped unless
its package is installed.

## Preserve existing conversation settings

When migrating the older prototype configuration, explicitly set
`conversation_idle_timeout_seconds = 0` and
`conversation_relevance_threshold = 0` in `[openai]` if those settings were
absent. This preserves the deployed conversation retention instead of silently
adopting newer idle/topic resets. Keep any values the owner explicitly selected.
The candidate trial uses these compatibility settings; model IDs are unchanged.

## Switch and recover

Only after candidate checks, point the service at the candidate checkout and
environment using `make install-service VENV_DIR=/opt/venvs/rpi-assistant-next`,
then restart it and confirm the interaction again. Preserve the old service file,
checkout, configuration and environment. To roll back, restore that service file,
run `sudo systemctl daemon-reload`, and restart the assistant. Keep API keys and
local configuration out of commits. Model API migration belongs to R01.
