"""The phone's INI editor. Only options consumed by the startup parser are editable."""

import base64
from configparser import ConfigParser
from dataclasses import fields
import io
import math
import os
from pathlib import Path
import re
from urllib.parse import urlsplit

from .config import MCPServerConfig, _server_from_section, parse_config


class EditorError(ValueError):
    """Only content-free messages may cross the HTTP boundary."""


SECRETS = {("openai", "api_key"), ("weather", "api_key"), ("weather", "ipgeolocation_api_key")}
# These free-form options can contain embedded credentials.
PRIVATE = SECRETS | {("app_store", "default_repository_url"), ("rpiface", "base_url")}
SERVER_PREFIX = "mcp.server."
SERVER_ID = re.compile(r"[A-Za-z0-9_-]{1,24}")
SERVER_FIELDS = {f.name: f.default for f in fields(MCPServerConfig)}
SERVER_FIELDS.update(name="", transport="stdio", args="", env_vars="")
SERVER_HELP = {
    "name": "Optional tool namespace. Defaults to the section name.",
    "transport": "Choose stdio for a local process or streamable-http for an HTTP endpoint.",
    "command": "Executable to launch as the assistant service user.",
    "args": "Arguments as a JSON string array or comma-separated list.",
    "env_vars": "Environment variable names passed to the process. Enter names only.",
    "url": "HTTP(S) endpoint used by streamable-http.",
    "token_env": "Name of the environment variable holding the HTTP bearer token.",
}
GROUPS = {
    "audio": "Microphone", "wakeword": "Wake word", "recording": "Recording and button",
    "openai": "OpenAI and conversation", "audio_output": "Speaker", "led": "LEDs",
    "logging": "Logs and privacy", "controls": "Phone access and mixer",
    "timers": "Timers", "household": "Shopping and reminders", "weather": "Local weather",
    "rpiface": "RPiFace display", "app_store": "App sources and signing", "mcp": "MCP tools",
}
EXAMPLE = Path(__file__).resolve().parents[1] / "config.ini.example"


def read_ini(data):
    parser = ConfigParser()
    if data:
        parser.read_string(data.decode("utf-8"))
    return parser


def example_help():
    """Use the project's field descriptions, including its commented alternatives."""
    result, comments, section = {}, [], ""
    for line in EXAMPLE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("["):
            section, comments = line[1:-1], []
        elif line.startswith("#"):
            comments.append(line[1:].strip())
        elif "=" in line:
            key = line.split("=", 1)[0].strip()
            result[section, key] = " ".join(comments)
            comments = []
        else:
            comments = []
    return result


def is_private(section, key):
    return (section, key) in PRIVATE or (section.startswith(SERVER_PREFIX) and key in ("command", "args", "url"))


def describe(parser):
    inventory = {}
    config = parse_config(parser, allow_missing_api_key=True, inventory=inventory)
    help_text = example_help()
    options = {}
    for (section, key), (env, default, kind) in inventory.items():
        source = "default"
        value = default
        if parser.has_option(section, key):
            source = "file" if key in parser._sections[section] else "INI DEFAULT"
            value = parser.get(section, key, raw=True).replace("%%", "%")
        elif (section, key) == ("mcp", "servers") and "MCP_SERVERS_JSON" in os.environ:
            source, value = "MCP_SERVERS_JSON", ", ".join(s.name for s in config.mcp.servers)
        elif env in os.environ:
            source, value = env, os.environ[env]
        info = field_info(section, key, source, value, kind, help_text.get((section, key), ""))
        info["environment"] = env
        if (section, key) in CHOICES:
            info["choices"] = CHOICES[section, key]
        if not info["private"]:
            info["default"] = "" if default is None else str(default)
        options.setdefault(section, {})[key] = info
    for section in parser.sections():
        if section.startswith(SERVER_PREFIX) and SERVER_ID.fullmatch(section[len(SERVER_PREFIX):]):
            options[section] = server_options(parser, section)
    return options


def field_info(section, key, source, value, kind, help_text):
    item = {"source": source, "type": kind.__name__, "help": help_text,
            "private": is_private(section, key)}
    if item["private"]:
        item["configured"] = bool(value)
    else:
        item["value"] = "" if value is None else str(value)
    return item


def server_options(parser, section):
    options = {}
    for key, default in SERVER_FIELDS.items():
        source = "default"
        value = section[len(SERVER_PREFIX):] if key == "name" else default
        if parser.has_option(section, key):
            source = "file" if key in parser._sections[section] else "INI DEFAULT"
            value = parser.get(section, key, raw=True).replace("%%", "%")
        options[key] = field_info(section, key, source, value, str, SERVER_HELP[key])
    return options


