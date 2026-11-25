"""One voice turn, including local failure feedback and recovery."""

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

    def process(self, audio_path: str, *, continue_conversation: bool = False) -> bool:
        """True permits a follow-up window only after a successful spoken answer."""
        stage = "transcription"
        print("\n🔄 Processing voice command...")
        app_response = None
        response = ""
        turn_started = False
        generation = None
        self.turn_generation = None
        try:
            if self.controls:
                generation = self.controls.begin_turn()
                self.turn_generation = generation
                turn_started = True
            transcription = self.client.transcribe_audio(audio_path).strip()
            self._check_cancelled()
            if not transcription:
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
                app_response = self.apps.handle(transcription)
                classifier_usage = None
                if app_response is None and self.apps.should_classify_app_intent(transcription):
                    intent, classifier_usage = self.client.classify_app_intent(
                        transcription, self.apps.app_intent_context(),
                    )
                    self._check_cancelled()
                    if intent is not None:
                        app_response = self.apps.handle_classified_intent(intent, transcription)

                self._check_cancelled()
                stage = "answer"
                if app_response is not None:
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
            print(f'\n📝 You said: "{transcription}"')
            print(f"\n💬 Assistant: {response}")
            print(f"\n📊 Tokens: {usage['total_tokens']}")

            if not self.config.audio_output.enabled:
                return False
            stage = "speech"
            print("\n🔊 Generating speech...")
            if self.pixels:
                self.pixels.speak()
            output = Path(self.config.audio_output.tts_output_path)
            # Clear the preceding answer before generation, including legacy Speech output.
            output.unlink(missing_ok=True)
            try:
                self.client.generate_speech(usage.get("spoken_response", response), str(output), self.config.openai.tts_voice)
                if not output.is_file() or not output.stat().st_size:
                    raise RuntimeError("Speech output is empty")
                self._check_cancelled()
                stage = "playback"
                self.rpiface.set_state("speaking")
                options = {"expected_generation": generation} if self.controls else {}
                return self.playback.play(str(output), backend=self.config.openai.tts_backend, interruptible=True, **options)
            finally:
                output.unlink(missing_ok=True)
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
            message = f"{stage} failed ({type(exc).__name__})"
            print(f"\n⚠️ {message}")
            self.logger.log_error(message, {})
            if self.controls and self.controls.cancelled.is_set():
                return False
            self._feedback("offline.mp3" if self.is_online() is False else "request_failed.wav")
            return False
        finally:
            self.rpiface.set_state("idle")
            self.client.mark_response_output_finished()
            if self.controls and turn_started:
                self.controls.end_turn()

    def _check_cancelled(self):
        if self.controls:
            self.controls.check()

    def _feedback(self, filename: str) -> None:
        """Local only: a failed provider is never used to explain its own failure."""
        try:
            self.rpiface.set_state("speaking")
            if self.pixels:
                self.pixels.speak()
            options = {"expected_generation": self.turn_generation} if self.controls else {}
            self.playback.prompt(filename, **options)
        except Exception as exc:
            # A failed/missing speaker must still release the recording worker.
            print(f"Local feedback unavailable ({type(exc).__name__})")
        finally:
            if self.pixels:
                self.pixels.listen()
