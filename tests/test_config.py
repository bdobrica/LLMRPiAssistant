import unittest
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


if __name__ == "__main__":
    unittest.main()
