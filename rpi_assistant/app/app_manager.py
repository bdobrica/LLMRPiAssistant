"""Voice app routing and lifecycle management."""

import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from rpi_assistant.app.app_install import AppInstallMetadata
from rpi_assistant.app.app_loader import (
    DEFAULT_EXTERNAL_APP_DIRS,
    discover_apps,
    load_external_app_bundle,
)
from rpi_assistant.app.app_manifest import AppManifest
from rpi_assistant.app.app_repository import (
    DEFAULT_APP_REPOSITORY_ROOTS,
    AppRepository,
    RepositoryRelease,
    load_default_repository_public_key,
)
from rpi_assistant.app.app_state import ActiveAppState, DEFAULT_ACTIVE_APP_STATE_PATH
from rpi_assistant.app.app_store import (
    find_installed_app_bundle,
    install_app_bundle,
    stage_app_bundle,
    uninstall_app_bundle,
)
from rpi_assistant.app.apps.base import AppResponse, VoiceApp
from rpi_assistant.app.intent_detector import (
    DetectedIntent,
    IntentDetector,
    manifest_aliases,
    normalize_text,
)


class AppManager:
    """Routes transcriptions to local voice apps before OpenAI fallback."""

    CANCEL_TRIGGERS = (
        "stop game",
        "cancel app",
        "cancel game",
        "nevermind",
        "never mind",
        "stop app",
    )

    def __init__(
        self,
        apps: Optional[List[VoiceApp]] = None,
        app_dirs: Optional[Sequence[Path]] = None,
        repository_roots: Optional[Sequence[str | Path]] = None,
        repository_public_key: str = "",
        require_repository_signature: bool = False,
        active_state_path: Optional[Path] = None,
    ):
        self.app_dirs = list(app_dirs) if app_dirs is not None else list(DEFAULT_EXTERNAL_APP_DIRS)
        self.repository_roots = (
            list(repository_roots)
            if repository_roots is not None
            else list(DEFAULT_APP_REPOSITORY_ROOTS)
        )
        self.repository_public_key = repository_public_key or load_default_repository_public_key()
        self.require_repository_signature = require_repository_signature
        self.active_state_path = active_state_path or DEFAULT_ACTIVE_APP_STATE_PATH
        self.repository_load_errors: List[tuple[str, str]] = []
        self.repositories = self._load_repositories()
        self.apps: List[VoiceApp] = []
        self.active_app: Optional[VoiceApp] = None

        if apps is not None:
            for app in apps:
                self.register_app(app)
        else:
            for app in discover_apps(app_dirs=self.app_dirs):
                self.register_app(app)

        self._restore_active_app()

    def handle(self, text: str) -> Optional[AppResponse]:
        """Route text to the active app or start a matching app."""
        if self._is_cancel_command(text):
            return self.cancel()

        detector = IntentDetector(self.apps, self.repositories)

        management_intent = detector.detect_management_intent(text)
        if management_intent is not None:
            return self._handle_detected_intent(management_intent)

        if self.active_app is not None:
            response = self.active_app.handle(text)
            if response.done:
                self.active_app.stop()
                self.active_app = None
                self._clear_active_app_state()
            else:
                self._persist_active_app_state()
            return response

        launch_app = detector.detect_launch_app(text)
        if launch_app is not None:
            self.active_app = launch_app
            response = launch_app.start(text)
            if response.done:
                active_app = self.active_app
                if active_app is not None:
                    active_app.stop()
                self.active_app = None
                self._clear_active_app_state()
            else:
                self._persist_active_app_state()
            return response

        for app in self.apps:
            if app.matches(text):
                self.active_app = app
                response = app.start(text)
                if response.done:
                    active_app = self.active_app
                    if active_app is not None:
                        active_app.stop()
                    self.active_app = None
                    self._clear_active_app_state()
                else:
                    self._persist_active_app_state()
                return response

        return None

    def app_intent_context(self) -> Dict[str, Any]:
        """Return the compact app catalog used by LLM intent classification."""
        available_apps = []
        for repository in self.repositories:
            for release in repository.list():
                available_apps.append(
                    {
                        "id": release.manifest.id,
                        "name": release.manifest.name,
                        "triggers": release.manifest.triggers,
                    }
                )

        installed_apps = [
            {
                "id": app.id,
                "name": app.name,
                "triggers": app.triggers,
            }
            for app in self.apps
        ]

        return {
            "installed_apps": sorted(installed_apps, key=lambda entry: entry["id"]),
            "available_apps": sorted(
                {entry["id"]: entry for entry in available_apps}.values(),
                key=lambda entry: entry["id"],
            ),
            "active_app": None
            if self.active_app is None
            else {"id": self.active_app.id, "name": self.active_app.name},
        }

    def should_classify_app_intent(self, text: str) -> bool:
        """Return whether an LLM app-intent pass is worth attempting."""
        normalized = normalize_text(text)
        app_words = {
            "app",
            "apps",
            "store",
            "install",
            "add",
            "uninstall",
            "remove",
            "delete",
            "upgrade",
            "update",
            "version",
            "versions",
            "available",
            "installed",
            "launch",
            "start",
            "play",
            "open",
            "resume",
            "continue",
            "active",
            "cancel",
        }
        if any(relevant_word in normalized.split() for relevant_word in app_words):
            return True

        for alias in self._all_app_aliases():
            if alias and alias in normalized:
                return True

        return False

    def handle_classified_intent(
        self,
        classified_intent: Dict[str, Any],
        original_text: str,
    ) -> Optional[AppResponse]:
        """Execute a strict app intent produced by the LLM classifier."""
        intent_name = str(classified_intent.get("intent", "")).strip().lower()
        confidence = _float_or_zero(classified_intent.get("confidence", 0))
        if not intent_name or intent_name == "none" or confidence < 0.55:
            return None

        if intent_name == "cancel":
            return self.cancel()

        if intent_name == "launch_app":
            app_id = str(classified_intent.get("app_id", "")).strip()
            app = self._find_app(app_id)
            if app is None:
                return None

            self.active_app = app
            response = app.start(original_text)
            if response.done:
                app.stop()
                self.active_app = None
                self._clear_active_app_state()
            else:
                self._persist_active_app_state()
            return response

        intent = DetectedIntent(
            name=intent_name,
            raw_target=str(classified_intent.get("raw_target", "")).strip(),
            app_id=_optional_str(classified_intent.get("app_id")),
            version=_optional_str(classified_intent.get("version")),
        )
        return self._handle_detected_intent(intent)

    def cancel(self) -> Optional[AppResponse]:
        """Cancel the active app, if any."""
        if self.active_app is None:
            return None

        app_name = self.active_app.name
        self.active_app.stop()
        self.active_app = None
        self._clear_active_app_state()
        return AppResponse(text=f"Stopped {app_name}.", done=True)

    def register_app(self, app: VoiceApp) -> None:
        """Register an app instance with uniqueness enforced by id."""
        if any(existing.id == app.id for existing in self.apps):
            raise ValueError(f"App id is already registered: {app.id}")
        self.apps.append(app)

    def unregister_app(self, app_id: str) -> Optional[VoiceApp]:
        """Remove a registered app and stop it if it is active."""
        for index, app in enumerate(self.apps):
            if app.id != app_id:
                continue

            if self.active_app is app:
                app.stop()
                self.active_app = None
                self._clear_active_app_state()

            return self.apps.pop(index)

        return None

    def list_apps(self) -> List[VoiceApp]:
        """Return a shallow copy of the registered apps."""
        return list(self.apps)

    def install_app(
        self,
        source_dir: Path,
        install_metadata: Optional[AppInstallMetadata] = None,
    ) -> AppManifest:
        """Install an external app bundle and register it immediately."""
        source_dir = source_dir.expanduser().resolve()
        manifest = AppManifest.load(source_dir / "manifest.json")
        metadata = install_metadata or AppInstallMetadata(
            source_type="path",
            source=str(source_dir),
            requested_target=str(source_dir),
            installed_version=manifest.version,
        )

        existing_app = self._find_app(manifest.id)
        if existing_app is None:
            destination_dir = install_app_bundle(source_dir, self.app_dirs[0])
            metadata.write(destination_dir)

            try:
                app = load_external_app_bundle(destination_dir)
                self.register_app(app)
            except Exception:
                uninstall_app_bundle(manifest.id, self.app_dirs)
                raise

            return manifest

        if existing_app.is_builtin:
            raise ValueError(f"Cannot replace built-in app {existing_app.name}.")

        existing_manifest = existing_app.manifest
        if existing_manifest is None:
            raise ValueError(f"Installed app {existing_app.name} has no manifest metadata.")

        if manifest.compare_version(existing_manifest) <= 0:
            raise ValueError(
                f"App {manifest.name} version {existing_manifest.version} is already installed."
            )

        self._upgrade_from_source(source_dir, manifest, metadata)
        return manifest

    def install_store_app(self, app_id: str, version: Optional[str] = None) -> AppManifest:
        """Install an app bundle from the configured repository catalog."""
        repository_release = self._find_repository_release(app_id, version)
        if repository_release is None:
            raise FileNotFoundError(f"App {app_id} was not found in the app store.")

        staged_dir = repository_release.materialize(self.app_dirs[0])
        metadata = AppInstallMetadata(
            source_type="repository",
            source=str(repository_release.repository_root),
            requested_target=f"{app_id}@{version}" if version else app_id,
            installed_version=repository_release.manifest.version,
            repository_root=str(repository_release.repository_root),
            bundle_ref=repository_release.bundle_ref,
            sha256=repository_release.sha256,
            signature_verified=repository_release.signature_verified,
        )
        try:
            return self.install_app(staged_dir, install_metadata=metadata)
        finally:
            if staged_dir.exists():
                shutil.rmtree(staged_dir)

    def uninstall_app(self, app_id: str) -> Optional[AppManifest]:
        """Uninstall an external app bundle and unregister it."""
        app = self._find_app(app_id)
        if app is not None and app.is_builtin:
            raise ValueError(f"Cannot uninstall built-in app {app.name}.")

        manifest = uninstall_app_bundle(app_id, self.app_dirs)
        if manifest is None:
            return None

        self.unregister_app(app_id)
        return manifest

    def upgrade_app(self, app_id: str) -> AppManifest:
        """Upgrade an installed external app from the configured repository catalog."""
        installed_app = self._find_app(app_id)
        if installed_app is None:
            raise ValueError(f"App {app_id} is not installed.")
        if installed_app.is_builtin:
            raise ValueError(f"Cannot upgrade built-in app {installed_app.name}.")

        repository_release = self._find_repository_release(app_id)
        if repository_release is None:
            raise FileNotFoundError(f"App {app_id} was not found in the app store.")

        installed_manifest = installed_app.manifest
        if installed_manifest is None:
            raise ValueError(f"Installed app {installed_app.name} has no manifest metadata.")
        if repository_release.manifest.compare_version(installed_manifest) <= 0:
            raise ValueError(f"App {installed_app.name} is already up to date.")

        staged_dir = repository_release.materialize(self.app_dirs[0])
        metadata = AppInstallMetadata(
            source_type="repository",
            source=str(repository_release.repository_root),
            requested_target=app_id,
            installed_version=repository_release.manifest.version,
            repository_root=str(repository_release.repository_root),
            bundle_ref=repository_release.bundle_ref,
            sha256=repository_release.sha256,
            signature_verified=repository_release.signature_verified,
        )
        try:
            self._upgrade_from_source(staged_dir, repository_release.manifest, metadata)
        finally:
            if staged_dir.exists():
                shutil.rmtree(staged_dir)

        return repository_release.manifest

    def describe_app(self, app_id: str) -> str:
        """Return a description of one installed or catalog app."""
        installed_app = self._find_app(app_id)
        repository_release = self._find_repository_release(app_id)

        if installed_app is None and repository_release is None:
            raise FileNotFoundError(f"App {app_id} was not found.")

        if installed_app is not None:
            manifest = installed_app.manifest
            description = manifest.description if manifest else installed_app.description
            version = manifest.version if manifest else "built-in"
            status = "installed"
            name = installed_app.name
            triggers = installed_app.triggers
            install_metadata = installed_app.install_metadata
        else:
            if repository_release is None:
                raise FileNotFoundError(f"App {app_id} was not found.")
            manifest = repository_release.manifest
            description = manifest.description
            version = manifest.version
            status = "available"
            name = manifest.name
            triggers = manifest.triggers
            install_metadata = None

        trigger_text = ", ".join(triggers) if triggers else "none"
        response = (
            f"{name}. Version: {version}. Status: {status}. "
            f"Description: {description or 'No description provided.'} "
            f"Triggers: {trigger_text}."
        )

        if install_metadata is not None:
            response = f"{response} {self._describe_install_source(install_metadata)}"

        return response

    def list_app_versions(self, app_id: str) -> str:
        """Return the available repository versions for one app."""
        releases: List[RepositoryRelease] = []
        for repository in self.repositories:
            releases.extend(repository.list_versions(app_id))

        if not releases:
            raise FileNotFoundError(f"App {app_id} was not found in the app store.")

        versions = []
        app_name = releases[0].manifest.name
        for release in releases:
            version = release.manifest.version
            if version not in versions:
                versions.append(version)

        return f"Available versions for {app_name}: {', '.join(versions)}."

    def describe_active_app(self) -> str:
        """Return a short spoken description of the currently active app."""
        if self.active_app is None:
            return "No app is active."
        return self.active_app.status_text()

    def resume_active_app(self) -> AppResponse:
        """Return the resume prompt for the currently active app."""
        if self.active_app is None:
            return AppResponse(text="No app is active.", done=True)

        response = self.active_app.resume()
        if response.done:
            self.active_app.stop()
            self.active_app = None
            self._clear_active_app_state()
        else:
            self._persist_active_app_state()
        return response

    def app_store_health(self) -> str:
        """Return a spoken summary of app-store readiness and repository loading."""
        configured_roots = [str(root) for root in self.repository_roots]
        loaded_roots = [str(repository.root) for repository in self.repositories]
        signature_mode = "enabled" if self.require_repository_signature else "optional"

        response = (
            f"App store: {len(self.repositories)} of {len(configured_roots)} repositories loaded. "
            f"Signature verification is {signature_mode}."
        )

        if loaded_roots:
            response += f" Loaded repositories: {', '.join(loaded_roots)}."

        if self.repository_load_errors:
            failed_roots = ", ".join(root for root, _ in self.repository_load_errors)
            response += f" Failed repositories: {failed_roots}."

        return response

    def _handle_detected_intent(self, intent: DetectedIntent) -> Optional[AppResponse]:
        if intent.name == "list_installed":
            app_names = sorted(app.name for app in self.list_apps())
            if not app_names:
                return AppResponse(text="No apps are installed.", done=True)
            return AppResponse(text=f"Installed apps: {', '.join(app_names)}.", done=True)

        if intent.name == "list_available":
            repository_apps = []
            for repository in self.repositories:
                repository_apps.extend(repository.list())
            names = sorted({entry.manifest.name for entry in repository_apps})
            if not names:
                return AppResponse(text="No app store entries are available.", done=True)
            return AppResponse(text=f"Available apps: {', '.join(names)}.", done=True)

        if intent.name == "resume_active":
            return self.resume_active_app()

        if intent.name == "active_status":
            return AppResponse(text=self.describe_active_app(), done=True)

        if intent.name == "app_store_health":
            return AppResponse(text=self.app_store_health(), done=True)

        if intent.name == "install_app":
            try:
                if self._looks_like_path(intent.raw_target):
                    manifest = self.install_app(Path(intent.raw_target))
                else:
                    manifest = self.install_store_app(intent.app_id or intent.raw_target, version=intent.version)
            except Exception as exc:
                return AppResponse(text=f"Could not install app: {exc}", done=True)

            existing_app = self._find_app(manifest.id)
            if existing_app is not None and existing_app.manifest is not None:
                return AppResponse(
                    text=f"Installed {manifest.name} version {existing_app.manifest.version}.",
                    done=True,
                )
            return AppResponse(text=f"Installed {manifest.name}.", done=True)

        if intent.name == "upgrade_app":
            app_target = intent.app_id or intent.raw_target
            try:
                manifest = self.upgrade_app(app_target)
            except Exception as exc:
                return AppResponse(text=str(exc), done=True)
            return AppResponse(text=f"Upgraded {manifest.name} to {manifest.version}.", done=True)

        if intent.name == "uninstall_app":
            app_target = intent.app_id or intent.raw_target
            try:
                manifest = self.uninstall_app(app_target)
            except Exception as exc:
                return AppResponse(text=str(exc), done=True)
            if manifest is None:
                return AppResponse(text=f"App {app_target} is not installed.", done=True)
            return AppResponse(text=f"Uninstalled {manifest.name}.", done=True)

        if intent.name == "describe_app":
            app_target = intent.app_id or intent.raw_target
            try:
                description = self.describe_app(app_target)
            except Exception as exc:
                return AppResponse(text=str(exc), done=True)
            return AppResponse(text=description, done=True)

        if intent.name == "list_versions":
            app_target = intent.app_id or intent.raw_target
            try:
                version_text = self.list_app_versions(app_target)
            except Exception as exc:
                return AppResponse(text=str(exc), done=True)
            return AppResponse(text=version_text, done=True)

        return None

    def _find_app(self, app_id: str) -> Optional[VoiceApp]:
        for app in self.apps:
            if app.id == app_id:
                return app
        return None

    def _find_repository_release(
        self,
        app_id: str,
        version: Optional[str] = None,
    ) -> Optional[RepositoryRelease]:
        for repository in self.repositories:
            repository_release = repository.get(app_id, version=version)
            if repository_release is not None:
                return repository_release
        return None

    def _all_app_aliases(self) -> List[str]:
        aliases = []
        for app in self.apps:
            manifest = app.manifest
            if manifest is None:
                aliases.extend(manifest_aliases(app.id, app.name, app.triggers))
            else:
                aliases.extend(
                    manifest_aliases(manifest.id, manifest.name, manifest.triggers)
                )

        for repository in self.repositories:
            for release in repository.list():
                aliases.extend(
                    manifest_aliases(
                        release.manifest.id,
                        release.manifest.name,
                        release.manifest.triggers,
                    )
                )

        return sorted(set(aliases), key=len, reverse=True)

    def _upgrade_from_source(
        self,
        source_dir: Path,
        manifest: AppManifest,
        install_metadata: AppInstallMetadata,
    ) -> None:
        existing_bundle_dir, _ = find_installed_app_bundle(manifest.id, self.app_dirs)
        if existing_bundle_dir is None:
            raise FileNotFoundError(f"Installed app bundle for {manifest.id} was not found.")

        staged_dir = stage_app_bundle(source_dir, self.app_dirs[0])
        try:
            install_metadata.write(staged_dir)
            upgraded_app = load_external_app_bundle(staged_dir)
            existing_app = self.unregister_app(manifest.id)
            if existing_app is not None and self.active_app is existing_app:
                self.active_app = None

            shutil.rmtree(existing_bundle_dir)
            final_dir = self.app_dirs[0] / manifest.id
            if final_dir.exists():
                shutil.rmtree(final_dir)
            shutil.copytree(staged_dir, final_dir)
            shutil.rmtree(staged_dir)
            upgraded_app.install_dir = final_dir
            upgraded_app.manifest = manifest
            upgraded_app.is_builtin = False
            self.register_app(upgraded_app)
        except Exception:
            if staged_dir.exists():
                shutil.rmtree(staged_dir)
            raise

    def _load_repositories(self) -> List[AppRepository]:
        repositories: List[AppRepository] = []
        for root in self.repository_roots:
            try:
                repository = AppRepository.load(
                    root,
                    trusted_public_key=self.repository_public_key,
                    require_signature=self.require_repository_signature,
                )
            except Exception as exc:
                self.repository_load_errors.append((str(root), str(exc)))
                print(f"⚠️  Could not load app store repository {root}: {exc}")
                continue

            if repository is not None:
                repositories.append(repository)
        return repositories

    def _describe_install_source(
        self,
        install_metadata: Optional[AppInstallMetadata],
    ) -> str:
        if install_metadata is None:
            return "Installed from: built-in or unknown source."

        if install_metadata.source_type == "repository":
            signature_text = "verified" if install_metadata.signature_verified else "not verified"
            return (
                f"Installed from repository {install_metadata.repository_root} "
                f"as {install_metadata.requested_target}; signature {signature_text}."
            )

        return f"Installed from path {install_metadata.source}."

    def _persist_active_app_state(self) -> None:
        if self.active_app is None:
            self._clear_active_app_state()
            return

        ActiveAppState(
            app_id=self.active_app.id,
            state=self.active_app.serialize_state(),
        ).write(self.active_state_path)

    def _restore_active_app(self) -> None:
        persisted_state = ActiveAppState.load(self.active_state_path)
        if persisted_state is None or not persisted_state.app_id:
            return

        app = self._find_app(persisted_state.app_id)
        if app is None:
            self._clear_active_app_state()
            return

        app.restore_state(persisted_state.state)
        self.active_app = app

    def _clear_active_app_state(self) -> None:
        if self.active_state_path.exists():
            self.active_state_path.unlink()

    def _looks_like_path(self, target: str) -> bool:
        return (
            "/" in target
            or target.startswith(".")
            or target.startswith("~")
            or Path(target).exists()
        )

    def _is_cancel_command(self, text: str) -> bool:
        lowered = text.lower()
        return any(trigger in lowered for trigger in self.CANCEL_TRIGGERS)


def _optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _float_or_zero(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
