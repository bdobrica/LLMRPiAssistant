"""Truth or Dare app bundle for the public app repository."""

import random
import re
from typing import Any, Dict, Optional

from rpi_assistant.app.apps.base import AppResponse, VoiceApp

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
    description = "Runs a quick truth-or-dare prompt for one player."
    triggers = [
        "truth or dare",
        "do truth or dare",
        "play truth or dare",
    ]

    def __init__(self):
        self.player_name: Optional[str] = None
        self.phase = "idle"

    def start(self, text: str) -> AppResponse:
        self.player_name = self._extract_player_name(text)

        if self.player_name:
            self.phase = "waiting_for_choice"
            return AppResponse(
                text=f"{self.player_name}, truth or dare?",
                expect_input=True,
                state=self.serialize_state(),
            )

        self.phase = "waiting_for_player"
        return AppResponse(
            text="Who is playing truth or dare?",
            expect_input=True,
            state=self.serialize_state(),
        )

    def handle(self, text: str) -> AppResponse:
        lowered = text.lower().strip()

        if self.phase == "waiting_for_player":
            extracted_name = self._extract_player_name(text)
            if extracted_name:
                self.player_name = extracted_name
            else:
                candidate = text.strip().split()[0].strip(",.!?") if text.strip() else ""
                self.player_name = candidate or None

            if self.player_name is None:
                return AppResponse(
                    text="Tell me who is playing truth or dare.",
                    expect_input=True,
                    state=self.serialize_state(),
                )

            self.phase = "waiting_for_choice"
            return AppResponse(
                text=f"{self.player_name}, truth or dare?",
                expect_input=True,
                state=self.serialize_state(),
            )

        if self.phase == "waiting_for_choice":
            if "truth" in lowered:
                self.phase = "finished"
                return AppResponse(
                    text=random.choice(TRUTHS),
                    done=True,
                    state=self.serialize_state(),
                )

            if "dare" in lowered:
                self.phase = "finished"
                return AppResponse(
                    text=random.choice(DARES),
                    done=True,
                    state=self.serialize_state(),
                )

            return AppResponse(
                text="I need one answer: truth or dare?",
                expect_input=True,
                state=self.serialize_state(),
            )

        return AppResponse(
            text="Truth or Dare is done.",
            done=True,
            state=self.serialize_state(),
        )

    def stop(self) -> None:
        self.player_name = None
        self.phase = "idle"

    def serialize_state(self) -> Dict[str, Any]:
        return {
            "phase": self.phase,
            "player_name": self.player_name or "",
        }

    def restore_state(self, state: Dict[str, Any]) -> None:
        self.phase = str(state.get("phase", "idle"))
        player_name = str(state.get("player_name", "")).strip()
        self.player_name = player_name or None

    def _extract_player_name(self, text: str) -> Optional[str]:
        match = re.search(r"for\s+([a-zA-ZăâîșțĂÂÎȘȚ]+)", text, re.IGNORECASE)
        if match:
            return match.group(1)
        return None
