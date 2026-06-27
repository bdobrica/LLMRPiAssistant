"""Installed app metadata persisted alongside installed bundles."""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

INSTALL_METADATA_FILENAME = ".rpi_assistant_install.json"


@dataclass(frozen=True)
class AppInstallMetadata:
    """Metadata describing where an installed app came from."""

    source_type: str
    source: str
    requested_target: str
    installed_version: str
    installed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    repository_root: str = ""
    bundle_ref: str = ""
    sha256: str = ""
    signature_verified: bool = False

    @classmethod
    def load(cls, metadata_path: Path) -> Optional["AppInstallMetadata"]:
        """Load install metadata from disk if present."""
        if not metadata_path.exists():
            return None

        data = json.loads(metadata_path.read_text(encoding="utf-8"))
        return cls(
            source_type=str(data.get("source_type", "")),
            source=str(data.get("source", "")),
            requested_target=str(data.get("requested_target", "")),
            installed_version=str(data.get("installed_version", "")),
            installed_at=str(data.get("installed_at", "")),
            repository_root=str(data.get("repository_root", "")),
            bundle_ref=str(data.get("bundle_ref", "")),
            sha256=str(data.get("sha256", "")),
            signature_verified=bool(data.get("signature_verified", False)),
        )

    def write(self, bundle_dir: Path) -> None:
        """Write install metadata into the bundle directory."""
        metadata_path = bundle_dir / INSTALL_METADATA_FILENAME
        metadata_path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
