"""A three-question voice quiz. Only the current round is saved."""

import random
import re
from typing import NamedTuple

from rpi_assistant.app.apps.base import AppResponse, VoiceApp


class Question(NamedTuple):
    prompt: str
    choices: tuple[str, str]
    correct: int
    reveal: str


QUESTIONS = {
    "tracks": Question("Who left tracks on the Moon, a person or a dinosaur?",
                       ("person", "dinosaur"), 0, "A person. With no wind or rain on the Moon, those boot prints can last for ages."),
    "hearts": Question("Which has three hearts, an octopus or a shark?",
                       ("octopus", "shark"), 0, "An octopus. Two hearts pump blood to its gills and one pumps it to the rest of its body."),
    "watch": Question("In a quartz watch, what vibrates to keep time, a spring or a crystal?",
                      ("spring", "crystal"), 1, "A crystal. The circuit counts its tiny vibrations to measure a second."),
    "planet": Question("Which planet spins on its side, Mars or Uranus?",
                       ("mars", "uranus"), 1, "Uranus. Its spin axis tips so far over that its poles take turns facing the Sun."),
    "strings": Question("Inside a piano, what strikes the strings, hammers or wheels?",
                        ("hammers", "wheels"), 0, "Hammers. Press a key slowly and you can feel the mechanism that sends one flying."),
    "compass": Question("Which part of a compass is a magnet, the case or the needle?",
                        ("case", "needle"), 1, "The needle. Earth's magnetic field turns it, even without a battery."),
}
ROUND_SIZE = 3
POSITION_ANSWERS = {
    "one": 0, "1": 0, "first": 0, "first one": 0, "option one": 0, "option 1": 0,
    "two": 1, "2": 1, "second": 1, "second one": 1, "option two": 1, "option 2": 1,
}


def choice_index(phrase: str, question: Question) -> int | None:
    phrase = re.sub(r"^(?:my (?:final )?(?:answer|guess) is |i think |i'll go with )", "", phrase)
    phrase = re.sub(r"^(?:it's |it is )", "", phrase)
    phrase = re.sub(r"^(?:an? |the )", "", phrase).removesuffix(" please")
    if phrase in question.choices:
        return question.choices.index(phrase)
    return POSITION_ANSWERS.get(phrase)


def final_choice(words: str, question: Question) -> int | None:
    words = re.sub(r"^(?:hey )?jarvis ", "", words)
    words = re.sub(r" (?:let's|let us) continue (?:playing )?trivia$", "", words)
    words = re.sub(r" (?:that's|that is) my (?:answer|guess)$", "", words)
    # Only discard a prior guess if it was a choice followed by a correction.
    # Quoted, conditional or unresolved alternatives should leave the score alone.
    parts = re.split(r"\b(?:i changed my mind|i've changed my mind|on second thought|actually|i mean|no wait)\b",
                     words)
    for earlier in parts[:-1]:
        earlier = earlier.strip().removesuffix(" but").removeprefix("i was going to say ")
        if earlier and choice_index(earlier, question) is None:
            return None
    return choice_index(parts[-1].strip(), question)


class TriviaApp(VoiceApp):
    def __init__(self):
        self.stop()

    def stop(self) -> None:
        self.round: list[str] = []
        self.position = 0
        self.score = 0
        self.paused = False

    def start(self, text: str) -> AppResponse:
        self.stop()
        self.round = random.sample(list(QUESTIONS), ROUND_SIZE)
        return self._prompt("Three quick questions. Say either choice.")

    def _prompt(self, lead: str = "") -> AppResponse:
        question = QUESTIONS[self.round[self.position]]
        return AppResponse(text=f"{lead} Question {self.position + 1}. {question.prompt}".strip(),
                           expect_input=True)

    def handle(self, text: str) -> AppResponse:
        words = " ".join(re.findall(r"[a-z0-9']+", text.lower().replace("’", "'")))
        if words in {"stop trivia", "quit trivia", "quit"}:
            return AppResponse(text="Thanks for playing.", done=True)
        if not self.round:
            return AppResponse(text="That round is over. Say play trivia for a new one.", done=True)
        if words in {"resume", "resume trivia", "continue", "continue trivia"}:
            return self.resume()
        if words in {"pause", "pause game", "pause trivia"} or self.paused:
            self.paused = True
            return AppResponse(text="Trivia paused. Say resume game to pick up here, or stop game to leave.")
        if words in {"repeat", "repeat the question", "say that again"}:
            return self._prompt()

        question = QUESTIONS[self.round[self.position]]
        choice = final_choice(words, question)
        if choice is None:
            reply = self._prompt("Could you repeat your choice?")
            # Set after construction so this signed bundle also runs on older hosts.
            reply.retry_input = True
            return reply

        matched = choice == question.correct
        self.score += int(matched)
        self.position += 1
        feedback = ("That's right! " if matched else "Good guess. ") + question.reveal
        if self.position == ROUND_SIZE:
            return AppResponse(text=f"{feedback} You scored {self.score} out of {ROUND_SIZE}.", done=True)
        return self._prompt(feedback)

    def resume(self) -> AppResponse:
        if not self.round:
            return AppResponse(text="That round is over. Say play trivia for a new one.", done=True)
        self.paused = False
        return self._prompt()

    def status_text(self) -> str:
        status = "paused" if self.paused else "waiting for your guess"
        return f"Trivia is {status} on question {self.position + 1} of {ROUND_SIZE}."

    def serialize_state(self) -> dict:
        return {"round": list(self.round), "position": self.position, "score": self.score, "paused": self.paused}

    def restore_state(self, state: dict) -> None:
        self.stop()
        ids = state.get("round")
        position, score, paused = state.get("position"), state.get("score"), state.get("paused")
        if (isinstance(ids, list) and len(ids) == ROUND_SIZE
                and all(isinstance(key, str) and key in QUESTIONS for key in ids)
                and len(set(ids)) == ROUND_SIZE
                and type(position) is int and type(score) is int and 0 <= score <= position < ROUND_SIZE
                and isinstance(paused, bool)):
            self.round, self.position, self.score, self.paused = list(ids), position, score, paused
