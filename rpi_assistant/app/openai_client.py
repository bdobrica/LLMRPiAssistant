"""OpenAI API client for transcription, app intent classification, and chat."""
import json
from pathlib import Path
import time
from typing import TYPE_CHECKING, Any, Optional

from openai import OpenAI

from .config import OpenAIConfig

if TYPE_CHECKING:
    from .mcp_manager import MCPClientManager


class OpenAIClient:
    """Client for OpenAI API interactions."""
    
    def __init__(self, config: OpenAIConfig, mcp_manager: "MCPClientManager | None" = None):
        """Initialize OpenAI client.
        
        Args:
            config: OpenAI configuration including API key.
        """
        self.config = config
        self.client = OpenAI(api_key=config.api_key)
        self.mcp_manager = mcp_manager
        self.conversation_history = []
        self.compacted_contexts = []
        self.last_response_output_finished_at: Optional[float] = None
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
            self._prepare_conversation_for(user_message)

            # Add user message to history
            self.conversation_history.append({"role": "user", "content": user_message})
            
            return self._chat_with_tools()
        except Exception as e:
            raise Exception(f"Chat completion failed: {e}")

    def _chat_with_tools(self) -> tuple[str, dict]:
        manager = getattr(self, "mcp_manager", None)
        tools = manager.openai_tools() if manager is not None else []
        max_rounds = manager.config.max_tool_rounds if manager is not None else 0
        usage = _empty_usage(self.config.chat_model)
        tool_rounds = 0

        while True:
            request = {
                "model": self.config.chat_model,
                "messages": self.conversation_history,
                "max_tokens": self.config.max_tokens,
                "temperature": self.config.temperature,
            }
            if tools and tool_rounds < max_rounds:
                request["tools"] = tools
                request["tool_choice"] = "auto"
            response = self.client.chat.completions.create(**request)
            _add_usage(usage, response)
            message = response.choices[0].message
            tool_calls = list(getattr(message, "tool_calls", None) or [])
            if not tool_calls:
                content = message.content or ""
                self.conversation_history.append({"role": "assistant", "content": content})
                return content, usage

            self.conversation_history.append(_assistant_tool_message(message, tool_calls))
            for tool_call in tool_calls:
                try:
                    arguments = json.loads(tool_call.function.arguments or "{}")
                    if not isinstance(arguments, dict):
                        raise TypeError("tool arguments must be an object")
                except (json.JSONDecodeError, TypeError):
                    result = json.dumps(
                        {"is_error": True, "error": "Invalid tool arguments"}
                    )
                else:
                    result = manager.call_tool(tool_call.function.name, arguments)
                self.conversation_history.append(
                    {"role": "tool", "tool_call_id": tool_call.id, "content": result}
                )
            tool_rounds += 1

    def mark_response_output_finished(self) -> None:
        """Record when the last response finished being presented to the user."""
        self.last_response_output_finished_at = time.time()

    def compact_conversation(self, reason: str) -> bool:
        """Archive active chat turns for future retrieval and reset chat context."""
        messages = self.conversation_history[1:]
        if not messages:
            return False

        self.compacted_contexts.append(
            {
                "reason": reason,
                "created_at": time.time(),
                "messages": [dict(message) for message in messages],
                "vector_store_status": "pending",
            }
        )
        self._initialize_conversation()
        print(f"Compacted chat context ({reason}); archived {len(messages)} messages.")
        return True

    def _prepare_conversation_for(self, user_message: str) -> None:
        if not self._has_active_chat_context():
            return

        if self._idle_timeout_exceeded():
            self.compact_conversation("idle_timeout")
            return

        relevance_score = self._conversation_relevance_score(user_message)
        if relevance_score is None:
            return
        if relevance_score < self.config.conversation_relevance_threshold:
            self.compact_conversation(f"low_relevance:{relevance_score:.2f}")

    def _has_active_chat_context(self) -> bool:
        return len(self.conversation_history) > 1

    def _idle_timeout_exceeded(self) -> bool:
        timeout = self.config.conversation_idle_timeout_seconds
        if timeout <= 0 or self.last_response_output_finished_at is None:
            return False
        return (time.time() - self.last_response_output_finished_at) >= timeout

    def _conversation_relevance_score(self, user_message: str) -> Optional[float]:
        history = self.conversation_history[1:]
        if not history:
            return None

        system_prompt = (
            "Estimate whether the current user message depends on or continues the "
            "prior chat history. Return only JSON using schema "
            "{\"relatedness\": number, \"reason\": string}. "
            "Use 0 for unrelated and 1 for clearly dependent on prior context."
        )
        payload = {
            "current_user_message": user_message,
            "prior_messages": history[-8:],
        }

        try:
            response = self.client.chat.completions.create(
                model=self.config.chat_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(payload)},
                ],
                max_tokens=80,
                temperature=0,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or "{}"
            parsed = json.loads(content)
            return _clamp_float(parsed.get("relatedness"))
        except Exception as e:
            print(f"⚠️  Conversation relevance check skipped: {e}")
            return None

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


def _empty_usage(model: str) -> dict:
    return {
        "model": model,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }


def _add_usage(total: dict, response: Any) -> None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        total[key] += getattr(usage, key, 0) or 0


def _assistant_tool_message(message: Any, tool_calls: list[Any]) -> dict:
    return {
        "role": "assistant",
        "content": message.content,
        "tool_calls": [
            {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.function.name,
                    "arguments": call.function.arguments,
                },
            }
            for call in tool_calls
        ],
    }


def _clamp_float(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, number))
