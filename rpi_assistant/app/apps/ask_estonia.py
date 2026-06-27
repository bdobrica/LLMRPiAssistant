"""Ask! conversation starter app."""

import random

from .base import AppResponse, VoiceApp

QUESTIONS = [
    "What is a movie that you can re-watch anytime?",
    "What food reminds you of childhood?",
    "What is a small thing that instantly improves your mood?",
    "What is something you are weirdly good at?",
    "What song do you never skip?",
]


class AskEstoniaApp(VoiceApp):
    """Single-turn prompt generator for the Ask! game."""

    id = "ask_estonia"
    name = "Ask!"
    description = "Returns a conversation starter for the Ask! party game."
    triggers = [
        "play ask",
        "estonian ask",
        "ask game",
    ]

    def start(self, text: str) -> AppResponse:
        return AppResponse(text=random.choice(QUESTIONS), done=True)

    def handle(self, text: str) -> AppResponse:
        return AppResponse(text=random.choice(QUESTIONS), done=True)
