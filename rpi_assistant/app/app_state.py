"""Persistence for the currently active voice app."""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_ACTIVE_APP_STATE_PATH = (
    Path.home() / ".config" / "rpi-assistant" / "active_app_state.json"
)


@dataclass(frozen=True)
class ActiveAppState:
    """Persisted state for the app that currently owns the conversation."""

    app_id: str
    state: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, state_path: Path) -> Optional["ActiveAppState"]:
        """Load active app state from disk if present."""
        if not state_path.exists():
            return None

        data = json.loads(state_path.read_text(encoding="utf-8"))
        return cls(
            app_id=str(data.get("app_id", "")),
            state=dict(data.get("state", {})),
        )

    def write(self, state_path: Path) -> None:
        """Persist active app state to disk."""
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
