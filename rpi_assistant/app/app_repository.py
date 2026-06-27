"""Repository index support for installable voice apps."""

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple
from urllib.parse import urljoin
from urllib.request import urlopen

from .app_manifest import AppManifest
from .app_signing import verify_catalog_signature
from .app_store import verify_bundle_checksum

APP_REPOSITORY_INDEX_FILENAME = "index.json"
DEFAULT_APP_REPOSITORY_ROOTS = (
    Path(__file__).resolve().parents[2] / "voice_apps",
)
DEFAULT_APP_REPOSITORY_PUBLIC_KEY_PATH = (
    Path(__file__).resolve().parents[2] / "voice_apps" / "public_key.txt"
)


def load_default_repository_public_key() -> str:
    """Load the shipped repository verification key if present."""
    if not DEFAULT_APP_REPOSITORY_PUBLIC_KEY_PATH.exists():
        return ""
    return DEFAULT_APP_REPOSITORY_PUBLIC_KEY_PATH.read_text(encoding="utf-8").strip()


@dataclass(frozen=True)
class RepositoryRelease:
    """One installable app release from a repository index."""

    manifest: AppManifest
    bundle_ref: str
    files: List[str]
    sha256: str
    repository_root: str | Path
    is_remote: bool
    signature_verified: bool = False

    def materialize(self, destination_root: Path) -> Path:
        """Copy or download one repository release into a local staging directory."""
        destination_root = destination_root.expanduser().resolve()
        destination_root.mkdir(parents=True, exist_ok=True)
        staging_dir = destination_root / f".{self.manifest.id}-{self.manifest.version}.repo"

        if staging_dir.exists():
            shutil.rmtree(staging_dir)

        staging_dir.mkdir(parents=True, exist_ok=True)

        for relative_path in self.files:
            destination_file = staging_dir / Path(relative_path)
            destination_file.parent.mkdir(parents=True, exist_ok=True)

            if self.is_remote:
                file_url = _remote_bundle_file_url(str(self.repository_root), self.bundle_ref, relative_path)
                destination_file.write_bytes(_read_remote_bytes(file_url))
            else:
                source_file = Path(self.repository_root).expanduser().resolve() / self.bundle_ref / relative_path
                if not source_file.exists():
                    raise FileNotFoundError(f"Repository bundle file not found: {source_file}")
                shutil.copy2(source_file, destination_file)

        verify_bundle_checksum(staging_dir, self.files, self.sha256)
        return staging_dir


class AppRepository:
    """Repository of installable app bundles, backed by a local path or remote URL."""

    def __init__(self, root: str | Path, apps: Dict[str, List[RepositoryRelease]]):
        self.root = root
        self.apps = apps

    @classmethod
    def load(
        cls,
        root: str | Path,
        trusted_public_key: str = "",
        require_signature: bool = False,
    ) -> Optional["AppRepository"]:
        """Load one repository index from disk or a remote base URL if it exists."""
        normalized_root = _normalize_repository_root(root)
        raw_data, signature_verified = _read_repository_index(
            normalized_root,
            trusted_public_key=trusted_public_key,
            require_signature=require_signature,
        )
        if raw_data is None:
            return None

        entries = raw_data.get("apps", [])
        if not isinstance(entries, list):
            raise ValueError("App repository index field 'apps' must be a list")

        apps: Dict[str, List[RepositoryRelease]] = {}
        for entry in entries:
            app_id = str(entry.get("id", "")).strip()
            versions = entry.get("versions", [])
            if not app_id or not isinstance(versions, list) or not versions:
                raise ValueError("Repository app entries require 'id' and non-empty 'versions'")

            releases: List[RepositoryRelease] = []
            for version_entry in versions:
                releases.append(
                    _load_release(
                        normalized_root,
                        app_id,
                        version_entry,
                        signature_verified=signature_verified,
                    )
                )

            apps[app_id] = _sort_releases(releases)

        return cls(root=normalized_root, apps=apps)

    def get(self, app_id: str, version: Optional[str] = None) -> Optional[RepositoryRelease]:
        """Return one repository release by id, optionally pinned to a specific version."""
        releases = self.apps.get(app_id)
        if not releases:
            return None

        if version is None:
            return releases[0]

        for release in releases:
            if release.manifest.version == version:
                return release

        return None

    def list(self) -> List[RepositoryRelease]:
        """Return the latest release for each app sorted by id."""
        return [self.apps[app_id][0] for app_id in sorted(self.apps)]

    def list_versions(self, app_id: str) -> List[RepositoryRelease]:
        """Return all releases for one app, sorted newest-first."""
        return list(self.apps.get(app_id, []))


