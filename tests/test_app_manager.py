import json
import shutil
import threading
import unittest
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from json import dumps
from pathlib import Path
from tempfile import TemporaryDirectory

from rpi_assistant.app.app_manager import AppManager
from rpi_assistant.app.app_loader import discover_apps
from nacl.encoding import Base64Encoder
from nacl.signing import SigningKey

from rpi_assistant.app.app_install import AppInstallMetadata, INSTALL_METADATA_FILENAME
from rpi_assistant.app.app_manifest import AppManifest
from rpi_assistant.app.app_store import calculate_bundle_checksum, list_bundle_files
from rpi_assistant.app.app_signing import sign_catalog


VOICE_APPS_REPOSITORY = Path(__file__).resolve().parents[1] / "voice_apps"
VOICE_APPS_PUBLIC_KEY = (VOICE_APPS_REPOSITORY / "public_key.txt").read_text(
    encoding="utf-8"
).strip()


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

    def create_repository(self, root_dir: Path, bundles: dict[str, list[Path]]) -> Path:
        apps_dir = root_dir / "apps"
        apps_dir.mkdir(parents=True, exist_ok=True)
        entries = []

        for app_id, source_bundles in bundles.items():
            versions = []

            for source_bundle in source_bundles:
                manifest = AppManifest.load(source_bundle / "manifest.json")
                destination = apps_dir / app_id / manifest.version
                shutil.copytree(source_bundle, destination)
                files = list_bundle_files(destination)
                versions.append(
                    {
                        "version": manifest.version,
                        "bundle": f"apps/{app_id}/{manifest.version}",
                        "files": files,
                        "sha256": calculate_bundle_checksum(destination, files),
                    }
                )

            entries.append({"id": app_id, "versions": versions})

        (root_dir / "index.json").write_text(
            dumps({"apps": entries}),
            encoding="utf-8",
        )
        return root_dir

    def sign_repository(self, repository_dir: Path, private_key_base64: str) -> str:
        index_path = repository_dir / "index.json"
        payload = json.loads(index_path.read_text(encoding="utf-8"))
        signature = sign_catalog(payload, private_key_base64)
        signed_payload = {
            "catalog": payload,
            "signing": {
                "algorithm": "ed25519",
                "key_id": "test",
                "signature": signature,
            },
        }
        index_path.write_text(json.dumps(signed_payload), encoding="utf-8")
        signing_key = SigningKey(private_key_base64, encoder=Base64Encoder)
        return signing_key.verify_key.encode(encoder=Base64Encoder).decode("utf-8")

    @contextmanager
    def serve_directory(self, directory: Path):
        class QuietHandler(SimpleHTTPRequestHandler):
            def log_message(self, format, *args):
                return

        handler = partial(QuietHandler, directory=str(directory))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        try:
            host, port = server.server_address
            yield f"http://{host}:{port}/"
        finally:
            server.shutdown()
            thread.join(timeout=2)
            server.server_close()

    def test_truth_or_dare_stays_active_until_choice(self):
        with TemporaryDirectory() as install_tmp, TemporaryDirectory() as state_tmp:
            manager = AppManager(
                app_dirs=[Path(install_tmp)],
                repository_roots=[VOICE_APPS_REPOSITORY],
                repository_public_key=VOICE_APPS_PUBLIC_KEY,
                active_state_path=Path(state_tmp) / "active_app.json",
            )
            manager.handle("install app truth_or_dare")

            response = manager.handle("do truth or dare for Alex")

            self.assertIsNotNone(response)
            self.assertEqual(response.text, "Alex, truth or dare?")
            self.assertTrue(response.expect_input)
            self.assertFalse(response.done)
            self.assertIsNotNone(manager.active_app)

            follow_up = manager.handle("truth")

        self.assertIsNotNone(follow_up)
        self.assertTrue(follow_up.done)
        self.assertNotEqual(follow_up.text, "Alex, truth or dare?")
        self.assertIsNone(manager.active_app)

    def test_cancel_stops_active_app(self):
        with TemporaryDirectory() as install_tmp, TemporaryDirectory() as state_tmp:
            manager = AppManager(
                app_dirs=[Path(install_tmp)],
                repository_roots=[VOICE_APPS_REPOSITORY],
                repository_public_key=VOICE_APPS_PUBLIC_KEY,
                active_state_path=Path(state_tmp) / "active_app.json",
            )
            manager.handle("install app truth_or_dare")

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
        with TemporaryDirectory() as install_tmp:
            manager = AppManager(
                app_dirs=[Path(install_tmp)],
                repository_roots=[VOICE_APPS_REPOSITORY],
                repository_public_key=VOICE_APPS_PUBLIC_KEY,
            )
            manager.handle("install app ask")

            response = manager.handle("play ask")

        self.assertIsNotNone(response)
        self.assertTrue(response.done)
        self.assertIsNone(manager.active_app)
        self.assertTrue(bool(response.text))

    def test_classified_install_intent_can_resolve_noisy_spoken_app_name(self):
        with TemporaryDirectory() as install_tmp:
            manager = AppManager(
                app_dirs=[Path(install_tmp)],
                repository_roots=[VOICE_APPS_REPOSITORY],
                repository_public_key=VOICE_APPS_PUBLIC_KEY,
            )

            response = manager.handle("Install the app through Tor Dare")
            if response is None:
                response = manager.handle_classified_intent(
                    {
                        "intent": "install_app",
                        "app_id": "truth_or_dare",
                        "version": None,
                        "raw_target": "through Tor Dare",
                        "confidence": 0.86,
                    },
                    "Install the app through Tor Dare",
                )

        self.assertIsNotNone(response)
        self.assertEqual(response.text, "Installed Truth or Dare version 0.1.0.")

    def test_list_available_apps_command_tolerates_asr_drift(self):
        with TemporaryDirectory() as store_tmp:
            source_dir = Path(store_tmp) / "source"
            source_dir.mkdir(parents=True, exist_ok=True)
            bundle = self.create_app_bundle(source_dir)
            repository_dir = self.create_repository(Path(store_tmp) / "repo", {"dice": [bundle]})
            manager = AppManager(repository_roots=[repository_dir])

            response = manager.handle("least available apps")

        self.assertIsNotNone(response)
        self.assertEqual(response.text, "Available apps: Dice.")

    def test_install_apps_without_target_lists_available_apps(self):
        with TemporaryDirectory() as store_tmp:
            source_dir = Path(store_tmp) / "source"
            source_dir.mkdir(parents=True, exist_ok=True)
            bundle = self.create_app_bundle(source_dir)
            repository_dir = self.create_repository(Path(store_tmp) / "repo", {"dice": [bundle]})
            manager = AppManager(repository_roots=[repository_dir])

            response = manager.handle("Please install apps")

        self.assertIsNotNone(response)
        self.assertEqual(response.text, "Available apps: Dice.")

    def test_list_installed_apps_command_can_be_embedded_in_sentence(self):
        with TemporaryDirectory() as install_tmp:
            manager = AppManager(
                app_dirs=[Path(install_tmp)],
                repository_roots=[VOICE_APPS_REPOSITORY],
                repository_public_key=VOICE_APPS_PUBLIC_KEY,
            )
            manager.handle("install app dice")

            response = manager.handle(
                "I don't want to install apps I want you to list the installed apps"
            )

        self.assertIsNotNone(response)
        self.assertEqual(response.text, "Installed apps: Dice.")

    def test_install_command_can_resolve_uppercase_store_app_name(self):
        with TemporaryDirectory() as install_tmp:
            manager = AppManager(
                app_dirs=[Path(install_tmp)],
                repository_roots=[VOICE_APPS_REPOSITORY],
                repository_public_key=VOICE_APPS_PUBLIC_KEY,
            )

            response = manager.handle("Install APP DICE")

        self.assertIsNotNone(response)
        self.assertEqual(response.text, "Installed Dice version 0.1.0.")

    def test_classifier_gate_only_allows_app_related_transcriptions(self):
        manager = AppManager(repository_roots=[VOICE_APPS_REPOSITORY])

        self.assertFalse(manager.should_classify_app_intent("Are you online?"))
        self.assertTrue(manager.should_classify_app_intent("Install app footordare"))
        self.assertTrue(manager.should_classify_app_intent("Start truth or dare"))

    def test_dare_choice_completes_app(self):
        with TemporaryDirectory() as install_tmp, TemporaryDirectory() as state_tmp:
            manager = AppManager(
                app_dirs=[Path(install_tmp)],
                repository_roots=[VOICE_APPS_REPOSITORY],
                repository_public_key=VOICE_APPS_PUBLIC_KEY,
                active_state_path=Path(state_tmp) / "active_app.json",
            )
            manager.handle("install app truth_or_dare")

            manager.handle("do truth or dare for Alex")
            response = manager.handle("dare")

        self.assertIsNotNone(response)
        self.assertTrue(response.done)
        self.assertIsNone(manager.active_app)

    def test_builtin_apps_are_discovered_dynamically(self):
        manager = AppManager()

        app_ids = {app.id for app in manager.list_apps()}

        self.assertEqual(app_ids, set())

    def test_external_app_directory_is_discovered(self):
        with TemporaryDirectory() as tmp_dir:
            self.create_app_bundle(Path(tmp_dir))

            apps = discover_apps(app_dirs=[Path(tmp_dir)])
            manager = AppManager(apps=apps)

            response = manager.handle("roll test die")

        self.assertIsNotNone(response)
        self.assertEqual(response.text, "rolled")

    def test_manifest_rejects_unsafe_app_id(self):
        with self.assertRaisesRegex(ValueError, "field 'id'"):
            AppManifest.from_dict(
                {
                    "id": "../dice",
                    "name": "Dice",
                    "version": "0.1.0",
                    "entrypoint": "app:DiceApp",
                }
            )

    def test_path_install_rejects_unsafe_manifest_id(self):
        with TemporaryDirectory() as source_tmp, TemporaryDirectory() as install_tmp:
            escape_name = f"escape_{Path(install_tmp).name}"
            bundle_dir = Path(source_tmp) / "bundle"
            bundle_dir.mkdir(parents=True, exist_ok=True)
            (bundle_dir / "manifest.json").write_text(
                dumps(
                    {
                        "id": f"../{escape_name}",
                        "name": "Escape",
                        "version": "0.1.0",
                        "entrypoint": "app:EscapeApp",
                    }
                ),
                encoding="utf-8",
            )
            (bundle_dir / "app.py").write_text(
                "from rpi_assistant.app.apps.base import AppResponse, VoiceApp\n"
                "class EscapeApp(VoiceApp):\n"
                "    def start(self, text: str) -> AppResponse:\n"
                "        return AppResponse(text='bad', done=True)\n"
                "    def handle(self, text: str) -> AppResponse:\n"
                "        return AppResponse(text='bad', done=True)\n",
                encoding="utf-8",
            )
            manager = AppManager(app_dirs=[Path(install_tmp)])

            response = manager.handle(f"install app {bundle_dir}")
            escaped_path = Path(install_tmp).parent / escape_name

        self.assertIsNotNone(response)
        self.assertIn("field 'id'", response.text)
        self.assertFalse(escaped_path.exists())

    def test_unregister_app_removes_it(self):
        with TemporaryDirectory() as install_tmp:
            manager = AppManager(
                app_dirs=[Path(install_tmp)],
                repository_roots=[VOICE_APPS_REPOSITORY],
                repository_public_key=VOICE_APPS_PUBLIC_KEY,
            )
            manager.handle("install app ask")

            removed = manager.unregister_app("ask")

        self.assertIsNotNone(removed)
        self.assertEqual(removed.id, "ask")
        self.assertEqual({app.id for app in manager.list_apps()}, set())

    def test_list_installed_apps_command_uses_registered_apps(self):
        manager = AppManager()

        response = manager.handle("list installed apps")

        self.assertIsNotNone(response)
        self.assertEqual(response.text, "No apps are installed.")

    def test_active_app_state_survives_restart(self):
        with TemporaryDirectory() as install_tmp, TemporaryDirectory() as state_tmp:
            state_path = Path(state_tmp) / "active_app.json"
            manager = AppManager(
                app_dirs=[Path(install_tmp)],
                repository_roots=[VOICE_APPS_REPOSITORY],
                repository_public_key=VOICE_APPS_PUBLIC_KEY,
                active_state_path=state_path,
            )
            manager.handle("install app truth_or_dare")
            manager.handle("do truth or dare for Alex")

            restarted_manager = AppManager(
                app_dirs=[Path(install_tmp)],
                repository_roots=[VOICE_APPS_REPOSITORY],
                repository_public_key=VOICE_APPS_PUBLIC_KEY,
                active_state_path=state_path,
            )
            follow_up = restarted_manager.handle("truth")

        self.assertIsNotNone(restarted_manager.active_app or follow_up)
        self.assertIsNotNone(follow_up)
        self.assertTrue(follow_up.done)
        self.assertIsNone(restarted_manager.active_app)
        self.assertFalse(state_path.exists())

    def test_resume_app_repeats_the_current_prompt(self):
        with TemporaryDirectory() as install_tmp, TemporaryDirectory() as state_tmp:
            state_path = Path(state_tmp) / "active_app.json"
            manager = AppManager(
                app_dirs=[Path(install_tmp)],
                repository_roots=[VOICE_APPS_REPOSITORY],
                repository_public_key=VOICE_APPS_PUBLIC_KEY,
                active_state_path=state_path,
            )
            manager.handle("install app truth_or_dare")
            manager.handle("do truth or dare for Alex")

            restarted_manager = AppManager(
                app_dirs=[Path(install_tmp)],
                repository_roots=[VOICE_APPS_REPOSITORY],
                repository_public_key=VOICE_APPS_PUBLIC_KEY,
                active_state_path=state_path,
            )
            response = restarted_manager.handle("resume app")

        self.assertIsNotNone(response)
        self.assertEqual(response.text, "Alex, truth or dare?")
        self.assertTrue(response.expect_input)
        self.assertIsNotNone(restarted_manager.active_app)

    def test_active_game_command_reports_current_game(self):
        with TemporaryDirectory() as install_tmp, TemporaryDirectory() as state_tmp:
            manager = AppManager(
                app_dirs=[Path(install_tmp)],
                repository_roots=[VOICE_APPS_REPOSITORY],
                repository_public_key=VOICE_APPS_PUBLIC_KEY,
                active_state_path=Path(state_tmp) / "active_app.json",
            )
            manager.handle("install app truth_or_dare")
            manager.handle("do truth or dare for Alex")

            response = manager.handle("what game is active")

        self.assertIsNotNone(response)
        self.assertEqual(response.text, "Truth or Dare (classic) is active for Alex.")

    def test_app_store_health_reports_loaded_roots_and_signature_mode(self):
        with TemporaryDirectory() as store_tmp:
            source_dir = Path(store_tmp) / "source"
            source_dir.mkdir(parents=True, exist_ok=True)
            bundle = self.create_app_bundle(source_dir)
            repository_dir = self.create_repository(Path(store_tmp) / "repo", {"dice": [bundle]})
            manager = AppManager(
                repository_roots=[repository_dir],
                require_repository_signature=False,
            )

            response = manager.handle("app store health")

        self.assertIsNotNone(response)
        self.assertIn("App store: 1 of 1 repositories loaded.", response.text)
        self.assertIn("Signature verification is optional.", response.text)
        self.assertIn(str(repository_dir), response.text)

    def test_truth_or_dare_asks_for_player_before_choice(self):
        with TemporaryDirectory() as install_tmp, TemporaryDirectory() as state_tmp:
            manager = AppManager(
                app_dirs=[Path(install_tmp)],
                repository_roots=[VOICE_APPS_REPOSITORY],
                repository_public_key=VOICE_APPS_PUBLIC_KEY,
                active_state_path=Path(state_tmp) / "active_app.json",
            )
            manager.handle("install app truth_or_dare")

            first = manager.handle("play truth or dare")
            second = manager.handle("Alex")

        self.assertIsNotNone(first)
        self.assertEqual(first.text, "Who is playing truth or dare?")
        self.assertTrue(first.expect_input)
        self.assertIsNotNone(second)
        self.assertEqual(second.text, "Alex, truth or dare?")

    def test_list_available_apps_command_uses_repository(self):
        with TemporaryDirectory() as store_tmp:
            source_dir = Path(store_tmp) / "source"
            source_dir.mkdir(parents=True, exist_ok=True)
            bundle = self.create_app_bundle(source_dir)
            repository_dir = self.create_repository(Path(store_tmp) / "repo", {"dice": [bundle]})
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

    def test_install_command_persists_install_metadata_for_path_sources(self):
        with TemporaryDirectory() as source_tmp, TemporaryDirectory() as install_tmp:
            source_bundle = self.create_app_bundle(Path(source_tmp))
            manager = AppManager(app_dirs=[Path(install_tmp)])

            manager.handle(f"install app from {source_bundle}")
            metadata_path = Path(install_tmp) / "dice" / INSTALL_METADATA_FILENAME
            metadata = AppInstallMetadata.load(metadata_path)
            response = manager.handle("describe app dice")

        self.assertIsNotNone(metadata)
        self.assertEqual(metadata.source_type, "path")
        self.assertEqual(metadata.requested_target, str(source_bundle))
        self.assertIsNotNone(response)
        self.assertIn("Installed from path", response.text)

    def test_install_command_can_resolve_app_store_id(self):
        with TemporaryDirectory() as store_tmp, TemporaryDirectory() as install_tmp:
            source_dir = Path(store_tmp) / "source"
            source_dir.mkdir(parents=True, exist_ok=True)
            bundle = self.create_app_bundle(source_dir)
            repository_dir = self.create_repository(Path(store_tmp) / "repo", {"dice": [bundle]})
            manager = AppManager(app_dirs=[Path(install_tmp)], repository_roots=[repository_dir])

            response = manager.handle("install app dice")

        self.assertIsNotNone(response)
        self.assertEqual(response.text, "Installed Dice version 0.1.0.")

    def test_install_command_can_resolve_spoken_app_name(self):
        with TemporaryDirectory() as install_tmp:
            manager = AppManager(
                app_dirs=[Path(install_tmp)],
                repository_roots=[VOICE_APPS_REPOSITORY],
                repository_public_key=VOICE_APPS_PUBLIC_KEY,
            )

            response = manager.handle("install app truth or dare")

        self.assertIsNotNone(response)
        self.assertEqual(response.text, "Installed Truth or Dare version 0.1.0.")

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
        self.assertEqual(response.text, "App truth_or_dare is not installed.")

    def test_describe_app_uses_repository_metadata(self):
        with TemporaryDirectory() as store_tmp:
            source_dir = Path(store_tmp) / "source"
            source_dir.mkdir(parents=True, exist_ok=True)
            bundle = self.create_app_bundle(
                source_dir,
                description="Roll a single six-sided die locally.",
            )
            repository_dir = self.create_repository(Path(store_tmp) / "repo", {"dice": [bundle]})
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
                {"dice": [upgrade_bundle]},
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

    def test_list_app_versions_returns_all_versions_newest_first(self):
        with TemporaryDirectory() as store_tmp:
            source_dir = Path(store_tmp) / "source"
            source_dir.mkdir(parents=True, exist_ok=True)
            older_bundle = self.create_app_bundle(source_dir, version="0.1.0")
            newer_source_dir = Path(store_tmp) / "newer_source"
            newer_source_dir.mkdir(parents=True, exist_ok=True)
            newer_bundle = self.create_app_bundle(newer_source_dir, version="0.2.0")
            repository_dir = self.create_repository(
                Path(store_tmp) / "repo",
                {"dice": [older_bundle, newer_bundle]},
            )
            manager = AppManager(repository_roots=[repository_dir])

            response = manager.handle("list app versions dice")

        self.assertIsNotNone(response)
        self.assertEqual(response.text, "Available versions for Dice: 0.2.0, 0.1.0.")

    def test_list_app_versions_can_resolve_spoken_app_name(self):
        manager = AppManager(
            repository_roots=[VOICE_APPS_REPOSITORY],
            repository_public_key=VOICE_APPS_PUBLIC_KEY,
        )

        response = manager.handle("list app versions truth or dare")

        self.assertIsNotNone(response)
        self.assertEqual(response.text, "Available versions for Truth or Dare: 0.1.0.")

    def test_install_command_can_pin_repository_version(self):
        with TemporaryDirectory() as store_tmp, TemporaryDirectory() as install_tmp:
            source_dir = Path(store_tmp) / "source"
            source_dir.mkdir(parents=True, exist_ok=True)
            older_bundle = self.create_app_bundle(
                source_dir,
                version="0.1.0",
                response_text="rolled one",
            )
            newer_source_dir = Path(store_tmp) / "newer_source"
            newer_source_dir.mkdir(parents=True, exist_ok=True)
            newer_bundle = self.create_app_bundle(
                newer_source_dir,
                version="0.2.0",
                response_text="rolled two",
            )
            repository_dir = self.create_repository(
                Path(store_tmp) / "repo",
                {"dice": [older_bundle, newer_bundle]},
            )
            manager = AppManager(app_dirs=[Path(install_tmp)], repository_roots=[repository_dir])

            response = manager.handle("install app dice@0.1.0")
            roll = manager.handle("roll test die")

        self.assertIsNotNone(response)
        self.assertEqual(response.text, "Installed Dice version 0.1.0.")
        self.assertIsNotNone(roll)
        self.assertEqual(roll.text, "rolled one")

    def test_repository_file_paths_cannot_escape_staging_directory(self):
        with TemporaryDirectory() as store_tmp, TemporaryDirectory() as install_tmp:
            source_dir = Path(store_tmp) / "source"
            source_dir.mkdir(parents=True, exist_ok=True)
            bundle = self.create_app_bundle(source_dir)
            repository_dir = self.create_repository(Path(store_tmp) / "repo", {"dice": [bundle]})
            index_path = repository_dir / "index.json"
            index = json.loads(index_path.read_text(encoding="utf-8"))
            escape_name = f"escape-{Path(install_tmp).name}.txt"
            index["apps"][0]["versions"][0]["files"] = [f"../{escape_name}"]
            index_path.write_text(json.dumps(index), encoding="utf-8")

            manager = AppManager(app_dirs=[Path(install_tmp)], repository_roots=[repository_dir])
            response = manager.handle("install app dice")

            escaped_path = Path(install_tmp).parent / escape_name

        self.assertIsNotNone(response)
        self.assertIn("Invalid bundle file path", response.text)
        self.assertFalse(escaped_path.exists())

    def test_remote_repository_install_downloads_bundle(self):
        with TemporaryDirectory() as store_tmp, TemporaryDirectory() as install_tmp:
            source_dir = Path(store_tmp) / "source"
            source_dir.mkdir(parents=True, exist_ok=True)
            bundle = self.create_app_bundle(source_dir)
            repository_dir = self.create_repository(Path(store_tmp) / "repo", {"dice": [bundle]})

            with self.serve_directory(repository_dir) as base_url:
                manager = AppManager(
                    app_dirs=[Path(install_tmp)],
                    repository_roots=[base_url],
                    require_repository_signature=False,
                )
                response = manager.handle("install app dice")
                roll = manager.handle("roll test die")

        self.assertIsNotNone(response)
        self.assertEqual(response.text, "Installed Dice version 0.1.0.")
        self.assertIsNotNone(roll)
        self.assertEqual(roll.text, "rolled")

    def test_remote_repository_requires_signature_by_default(self):
        with TemporaryDirectory() as store_tmp:
            source_dir = Path(store_tmp) / "source"
            source_dir.mkdir(parents=True, exist_ok=True)
            bundle = self.create_app_bundle(source_dir)
            repository_dir = self.create_repository(Path(store_tmp) / "repo", {"dice": [bundle]})

            with self.serve_directory(repository_dir) as base_url:
                manager = AppManager(repository_roots=[base_url])
                response = manager.handle("list available apps")

        self.assertIsNotNone(response)
        self.assertEqual(response.text, "No app store entries are available.")
        self.assertEqual(manager.repositories, [])

    def test_remote_repository_signature_requirement_can_be_explicitly_disabled(self):
        with TemporaryDirectory() as store_tmp:
            source_dir = Path(store_tmp) / "source"
            source_dir.mkdir(parents=True, exist_ok=True)
            bundle = self.create_app_bundle(source_dir)
            repository_dir = self.create_repository(Path(store_tmp) / "repo", {"dice": [bundle]})

            with self.serve_directory(repository_dir) as base_url:
                manager = AppManager(
                    repository_roots=[base_url],
                    require_repository_signature=False,
                )
                response = manager.handle("list available apps")

        self.assertIsNotNone(response)
        self.assertEqual(response.text, "Available apps: Dice.")

    def test_launch_can_resolve_spoken_name_without_custom_trigger(self):
        with TemporaryDirectory() as install_tmp:
            manager = AppManager(
                app_dirs=[Path(install_tmp)],
                repository_roots=[VOICE_APPS_REPOSITORY],
                repository_public_key=VOICE_APPS_PUBLIC_KEY,
            )
            manager.handle("install app ask")

            response = manager.handle("start ask")

        self.assertIsNotNone(response)
        self.assertTrue(response.done)
        self.assertTrue(bool(response.text))

    def test_launch_can_resolve_fuzzy_spoken_name(self):
        with TemporaryDirectory() as install_tmp, TemporaryDirectory() as state_tmp:
            manager = AppManager(
                app_dirs=[Path(install_tmp)],
                repository_roots=[VOICE_APPS_REPOSITORY],
                repository_public_key=VOICE_APPS_PUBLIC_KEY,
                active_state_path=Path(state_tmp) / "active_app.json",
            )
            manager.handle("install app truth or dare")

            response = manager.handle("Start true or dare")

        self.assertIsNotNone(response)
        self.assertEqual(response.text, "Who is playing truth or dare?")
        self.assertTrue(response.expect_input)

    def test_classified_launch_intent_can_start_installed_app(self):
        with TemporaryDirectory() as install_tmp, TemporaryDirectory() as state_tmp:
            manager = AppManager(
                app_dirs=[Path(install_tmp)],
                repository_roots=[VOICE_APPS_REPOSITORY],
                repository_public_key=VOICE_APPS_PUBLIC_KEY,
                active_state_path=Path(state_tmp) / "active_app.json",
            )
            manager.handle("install app truth or dare")

            response = manager.handle_classified_intent(
                {
                    "intent": "launch_app",
                    "app_id": "truth_or_dare",
                    "version": None,
                    "raw_target": "true or dare",
                    "confidence": 0.81,
                },
                "Start true or dare",
            )

        self.assertIsNotNone(response)
        self.assertEqual(response.text, "Who is playing truth or dare?")
        self.assertTrue(response.expect_input)

    def test_signed_repository_can_be_required_and_persists_verified_metadata(self):
        with TemporaryDirectory() as store_tmp, TemporaryDirectory() as install_tmp:
            source_dir = Path(store_tmp) / "source"
            source_dir.mkdir(parents=True, exist_ok=True)
            bundle = self.create_app_bundle(source_dir)
            repository_dir = self.create_repository(Path(store_tmp) / "repo", {"dice": [bundle]})
            private_key = SigningKey.generate().encode(encoder=Base64Encoder).decode("utf-8")
            public_key = self.sign_repository(repository_dir, private_key)
            manager = AppManager(
                app_dirs=[Path(install_tmp)],
                repository_roots=[repository_dir],
                repository_public_key=public_key,
                require_repository_signature=True,
            )

            response = manager.handle("install app dice")
            metadata_path = Path(install_tmp) / "dice" / INSTALL_METADATA_FILENAME
            metadata = AppInstallMetadata.load(metadata_path)

        self.assertIsNotNone(response)
        self.assertEqual(response.text, "Installed Dice version 0.1.0.")
        self.assertIsNotNone(metadata)
        self.assertEqual(metadata.source_type, "repository")
        self.assertTrue(metadata.signature_verified)

    def test_invalid_required_signature_skips_repository(self):
        with TemporaryDirectory() as store_tmp:
            source_dir = Path(store_tmp) / "source"
            source_dir.mkdir(parents=True, exist_ok=True)
            bundle = self.create_app_bundle(source_dir)
            repository_dir = self.create_repository(Path(store_tmp) / "repo", {"dice": [bundle]})
            private_key = SigningKey.generate().encode(encoder=Base64Encoder).decode("utf-8")
            self.sign_repository(repository_dir, private_key)
            wrong_public_key = SigningKey.generate().verify_key.encode(encoder=Base64Encoder).decode("utf-8")
            manager = AppManager(
                repository_roots=[repository_dir],
                repository_public_key=wrong_public_key,
                require_repository_signature=True,
            )

            response = manager.handle("list available apps")

        self.assertIsNotNone(response)
        self.assertEqual(response.text, "No app store entries are available.")

    def test_checksum_mismatch_blocks_install(self):
        with TemporaryDirectory() as store_tmp, TemporaryDirectory() as install_tmp:
            source_dir = Path(store_tmp) / "source"
            source_dir.mkdir(parents=True, exist_ok=True)
            bundle = self.create_app_bundle(source_dir)
            repository_dir = self.create_repository(Path(store_tmp) / "repo", {"dice": [bundle]})
            index_path = repository_dir / "index.json"
            index_data = json.loads(index_path.read_text(encoding="utf-8"))
            index_data["apps"][0]["versions"][0]["sha256"] = "deadbeef"
            index_path.write_text(json.dumps(index_data), encoding="utf-8")
            manager = AppManager(app_dirs=[Path(install_tmp)], repository_roots=[repository_dir])

            response = manager.handle("install app dice")

        self.assertIsNotNone(response)
        self.assertIn("Bundle checksum mismatch", response.text)


if __name__ == "__main__":
    unittest.main()
