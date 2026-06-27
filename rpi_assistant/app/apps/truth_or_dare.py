"""Truth or Dare voice app."""

import random
import re
from typing import Optional

from .base import AppResponse, VoiceApp

TRUTHS = [
    "What is something embarrassing you still think about?",
    "Who in this room would you trust least with your phone?",
    "What is a harmless secret you have never told this group?",
]

DARES = [
    "Do your best dramatic movie death scene.",
    "Let the group choose a ridiculous accent for you for the next two minutes.",
    "Give someone in the room a very serious compliment.",
]


class TruthOrDareApp(VoiceApp):
    """One-turn Truth or Dare game flow."""

    id = "truth_or_dare"
    name = "Truth or Dare"
    triggers = [
        "truth or dare",
        "do truth or dare",
        "play truth or dare",
    ]

    def __init__(self):
        self.player_name: Optional[str] = None
        self.state = "idle"

    def start(self, text: str) -> AppResponse:
        self.player_name = self._extract_player_name(text)
        self.state = "waiting_for_choice"

        if self.player_name:
            return AppResponse(
                text=f"{self.player_name}, truth or dare?",
                expect_input=True,
                state={"phase": self.state},
            )

        return AppResponse(
            text="Who is playing truth or dare?",
            expect_input=True,
            state={"phase": self.state},
        )

    def handle(self, text: str) -> AppResponse:
        lowered = text.lower().strip()

        if self.state == "waiting_for_choice":
            if "truth" in lowered:
                self.state = "finished"
                return AppResponse(
                    text=random.choice(TRUTHS),
                    done=True,
                    state={"phase": self.state},
                )

            if "dare" in lowered:
                self.state = "finished"
                return AppResponse(
                    text=random.choice(DARES),
                    done=True,
                    state={"phase": self.state},
                )

            return AppResponse(
                text="I need one answer: truth or dare?",
                expect_input=True,
                state={"phase": self.state},
            )

        return AppResponse(
            text="Truth or Dare is done.",
            done=True,
            state={"phase": self.state},
        )

    def stop(self) -> None:
        self.player_name = None
        self.state = "idle"

    def _extract_player_name(self, text: str) -> Optional[str]:
        match = re.search(r"for\s+([a-zA-ZăâîșțĂÂÎȘȚ]+)", text, re.IGNORECASE)
        if match:
            return match.group(1)
        return None
