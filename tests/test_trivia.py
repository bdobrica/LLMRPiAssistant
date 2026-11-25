import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from rpi_assistant.app.app_manager import AppManager


class TriviaTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.save = root / "active.json"
        self.options = dict(
            app_dirs=[root / "installed"],
            repository_roots=[Path(__file__).resolve().parents[1] / "voice_apps"],
            require_repository_signature=True,
            active_state_path=self.save,
        )
        self.manager = AppManager(**self.options)
        self.assertIn("Installed Trivia", self.say("Install app trivia").text)
        with patch("random.sample", return_value=["hearts", "watch", "compass"]):
            self.first = self.say("Play trivia").text

    def say(self, words):
        return self.manager.handle(words)

    def test_round_scores_once_per_choice_and_returns_to_questions(self):
        saved = self.save.read_bytes()
        self.assertIn("three hearts", self.first)
        for guess in ["octopus or shark", "x" * 4000, "repeat"]:
            self.assertIn("Question 1.", self.say(guess).text)
            self.assertEqual(self.save.read_bytes(), saved)
        self.assertIn("Question 2.", self.say("I think it's an octopus.").text)
        self.assertIn("Question 3.", self.say("the first one").text)
        final = self.say("The needle!")
        self.assertTrue(final.done)
        self.assertIn("2 out of 3", final.text)
        self.assertFalse(self.save.exists())
        self.assertIsNone(self.say("Why is the sky blue?"))

    def test_pause_survives_restart_and_resumes_same_question(self):
        self.say("octopus")
        self.assertIn("paused", self.say("pause game").text)
        saved = self.save.read_bytes()
        self.manager = AppManager(**self.options)
        self.assertIn("paused", self.say("What game is active?").text)
        self.assertIn("paused", self.say("crystal").text)
        self.assertEqual(saved, self.save.read_bytes())
        self.assertIn("Question 2.", self.say("resume game").text)
        self.assertIn("right", self.say("second").text)
        self.assertIn("3 out of 3", self.say("needle").text)

    def test_stop_while_paused_discards_round(self):
        self.say("pause")
        self.assertTrue(self.say("Stop game").done)
        self.assertFalse(self.save.exists())
        self.assertIn("No app is active", self.say("Resume app").text)
        self.say("Play trivia")
        state = json.loads(self.save.read_bytes())["state"]
        self.assertEqual(len(state["round"]), 3)
        self.assertEqual(len(set(state["round"])), 3)
        self.assertEqual(state["score"], 0)

    def test_moon_guess_with_confirmation_and_natural_exit(self):
        self.say("Stop game")
        with patch("random.sample", return_value=["watch", "tracks", "compass"]):
            self.say("Play trivia")
        self.say("second")
        saved = self.save.read_bytes()
        self.assertTrue(self.say("A person or a dinosaur. That's my answer.").retry_input)
        self.assertEqual(saved, self.save.read_bytes())
        answer = self.say("Hey Jarvis, a person. That’s my answer. Let’s continue playing trivia.")
        self.assertIn("That's right!", answer.text)
        self.assertIn("Question 3.", answer.text)
        self.assertEqual(json.loads(self.save.read_bytes())["state"]["score"], 2)
        self.assertTrue(self.say("I don’t want to play anymore.").done)
        self.assertFalse(self.save.exists())
        self.assertIsNone(self.say("I don't want to play anymore."))

    def test_invalid_restored_round_finishes_without_scoring(self):
        saved = json.loads(self.save.read_bytes())
        saved["state"]["position"] = -1
        self.save.write_text(json.dumps(saved))
        self.manager = AppManager(**self.options)
        self.assertTrue(self.say("resume game").done)
        self.assertFalse(self.save.exists())