# Bounds for newly entered settings on the 512 MB target, including finite values.
BOUNDS = {
    "audio": {"sample_rate": (16000, 16000), "channels": (1, 16), "chunk_size": (1, 16000),
              "mic_channel_index": (0, 15), "queue_seconds": (0.08, 30)},
    "wakeword": {"threshold": (0, 1), "cooldown_seconds": (0, 60)},
    "recording": {"max_duration_seconds": (0.1, 120), "silence_hold_seconds": (0, 30),
                  "silence_rms_threshold": (0, 1), "pre_roll_seconds": (0, 10),
                  "follow_up_window_seconds": (0, 15), "follow_up_echo_guard_seconds": (0, 10),
                  "processing_drain_seconds": (0, 30), "correction_window_seconds": (0.1, 30)},
    "led": {"count": (1, 256)},
    "openai": {"temperature": (0, 2), "max_tokens": (1, 32768), "request_timeout_seconds": (0.1, 180),
               "tts_timeout_seconds": (0.1, 180), "conversation_idle_timeout_seconds": (0, 86400),
               "conversation_relevance_threshold": (0, 1), "conversation_max_turns": (1, 1024),
               "conversation_max_bytes": (1024, 4194304)},
    "mcp": {"timeout_seconds": (0.1, 120)},
}
CHOICES = {("openai", "tts_backend"): ("realtime", "speech"),
           ("logging", "log_level"): ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")}


def candidate(before, edits):
    """Apply only explicit operations. A null removes the file override."""
    if not isinstance(edits, dict) or not 1 <= len(edits) <= 128:
        raise EditorError("Choose at least one setting to change.")
    parser = read_ini(before)
    inventory = {}
    parse_config(parser, allow_missing_api_key=True, inventory=inventory)
    touched = set()
    for section, entries in edits.items():
        server = section.startswith(SERVER_PREFIX) and SERVER_ID.fullmatch(section[len(SERVER_PREFIX):])
        if not server and section not in GROUPS:
            raise EditorError("Unknown configuration group or invalid MCP server name.")
        if not isinstance(entries, dict) or not entries:
            raise EditorError("Expected individual settings.")
        for key, value in entries.items():
            if not (key in SERVER_FIELDS if server else (section, key) in inventory):
                raise EditorError("Unknown configuration option.")
            if value is None:
                if parser.has_section(section):
                    parser.remove_option(section, key)
            else:
                if not isinstance(value, str) or len(value) > 4096 or any(ord(c) < 32 or ord(c) == 127 for c in value):
                    raise EditorError(f"Enter a single line for {section}.{key} (up to 4096 characters).")
                if (section, key) in SECRETS and value and not re.fullmatch(r"[A-Za-z0-9._-]{8,512}", value):
                    raise EditorError("Invalid provider key format.")
                if not server:
                    kind = inventory[section, key][2]
                    try:
                        if kind in (int, float):
                            kind(value)
                        if kind is bool and value.strip().lower() not in ConfigParser.BOOLEAN_STATES:
                            raise ValueError()
                    except ValueError:
                        raise EditorError(f"Invalid {kind.__name__} value for {section}.{key}.") from None
                if not parser.has_section(section):
                    parser.add_section(section)
                parser.set(section, key, value.strip().replace("%", "%%"))
            touched.add((section, key))
        if server and parser.has_section(section) and not parser._sections[section]:
            parser.remove_section(section)
    try:
        config = parse_config(parser, allow_missing_api_key=True)
        for section in {s for s, _ in touched if s.startswith(SERVER_PREFIX) and parser.has_section(s)}:
            server_config = _server_from_section(parser, section[len(SERVER_PREFIX):])
            names = list(server_config.env_vars)
            if server_config.token_env:
                names.append(server_config.token_env)
            if any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) for name in names):
                raise EditorError("Enter environment variable names for MCP credentials.")
        for section, key in sorted(touched):
            if section.startswith(SERVER_PREFIX):
                continue
            obj = getattr(config, "wake_word" if section == "wakeword" else section)
            value = getattr(obj, key)
            bounds = BOUNDS.get(section, {}).get(key)
            if bounds and not bounds[0] <= value <= bounds[1]:
                raise EditorError(f"{section}.{key} must be between {bounds[0]} and {bounds[1]}.")
            if isinstance(value, float) and not math.isfinite(value):
                raise EditorError(f"{section}.{key} must be finite.")
            if (section, key) in CHOICES and value not in CHOICES[section, key]:
                raise EditorError("Choose one of " + ", ".join(CHOICES[section, key]) + ".")
            if (section, key) == ("app_store", "trusted_public_key") and value and len(base64.b64decode(value, validate=True)) != 32:
                raise EditorError("Use a Base64-encoded Ed25519 public key.")
            if (section, key) == ("rpiface", "base_url") and (urlsplit(value).scheme not in ("http","https") or not urlsplit(value).hostname):
                raise EditorError("RPiFace needs an HTTP or HTTPS URL.")
        if config.audio.mic_channel_index >= config.audio.channels:
            raise EditorError("Microphone channel index must be less than the number of channels.")
        if config.recording.silence_hold_seconds > config.recording.max_duration_seconds:
            raise EditorError("Silence hold must fit within the recording duration.")
    except EditorError:
        raise
    except Exception:
        raise EditorError("Invalid configuration. Check the edited values, timezones, coordinates and named MCP definitions.") from None
    buf = io.StringIO()
    parser.write(buf)
    return buf.getvalue().encode(), config, touched
