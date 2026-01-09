"""RPI Voice Assistant - Main entry point.

A voice-controlled assistant using:
- OpenWakeWord for wake word detection
- OpenAI Whisper for speech transcription
- OpenAI GPT for intelligent responses
"""
import signal
import sys
from pathlib import Path

from .audio import WakeWordRecorder
from .config import load_config
from .logger import InteractionLogger
from .openai_client import OpenAIClient


def main():
    """Main application entry point."""
    recorder = None
    
    def cleanup():
        """Cleanup resources before exit."""
        if recorder is not None:
            print("\n🧹 Cleaning up audio resources...")
            recorder.stop()
    
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
