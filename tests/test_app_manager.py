import unittest
from json import dumps
from pathlib import Path
from tempfile import TemporaryDirectory

from rpi_assistant.app.app_manager import AppManager
from rpi_assistant.app.app_loader import discover_apps
from rpi_assistant.app.apps.ask_estonia import QUESTIONS
from rpi_assistant.app.apps.truth_or_dare import DARES, TRUTHS


class AppManagerTests(unittest.TestCase):
    def create_app_bundle(
        self,
        parent_dir: Path,
        app_id: str = "dice",
        name: str = "Dice",
        trigger: str = "roll test die",
        response_text: str = "rolled",
        version: str = "0.1.0",
        description: str = "Roll a single die.",
    ) -> Path:
        bundle_dir = parent_dir / app_id
        bundle_dir.mkdir(parents=True, exist_ok=True)
        (bundle_dir / "manifest.json").write_text(
            dumps(
                {
                    "id": app_id,
                    "name": name,
                    "version": version,
                    "entrypoint": "app:DiceApp",
                    "triggers": [trigger],
                    "description": description,
                }
            ),
            encoding="utf-8",
        )
        (bundle_dir / "app.py").write_text(
            "from rpi_assistant.app.apps.base import AppResponse, VoiceApp\n"
            "\n"
            "class DiceApp(VoiceApp):\n"
            "    id = 'placeholder'\n"
            "    name = 'Placeholder'\n"
            "    triggers = []\n"
            "\n"
            "    def start(self, text: str) -> AppResponse:\n"
            f"        return AppResponse(text='{response_text}', done=True)\n"
            "\n"
            "    def handle(self, text: str) -> AppResponse:\n"
            f"        return AppResponse(text='{response_text} again', done=True)\n",
            encoding="utf-8",
        )
        return bundle_dir

    def create_repository(self, root_dir: Path, bundles: list[tuple[str, Path]]) -> Path:
        apps_dir = root_dir / "apps"
        apps_dir.mkdir(parents=True, exist_ok=True)
        entries = []

        for app_id, source_bundle in bundles:
            destination = apps_dir / app_id
            destination.mkdir(parents=True, exist_ok=True)
            for source_file in source_bundle.iterdir():
                destination.joinpath(source_file.name).write_text(
                    source_file.read_text(encoding="utf-8"),
                    encoding="utf-8",
                )
            entries.append({"id": app_id, "bundle": f"apps/{app_id}"})

        (root_dir / "index.json").write_text(
            dumps({"apps": entries}),
            encoding="utf-8",
        )
        return root_dir

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
            self.create_app_bundle(Path(tmp_dir))

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

    def test_list_installed_apps_command_uses_registered_apps(self):
        manager = AppManager()

        response = manager.handle("list installed apps")

        self.assertIsNotNone(response)
        self.assertEqual(response.text, "Installed apps: Ask!, Truth or Dare.")

    def test_list_available_apps_command_uses_repository(self):
        with TemporaryDirectory() as store_tmp:
            source_dir = Path(store_tmp) / "source"
            source_dir.mkdir(parents=True, exist_ok=True)
            bundle = self.create_app_bundle(source_dir)
            repository_dir = self.create_repository(Path(store_tmp) / "repo", [("dice", bundle)])
            manager = AppManager(repository_roots=[repository_dir])

            response = manager.handle("list available apps")

        self.assertIsNotNone(response)
        self.assertEqual(response.text, "Available apps: Dice.")

    def test_install_command_copies_bundle_and_registers_app(self):
        with TemporaryDirectory() as source_tmp, TemporaryDirectory() as install_tmp:
            source_bundle = self.create_app_bundle(Path(source_tmp))
            manager = AppManager(app_dirs=[Path(install_tmp)])

            response = manager.handle(f"install app from {source_bundle}")

            self.assertIsNotNone(response)
            self.assertEqual(response.text, "Installed Dice version 0.1.0.")
            self.assertTrue((Path(install_tmp) / "dice" / "manifest.json").exists())
            self.assertIn("dice", {app.id for app in manager.list_apps()})

            roll = manager.handle("roll test die")

        self.assertIsNotNone(roll)
        self.assertEqual(roll.text, "rolled")

    def test_install_command_can_resolve_app_store_id(self):
        with TemporaryDirectory() as store_tmp, TemporaryDirectory() as install_tmp:
            source_dir = Path(store_tmp) / "source"
            source_dir.mkdir(parents=True, exist_ok=True)
            bundle = self.create_app_bundle(source_dir)
            repository_dir = self.create_repository(Path(store_tmp) / "repo", [("dice", bundle)])
            manager = AppManager(app_dirs=[Path(install_tmp)], repository_roots=[repository_dir])

            response = manager.handle("install app dice")

        self.assertIsNotNone(response)
        self.assertEqual(response.text, "Installed Dice version 0.1.0.")

    def test_uninstall_command_removes_bundle_and_unregisters_app(self):
        with TemporaryDirectory() as source_tmp, TemporaryDirectory() as install_tmp:
            source_bundle = self.create_app_bundle(Path(source_tmp))
            manager = AppManager(app_dirs=[Path(install_tmp)])
            manager.handle(f"install app from {source_bundle}")

            response = manager.handle("uninstall app dice")

            self.assertIsNotNone(response)
            self.assertEqual(response.text, "Uninstalled Dice.")
            self.assertFalse((Path(install_tmp) / "dice").exists())
            self.assertNotIn("dice", {app.id for app in manager.list_apps()})

    def test_cannot_uninstall_built_in_app(self):
        manager = AppManager()

        response = manager.handle("uninstall app truth_or_dare")

        self.assertIsNotNone(response)
        self.assertEqual(response.text, "Cannot uninstall built-in app Truth or Dare.")

    def test_describe_app_uses_repository_metadata(self):
        with TemporaryDirectory() as store_tmp:
            source_dir = Path(store_tmp) / "source"
            source_dir.mkdir(parents=True, exist_ok=True)
            bundle = self.create_app_bundle(
                source_dir,
                description="Roll a single six-sided die locally.",
            )
            repository_dir = self.create_repository(Path(store_tmp) / "repo", [("dice", bundle)])
            manager = AppManager(repository_roots=[repository_dir])

            response = manager.handle("describe app dice")

        self.assertIsNotNone(response)
        self.assertEqual(
            response.text,
            "Dice. Version: 0.1.0. Status: available. Description: "
            "Roll a single six-sided die locally. Triggers: roll test die.",
        )

    def test_upgrade_command_uses_repository_version(self):
        with TemporaryDirectory() as store_tmp, TemporaryDirectory() as install_tmp:
            source_dir = Path(store_tmp) / "source"
            source_dir.mkdir(parents=True, exist_ok=True)
            installed_bundle = self.create_app_bundle(
                source_dir,
                version="0.1.0",
                response_text="rolled one",
            )
            upgrade_source_dir = Path(store_tmp) / "upgrade_source"
            upgrade_source_dir.mkdir(parents=True, exist_ok=True)
            upgrade_bundle = self.create_app_bundle(
                upgrade_source_dir,
                version="0.2.0",
                response_text="rolled two",
            )
            repository_dir = self.create_repository(
                Path(store_tmp) / "repo",
                [("dice", upgrade_bundle)],
            )
            manager = AppManager(app_dirs=[Path(install_tmp)], repository_roots=[repository_dir])
            manager.handle(f"install app from {installed_bundle}")

            response = manager.handle("upgrade app dice")
            roll = manager.handle("roll test die")

        self.assertIsNotNone(response)
        self.assertEqual(response.text, "Upgraded Dice to 0.2.0.")
        self.assertIsNotNone(roll)
        self.assertEqual(roll.text, "rolled two")

    def test_install_command_upgrades_when_newer_version_is_available(self):
        with (
            TemporaryDirectory() as source_tmp,
            TemporaryDirectory() as upgrade_tmp,
            TemporaryDirectory() as install_tmp,
        ):
            installed_bundle = self.create_app_bundle(
                Path(source_tmp),
                version="0.1.0",
                response_text="rolled one",
            )
            newer_bundle = self.create_app_bundle(
                Path(upgrade_tmp),
                version="0.2.0",
                response_text="rolled two",
            )
            manager = AppManager(app_dirs=[Path(install_tmp)])
            manager.handle(f"install app from {installed_bundle}")

            response = manager.handle(f"install app from {newer_bundle}")
            roll = manager.handle("roll test die")

        self.assertIsNotNone(response)
        self.assertEqual(response.text, "Installed Dice version 0.2.0.")
        self.assertIsNotNone(roll)
        self.assertEqual(roll.text, "rolled two")


if __name__ == "__main__":
    unittest.main()
