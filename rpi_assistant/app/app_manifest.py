"""Manifest model for installable voice apps."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple

APP_MANIFEST_FILENAME = "manifest.json"


@dataclass(frozen=True)
class AppManifest:
    """Metadata for an installable external voice app."""

    id: str
    name: str
    version: str
    entrypoint: str
    triggers: List[str] = field(default_factory=list)
    description: str = ""

    @classmethod
    def load(cls, manifest_path: Path) -> "AppManifest":
        """Load and validate a manifest from disk."""
        if not manifest_path.exists():
            raise FileNotFoundError(f"App manifest not found: {manifest_path}")

        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AppManifest":
        """Create a validated manifest instance from raw JSON data."""
        required_fields = ("id", "name", "version", "entrypoint")
        missing = [field_name for field_name in required_fields if not data.get(field_name)]
        if missing:
            raise ValueError(f"App manifest is missing required fields: {', '.join(missing)}")

        triggers = data.get("triggers", [])
        if triggers and not isinstance(triggers, list):
            raise ValueError("App manifest field 'triggers' must be a list")

        manifest = cls(
            id=str(data["id"]),
            name=str(data["name"]),
            version=str(data["version"]),
            entrypoint=str(data["entrypoint"]),
            triggers=[str(trigger) for trigger in triggers],
            description=str(data.get("description", "")),
        )

        manifest.entrypoint_parts()
        return manifest

    def entrypoint_parts(self) -> Tuple[str, str]:
        """Split the entrypoint into module path and class name."""
        module_name, separator, class_name = self.entrypoint.partition(":")
        if not separator or not module_name or not class_name:
            raise ValueError(
                "App manifest entrypoint must use the format 'module_path:ClassName'"
            )
        return module_name, class_name
