"""Discovery helpers for built-in and external voice apps."""

from importlib import import_module, util
from inspect import getmembers, isclass
from pathlib import Path
from pkgutil import iter_modules
from types import ModuleType
from typing import Iterable, List, Optional, Sequence, Type

from .app_store import load_install_metadata
from .app_manifest import APP_MANIFEST_FILENAME, AppManifest
from .apps.base import VoiceApp

BUILTIN_APPS_PACKAGE = "rpi_assistant.app.apps"
DEFAULT_EXTERNAL_APP_DIRS = (
    Path.home() / ".config" / "rpi-assistant" / "apps",
)


def discover_apps(app_dirs: Optional[Sequence[Path]] = None) -> List[VoiceApp]:
    """Instantiate all discovered built-in and external voice apps."""
    apps = discover_builtin_apps()
    apps.extend(discover_external_apps(app_dirs or DEFAULT_EXTERNAL_APP_DIRS))

    seen_ids = set()

    for app in apps:
        if not app.id:
            raise ValueError(f"Discovered app {app.__class__.__name__} is missing an id")
        if app.id in seen_ids:
            raise ValueError(f"Duplicate app id discovered: {app.id}")
        seen_ids.add(app.id)

    return sorted(apps, key=lambda app: app.id)


def discover_builtin_apps() -> List[VoiceApp]:
    """Instantiate built-in app classes from the packaged apps directory."""
    apps: List[VoiceApp] = []

    for app_class in discover_builtin_app_classes():
        app = app_class()
        app.is_builtin = True
        app.manifest = None
        app.install_dir = None
        apps.append(app)

    return apps


def discover_builtin_app_classes() -> List[Type[VoiceApp]]:
    """Discover built-in app classes from the packaged apps directory."""
    package = import_module(BUILTIN_APPS_PACKAGE)
    discovered: List[Type[VoiceApp]] = []

    for module_info in iter_modules(package.__path__, f"{BUILTIN_APPS_PACKAGE}."):
        if module_info.name.endswith(".base"):
            continue
        module = import_module(module_info.name)
        discovered.extend(_get_voice_app_classes(module))

    return sorted(discovered, key=lambda app_class: app_class.id)


def discover_external_apps(app_dirs: Sequence[Path]) -> List[VoiceApp]:
    """Instantiate manifest-based app bundles from configured app directories."""
    discovered: List[VoiceApp] = []

    for app_dir in app_dirs:
        if not app_dir.exists() or not app_dir.is_dir():
            continue

        for manifest_path in sorted(_iter_external_manifest_paths(app_dir)):
            discovered.append(load_external_app_bundle(manifest_path.parent))

    return sorted(discovered, key=lambda app: app.id)


def load_external_app_bundle(bundle_dir: Path) -> VoiceApp:
    """Instantiate one external app bundle from its manifest."""
    manifest = AppManifest.load(bundle_dir / APP_MANIFEST_FILENAME)
    app_class = _load_entrypoint_class(manifest, bundle_dir)
    app = app_class()

    app.id = manifest.id
    app.name = manifest.name
    if manifest.triggers:
        app.triggers = list(manifest.triggers)
    app.manifest = manifest
    app.install_dir = bundle_dir
    app.install_metadata = load_install_metadata(bundle_dir)
    app.is_builtin = False

    return app


def _get_voice_app_classes(module: ModuleType) -> List[Type[VoiceApp]]:
    classes: List[Type[VoiceApp]] = []

    for _, candidate in getmembers(module, isclass):
        if candidate is VoiceApp:
            continue
        if candidate.__module__ != module.__name__:
            continue
        if issubclass(candidate, VoiceApp):
            classes.append(candidate)

    return classes


def _iter_external_manifest_paths(app_dir: Path) -> Iterable[Path]:
    direct_manifest = app_dir / APP_MANIFEST_FILENAME
    if direct_manifest.exists():
        yield direct_manifest

    for child in app_dir.iterdir():
        if child.name.startswith("_"):
            continue
        if child.is_dir() and (child / APP_MANIFEST_FILENAME).exists():
            yield child / APP_MANIFEST_FILENAME


def _load_entrypoint_class(manifest: AppManifest, bundle_dir: Path) -> Type[VoiceApp]:
    module_name, class_name = manifest.entrypoint_parts()
    module_path = _resolve_entrypoint_module_path(bundle_dir, module_name)
    module = _load_module_from_path(_external_module_name(module_path), module_path)
    app_class = getattr(module, class_name, None)

    if not isclass(app_class) or not issubclass(app_class, VoiceApp):
        raise TypeError(
            f"App entrypoint {manifest.entrypoint} must resolve to a VoiceApp subclass"
        )

    return app_class


def _resolve_entrypoint_module_path(bundle_dir: Path, module_name: str) -> Path:
    module_parts = module_name.split(".")
    module_path = bundle_dir.joinpath(*module_parts).with_suffix(".py")
    package_init = bundle_dir.joinpath(*module_parts, "__init__.py")

    if module_path.exists():
        return module_path
    if package_init.exists():
        return package_init

    raise FileNotFoundError(
        f"App entrypoint module '{module_name}' was not found in bundle {bundle_dir}"
    )


def _external_module_name(module_path: Path) -> str:
    normalized = str(module_path).replace("/", "_").replace(".", "_").replace("-", "_")
    return f"rpi_assistant_external_apps.{normalized}"


def _load_module_from_path(module_name: str, module_path: Path) -> ModuleType:
    spec = util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load app module from {module_path}")

    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
