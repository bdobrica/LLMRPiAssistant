"""Base interfaces for local voice apps."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List


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
    triggers: List[str] = []

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
