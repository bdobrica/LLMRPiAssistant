"""Dice app bundle for the public app repository."""

import random

from rpi_assistant.app.apps.base import AppResponse, VoiceApp


class DiceApp(VoiceApp):
    """Simple local die roll app."""

    id = "dice"
    name = "Dice"
    description = "Rolls a six-sided die locally."
    triggers = [
        "roll dice",
        "roll a die",
        "roll d6",
    ]

    def start(self, text: str) -> AppResponse:
        value = random.randint(1, 6)
        return AppResponse(text=f"You rolled {value}.", done=True)

    def handle(self, text: str) -> AppResponse:
        return self.start(text)
