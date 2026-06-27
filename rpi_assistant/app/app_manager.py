"""Voice app routing and lifecycle management."""

import re
import shutil
from pathlib import Path
from typing import List, Optional, Sequence

from rpi_assistant.app.app_loader import (
    DEFAULT_EXTERNAL_APP_DIRS,
    discover_apps,
    load_external_app_bundle,
)
from rpi_assistant.app.app_manifest import AppManifest
from rpi_assistant.app.app_repository import (
    DEFAULT_APP_REPOSITORY_ROOTS,
    RepositoryApp,
    load_app_repositories,
)
from rpi_assistant.app.app_store import (
    find_installed_app_bundle,
    install_app_bundle,
    stage_app_bundle,
    uninstall_app_bundle,
)
from rpi_assistant.app.apps.base import AppResponse, VoiceApp


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
    INSTALL_PATTERN = re.compile(r"^(?:install|add)\s+app(?:\s+from)?\s+(?P<source>.+)$", re.IGNORECASE)
    UPGRADE_PATTERN = re.compile(r"^(?:upgrade|update)\s+app\s+(?P<app_id>[a-zA-Z0-9_-]+)$", re.IGNORECASE)
    UNINSTALL_PATTERN = re.compile(
        r"^(?:uninstall|remove|delete)\s+app\s+(?P<app_id>[a-zA-Z0-9_-]+)$",
        re.IGNORECASE,
    )
    DESCRIBE_PATTERN = re.compile(r"^(?:describe|show)\s+app\s+(?P<app_id>[a-zA-Z0-9_-]+)$", re.IGNORECASE)
    LIST_PATTERNS = (
        "list apps",
        "list installed apps",
        "what apps are installed",
        "what app is installed",
    )
    LIST_AVAILABLE_PATTERNS = (
        "list available apps",
        "list store apps",
        "what apps are available",
    )

    def __init__(
        self,
        apps: Optional[List[VoiceApp]] = None,
        app_dirs: Optional[Sequence[Path]] = None,
        repository_roots: Optional[Sequence[Path]] = None,
    ):
        self.app_dirs = list(app_dirs) if app_dirs is not None else list(DEFAULT_EXTERNAL_APP_DIRS)
        self.repository_roots = (
            list(repository_roots)
            if repository_roots is not None
            else list(DEFAULT_APP_REPOSITORY_ROOTS)
        )
        self.repositories = load_app_repositories(self.repository_roots)
        self.apps: List[VoiceApp] = []
        self.active_app: Optional[VoiceApp] = None

        if apps is not None:
            for app in apps:
                self.register_app(app)
        else:
            for app in discover_apps(app_dirs=self.app_dirs):
                self.register_app(app)

    def handle(self, text: str) -> Optional[AppResponse]:
        """Route text to the active app or start a matching app."""
        if self._is_cancel_command(text):
            return self.cancel()

        if self.active_app is not None:
            response = self.active_app.handle(text)
            if response.done:
                self.active_app.stop()
                self.active_app = None
            return response

        management_response = self._handle_management_command(text)
        if management_response is not None:
            return management_response

        for app in self.apps:
            if app.matches(text):
                self.active_app = app
                response = app.start(text)
                if response.done:
                    active_app = self.active_app
                    if active_app is not None:
                        active_app.stop()
                    self.active_app = None
                return response

        return None

    def cancel(self) -> Optional[AppResponse]:
        """Cancel the active app, if any."""
        if self.active_app is None:
            return None

        app_name = self.active_app.name
        self.active_app.stop()
        self.active_app = None
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

            return self.apps.pop(index)

        return None

    def list_apps(self) -> List[VoiceApp]:
        """Return a shallow copy of the registered apps."""
        return list(self.apps)

    def install_app(self, source_dir: Path) -> AppManifest:
        """Install an external app bundle and register it immediately."""
        source_dir = source_dir.expanduser().resolve()
        manifest = AppManifest.load(source_dir / "manifest.json")

        existing_app = self._find_app(manifest.id)
        if existing_app is None:
            destination_dir = install_app_bundle(source_dir, self.app_dirs[0])

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

        self._upgrade_from_source(source_dir, manifest)
        return manifest

    def install_store_app(self, app_id: str) -> AppManifest:
        """Install an app bundle from the configured repository catalog."""
        repository_app = self._find_repository_app(app_id)
        if repository_app is None:
            raise FileNotFoundError(f"App {app_id} was not found in the app store.")
        return self.install_app(repository_app.bundle_dir)

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

        repository_app = self._find_repository_app(app_id)
        if repository_app is None:
            raise FileNotFoundError(f"App {app_id} was not found in the app store.")

        installed_manifest = installed_app.manifest
        if installed_manifest is None:
            raise ValueError(f"Installed app {installed_app.name} has no manifest metadata.")
        if repository_app.manifest.compare_version(installed_manifest) <= 0:
            raise ValueError(f"App {installed_app.name} is already up to date.")

        self._upgrade_from_source(repository_app.bundle_dir, repository_app.manifest)
        return repository_app.manifest

    def describe_app(self, app_id: str) -> str:
        """Return a description of one installed or catalog app."""
        installed_app = self._find_app(app_id)
        repository_app = self._find_repository_app(app_id)

        if installed_app is None and repository_app is None:
            raise FileNotFoundError(f"App {app_id} was not found.")

        if installed_app is not None:
            manifest = installed_app.manifest
            description = manifest.description if manifest else installed_app.description
            version = manifest.version if manifest else "built-in"
            status = "installed"
            name = installed_app.name
            triggers = installed_app.triggers
        else:
            if repository_app is None:
                raise FileNotFoundError(f"App {app_id} was not found.")
            manifest = repository_app.manifest
            description = manifest.description
            version = manifest.version
            status = "available"
            name = manifest.name
            triggers = manifest.triggers

        trigger_text = ", ".join(triggers) if triggers else "none"
        return (
            f"{name}. Version: {version}. Status: {status}. "
            f"Description: {description or 'No description provided.'} "
            f"Triggers: {trigger_text}."
        )

    def _find_app(self, app_id: str) -> Optional[VoiceApp]:
        for app in self.apps:
            if app.id == app_id:
                return app
        return None

    def _find_repository_app(self, app_id: str) -> Optional[RepositoryApp]:
        for repository in self.repositories:
            repository_app = repository.get(app_id)
            if repository_app is not None:
                return repository_app
        return None

    def _upgrade_from_source(self, source_dir: Path, manifest: AppManifest) -> None:
        existing_bundle_dir, _ = find_installed_app_bundle(manifest.id, self.app_dirs)
        if existing_bundle_dir is None:
            raise FileNotFoundError(f"Installed app bundle for {manifest.id} was not found.")

        staged_dir = stage_app_bundle(source_dir, self.app_dirs[0])
        try:
            upgraded_app = load_external_app_bundle(staged_dir)
            existing_app = self.unregister_app(manifest.id)
            if existing_app is not None and self.active_app is existing_app:
                self.active_app = None

            shutil.rmtree(existing_bundle_dir)
            final_dir = self.app_dirs[0] / manifest.id
            staged_dir.rename(final_dir)
            upgraded_app.install_dir = final_dir
            upgraded_app.manifest = manifest
            upgraded_app.is_builtin = False
            self.register_app(upgraded_app)
        except Exception:
            if staged_dir.exists():
                shutil.rmtree(staged_dir)
            raise

    def _looks_like_path(self, target: str) -> bool:
        return (
            "/" in target
            or target.startswith(".")
            or target.startswith("~")
            or Path(target).exists()
        )

    def _handle_management_command(self, text: str) -> Optional[AppResponse]:
        normalized = text.strip()
        lowered = normalized.lower()

        if lowered in self.LIST_PATTERNS:
            app_names = sorted(app.name for app in self.list_apps())
            return AppResponse(text=f"Installed apps: {', '.join(app_names)}.", done=True)

        if lowered in self.LIST_AVAILABLE_PATTERNS:
            repository_apps = []
            for repository in self.repositories:
                repository_apps.extend(repository.list())
            names = sorted({entry.manifest.name for entry in repository_apps})
            if not names:
                return AppResponse(text="No app store entries are available.", done=True)
            return AppResponse(text=f"Available apps: {', '.join(names)}.", done=True)

        install_match = self.INSTALL_PATTERN.match(normalized)
        if install_match:
            source = install_match.group("source").strip().strip("\"'")
            try:
                if self._looks_like_path(source):
                    manifest = self.install_app(Path(source))
                else:
                    manifest = self.install_store_app(source)
            except Exception as exc:
                return AppResponse(text=f"Could not install app: {exc}", done=True)

            existing_app = self._find_app(manifest.id)
            if existing_app is not None and existing_app.manifest is not None:
                return AppResponse(
                    text=f"Installed {manifest.name} version {existing_app.manifest.version}.",
                    done=True,
                )
            return AppResponse(text=f"Installed {manifest.name}.", done=True)

        upgrade_match = self.UPGRADE_PATTERN.match(normalized)
        if upgrade_match:
            app_id = upgrade_match.group("app_id")
            try:
                manifest = self.upgrade_app(app_id)
            except Exception as exc:
                return AppResponse(text=str(exc), done=True)

            return AppResponse(text=f"Upgraded {manifest.name} to {manifest.version}.", done=True)

        uninstall_match = self.UNINSTALL_PATTERN.match(normalized)
        if uninstall_match:
            app_id = uninstall_match.group("app_id")
            try:
                manifest = self.uninstall_app(app_id)
            except Exception as exc:
                return AppResponse(text=str(exc), done=True)

            if manifest is None:
                return AppResponse(text=f"App {app_id} is not installed.", done=True)

            return AppResponse(text=f"Uninstalled {manifest.name}.", done=True)

        describe_match = self.DESCRIBE_PATTERN.match(normalized)
        if describe_match:
            app_id = describe_match.group("app_id")
            try:
                description = self.describe_app(app_id)
            except Exception as exc:
                return AppResponse(text=str(exc), done=True)

            return AppResponse(text=description, done=True)

        return None

    def _is_cancel_command(self, text: str) -> bool:
        lowered = text.lower()
        return any(trigger in lowered for trigger in self.CANCEL_TRIGGERS)
