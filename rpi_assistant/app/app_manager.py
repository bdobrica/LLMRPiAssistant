"""Voice app routing and lifecycle management."""

from pathlib import Path
from typing import List, Optional, Sequence

from .app_loader import discover_apps
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

    def __init__(
        self,
        apps: Optional[List[VoiceApp]] = None,
        app_dirs: Optional[Sequence[Path]] = None,
    ):
        self.apps: List[VoiceApp] = []
        self.active_app: Optional[VoiceApp] = None

        if apps is not None:
            for app in apps:
                self.register_app(app)
        else:
            for app in discover_apps(app_dirs=app_dirs):
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

    def _is_cancel_command(self, text: str) -> bool:
        lowered = text.lower()
        return any(trigger in lowered for trigger in self.CANCEL_TRIGGERS)
