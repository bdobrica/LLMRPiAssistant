import json
import unittest
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory

from rpi_assistant.app.config import load_config


class ConfigTests(unittest.TestCase):
    def test_followup_settings_can_be_configured_and_disabled(self):
        with TemporaryDirectory() as directory, patch.dict("os.environ", {}, clear=True):
            path = Path(directory) / "config.ini"
            path.write_text("[openai]\napi_key=test\n[recording]\nfollow_up_window_seconds=0\n"
                            "follow_up_echo_guard_seconds=0.5\n")
            config = load_config(str(path))
            self.assertEqual(config.recording.follow_up_window_seconds, 0)
            self.assertEqual(config.recording.follow_up_echo_guard_seconds, 0.5)
            path.write_text("[openai]\napi_key=test\n[recording]\nfollow_up_window_seconds=nan\n")
            with self.assertRaisesRegex(ValueError, "finite and nonnegative"):
                load_config(str(path))

    def test_model_workflow_defaults_and_legacy_override(self):
        with TemporaryDirectory() as directory, patch.dict("os.environ", {}, clear=True):
            path = Path(directory) / "config.ini"
            path.write_text("[openai]\napi_key=test\n")
            config = load_config(str(path))
            self.assertEqual(config.openai.whisper_model, "gpt-transcribe")
            self.assertEqual(config.openai.chat_model, "gpt-6-luna")
            self.assertEqual(config.openai.reasoning_effort, "none")
            self.assertEqual(config.openai.tts_backend, "realtime")
            self.assertEqual(config.openai.tts_model, "gpt-realtime-2.1-mini")
            self.assertEqual(config.audio_output.tts_output_path, "/tmp/response.wav")
            path.write_text("[openai]\napi_key=test\ntts_backend=speech\ntts_model=tts-1\n"
                            "reasoning_effort=\ntts_timeout_seconds=45\n")
            config = load_config(str(path))
            self.assertEqual(config.openai.tts_backend, "speech")
            self.assertEqual(config.openai.reasoning_effort, "")
            self.assertEqual(config.openai.tts_timeout_seconds, 45)

    def test_load_config_reads_audio_queue_and_processing_drain_seconds(self):
        with TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.ini"
            config_path.write_text(
                "\n".join(
                    [
                        "[openai]",
                        "api_key = test-key",
                        "conversation_idle_timeout_seconds = 42",
                        "conversation_relevance_threshold = 0.6",
                        "",
                        "[audio]",
                        "queue_seconds = 1.5",
                        "",
                        "[recording]",
                        "processing_drain_seconds = 0.75",
                    ]
                ),
                encoding="utf-8",
            )

            config = load_config(str(config_path))

        self.assertEqual(config.audio.queue_seconds, 1.5)
        self.assertEqual(config.recording.processing_drain_seconds, 0.75)
        self.assertEqual(config.openai.conversation_idle_timeout_seconds, 42)
        self.assertEqual(config.openai.conversation_relevance_threshold, 0.6)
        self.assertFalse(config.rpiface.enabled)
        self.assertEqual(config.rpiface.base_url, "http://127.0.0.1:8765")
        self.assertEqual(config.rpiface.timeout_seconds, 0.3)
        self.assertFalse(config.mcp.enabled)
        self.assertEqual(config.mcp.servers, ())

    def test_load_config_reads_rpiface_section(self):
        with TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.ini"
            config_path.write_text(
                "[openai]\napi_key=test-key\n[rpiface]\n"
                "enabled=true\nbase_url=http://localhost:9000\ntimeout_seconds=0.2\n",
                encoding="utf-8",
            )
            config = load_config(str(config_path))

        self.assertTrue(config.rpiface.enabled)
        self.assertEqual(config.rpiface.base_url, "http://localhost:9000")
        self.assertEqual(config.rpiface.timeout_seconds, 0.2)

    def test_load_config_reads_rpiface_environment(self):
        with (
            TemporaryDirectory() as tmp_dir,
            patch.dict(
                "os.environ",
                {
                    "OPENAI_API_KEY": "test-key",
                    "RPIFACE_ENABLED": "true",
                    "RPIFACE_BASE_URL": "http://127.0.0.1:9999",
                    "RPIFACE_TIMEOUT_SECONDS": "0.25",
                },
                clear=True,
            ),
        ):
            config = load_config(str(Path(tmp_dir) / "missing.ini"))

        self.assertTrue(config.rpiface.enabled)
        self.assertEqual(config.rpiface.base_url, "http://127.0.0.1:9999")
        self.assertEqual(config.rpiface.timeout_seconds, 0.25)

    def test_rejects_non_subsecond_rpiface_timeout(self):
        with TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.ini"
            config_path.write_text(
                "[openai]\napi_key=test-key\n[rpiface]\ntimeout_seconds=1\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "less than 1"):
                load_config(str(config_path))

    def test_loads_multiple_mcp_server_transports(self):
        with TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.ini"
            config_path.write_text(
                "\n".join(
                    [
                        "[openai]",
                        "api_key=test-key",
                        "[mcp]",
                        "enabled=true",
                        "servers=face, utility",
                        "max_tool_rounds=4",
                        "[mcp.server.face]",
                        "transport=stdio",
                        "command=rpiface-mcp",
                        'args=["--config", "face.toml"]',
                        "[mcp.server.utility]",
                        "transport=streamable-http",
                        "url=http://127.0.0.1:9000/mcp",
                        "token_env=UTILITY_MCP_TOKEN",
                    ]
                ),
                encoding="utf-8",
            )
            config = load_config(str(config_path))

        self.assertTrue(config.mcp.enabled)
        self.assertEqual(config.mcp.max_tool_rounds, 4)
        self.assertEqual(len(config.mcp.servers), 2)
        self.assertEqual(config.mcp.servers[0].args, ("--config", "face.toml"))
        self.assertEqual(config.mcp.servers[1].token_env, "UTILITY_MCP_TOKEN")

    def test_loads_mcp_servers_from_environment_json(self):
        with (
            TemporaryDirectory() as tmp_dir,
            patch.dict(
                "os.environ",
                {
                    "OPENAI_API_KEY": "test-key",
                    "MCP_ENABLED": "true",
                    "MCP_SERVERS_JSON": json.dumps(
                        [
                            {
                                "name": "utility",
                                "transport": "streamable-http",
                                "url": "https://mcp.example.test/mcp",
                                "token_env": "UTILITY_TOKEN",
                            }
                        ]
                    ),
                },
                clear=True,
            ),
        ):
            config = load_config(str(Path(tmp_dir) / "missing.ini"))

        self.assertEqual(config.mcp.servers[0].name, "utility")
        self.assertEqual(config.mcp.servers[0].token_env, "UTILITY_TOKEN")


if __name__ == "__main__":
    unittest.main()
