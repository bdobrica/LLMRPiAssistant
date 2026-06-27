"""Repository index support for installable voice apps."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from .app_manifest import AppManifest

APP_REPOSITORY_INDEX_FILENAME = "index.json"
DEFAULT_APP_REPOSITORY_ROOTS = (
    Path(__file__).resolve().parents[2] / "voice_apps",
)


@dataclass(frozen=True)
class RepositoryApp:
    """One app entry from a repository index."""

    manifest: AppManifest
    bundle_dir: Path


class AppRepository:
    """Local repository of installable app bundles."""

    def __init__(self, root: Path, apps: Dict[str, RepositoryApp]):
        self.root = root
        self.apps = apps

    @classmethod
    def load(cls, root: Path) -> Optional["AppRepository"]:
        """Load one repository index from disk if it exists."""
        root = root.expanduser().resolve()
        index_path = root / APP_REPOSITORY_INDEX_FILENAME
        if not index_path.exists():
            return None

        raw_data = json.loads(index_path.read_text(encoding="utf-8"))
        entries = raw_data.get("apps", [])
        if not isinstance(entries, list):
            raise ValueError("App repository index field 'apps' must be a list")

        apps: Dict[str, RepositoryApp] = {}
        for entry in entries:
            app_id = str(entry.get("id", "")).strip()
            bundle = str(entry.get("bundle", "")).strip()
            if not app_id or not bundle:
                raise ValueError("Repository app entries require 'id' and 'bundle'")

            bundle_dir = (root / bundle).resolve()
            manifest = AppManifest.load(bundle_dir / "manifest.json")
            if manifest.id != app_id:
                raise ValueError(
                    f"Repository entry id '{app_id}' does not match manifest id '{manifest.id}'"
                )
            apps[app_id] = RepositoryApp(manifest=manifest, bundle_dir=bundle_dir)

        return cls(root=root, apps=apps)

    def get(self, app_id: str) -> Optional[RepositoryApp]:
        """Return one repository app by id."""
        return self.apps.get(app_id)

    def list(self) -> List[RepositoryApp]:
        """Return all repository apps sorted by id."""
        return [self.apps[app_id] for app_id in sorted(self.apps)]


def load_app_repositories(roots: Sequence[Path]) -> List[AppRepository]:
    """Load all available repositories from the configured roots."""
    repositories: List[AppRepository] = []
    for root in roots:
        repository = AppRepository.load(root)
        if repository is not None:
            repositories.append(repository)
    return repositories
