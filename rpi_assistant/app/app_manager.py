"""Voice app routing and lifecycle management."""

import re
from pathlib import Path
from typing import List, Optional, Sequence

from .app_loader import DEFAULT_EXTERNAL_APP_DIRS, discover_apps, load_external_app_bundle
from .app_manifest import AppManifest
from .app_store import install_app_bundle, uninstall_app_bundle
from .apps.base import AppResponse, VoiceApp


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
    UNINSTALL_PATTERN = re.compile(
        r"^(?:uninstall|remove|delete)\s+app\s+(?P<app_id>[a-zA-Z0-9_-]+)$",
        re.IGNORECASE,
    )
    LIST_PATTERNS = (
        "list apps",
        "list installed apps",
        "what apps are installed",
        "what app is installed",
    )

    def __init__(
        self,
        apps: Optional[List[VoiceApp]] = None,
        app_dirs: Optional[Sequence[Path]] = None,
    ):
        self.app_dirs = list(app_dirs) if app_dirs is not None else list(DEFAULT_EXTERNAL_APP_DIRS)
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
                    self.active_app.stop()
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

        if any(existing.id == manifest.id for existing in self.apps):
            raise ValueError(f"App id is already registered: {manifest.id}")

        destination_dir = install_app_bundle(source_dir, self.app_dirs[0])

        try:
            app = load_external_app_bundle(destination_dir)
            self.register_app(app)
        except Exception:
            uninstall_app_bundle(manifest.id, self.app_dirs)
            raise

        return manifest

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

    def _find_app(self, app_id: str) -> Optional[VoiceApp]:
        for app in self.apps:
            if app.id == app_id:
                return app
        return None

    def _handle_management_command(self, text: str) -> Optional[AppResponse]:
        normalized = text.strip()
        lowered = normalized.lower()

        if lowered in self.LIST_PATTERNS:
            app_names = sorted(app.name for app in self.list_apps())
            return AppResponse(text=f"Installed apps: {', '.join(app_names)}.", done=True)

        install_match = self.INSTALL_PATTERN.match(normalized)
        if install_match:
            source = install_match.group("source").strip().strip("\"'")
            try:
                manifest = self.install_app(Path(source))
            except Exception as exc:
                return AppResponse(text=f"Could not install app: {exc}", done=True)

            return AppResponse(text=f"Installed {manifest.name}.", done=True)

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

        return None

    def _is_cancel_command(self, text: str) -> bool:
        lowered = text.lower()
        return any(trigger in lowered for trigger in self.CANCEL_TRIGGERS)
