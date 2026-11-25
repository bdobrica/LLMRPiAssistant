"""Synthetic coverage inventory, phone round trips and interrupted restart recovery."""

from configparser import ConfigParser
from dataclasses import fields
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from rpi_assistant.app.admin_auth import DeviceAuth, verifier
from rpi_assistant.app.config import load_config, parse_config
from rpi_assistant.app.config_editor import candidate, describe, EditorError, EXAMPLE, read_ini
from rpi_assistant.app.control_server import ControlServer
from rpi_assistant.app.settings_trial import SettingsTrial
import test_phone_setup


class ConfigEditorTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, {}, clear=True))
        self.directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.path = self.directory/"config.ini"

    def test_every_example_alternative_and_parsed_dataclass_field_is_in_ui(self):
        parser = read_ini(EXAMPLE.read_bytes())
        options = describe(parser)
        config = parse_config(parser, allow_missing_api_key=True)
        for section in fields(config):
            name = "wakeword" if section.name == "wake_word" else section.name
            self.assertEqual(set(options[name]), {f.name for f in fields(getattr(config, section.name))})
        section = None
        for line in EXAMPLE.read_text().splitlines():
            if line.startswith("["):
                section = line[1:-1]
            match = re.match(r"^(?:#\s*)?([a-z][a-z0-9_]*)\s*=", line)
            if match:
                self.assertIn(match[1], options[section], (section, match[1]))
        for field in fields(config.mcp.servers[0]):
            self.assertIn(field.name, options["mcp.server.rpiface"])
        env = '[{"name":"private","transport":"stdio","command":"private-cli","args":["secret-marker"]}]'
        with patch.dict(os.environ, {"MCP_SERVERS_JSON":env}):
            desc = describe(ConfigParser())
            self.assertEqual(desc["mcp"]["servers"]["source"], "MCP_SERVERS_JSON")
            self.assertNotIn("secret-marker", json.dumps(desc))

    def test_save_and_restart_all_groups_named_servers_and_persistent_undo(self):
        before = b"[custom]\nunknown = preserve\n"
        self.path.write_bytes(before)
        example = read_ini(EXAMPLE.read_bytes())
        edits = {s: dict(example.items(s, raw=True)) for s in example.sections()}
        edits["mcp"]["servers"] = "rpiface,remote"
        edits["mcp.server.remote"] = {"transport":"streamable-http", "url":"https://example.invalid/mcp",
                                      "token_env":"REMOTE_KEY"}
        edits["openai"]["system_prompt"] = "Use 100% literal text."
        after, expected, touched = candidate(before, edits)
        trial = SettingsTrial(self.path)
        trial.arm(before, after, touched)
        self.assertEqual(self.path.read_bytes(), before)
        trial = SettingsTrial(self.path)
        self.assertEqual(trial.begin(), expected)
        trial.finish()
        self.assertEqual(load_config(self.path, allow_missing_api_key=True), expected)
        self.assertEqual(read_ini(after)["custom"]["unknown"], "preserve")
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        backup = json.loads(trial.undo.read_bytes())
        self.assertEqual(backup["config_text"].encode(), before)
        trial.arm(after, before, backup["fields"], undo=True)
        self.assertIsNotNone(trial.begin())
        trial.finish()
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(trial.undo.exists())

    def test_cross_field_validation_and_redacted_errors(self):
        for edits in ({"audio":{"channels":"2","mic_channel_index":"3"}},
                      {"rpiface":{"timeout_seconds":"1"}}, {"weather":{"latitude":"45"}},
                      {"openai":{"temperature":"nan"}}, {"logging":{"max_bytes":"secret-marker"}},
                      {"mcp":{"servers":"missing"}}, {"openai":{"system_prompt":"a\n[custom]"}},
                      {"mcp.server.extra":{"transport":"streamable-http","url":"secret-marker"}},
                      {"app_store":{"trusted_public_key":"secret-marker"}},
                      {"controls":{"port":"65536"}}, {"household":{"timezone":"secret-marker"}}):
            with self.subTest(groups=list(edits)), self.assertRaises(EditorError) as caught:
                candidate(None, edits)
            self.assertNotIn("secret-marker", str(caught.exception))

    def test_state_path_rollback_and_undo_preserve_new_household_writes(self):
        source, dest = self.directory/'house.sqlite3', self.directory/'moved.sqlite3'
        other = self.directory/'timers.sqlite3'
        start = f"[household]\nstate_path={source}\n[timers]\nstate_path={other}\n".encode()
        change, _, names = candidate(start, {"household":{"state_path":str(dest)},
                                              "timers":{"state_path":str(source)}})
        with self.assertRaisesRegex(EditorError, "separate"):
            SettingsTrial(self.path).arm(start, change, names)
        source.write_bytes(b"synthetic shopping")
        before = f"[household]\nstate_path={source}\n".encode()
        self.path.write_bytes(before)
        after, _, touched = candidate(before, {"household":{"state_path":str(dest)}})
        trial = SettingsTrial(self.path)
        dest.write_bytes(b"other data")
        with self.assertRaises(EditorError):
            trial.arm(before, after, touched)
        self.assertEqual(dest.read_bytes(), b"other data")
        dest.unlink()
        trial.arm(before, after, touched)
        trial.begin()
        self.assertEqual(dest.read_bytes(), b"synthetic shopping")
        dest.write_bytes(b"new reminder during trial")
        self.assertIsNone(SettingsTrial(self.path).begin())  # crash before readiness
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(source.read_bytes(), b"new reminder during trial")
        self.assertFalse(dest.exists())
        trial.arm(before, after, touched)
        trial.begin()
        trial.finish()
        dest.write_bytes(b"new shopping after successful save")
        trial.arm(after, before, touched, undo=True)
        trial.begin()
        trial.finish()
        self.assertEqual(source.read_bytes(), b"new shopping after successful save")

    def test_external_edit_cancels_restart_without_touching_file(self):
        before = b"[led]\ncount = 12\n"
        self.path.write_bytes(before)
        trial = SettingsTrial(self.path)
        after, _, touched = candidate(before, {"led":{"count":"3"}})
        trial.arm(before, after, touched)
        self.path.write_bytes(b"[led]\ncount = 8\n")
        self.assertIsNone(trial.begin())
        self.assertEqual(read_ini(self.path.read_bytes()).getint("led", "count"), 8)


