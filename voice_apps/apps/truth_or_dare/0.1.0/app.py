"""Truth or Dare app bundle for the public app repository."""

import json
import random
import re
from pathlib import Path
from typing import Any, Dict, Optional

from rpi_assistant.app.apps.base import AppResponse, VoiceApp

PROMPTS_PATH = Path(__file__).with_name("prompts.json")


def load_categories() -> Dict[str, Dict[str, Any]]:
    """Load category prompts from the bundled JSON data file."""
    return json.loads(PROMPTS_PATH.read_text(encoding="utf-8"))


CATEGORIES = load_categories()


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
        self.category_id = "classic"
        self.phase = "idle"

    def start(self, text: str) -> AppResponse:
        selected_category = self._extract_category(text)
        if selected_category:
            self.category_id = selected_category
        else:
            self.category_id = "classic"

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
                    text=random.choice(self._truths()),
                    done=True,
                    state=self.serialize_state(),
                )

            if "dare" in lowered:
                if not self._dares():
                    return AppResponse(
                        text=(
                            f"{self._category_label().title()}"
                            " only has truth questions. Say truth or choose another type."
                        ),
                        expect_input=True,
                        state=self.serialize_state(),
                    )
                self.phase = "finished"
                return AppResponse(
                    text=random.choice(self._dares()),
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
        self.category_id = "classic"
        self.phase = "idle"

    def serialize_state(self) -> Dict[str, Any]:
        return {
            "category_id": self.category_id,
            "phase": self.phase,
            "player_name": self.player_name or "",
        }

    def restore_state(self, state: Dict[str, Any]) -> None:
        category_id = str(state.get("category_id", "classic")).strip()
        self.category_id = category_id if category_id in CATEGORIES else "classic"
        self.phase = str(state.get("phase", "idle"))
        player_name = str(state.get("player_name", "")).strip()
        self.player_name = player_name or None

    def resume(self) -> AppResponse:
        if self.phase == "waiting_for_player":
            return AppResponse(
                text=f"Who is playing {self._category_label()} truth or dare?",
                expect_input=True,
                state=self.serialize_state(),
            )

        if self.phase == "waiting_for_choice":
            if self.player_name:
                prompt = f"{self.player_name}, truth or dare?"
            else:
                prompt = "Truth or dare?"
            return AppResponse(
                text=prompt,
                expect_input=True,
                state=self.serialize_state(),
            )

        return AppResponse(text="Truth or Dare is done.", done=True)

    def status_text(self) -> str:
        if self.phase == "waiting_for_player":
            return f"Truth or Dare ({self._category_label()}) is active and waiting for a player."
        if self.phase == "waiting_for_choice":
            if self.player_name:
                return f"Truth or Dare ({self._category_label()}) is active for {self.player_name}."
            return f"Truth or Dare ({self._category_label()}) is active and waiting for truth or dare."
        return "No app is active."

    def _extract_category(self, text: str) -> Optional[str]:
        lowered = text.lower()
        for category_id, data in CATEGORIES.items():
            for keyword in data["keywords"]:
                if keyword in lowered:
                    return category_id
        return None

    def _category_label(self) -> str:
        return str(CATEGORIES[self.category_id]["label"])

    def _truths(self) -> list[str]:
        return list(CATEGORIES[self.category_id]["truths"])

    def _dares(self) -> list[str]:
        return list(CATEGORIES[self.category_id]["dares"])

    def _extract_player_name(self, text: str) -> Optional[str]:
        match = re.search(r"for\s+([a-zA-ZăâîșțĂÂÎȘȚ]+)", text, re.IGNORECASE)
        if match:
            return match.group(1)
        return None
