import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from rpi_assistant.app.app_manager import AppManager
from rpi_assistant.app.app_loader import discover_apps
from rpi_assistant.app.apps.ask_estonia import QUESTIONS
from rpi_assistant.app.apps.truth_or_dare import DARES, TRUTHS


class AppManagerTests(unittest.TestCase):
    def test_truth_or_dare_stays_active_until_choice(self):
        manager = AppManager()

        response = manager.handle("do truth or dare for Alex")

        self.assertIsNotNone(response)
        self.assertEqual(response.text, "Alex, truth or dare?")
        self.assertTrue(response.expect_input)
        self.assertFalse(response.done)
        self.assertIsNotNone(manager.active_app)

        follow_up = manager.handle("truth")

        self.assertIn(follow_up.text, TRUTHS)
        self.assertTrue(follow_up.done)
        self.assertIsNone(manager.active_app)

    def test_cancel_stops_active_app(self):
        manager = AppManager()

        manager.handle("play truth or dare")
        response = manager.handle("cancel app")

        self.assertIsNotNone(response)
        self.assertEqual(response.text, "Stopped Truth or Dare.")
        self.assertTrue(response.done)
        self.assertIsNone(manager.active_app)

    def test_non_matching_command_falls_through(self):
        manager = AppManager()

        response = manager.handle("what time is it")

        self.assertIsNone(response)

    def test_ask_app_returns_local_prompt(self):
        manager = AppManager()

        response = manager.handle("play ask")

        self.assertIsNotNone(response)
        self.assertIn(response.text, QUESTIONS)
        self.assertTrue(response.done)
        self.assertIsNone(manager.active_app)

    def test_dare_choice_completes_app(self):
        manager = AppManager()

        manager.handle("play truth or dare")
        response = manager.handle("dare")

        self.assertIn(response.text, DARES)
        self.assertTrue(response.done)
        self.assertIsNone(manager.active_app)

    def test_builtin_apps_are_discovered_dynamically(self):
        manager = AppManager()

        app_ids = {app.id for app in manager.list_apps()}

        self.assertEqual(app_ids, {"ask_estonia", "truth_or_dare"})

    def test_external_app_directory_is_discovered(self):
        with TemporaryDirectory() as tmp_dir:
            app_file = Path(tmp_dir) / "dice.py"
            app_file.write_text(
                "from rpi_assistant.app.apps.base import AppResponse, VoiceApp\n"
                "\n"
                "class DiceApp(VoiceApp):\n"
                "    id = 'dice'\n"
                "    name = 'Dice'\n"
                "    triggers = ['roll test die']\n"
                "\n"
                "    def start(self, text: str) -> AppResponse:\n"
                "        return AppResponse(text='rolled', done=True)\n"
                "\n"
                "    def handle(self, text: str) -> AppResponse:\n"
                "        return AppResponse(text='rolled again', done=True)\n",
                encoding="utf-8",
            )

            apps = discover_apps(app_dirs=[Path(tmp_dir)])
            manager = AppManager(apps=apps)

            response = manager.handle("roll test die")

        self.assertIsNotNone(response)
        self.assertEqual(response.text, "rolled")

    def test_unregister_app_removes_it(self):
        manager = AppManager()

        removed = manager.unregister_app("truth_or_dare")

        self.assertIsNotNone(removed)
        self.assertEqual(removed.id, "truth_or_dare")
        self.assertEqual({app.id for app in manager.list_apps()}, {"ask_estonia"})


if __name__ == "__main__":
    unittest.main()
