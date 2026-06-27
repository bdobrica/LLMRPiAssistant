"""Deterministic spoken-intent detection for voice apps and app-store commands."""

import re
from dataclasses import dataclass
from typing import List, Optional, Sequence

from rpi_assistant.app.app_repository import AppRepository
from rpi_assistant.app.apps.base import VoiceApp

LAUNCH_VERBS = ("play", "start", "open", "launch", "run", "do")
FILLER_PREFIXES = ("the ", "a ", "an ")
FILLER_SUFFIXES = (" app", " game")


@dataclass(frozen=True)
class DetectedIntent:
    """Structured result from deterministic spoken-intent detection."""

    name: str
    raw_target: str = ""
    app_id: Optional[str] = None
    version: Optional[str] = None


class IntentDetector:
    """Resolves spoken commands to app-store actions and app launches."""

    def __init__(self, apps: Sequence[VoiceApp], repositories: Sequence[AppRepository]):
        self.apps = list(apps)
        self.repositories = list(repositories)

    def detect_management_intent(self, text: str) -> Optional[DetectedIntent]:
        normalized = normalize_text(text)

        if normalized in {
            "list apps",
            "list installed apps",
            "what apps are installed",
            "what app is installed",
        }:
            return DetectedIntent(name="list_installed")

        if normalized in {
            "list available apps",
            "list store apps",
            "what apps are available",
        }:
            return DetectedIntent(name="list_available")

        if normalized in {
            "resume app",
            "resume game",
            "continue app",
            "continue game",
        }:
            return DetectedIntent(name="resume_active")

        if normalized in {
            "what app is active",
            "what game is active",
            "active app",
            "active game",
        }:
            return DetectedIntent(name="active_status")

        if normalized in {
            "app store health",
            "app store status",
            "store health",
            "store status",
        }:
            return DetectedIntent(name="app_store_health")

        install_match = re.match(r"^(?:install|add)\s+app(?:\s+from)?\s+(.+)$", text.strip(), re.IGNORECASE)
        if install_match:
            raw_target = install_match.group(1).strip().strip('"\'')
            app_id, version = self._resolve_repository_target(raw_target)
            return DetectedIntent(
                name="install_app",
                raw_target=raw_target,
                app_id=app_id,
                version=version,
            )

        uninstall_match = re.match(
            r"^(?:uninstall|remove|delete)\s+app\s+(.+)$",
            text.strip(),
            re.IGNORECASE,
        )
        if uninstall_match:
            raw_target = uninstall_match.group(1).strip()
            return DetectedIntent(
                name="uninstall_app",
                raw_target=raw_target,
                app_id=self._resolve_installed_or_repository_app(raw_target),
            )

        describe_match = re.match(r"^(?:describe|show)\s+app\s+(.+)$", text.strip(), re.IGNORECASE)
        if describe_match:
            raw_target = describe_match.group(1).strip()
            return DetectedIntent(
                name="describe_app",
                raw_target=raw_target,
                app_id=self._resolve_installed_or_repository_app(raw_target),
            )

        upgrade_match = re.match(r"^(?:upgrade|update)\s+app\s+(.+)$", text.strip(), re.IGNORECASE)
        if upgrade_match:
            raw_target = upgrade_match.group(1).strip()
            return DetectedIntent(
                name="upgrade_app",
                raw_target=raw_target,
                app_id=self._resolve_installed_or_repository_app(raw_target),
            )

        versions_match = re.match(r"^(?:list|show)\s+app\s+versions\s+(.+)$", text.strip(), re.IGNORECASE)
        if versions_match:
            raw_target = versions_match.group(1).strip()
            app_id, version = self._resolve_repository_target(raw_target)
            return DetectedIntent(
                name="list_versions",
                raw_target=raw_target,
                app_id=app_id,
                version=version,
            )

        return None

    def detect_launch_app(self, text: str) -> Optional[VoiceApp]:
        normalized = normalize_text(text)
        best_match: Optional[tuple[int, VoiceApp]] = None

        for app in self.apps:
            for alias in app_aliases(app):
                if not alias:
                    continue
                if normalized == alias or normalized.startswith(f"{alias} "):
                    score = len(alias)
                elif any(normalized.startswith(f"{verb} {alias}") for verb in LAUNCH_VERBS):
                    score = len(alias)
                elif alias in normalized and app.matches(text):
                    score = len(alias)
                else:
                    continue

                if best_match is None or score > best_match[0]:
                    best_match = (score, app)

        return None if best_match is None else best_match[1]

    def _resolve_repository_target(self, raw_target: str) -> tuple[Optional[str], Optional[str]]:
        app_target, version = split_version_target(raw_target)
        app_id = self._resolve_repository_app(app_target)
        return app_id, version

    def _resolve_installed_or_repository_app(self, raw_target: str) -> Optional[str]:
        return self._resolve_installed_app(raw_target) or self._resolve_repository_app(raw_target)

    def _resolve_installed_app(self, raw_target: str) -> Optional[str]:
        normalized_target = normalize_app_target(raw_target)
        for app in self.apps:
            for alias in app_aliases(app):
                if alias == normalized_target:
                    return app.id
        return None

    def _resolve_repository_app(self, raw_target: str) -> Optional[str]:
        normalized_target = normalize_app_target(raw_target)
        for repository in self.repositories:
            for release in repository.list():
                for alias in manifest_aliases(release.manifest.id, release.manifest.name, release.manifest.triggers):
                    if alias == normalized_target:
                        return release.manifest.id
        return None


def split_version_target(raw_target: str) -> tuple[str, Optional[str]]:
    target, separator, version = raw_target.partition("@")
    if not separator:
        return target.strip(), None
    return target.strip(), version.strip() or None


def normalize_text(text: str) -> str:
    normalized = text.lower().replace("_", " ").replace("!", "")
    normalized = re.sub(r"[^a-z0-9@\s]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def normalize_app_target(text: str) -> str:
    normalized = normalize_text(text)
    for prefix in FILLER_PREFIXES:
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]
    for suffix in FILLER_SUFFIXES:
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)]
    return normalized.strip()


def manifest_aliases(app_id: str, app_name: str, triggers: Sequence[str]) -> List[str]:
    aliases = {
        normalize_app_target(app_id),
        normalize_app_target(app_name),
    }
    for trigger in triggers:
        normalized_trigger = normalize_text(trigger)
        aliases.add(normalized_trigger)
        for verb in LAUNCH_VERBS:
            prefix = f"{verb} "
            if normalized_trigger.startswith(prefix):
                aliases.add(normalized_trigger[len(prefix):].strip())
    return sorted(alias for alias in aliases if alias)


def app_aliases(app: VoiceApp) -> List[str]:
    manifest = app.manifest
    if manifest is not None:
        return manifest_aliases(manifest.id, manifest.name, manifest.triggers)
    return manifest_aliases(app.id, app.name, app.triggers)
