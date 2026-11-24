"""One voice turn, including local failure feedback and recovery."""

from pathlib import Path
import wave


class VoiceCommandHandler:
    def __init__(self, config, client, apps, logger, playback, rpiface, *, pixels=None, is_online=lambda: None):
        self.config = config
        self.client = client
        self.apps = apps
        self.logger = logger
        self.playback = playback
        self.rpiface = rpiface
        self.pixels = pixels
        self.is_online = is_online

    def process(self, audio_path: str, *, continue_conversation: bool = False) -> bool:
        """True permits a follow-up window only after a successful spoken answer."""
        stage = "transcription"
        print("\n🔄 Processing voice command...")
        try:
            transcription = self.client.transcribe_audio(audio_path).strip()
            if not transcription:
                self._feedback("unheard.wav")
                return False

            stage = "app routing"
            app_response = self.apps.handle(transcription)
            classifier_usage = None
            if app_response is None and self.apps.should_classify_app_intent(transcription):
                intent, classifier_usage = self.client.classify_app_intent(
                    transcription, self.apps.app_intent_context(),
                )
                if intent is not None:
                    app_response = self.apps.handle_classified_intent(intent, transcription)

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
                self.client.generate_speech(response, str(output), self.config.openai.tts_voice)
                if not output.is_file() or not output.stat().st_size:
                    raise RuntimeError("Speech output is empty")
                stage = "playback"
                self.rpiface.set_state("speaking")
                return self.playback.play(str(output), backend=self.config.openai.tts_backend)
            finally:
                output.unlink(missing_ok=True)
        except Exception as exc:
            message = f"{stage} failed ({type(exc).__name__})"
            print(f"\n⚠️ {message}")
            self.logger.log_error(message, {})
            self._feedback("offline.mp3" if self.is_online() is False else "request_failed.wav")
            return False
        finally:
            self.rpiface.set_state("idle")
            self.client.mark_response_output_finished()

    def _feedback(self, filename: str) -> None:
        """Local only: a failed provider is never used to explain its own failure."""
        try:
            self.rpiface.set_state("speaking")
            if self.pixels:
                self.pixels.speak()
            self.playback.prompt(filename)
        except Exception as exc:
            # A failed/missing speaker must still release the recording worker.
            print(f"Local feedback unavailable ({type(exc).__name__})")
        finally:
            if self.pixels:
                self.pixels.listen()
