"""Base interfaces for local voice apps."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from ..app_install import AppInstallMetadata
    from ..app_manifest import AppManifest


@dataclass
class AppResponse:
    """Structured app response returned to the main assistant loop."""

    text: str
    done: bool = False
    expect_input: bool = False
    state: Dict[str, str] = field(default_factory=dict)


class VoiceApp(ABC):
    """Small stateful app that can own the next user turns."""

    id: str = ""
    name: str = ""
    description: str = ""
    triggers: List[str] = []
    manifest: Optional["AppManifest"] = None
    install_dir: Optional[Path] = None
    install_metadata: Optional["AppInstallMetadata"] = None
    is_builtin: bool = True

    def matches(self, text: str) -> bool:
        lowered = text.lower()
        return any(trigger in lowered for trigger in self.triggers)

    @abstractmethod
    def start(self, text: str) -> AppResponse:
        """Start a new app session."""

    @abstractmethod
    def handle(self, text: str) -> AppResponse:
        """Handle a follow-up utterance for an active app."""

    def stop(self) -> None:
        """Reset any local app state on exit."""

    def serialize_state(self) -> Dict[str, Any]:
        """Return persistent state for restart recovery."""
        return {}

    def restore_state(self, state: Dict[str, Any]) -> None:
        """Restore previously persisted state."""
