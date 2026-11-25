# Make something of your own

Once the assistant is talking, a small voice activity is a good first extension.
You don't need to change the microphone or AI pipeline. For installing existing
games, use [Voice apps](voice-apps.md).

## Explore a working app

Start with [the Dice bundle](../voice_apps/apps/dice/0.1.0/). Its `manifest.json`
names the app and its spoken triggers; `app.py` supplies the behaviour.

```json
{
  "id": "dice",
  "name": "Dice",
  "version": "0.1.0",
  "entrypoint": "app:DiceApp",
  "triggers": ["roll a die"]
}
```

`app:DiceApp` means the `DiceApp` class in `app.py`. It subclasses
[VoiceApp](../rpi_assistant/app/apps/base.py), implements `start` and `handle`, and
returns an `AppResponse`. `done=True` ends the activity; `expect_input=True` asks
for another turn. Stateful apps can implement `serialize_state` and `restore_state`.
Use a new ID/class and specific trigger phrases for your own activity.

Installed bundles live in `~/.config/rpi-assistant/apps/`. They run as Python code
with the assistant user's access, so review code before loading it. Keep tests of
new apps separate from a working installation.

## Share an app through a catalog

The existing [voice_apps/index.json](../voice_apps/index.json) is a signed catalog.
Each release names its bundle directory, declared files and SHA-256 checksum.
A remote catalog URL points to the directory containing `index.json`; the installer
downloads the declared files and verifies them. Paths, manifest IDs, checksums and
signatures are checked before loading a catalog app.

The `[app_store]` section in the [configuration example](../rpi_assistant/config.ini.example)
selects the remote URL, local fallback and trusted public key. A blank key uses
`voice_apps/public_key.txt`; keep `require_signature = true`.
Changing the catalog or bundles requires updating checksums and signing again.
See [catalog signing](../scripts/sign-app-store.py) (`--help`) and the
[signing workflow](../.github/workflows/sign-app-store.yml). Keep the private signing
key out of Git and shell history. The workflow reads `APP_STORE_SIGNING_PRIVATE_KEY`
from a repository secret and checks the corresponding shipped public key.

## Add a face or external tools

RPiFace is an optional, separately installed display service. Enable lifecycle
updates in `config.ini` to show listening/thinking/speaking states:

```ini
[rpiface]
enabled = true
base_url = http://127.0.0.1:8765
timeout_seconds = 0.3
```

External tool servers use MCP, a protocol for making tools available to the answer
model. This is independent of the face lifecycle setting. Start from the `[mcp]`
example in the config file; enable only servers you trust. A remote example is:

```ini
[mcp]
enabled = true
servers = utility
timeout_seconds = 30
max_tool_rounds = 3

[mcp.server.utility]
transport = streamable-http
url = https://your-tool-server.example/mcp
token_env = UTILITY_MCP_TOKEN
```

Replace the example URL. Set `UTILITY_MCP_TOKEN` in the assistant service's environment,
not as a literal token in `token_env`. Local `stdio` servers instead specify a command
and arguments; `env_vars` explicitly lists any extra inherited environment variables.
Restart after edits. An unavailable server shouldn't prevent ordinary chat, but test
its actual actions before sharing the device.

SecondContext personal memory is a planned optional integration, not required for
conversation or current features. Heavy services belong off the 512 MB Pi.
For contributing code and running tests, follow [AGENTS.md](../AGENTS.md).

[Back to the guides](README.md)
