"""Built-in local voice apps."""

from .ask_estonia import AskEstoniaApp
from .base import AppResponse, VoiceApp
from .truth_or_dare import TruthOrDareApp

__all__ = [
    "AppResponse",
    "VoiceApp",
    "AskEstoniaApp",
    "TruthOrDareApp",
]