class AdvancedPhoneTests(unittest.TestCase):
    def setUp(self):
        fixture = test_phone_setup.PhoneSetupTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.settings = fixture.settings
        self.controls = fixture.controls

    def apply(self, edits, **extra):
        payload = {"revision":self.settings.options()["revision"], "edits":edits, **extra}
        return self.controls.command("settings_advanced", payload)

    def test_remove_override_inherit_env_disable_key_replace_and_undo(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY":"synthetic-env-secret"}), patch('rpi_assistant.app.phone_settings.OpenAI'):
            self.apply({"openai":{"api_key":None}})
            self.assertEqual(self.settings.config.openai.api_key, "synthetic-env-secret")
            options = self.settings.options()
            self.assertEqual(options["options"]["openai"]["api_key"]["source"], "OPENAI_API_KEY")
            self.apply({"openai":{"api_key":""}})
            self.assertFalse(self.settings.status()["keys_configured"]["openai_key"])
            self.assertNotIn("synthetic-env-secret", self.settings.backup.read_text())
            os.environ["OPENAI_API_KEY"] = "updated-env-secret"
            self.controls.command("settings_undo", {"revision":self.settings.options()["revision"]})
            self.assertEqual(self.settings.config.openai.api_key, "updated-env-secret")
            self.apply({"openai":{"api_key":""}})
            self.apply({"openai":{"api_key":"replacement-synthetic"}})
            self.assertEqual(self.settings.config.openai.api_key, "replacement-synthetic")
            self.assertNotIn("replacement-synthetic", json.dumps(self.settings.options()))
            self.assertNotIn("synthetic-env-secret", json.dumps(self.controls.status()))
            self.controls.command("settings_undo", {"revision":self.settings.options()["revision"]})
            self.assertFalse(self.settings.config.openai.api_key)

    def test_failed_live_apply_preserves_last_working_undo(self):
        self.apply({"recording":{"follow_up_window_seconds":"4"}})
        undo = self.settings.backup.read_bytes()
        with patch.object(self.settings, "_prepare", side_effect=RuntimeError("synthetic-secret")):
            with self.assertRaises(EditorError):
                self.apply({"recording":{"follow_up_window_seconds":"3"}})
        self.assertEqual(self.settings.backup.read_bytes(), undo)

    def test_restart_and_trust_need_explicit_confirmation(self):
        self.enterContext(patch.dict(os.environ, {"INVOCATION_ID":"fixture", "CREDENTIALS_DIRECTORY":"/fixture"}))
        timer = self.enterContext(patch('rpi_assistant.app.phone_settings.threading.Timer'))
        self.assertRaisesRegex(EditorError, "Confirm the service restart", self.apply, {"led":{"count":"3"}})
        self.assertRaisesRegex(EditorError, "trusted app", self.apply, {"app_store":{"require_signature":"false"}}, confirm_restart=True)
        self.apply({"led":{"count":"3"}}, confirm_restart=True)
        timer.return_value.start.assert_called_once()
        self.assertRaisesRegex(EditorError, "restart", self.apply, {"openai":{"temperature":"0.5"}})

    @unittest.skipUnless(shutil.which("curl"), "requires a Digest-capable HTTP client")
    def test_real_http_digest_and_no_legacy_write_bypass(self):
        server = ControlServer(type("Config", (), {"host":"127.0.0.1","port":0})(), self.controls)
        self.addCleanup(server.close)
        server.auth = DeviceAuth(verifier("synthetic-device-code"))
        base = f"http://127.0.0.1:{server.server_port}"
        def fetch(route, code, *extra):
            return subprocess.run(["curl","--silent","--show-error","--digest","-u","admin:"+code,
                                   "-w","\n%{http_code}", *extra, base + route],
                                  capture_output=True, text=True, check=True, timeout=6).stdout.rsplit("\n", 1)
        self.assertEqual(fetch("/admin/options", "incorrect")[1], "401")
        body, status = fetch("/admin/options", "synthetic-device-code")
        self.assertEqual(status, "200")
        self.assertNotIn("old-private-key", body)
        payload = json.dumps({"action":"settings_advanced","value":{"revision":json.loads(body)["revision"],
                              "edits":{"recording":{"follow_up_window_seconds":"3"}}}})
        args = ("-H","X-Assistant-Control: 1","--data-binary",payload)
        self.assertEqual(fetch("/admin/change","synthetic-device-code",*args)[1], "200")
        self.assertEqual(self.settings.config.recording.follow_up_window_seconds, 3)
        self.assertEqual(fetch("/admin/change","synthetic-device-code",*args)[1], "400")  # stale
        self.assertEqual(fetch("/admin/change","synthetic-device-code","-H","Origin: http://wrong.test",*args)[1], "403")
