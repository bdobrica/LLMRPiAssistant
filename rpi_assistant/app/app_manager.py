"""Voice app routing and lifecycle management."""

from typing import List, Optional

from .apps.ask_estonia import AskEstoniaApp
from .apps.base import AppResponse, VoiceApp
from .apps.truth_or_dare import TruthOrDareApp


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

    def __init__(self, apps: Optional[List[VoiceApp]] = None):
        self.apps = apps if apps is not None else self._default_apps()
        self.active_app: Optional[VoiceApp] = None

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

    def _default_apps(self) -> List[VoiceApp]:
        return [
            TruthOrDareApp(),
            AskEstoniaApp(),
        ]

    def _is_cancel_command(self, text: str) -> bool:
        lowered = text.lower()
        return any(trigger in lowered for trigger in self.CANCEL_TRIGGERS)
