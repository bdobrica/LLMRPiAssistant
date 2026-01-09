"""OpenAI API client for transcription and chat completion."""
from pathlib import Path
from typing import Optional

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
