import unittest
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory

from rpi_assistant.app.config import load_config


class ConfigTests(unittest.TestCase):
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
        with TemporaryDirectory() as tmp_dir, patch.dict(
            "os.environ",
            {
                "OPENAI_API_KEY": "test-key",
                "RPIFACE_ENABLED": "true",
                "RPIFACE_BASE_URL": "http://127.0.0.1:9999",
                "RPIFACE_TIMEOUT_SECONDS": "0.25",
            },
            clear=True,
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


if __name__ == "__main__":
    unittest.main()
