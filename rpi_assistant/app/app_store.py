"""File-system operations for installable voice app bundles."""

import hashlib
import shutil
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from .app_manifest import APP_MANIFEST_FILENAME, AppManifest


def list_bundle_files(bundle_dir: Path) -> List[str]:
    """Return all files in a bundle as normalized relative paths."""
    bundle_dir = bundle_dir.expanduser().resolve()
    files = []

    for file_path in sorted(bundle_dir.rglob("*")):
        if not file_path.is_file():
            continue
        if file_path.suffix == ".pyc":
            continue
        if "__pycache__" in file_path.parts:
            continue
        files.append(file_path.relative_to(bundle_dir).as_posix())

    return files


def calculate_bundle_checksum(bundle_dir: Path, files: Sequence[str]) -> str:
    """Calculate a deterministic checksum across bundle file names and contents."""
    bundle_dir = bundle_dir.expanduser().resolve()
    digest = hashlib.sha256()

    for relative_path in sorted(files):
        bundle_file = _bundle_file_path(bundle_dir, relative_path)
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(bundle_file.read_bytes())
        digest.update(b"\0")

    return digest.hexdigest()


def verify_bundle_checksum(bundle_dir: Path, files: Sequence[str], expected_sha256: str) -> None:
    """Verify a bundle checksum against the expected SHA-256 value."""
    actual_sha256 = calculate_bundle_checksum(bundle_dir, files)
    if actual_sha256 != expected_sha256:
        raise ValueError(
            f"Bundle checksum mismatch: expected {expected_sha256}, got {actual_sha256}"
        )


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


def _bundle_file_path(bundle_dir: Path, relative_path: str) -> Path:
    path = Path(relative_path)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Invalid bundle file path: {relative_path}")
    return bundle_dir / path
