"""OpenAI API client for transcription and chat completion."""
from pathlib import Path
from typing import Optional

import numpy as np
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
        self.retrieved_memories = None  # Store retrieved memories for this session
        self._initialize_conversation()
    
    def _initialize_conversation(self) -> None:
        """Initialize conversation with system prompt."""
        self.conversation_history = [
            {"role": "system", "content": self.config.system_prompt}
        ]
        # If we have retrieved memories, add them to the context
        if self.retrieved_memories:
            self.conversation_history.append({
                "role": "system", 
                "content": self.retrieved_memories
            })
    
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
    
    def set_retrieved_memories(self, memories_text: Optional[str]) -> None:
        """Set retrieved memories for the current session.
        
        Args:
            memories_text: Formatted memory text to inject into context.
        """
        self.retrieved_memories = memories_text
    
    def embed_text(self, text: str, model: str = "text-embedding-3-small") -> np.ndarray:
        """Generate embedding for text using OpenAI.
        
        Args:
            text: Text to embed.
            model: Embedding model to use.
        
        Returns:
            Embedding vector as numpy array.
        
        Raises:
            Exception: If embedding generation fails.
        """
        try:
            response = self.client.embeddings.create(
                model=model,
                input=text,
            )
            # Convert to numpy array
            embedding = np.array(response.data[0].embedding, dtype=np.float32)
            return embedding
        except Exception as e:
            raise Exception(f"Embedding generation failed: {e}")
    
    def summarize_conversation(self, turns: list[dict]) -> str:
        """Generate a summary of conversation turns.
        
        Args:
            turns: List of conversation turns with 'role' and 'text' keys.
        
        Returns:
            Summary text.
        
        Raises:
            Exception: If summarization fails.
        """
        if not turns:
            return ""
        
        # Build conversation text
        conv_text = "\n".join([f"{t['role']}: {t['text']}" for t in turns])
        
        # Create summarization prompt
        prompt = f"""Summarize the following conversation in 3-5 concise bullet points. 
Focus on:
- User's goals or requests
- Key information provided
- Any preferences or commitments made
- Unresolved tasks or questions

Conversation:
{conv_text}

Summary (bullet points):"""
        
        try:
            response = self.client.chat.completions.create(
                model=self.config.chat_model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that creates concise conversation summaries."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=300,
                temperature=0.3,
            )
            
            summary = response.choices[0].message.content.strip()
            return summary
        except Exception as e:
            raise Exception(f"Conversation summarization failed: {e}")

