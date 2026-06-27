"""OpenAI API client for transcription, app intent classification, and chat."""
import json
from pathlib import Path
from typing import Any, Optional

from openai import OpenAI

from .config import OpenAIConfig


class OpenAIClient:
    """Client for OpenAI API interactions."""
    
    def __init__(self, config: OpenAIConfig):
        """Initialize OpenAI client.
        
        Args:
            config: OpenAI configuration including API key.
        """
        self.config = config
        self.client = OpenAI(api_key=config.api_key)
        self.conversation_history = []
        self._initialize_conversation()
    
    def _initialize_conversation(self) -> None:
        """Initialize conversation with system prompt."""
        self.conversation_history = [
            {"role": "system", "content": self.config.system_prompt}
        ]
    
    def transcribe_audio(self, audio_file_path: str) -> str:
        """Transcribe audio file using Whisper.
        
        Args:
            audio_file_path: Path to audio file (WAV, MP3, etc.).
        
        Returns:
            Transcribed text.
        
        Raises:
            Exception: If transcription fails.
        """
        try:
            with open(audio_file_path, "rb") as audio_file:
                transcript = self.client.audio.transcriptions.create(
                    model=self.config.whisper_model,
                    file=audio_file,
                )
            return transcript.text
        except Exception as e:
            raise Exception(f"Whisper transcription failed: {e}")
    
    def get_chat_response(self, user_message: str) -> tuple[str, dict]:
        """Get chat completion response.
        
        Args:
            user_message: User's message to send.
        
        Returns:
            Tuple of (response_text, usage_dict) where usage_dict contains
            token counts and model info.
        
        Raises:
            Exception: If chat completion fails.
        """
        try:
            # Add user message to history
            self.conversation_history.append({"role": "user", "content": user_message})
            
            # Get completion
            response = self.client.chat.completions.create(
                model=self.config.chat_model,
                messages=self.conversation_history,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
            )
            
            # Extract response
            assistant_message = response.choices[0].message.content
            
            # Add assistant response to history
            self.conversation_history.append({"role": "assistant", "content": assistant_message})
            
            # Build usage info
            usage = {
                "model": self.config.chat_model,
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }
            
            return assistant_message, usage
        except Exception as e:
            raise Exception(f"Chat completion failed: {e}")

    def classify_app_intent(self, user_message: str, app_context: dict) -> tuple[Optional[dict], dict]:
        """Classify whether a transcription should be handled by the local app manager.

        The classifier is intentionally stateless and constrained to known app IDs so
        ambiguous ASR output can still route to local app commands without letting the
        general chat assistant answer on behalf of the app manager.
        """
        system_prompt = (
            "You classify voice assistant transcriptions into local app-manager intents. "
            "Return only JSON. Use only app IDs from the provided context. "
            "If the user is asking a normal general question, return intent none. "
            "Valid intents: none, list_installed, list_available, install_app, "
            "uninstall_app, upgrade_app, describe_app, list_versions, launch_app, "
            "resume_active, active_status, app_store_health, cancel. "
            "Schema: {\"intent\": string, \"app_id\": string|null, "
            "\"version\": string|null, \"raw_target\": string|null, "
            "\"confidence\": number}."
        )
        payload = {
            "transcription": user_message,
            "context": app_context,
        }

        try:
            response = self.client.chat.completions.create(
                model=self.config.chat_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(payload)},
                ],
                max_tokens=120,
                temperature=0,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or "{}"
            usage = _usage_dict(response, self.config.chat_model)
            parsed = json.loads(content)
            if not isinstance(parsed, dict):
                return None, usage
            return parsed, usage
        except Exception as e:
            raise Exception(f"App intent classification failed: {e}")
    
    def generate_speech(self, text: str, output_path: str, voice: str = "alloy") -> None:
        """Generate speech from text using OpenAI TTS.
        
        Args:
            text: Text to convert to speech.
            output_path: Path to save the audio file (MP3).
            voice: Voice to use (alloy, echo, fable, onyx, nova, shimmer).
        
        Raises:
            Exception: If TTS generation fails.
        """
        try:
            response = self.client.audio.speech.create(
                model=self.config.tts_model,
                voice=voice,
                input=text,
            )
            
            # Stream to file
            response.stream_to_file(output_path)
        except Exception as e:
            raise Exception(f"TTS generation failed: {e}")
    
    def process_voice_command(self, audio_file_path: str) -> tuple[str, str, dict]:
        """Complete pipeline: transcribe audio and get chat response.
        
        Args:
            audio_file_path: Path to recorded audio file.
        
        Returns:
            Tuple of (transcription, response, usage_dict).
        
        Raises:
            Exception: If transcription or chat completion fails.
        """
        # Transcribe audio
        transcription = self.transcribe_audio(audio_file_path)
        
        # Get chat response
        response, usage = self.get_chat_response(transcription)
        
        return transcription, response, usage
    
    def reset_conversation(self) -> None:
        """Reset conversation history, keeping only system prompt."""
        self._initialize_conversation()


def _usage_dict(response: Any, model: str) -> dict:
    usage = getattr(response, "usage", None)
    return {
        "model": model,
        "prompt_tokens": getattr(usage, "prompt_tokens", 0) if usage is not None else 0,
        "completion_tokens": getattr(usage, "completion_tokens", 0) if usage is not None else 0,
        "total_tokens": getattr(usage, "total_tokens", 0) if usage is not None else 0,
    }
