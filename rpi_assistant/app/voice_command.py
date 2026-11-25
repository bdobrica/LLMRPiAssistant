"""One voice turn, including local failure feedback and recovery."""

import re
from pathlib import Path
import wave

from .playback import PlaybackInterrupted, PlaybackStopped
from .controls import voice_control


class VoiceCommandHandler:
    def __init__(self, config, client, apps, logger, playback, rpiface, *, pixels=None, is_online=lambda: None, controls=None):
        self.config = config
        self.client = client
        self.apps = apps
        self.logger = logger
        self.playback = playback
        self.rpiface = rpiface
        self.pixels = pixels
        self.is_online = is_online
        self.controls = controls
        self.awaiting_app = None
        self.game_repeats = 0

    def process(self, audio_path: str, *, continue_conversation: bool = False) -> bool:
        """True opens a follow-up after an answer or a successfully played retry prompt."""
        stage = "transcription"
        print("\n🔄 Processing voice command...")
        app_response = None
        response = ""
        turn_started = False
        generation = None
        self.turn_generation = None
        waiting = self.awaiting_app
        self.awaiting_app = None
        if not continue_conversation:
            self.game_repeats = 0
        try:
            if self.controls:
                generation = self.controls.begin_turn()
                self.turn_generation = generation
                turn_started = True
            transcription = self.client.transcribe_audio(audio_path).strip()
            self._check_cancelled()
            if not transcription:
                if waiting is not None and waiting is self.apps.active_app and self._allow_game_retry():
                    if self._feedback("game_repeat.wav"):
                        self.awaiting_app = waiting
                        return True
                    return False
                self._feedback("unheard.wav")
                return False

            control = voice_control(transcription) if self.controls else None
            if control:
                response = self.controls.command(*control)
                if response is None:
                    if control[0] == "new_conversation":
                        # New context takes effect in end_turn; acknowledge locally.
                        self.playback.prompt("new_conversation.wav", expected_generation=self.playback.generation)
                    return False  # Stop/mute/reset use local state feedback, never another cloud call.
                usage = {"model": "local_control", "total_tokens": 0}
            else:
                stage = "app routing"
                timer_request = self.controls and ((self.controls.timers and re.search(r"\btimers?\b", transcription, re.I)) or (self.controls.household and re.search(r"\b(remind|reminders?|shopping|groceries|grocery)\b", transcription, re.I)))
                app_response = None if timer_request else self.apps.handle(transcription)
                classifier_usage = None
                if not timer_request and app_response is None and self.apps.should_classify_app_intent(transcription):
                    intent, classifier_usage = self.client.classify_app_intent(
                        transcription, self.apps.app_intent_context(),
                    )
                    self._check_cancelled()
                    if intent is not None:
                        app_response = self.apps.handle_classified_intent(intent, transcription)

                self._check_cancelled()
                stage = "answer"
                if app_response is not None:
                    if getattr(app_response, "retry_input", False):
                        if not self._allow_game_retry():
                            self._feedback("unheard.wav")
                            return False
                    else:
                        self.game_repeats = 0
                    response = app_response.text
                    usage = {
                        "model": "local_app" if classifier_usage is None else f"local_app via {classifier_usage['model']}",
                        **{key: classifier_usage[key] if classifier_usage else 0
                           for key in ("prompt_tokens", "completion_tokens", "total_tokens")},
                    }
                else:
                    response, usage = self.client.get_chat_response(
                        transcription, continue_conversation=continue_conversation,
                    )
            self._check_cancelled()
            if not response.strip():
                raise RuntimeError("No answer was returned")

            duration = None
            if Path(audio_path).exists():
                with wave.open(audio_path, "rb") as audio:
                    duration = audio.getnframes() / audio.getframerate()
            self.logger.log_complete_interaction(audio_path, transcription, response, usage, duration)
            print("Voice answer ready.")

            if not self.config.audio_output.enabled:
                return False
            stage = "speech"
            print("\n🔊 Generating speech...")
            if self.pixels:
                self.pixels.speak()
            spoken = usage.get("spoken_response", response)
            options = {"expected_generation": generation} if self.controls else {}
            if self.config.openai.tts_backend == "realtime" and self.config.audio_output.stream_realtime:
                self.rpiface.set_state("speaking")
                played = self.playback.play_stream(
                    lambda sink: self.client.stream_speech(spoken, self.config.openai.tts_voice, sink),
                    timeout=self.config.openai.tts_timeout_seconds + 125, **options,
                )
            else:
                output = Path(self.config.audio_output.tts_output_path)
                output.unlink(missing_ok=True)
                self.client.generate_speech(spoken, str(output), self.config.openai.tts_voice)
                if not output.is_file() or not output.stat().st_size:
                    raise RuntimeError("Speech output is empty")
                self._check_cancelled()
                stage = "playback"
                self.rpiface.set_state("speaking")
                played = self.playback.play(str(output), backend=self.config.openai.tts_backend, interruptible=True, **options)
            if played and getattr(app_response, "expect_input", False):
                self.awaiting_app = self.apps.active_app
            return played
        except PlaybackStopped:
            if app_response is not None:
                self.client.remember_app_response(transcription, app_response.text)
            return False
        except PlaybackInterrupted:
            # Actions already ran before playback. Keep their result for the correction,
            # without invoking app routing, tools, generation or playback again.
            if app_response is not None:
                self.client.remember_app_response(transcription, response)
            print("Answer interrupted; preparing to listen for a correction.")
            raise
        except Exception as exc:
            if app_response is not None and stage in ("speech", "playback"):
                self.client.remember_app_response(transcription, response)
            message = f"{stage} failed ({type(exc).__name__})"
            print(f"\n⚠️ {message}")
            self.logger.log_error(message, {})
            if self.controls and self.controls.cancelled.is_set():
                return False
            self._feedback("offline.mp3" if self.is_online() is False else "request_failed.wav")
            return False
        finally:
            for path in (Path(audio_path), Path(self.config.audio_output.tts_output_path)):
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    print("Temporary voice audio cleanup failed; check storage permissions.")
            self.rpiface.set_state("idle")
            self.client.mark_response_output_finished()
            if self.controls and turn_started:
                self.controls.end_turn()

    def _check_cancelled(self):
        if self.controls:
            self.controls.check()

    def _allow_game_retry(self) -> bool:
        recording = self.config.recording
        if recording.follow_up_window_seconds <= 0 or self.game_repeats >= recording.game_answer_retries:
            return False
        self.game_repeats += 1
        return True

    def _feedback(self, filename: str) -> bool:
        """Local only: a failed provider is never used to explain its own failure."""
        try:
            self.rpiface.set_state("speaking")
            if self.pixels:
                self.pixels.speak()
            options = {"expected_generation": self.turn_generation} if self.controls else {}
            return self.playback.prompt(filename, **options)
        except Exception as exc:
            # A failed/missing speaker must still release the recording worker.
            print(f"Local feedback unavailable ({type(exc).__name__})")
            return False
        finally:
            if self.pixels:
                self.pixels.listen()
