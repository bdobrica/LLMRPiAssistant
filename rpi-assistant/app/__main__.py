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
from pathlib import Path

from .audio import WakeWordRecorder
from .config import load_config
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
    
    def cleanup():
        """Cleanup resources before exit."""
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
        
        # Initialize LED pixels if available
        if PIXELS_AVAILABLE:
            try:
                pixels = Pixels()
                print("✨ LED pixels initialized")
            except Exception as e:
                print(f"⚠️  Could not initialize pixels: {e}")
                pixels = None
        
        print("=" * 60)
        print("🤖 RPI Voice Assistant")
        print("=" * 60)
        
        def on_recording_complete(audio_path: str):
            """Handle completed voice recording."""
            print("\n🔄 Processing voice command...")
            
            try:
                # Process voice command through OpenAI
                transcription, response, usage = openai_client.process_voice_command(audio_path)
                
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
                        wav_path = mp3_path.replace('.mp3', '.wav')
                        
                        openai_client.generate_speech(
                            text=response,
                            output_path=mp3_path,
                            voice=config.openai.tts_voice,
                        )
                        
                        # Convert MP3 to WAV with correct sample rate using ffmpeg
                        print("Converting audio format...")
                        subprocess.run(
                            [
                                "ffmpeg", "-y", "-i", mp3_path,
                                "-ar", "48000",  # Resample to 48kHz (common for audio output)
                                "-ac", "2",       # Stereo
                                "-sample_fmt", "s16",  # 16-bit signed
                                wav_path
                            ],
                            check=True,
                            capture_output=True,
                        )
                        
                        # Play the WAV audio using aplay
                        subprocess.run(
                            ["aplay", "-D", config.audio_output.device, wav_path],
                            check=True,
                            capture_output=True,
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
