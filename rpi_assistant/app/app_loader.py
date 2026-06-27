"""Discovery helpers for built-in and external voice apps."""

from importlib import import_module, util
from inspect import getmembers, isclass
from pathlib import Path
from pkgutil import iter_modules
from types import ModuleType
from typing import Iterable, List, Optional, Sequence, Type

from .apps.base import VoiceApp

BUILTIN_APPS_PACKAGE = "rpi_assistant.app.apps"
DEFAULT_EXTERNAL_APP_DIRS = (
    Path.home() / ".config" / "rpi-assistant" / "apps",
)


def discover_apps(app_dirs: Optional[Sequence[Path]] = None) -> List[VoiceApp]:
    """Instantiate all discovered built-in and external voice apps."""
    classes = discover_builtin_app_classes()
    classes.extend(discover_external_app_classes(app_dirs or DEFAULT_EXTERNAL_APP_DIRS))

    instances: List[VoiceApp] = []
    seen_ids = set()

    for app_class in classes:
        app = app_class()
        if not app.id:
            raise ValueError(f"Discovered app {app_class.__name__} is missing an id")
        if app.id in seen_ids:
            raise ValueError(f"Duplicate app id discovered: {app.id}")
        seen_ids.add(app.id)
        instances.append(app)

    return instances


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


def discover_external_app_classes(app_dirs: Sequence[Path]) -> List[Type[VoiceApp]]:
    """Discover app classes from configured app directories on disk."""
    discovered: List[Type[VoiceApp]] = []

    for app_dir in app_dirs:
        if not app_dir.exists() or not app_dir.is_dir():
            continue

        for module_path in sorted(_iter_external_module_paths(app_dir)):
            module_name = _external_module_name(module_path)
            module = _load_module_from_path(module_name, module_path)
            discovered.extend(_get_voice_app_classes(module))

    return sorted(discovered, key=lambda app_class: app_class.id)


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


def _iter_external_module_paths(app_dir: Path) -> Iterable[Path]:
    for child in app_dir.iterdir():
        if child.name.startswith("_"):
            continue
        if child.is_file() and child.suffix == ".py" and child.name != "__init__.py":
            yield child
        elif child.is_dir() and (child / "app.py").exists():
            yield child / "app.py"


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
