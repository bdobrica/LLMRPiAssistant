"""Deterministic spoken-intent detection for voice apps and app-store commands."""

import difflib
import re
from dataclasses import dataclass
from typing import List, Optional, Sequence

from rpi_assistant.app.app_repository import AppRepository
from rpi_assistant.app.apps.base import VoiceApp

LAUNCH_VERBS = ("play", "start", "open", "launch", "run", "do")
FILLER_PREFIXES = ("the ", "a ", "an ")
FILLER_SUFFIXES = (" app", " apps", " game")
FUZZY_MATCH_THRESHOLD = 0.72


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

        path_install_match = re.match(
            r"^(?:please\s+)?(?:install|add)\s+(?:the\s+)?app(?:\s+from)?\s+(.+)$",
            text.strip(),
            re.IGNORECASE,
        )
        if path_install_match and looks_like_path(path_install_match.group(1).strip()):
            raw_target = path_install_match.group(1).strip().strip('"\'')
            app_id, version = self._resolve_repository_target(raw_target)
            return DetectedIntent(
                name="install_app",
                raw_target=raw_target,
                app_id=app_id,
                version=version,
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

        if is_installed_list_request(normalized):
            return DetectedIntent(name="list_installed")

        if is_available_list_request(normalized):
            return DetectedIntent(name="list_available")

        install_target = extract_install_target(text)
        if install_target is not None:
            if normalize_app_target(install_target) in {"app", "apps"}:
                return DetectedIntent(name="list_available")

            app_id, version = self._resolve_repository_target(install_target)
            if app_id is None:
                return None
            return DetectedIntent(
                name="install_app",
                raw_target=install_target,
                app_id=app_id,
                version=version,
            )

        available_score = phrase_match_score(
            normalized,
            (
                "list available apps",
                "list store apps",
                "what apps are available",
            ),
        )
        installed_score = phrase_match_score(
            normalized,
            (
                "list apps",
                "list installed apps",
                "what apps are installed",
                "what app is installed",
            ),
        )

        if available_score >= FUZZY_MATCH_THRESHOLD and available_score >= installed_score:
            return DetectedIntent(name="list_available")

        if installed_score >= FUZZY_MATCH_THRESHOLD:
            return DetectedIntent(name="list_installed")

        if matches_phrase(
            normalized,
            ("resume app", "resume game", "continue app", "continue game"),
        ):
            return DetectedIntent(name="resume_active")

        if matches_phrase(
            normalized,
            ("what app is active", "what game is active", "active app", "active game"),
        ):
            return DetectedIntent(name="active_status")

        if matches_phrase(
            normalized,
            ("app store health", "app store status", "store health", "store status"),
        ):
            return DetectedIntent(name="app_store_health")

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

        return None

    def detect_launch_app(self, text: str) -> Optional[VoiceApp]:
        normalized = normalize_text(text)
        best_match: Optional[tuple[float, VoiceApp]] = None

        for app in self.apps:
            for alias in app_aliases(app):
                if not alias:
                    continue
                if normalized == alias or normalized.startswith(f"{alias} "):
                    score = float(len(alias))
                elif any(normalized.startswith(f"{verb} {alias}") for verb in LAUNCH_VERBS):
                    score = float(len(alias))
                elif alias in normalized and app.matches(text):
                    score = float(len(alias))
                else:
                    target = extract_launch_target(normalized)
                    ratio = max(
                        fuzzy_ratio(normalized, alias),
                        fuzzy_ratio(target, alias),
                    )
                    if ratio < FUZZY_MATCH_THRESHOLD:
                        continue
                    score = ratio

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
        best_match: Optional[tuple[float, str]] = None
        for app in self.apps:
            for alias in app_aliases(app):
                if alias == normalized_target:
                    return app.id
                ratio = fuzzy_ratio(normalized_target, alias)
                if ratio >= FUZZY_MATCH_THRESHOLD and (best_match is None or ratio > best_match[0]):
                    best_match = (ratio, app.id)
        return None if best_match is None else best_match[1]

    def _resolve_repository_app(self, raw_target: str) -> Optional[str]:
        normalized_target = normalize_app_target(raw_target)
        best_match: Optional[tuple[float, str]] = None
        for repository in self.repositories:
            for release in repository.list():
                for alias in manifest_aliases(release.manifest.id, release.manifest.name, release.manifest.triggers):
                    if alias == normalized_target:
                        return release.manifest.id
                    ratio = fuzzy_ratio(normalized_target, alias)
                    if ratio >= FUZZY_MATCH_THRESHOLD and (best_match is None or ratio > best_match[0]):
                        best_match = (ratio, release.manifest.id)
        return None if best_match is None else best_match[1]


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


def fuzzy_ratio(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    compact_left = left.replace(" ", "")
    compact_right = right.replace(" ", "")
    return max(
        difflib.SequenceMatcher(a=left, b=right).ratio(),
        difflib.SequenceMatcher(a=compact_left, b=compact_right).ratio(),
    )


def matches_phrase(normalized_text: str, phrases: Sequence[str]) -> bool:
    return phrase_match_score(normalized_text, phrases) >= FUZZY_MATCH_THRESHOLD


def phrase_match_score(normalized_text: str, phrases: Sequence[str]) -> float:
    best_score = 0.0
    for phrase in phrases:
        normalized_phrase = normalize_text(phrase)
        if normalized_text == normalized_phrase:
            return 1.0
        best_score = max(best_score, fuzzy_ratio(normalized_text, normalized_phrase))
    return best_score


def is_installed_list_request(normalized_text: str) -> bool:
    return bool(
        re.search(r"\b(?:list|show|tell me|what)\b", normalized_text)
        and re.search(r"\binstalled\b", normalized_text)
        and re.search(r"\bapps?\b", normalized_text)
    )


def is_available_list_request(normalized_text: str) -> bool:
    if bool(
        re.search(r"\b(?:list|show|tell me|what)\b", normalized_text)
        and re.search(r"\b(?:available|store)\b", normalized_text)
        and re.search(r"\bapps?\b", normalized_text)
    ):
        return True

    return phrase_match_score(
        normalized_text,
        (
            "list available apps",
            "least available apps",
            "show available apps",
            "what apps are available",
        ),
    ) >= FUZZY_MATCH_THRESHOLD


def extract_install_target(text: str) -> Optional[str]:
    normalized_text = normalize_text(text)
    match = re.search(
        r"\b(?:install|add)\b\s+(?:the\s+)?(?:apps?\s+)?(?:from\s+)?(.+)$",
        normalized_text,
    )
    if not match:
        return None

    raw_match = re.search(
        r"\b(?:install|add)\b\s+(?:the\s+)?(?:apps?\s+)?(?:from\s+)?(.+)$",
        text.strip(),
        re.IGNORECASE,
    )
    target = (raw_match.group(1) if raw_match else match.group(1)).strip().strip('"\'')
    if normalize_app_target(target) in {"", "please"}:
        return "apps"
    return target


def extract_launch_target(normalized_text: str) -> str:
    for verb in LAUNCH_VERBS:
        prefix = f"{verb} "
        if normalized_text.startswith(prefix):
            return normalized_text[len(prefix):].strip()
    return normalized_text


def looks_like_path(text: str) -> bool:
    stripped = text.strip().strip('"\'')
    return "/" in stripped or "\\" in stripped or stripped.startswith((".", "~"))


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
