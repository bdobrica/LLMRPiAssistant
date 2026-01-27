"""Logging for OpenAI interactions."""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import LoggingConfig


class InteractionLogger:
    """Logger for tracking OpenAI API interactions."""
    
    def __init__(self, config: LoggingConfig):
        """Initialize interaction logger.
        
        Args:
            config: Logging configuration.
        """
        self.config = config
        self.log_file = Path(config.log_file)
        
        # Set up Python logger
        self.logger = logging.getLogger("openai_interactions")
        self.logger.setLevel(getattr(logging, config.log_level.upper()))
        
        # File handler for structured logs
        if not self.logger.handlers:
            handler = logging.FileHandler(config.log_file)
            handler.setFormatter(logging.Formatter("%(message)s"))
            self.logger.addHandler(handler)
    
    def log_transcription(
        self,
        audio_file: str,
        transcription: str,
        model: str = "whisper-1",
        duration_seconds: Optional[float] = None,
    ) -> None:
        """Log audio transcription.
        
        Args:
            audio_file: Path to audio file.
            transcription: Transcribed text.
            model: Whisper model used.
            duration_seconds: Audio duration in seconds.
        """
        entry = {
            "timestamp": datetime.now().isoformat(),
            "type": "transcription",
            "model": model,
            "audio_file": audio_file,
            "transcription": transcription,
        }
        
        if duration_seconds is not None:
            entry["duration_seconds"] = round(duration_seconds, 2)
        
        self.logger.info(json.dumps(entry))
    
    def log_chat_completion(
        self,
        user_message: str,
        assistant_response: str,
        usage: dict,
    ) -> None:
        """Log chat completion interaction.
        
        Args:
            user_message: User's input message.
            assistant_response: Assistant's response.
            usage: Usage information including token counts.
        """
        entry = {
            "timestamp": datetime.now().isoformat(),
            "type": "chat_completion",
            "model": usage.get("model", "unknown"),
            "user_message": user_message,
            "assistant_response": assistant_response,
            "usage": {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            }
        }
        
        self.logger.info(json.dumps(entry))
    
    def log_complete_interaction(
        self,
        audio_file: str,
        transcription: str,
        assistant_response: str,
        usage: dict,
        duration_seconds: Optional[float] = None,
    ) -> None:
        """Log complete voice interaction (transcription + chat).
        
        Args:
            audio_file: Path to audio file.
            transcription: Transcribed text.
            assistant_response: Assistant's response.
            usage: Usage information from chat completion.
            duration_seconds: Audio duration in seconds.
        """
        entry = {
            "timestamp": datetime.now().isoformat(),
            "type": "voice_interaction",
            "audio_file": audio_file,
            "transcription": transcription,
            "assistant_response": assistant_response,
            "chat_model": usage.get("model", "unknown"),
            "usage": {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            }
        }
        
        if duration_seconds is not None:
            entry["audio_duration_seconds"] = round(duration_seconds, 2)
        
        self.logger.info(json.dumps(entry))
    
    def log_error(self, error_message: str, context: Optional[dict] = None) -> None:
        """Log error.
        
        Args:
            error_message: Error message.
            context: Additional context information.
        """
        entry = {
            "timestamp": datetime.now().isoformat(),
            "type": "error",
            "error": error_message,
        }
        
        if context:
            entry["context"] = context
        
        self.logger.error(json.dumps(entry))
    
    def get_log_summary(self, last_n: int = 10) -> list[dict]:
        """Get summary of recent log entries.
        
        Args:
            last_n: Number of recent entries to return.
        
        Returns:
            List of log entry dictionaries.
        """
        if not self.log_file.exists():
            return []
        
        entries = []
        with open(self.log_file, 'r') as f:
            for line in f:
                try:
                    entries.append(json.loads(line.strip()))
                except json.JSONDecodeError:
                    continue
        
        return entries[-last_n:]
