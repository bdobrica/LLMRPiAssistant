"""File-system operations for installable voice app bundles."""

import shutil
from pathlib import Path
from typing import Optional, Sequence, Tuple

from .app_manifest import APP_MANIFEST_FILENAME, AppManifest


def install_app_bundle(source_dir: Path, destination_root: Path) -> Path:
    """Copy a manifest-based app bundle into the external app directory."""
    source_dir = source_dir.expanduser().resolve()
    destination_root = destination_root.expanduser().resolve()

    if not source_dir.exists() or not source_dir.is_dir():
        raise FileNotFoundError(f"App bundle not found: {source_dir}")

    manifest = AppManifest.load(source_dir / APP_MANIFEST_FILENAME)
    destination_root.mkdir(parents=True, exist_ok=True)
    destination_dir = destination_root / manifest.id

    if destination_dir.exists():
        raise FileExistsError(f"App is already installed at {destination_dir}")

    shutil.copytree(source_dir, destination_dir)
    return destination_dir


def stage_app_bundle(source_dir: Path, destination_root: Path) -> Path:
    """Copy an app bundle into a temporary staging directory."""
    source_dir = source_dir.expanduser().resolve()
    destination_root = destination_root.expanduser().resolve()

    if not source_dir.exists() or not source_dir.is_dir():
        raise FileNotFoundError(f"App bundle not found: {source_dir}")

    manifest = AppManifest.load(source_dir / APP_MANIFEST_FILENAME)
    destination_root.mkdir(parents=True, exist_ok=True)
    staged_dir = destination_root / f".{manifest.id}.staged"

    if staged_dir.exists():
        shutil.rmtree(staged_dir)

    shutil.copytree(source_dir, staged_dir)
    return staged_dir


def uninstall_app_bundle(app_id: str, app_dirs: Sequence[Path]) -> Optional[AppManifest]:
    """Remove an installed app bundle by manifest id."""
    bundle_dir, manifest = find_installed_app_bundle(app_id, app_dirs)
    if bundle_dir is None or manifest is None:
        return None

    shutil.rmtree(bundle_dir)
    return manifest


def find_installed_app_bundle(
    app_id: str,
    app_dirs: Sequence[Path],
) -> Tuple[Optional[Path], Optional[AppManifest]]:
    """Locate an installed app bundle and its manifest."""
    for app_dir in app_dirs:
        app_dir = app_dir.expanduser().resolve()
        if not app_dir.exists() or not app_dir.is_dir():
            continue

        for bundle_dir in sorted(app_dir.iterdir()):
            if not bundle_dir.is_dir():
                continue

            manifest_path = bundle_dir / APP_MANIFEST_FILENAME
            if not manifest_path.exists():
                continue

            manifest = AppManifest.load(manifest_path)
            if manifest.id == app_id:
                return bundle_dir, manifest

    return None, None