def load_app_repositories(roots: Sequence[str | Path]) -> List[AppRepository]:
    """Load all available repositories from the configured roots."""
    repositories: List[AppRepository] = []
    for root in roots:
        repository = AppRepository.load(root)
        if repository is not None:
            repositories.append(repository)
    return repositories


def _load_release(
    root: str | Path,
    app_id: str,
    version_entry: dict,
    signature_verified: bool,
) -> RepositoryRelease:
    bundle_ref = str(version_entry.get("bundle", "")).strip()
    files = version_entry.get("files", [])
    sha256 = str(version_entry.get("sha256", "")).strip()

    if not bundle_ref or not isinstance(files, list) or not files or not sha256:
        raise ValueError(
            "Repository release entries require 'bundle', non-empty 'files', and 'sha256'"
        )

    manifest = _load_manifest(root, bundle_ref)
    if manifest.id != app_id:
        raise ValueError(
            f"Repository entry id '{app_id}' does not match manifest id '{manifest.id}'"
        )

    declared_version = str(version_entry.get("version", "")).strip()
    if declared_version and declared_version != manifest.version:
        raise ValueError(
            f"Repository release version '{declared_version}' does not match manifest version "
            f"'{manifest.version}'"
        )

    return RepositoryRelease(
        manifest=manifest,
        bundle_ref=bundle_ref,
        files=[str(file_name) for file_name in files],
        sha256=sha256,
        repository_root=root,
        is_remote=isinstance(root, str),
        signature_verified=signature_verified,
    )


def _sort_releases(releases: Sequence[RepositoryRelease]) -> List[RepositoryRelease]:
    sorted_releases: List[RepositoryRelease] = []
    for release in releases:
        inserted = False
        for index, current in enumerate(sorted_releases):
            if release.manifest.compare_version(current.manifest) > 0:
                sorted_releases.insert(index, release)
                inserted = True
                break
        if not inserted:
            sorted_releases.append(release)
    return sorted_releases


def _normalize_repository_root(root: str | Path) -> str | Path:
    if isinstance(root, Path):
        return root.expanduser().resolve()

    root_text = str(root).strip()
    if root_text.startswith(("http://", "https://")):
        return root_text.rstrip("/") + "/"

    return Path(root_text).expanduser().resolve()


def _read_repository_index(
    root: str | Path,
    trusted_public_key: str = "",
    require_signature: bool = False,
) -> Tuple[Optional[dict], bool]:
    if isinstance(root, Path):
        index_path = root / APP_REPOSITORY_INDEX_FILENAME
        if not index_path.exists():
            return None, False
        payload = json.loads(index_path.read_text(encoding="utf-8"))
        return _unwrap_signed_catalog(
            payload,
            trusted_public_key=trusted_public_key,
            require_signature=require_signature,
        )

    index_url = urljoin(root, APP_REPOSITORY_INDEX_FILENAME)
    try:
        payload = json.loads(_read_remote_text(index_url))
        return _unwrap_signed_catalog(
            payload,
            trusted_public_key=trusted_public_key,
            require_signature=require_signature,
        )
    except Exception:
        return None, False


def _load_manifest(root: str | Path, bundle_ref: str) -> AppManifest:
    if isinstance(root, Path):
        return AppManifest.load(root / bundle_ref / "manifest.json")

    manifest_url = _remote_bundle_file_url(root, bundle_ref, "manifest.json")
    data = json.loads(_read_remote_text(manifest_url))
    return AppManifest.from_dict(data)


def _remote_bundle_file_url(root_url: str, bundle_ref: str, relative_path: str) -> str:
    bundle_url = urljoin(root_url, bundle_ref.rstrip("/") + "/")
    return urljoin(bundle_url, relative_path)


def _read_remote_text(url: str) -> str:
    return _read_remote_bytes(url).decode("utf-8")


def _read_remote_bytes(url: str) -> bytes:
    with urlopen(url, timeout=5) as response:
        return response.read()


def _unwrap_signed_catalog(
    payload: dict,
    trusted_public_key: str,
    require_signature: bool,
) -> Tuple[dict, bool]:
    if "catalog" not in payload:
        if require_signature:
            raise ValueError("App repository signature is required but missing")
        return payload, False

    catalog = payload.get("catalog")
    signing = payload.get("signing", {})
    if not isinstance(catalog, dict) or not isinstance(signing, dict):
        raise ValueError("Signed repository index must contain 'catalog' and 'signing' objects")

    signature = str(signing.get("signature", "")).strip()
    algorithm = str(signing.get("algorithm", "")).strip().lower()
    if algorithm != "ed25519":
        raise ValueError("Unsupported app repository signature algorithm")
    if not signature:
        raise ValueError("Signed app repository is missing a signature")
    if not trusted_public_key:
        raise ValueError("App repository signature verification requires a trusted public key")

    verify_catalog_signature(catalog, signature, trusted_public_key)
    return catalog, True
