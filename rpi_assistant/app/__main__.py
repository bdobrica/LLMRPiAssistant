"""RPI Voice Assistant - Main entry point.

A voice-controlled assistant using:
- OpenWakeWord for wake word detection
- OpenAI Whisper for speech transcription
- OpenAI GPT for intelligent responses
- OpenAI TTS for voice responses
"""
import signal
import subprocess
import sys
import threading
from pathlib import Path

from .app_manager import AppManager
from .app_repository import DEFAULT_APP_REPOSITORY_ROOTS
from .audio import WakeWordRecorder
from .config import load_config
from .connectivity import check_internet_connection
from .logger import InteractionLogger
from .openai_client import OpenAIClient

try:
    from .pixels import Pixels
    PIXELS_AVAILABLE = True
except ImportError:
    PIXELS_AVAILABLE = False
    print("Warning: Pixels library not available (requires apa102, gpiozero)")


def main():
    """Main application entry point."""
    recorder = None
    pixels = None
    connection_monitor_thread = None
    connection_state = {"online": None, "first_check": True}  # None = unknown, True = online, False = offline
    stop_monitor = threading.Event()

    def cleanup():
        """Cleanup resources before exit."""
        stop_monitor.set()
        if connection_monitor_thread is not None:
            connection_monitor_thread.join(timeout=2)
        if recorder is not None:
            print("\n🧹 Cleaning up audio resources...")
            recorder.stop()
        if pixels is not None:
            pixels.off()

    def signal_handler(signum, frame):
        """Handle termination signals."""
        print(f"\n📡 Received signal {signum}")
        cleanup()
        sys.exit(0)

    # Register signal handlers for clean shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Load configuration
        config = load_config()

        # Initialize components
        logger = InteractionLogger(config.logging)
        openai_client = OpenAIClient(config.openai)
        repository_roots: list[str | Path] = []
        if config.app_store.default_repository_url:
            repository_roots.append(config.app_store.default_repository_url)
        if config.app_store.use_local_repository_fallback:
            repository_roots.extend(DEFAULT_APP_REPOSITORY_ROOTS)
        app_manager = AppManager(
            repository_roots=repository_roots or None,
            repository_public_key=config.app_store.trusted_public_key,
            require_repository_signature=config.app_store.require_signature,
        )

        # Initialize LED pixels if available
        if PIXELS_AVAILABLE:
            try:
                pixels = Pixels(num_pixels=config.led.count)
                print(f"✨ LED pixels initialized ({config.led.count} LEDs)")
            except Exception as e:
                print(f"⚠️  Could not initialize pixels: {e}")
                pixels = None

        print("=" * 60)
        print("🤖 RPI Voice Assistant")
        print("=" * 60)

        def play_audio_prompt(filename: str):
            """Play a pre-generated audio prompt."""
            if not config.audio_output.enabled:
                return

            prompt_path = Path(__file__).parent / "audio_prompts" / filename
            if not prompt_path.exists():
                print(f"⚠️  Audio prompt not found: {prompt_path}")
                return

            try:
                subprocess.run(
                    ["mpg123", "-a", config.audio_output.device, str(prompt_path)],
                    capture_output=True,
                    check=True
                )
            except subprocess.CalledProcessError as e:
                print(f"⚠️  Error playing audio prompt: {e}")

        def monitor_connection():
            """Monitor internet connection and handle state changes."""
            while not stop_monitor.is_set():
                is_online = check_internet_connection(timeout=3)

                # Check if state changed
                if connection_state["online"] != is_online:
                    was_offline = connection_state["online"] is False
                    connection_state["online"] = is_online

                    if is_online:
                        if was_offline and not connection_state["first_check"]:
                            # Was offline, now online - announce return
                            print("\n✅ Internet connection restored!")
                            if pixels:
                                pixels.listen()
                            play_audio_prompt("online.mp3")
                        elif connection_state["first_check"]:
                            # First check and online - don't announce
                            print("✅ Internet connection OK")
                            if pixels:
                                pixels.listen()
                    else:
                        # Lost connection
                        print("\n⚠️  Internet connection lost!")
                        if pixels:
                            pixels.offline()
                        if not connection_state["first_check"]:
                            play_audio_prompt("offline.mp3")

                    connection_state["first_check"] = False

                # Check every 10 seconds
                stop_monitor.wait(10)

        # Start connection monitoring thread
        connection_monitor_thread = threading.Thread(target=monitor_connection, daemon=True)
        connection_monitor_thread.start()

        def on_recording_complete(audio_path: str):
            """Handle completed voice recording."""
            print("\n🔄 Processing voice command...")

            try:
                transcription = openai_client.transcribe_audio(audio_path)
                app_response = app_manager.handle(transcription)

                if app_response is not None:
                    response = app_response.text
                    usage = {
                        "model": "local_app",
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0,
                    }
                else:
                    response, usage = openai_client.get_chat_response(transcription)

                # Log the interaction
                audio_file = Path(audio_path)
                duration = None
                if audio_file.exists():
                    import wave

                    with wave.open(str(audio_file), 'rb') as wf:
                        duration = wf.getnframes() / wf.getframerate()

                logger.log_complete_interaction(
                    audio_path,
                    transcription,
                    response,
                    usage,
                    duration
                )

                # Display results
                print(f"\n📝 You said: \"{transcription}\"")
                print(f"\n💬 Assistant: {response}")
                print(f"\n📊 Tokens: {usage['total_tokens']} "
                      f"(prompt: {usage['prompt_tokens']}, "
                      f"completion: {usage['completion_tokens']})")

                # Generate and play TTS response
                if config.audio_output.enabled:
                    try:
                        print("\n🔊 Generating speech...")
                        if pixels:
                            pixels.speak()

                        # Generate TTS as MP3
                        mp3_path = config.audio_output.tts_output_path

                        openai_client.generate_speech(
                            text=response,
                            output_path=mp3_path,
                            voice=config.openai.tts_voice,
                        )

                        # Play the MP3 audio using mpg123
                        result = subprocess.run(
                            ["mpg123", "-a", config.audio_output.device, mp3_path],
                            capture_output=True,
                            text=True,
                        )

                        if result.returncode != 0:
                            print(f"mpg123 stderr: {result.stderr}")
                            print(f"mpg123 stdout: {result.stdout}")
                            raise subprocess.CalledProcessError(
                                result.returncode,
                                result.args,
                                result.stdout,
                                result.stderr,
                            )

                        if pixels:
                            pixels.listen()
                    except Exception as e:
                        print(f"\n⚠️  TTS playback error: {e}")
                        if pixels:
                            pixels.listen()

                print("\n" + "=" * 60)
                print("Listening for wake word...\n")

            except Exception as e:
                error_msg = f"Error processing command: {e}"
                print(f"\n❌ {error_msg}\n")
                logger.log_error(error_msg, {"audio_file": audio_path})

        # Start wake word recorder
        recorder = WakeWordRecorder(
            config.audio,
            config.wake_word,
            config.recording,
            on_recording_complete=on_recording_complete,
            pixels=pixels,
        )

        recorder.start()

    except KeyboardInterrupt:
        print("\n\n👋 Shutting down...")
        cleanup()
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        cleanup()
        sys.exit(1)
    finally:
        # Ensure cleanup happens even if exception wasn't caught
        cleanup()


if __name__ == "__main__":
    main()
