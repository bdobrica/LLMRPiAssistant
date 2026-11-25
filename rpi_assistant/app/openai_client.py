"""OpenAI API client for transcription, app intent classification, and chat."""
import json
import hashlib
import uuid
from pathlib import Path
import time
from typing import TYPE_CHECKING, Any, Optional

from openai import OpenAI

from .playback import PlaybackStopped
from .privacy import private_audio
from .config import OpenAIConfig
from .timers import TIMER_TOOLS, TIMER_NAMES, TIMER_INSTRUCTIONS, timer_action
from .household import HOUSEHOLD_TOOLS, HOUSEHOLD_NAMES, HOUSEHOLD_MUTATIONS, household_instructions, household_action
from .web_lookup import LOOKUP_NAME, LOOKUP_TOOL, lookup, lookup_instructions, spoken_without_links, unavailable
from .weather import WEATHER_NAME, WEATHER_TOOL, LOCATION_NAME, LOCATION_TOOL

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
        self.client = OpenAI(
            api_key=config.api_key or "not-configured", timeout=config.request_timeout_seconds, max_retries=0,
        )
        self.mcp_manager = mcp_manager
        self.timers = None
        self.household = None
        self.weather = None
        self.conversation_history = []
        self.last_response_output_finished_at: Optional[float] = None
        self._initialize_conversation()
    
    def _initialize_conversation(self) -> None:
        """Initialize conversation with system prompt."""
        self.history_limited = False
        self.conversation_history = [
            {"role": "system", "content": self.config.system_prompt}
        ]
    
    def transcribe_audio(self, audio_file_path: str) -> str:
        """Transcribe a recorded audio file.
        
        Args:
            audio_file_path: Path to audio file (WAV, MP3, etc.).
        
        Returns:
            Transcribed text.
        
        Raises:
            Exception: If transcription fails.
        """
        if not self.config.api_key:
            raise RuntimeError("Set the OpenAI key on the local phone page before making voice requests")
        try:
            with open(audio_file_path, "rb") as audio_file:
                transcript = self.client.audio.transcriptions.create(
                    model=self.config.whisper_model,
                    file=audio_file,
                )
            return transcript.text
        except Exception as e:
            raise Exception(f"Audio transcription failed: {e}")
    
    def get_chat_response(self, user_message: str, *, continue_conversation: bool = False) -> tuple[str, dict]:
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
            if not continue_conversation:
                self._prepare_conversation_for(user_message)

            # Add user message to history
            self.conversation_history.append({"role": "user", "content": user_message})
            
            return self._chat_with_tools()
        except PlaybackStopped:
            raise
        except Exception as e:
            raise Exception(f"Chat completion failed: {e}")
        finally:
            self._close_unanswered_tool_calls()
            self._bound_history()

    def _close_unanswered_tool_calls(self) -> None:
        """Keep failed/interrupted tool rounds valid without repeating an action."""
        pending = {}
        for message in self.conversation_history:
            for call in message.get("tool_calls", []):
                pending[call["id"]] = True
            if message["role"] == "tool":
                pending.pop(message.get("tool_call_id"), None)
        for call_id in pending:
            self.conversation_history.append({
                "role": "tool", "tool_call_id": call_id,
                "content": '{"error":"Result unavailable; the action may already have run. Do not repeat it automatically."}',
            })

    def _bound_history(self, *, preparing_request: bool = False) -> None:
        """Evict whole oldest user turns, including their tool calls and results."""
        messages = self.conversation_history
        starts = [i for i, message in enumerate(messages) if message["role"] == "user"]
        if not starts:
            return
        ends = starts[1:] + [len(messages)]
        sizes = [len(json.dumps(messages[start:end], ensure_ascii=False).encode("utf-8"))
                 for start, end in zip(starts, ends)]
        total = sum(sizes)
        remove = 0
        while len(starts) - remove > 1 and (
            len(starts) - remove > self.config.conversation_max_turns
            or total > self.config.conversation_max_bytes
        ):
            total -= sizes[remove]
            remove += 1
        if remove:
            del messages[1:starts[remove]]
            self.history_limited = True
        if total > self.config.conversation_max_bytes:
            if preparing_request:
                # Never send an oversized tool round or resume it with missing evidence.
                raise RuntimeError("Current exchange exceeds the configured conversation size limit")
            self.conversation_history[1:] = [
                {"role": "user", "content": "[An earlier exchange exceeded the local history limit.]"},
                {"role": "assistant", "content": "Its details are unavailable. Actions may already have run; do not repeat them without an explicit new request."},
            ]
            self.history_limited = True

    def _check_cancelled(self):
        check = getattr(self, "cancel_check", None)
        if check is not None:
            check()

    def _completion_options(self, max_tokens: int, temperature: float) -> dict:
        options = {"max_completion_tokens": max_tokens, "temperature": temperature}
        if self.config.reasoning_effort:
            options["reasoning_effort"] = self.config.reasoning_effort
        return options

    def _chat_with_tools(self) -> tuple[str, dict]:
        manager = getattr(self, "mcp_manager", None)
        tools = list(manager.openai_tools()) if manager is not None else []
        max_rounds = manager.config.max_tool_rounds if manager is not None else 0
        weather = getattr(self, "weather", None)
        if weather is not None:
            tools.extend((WEATHER_TOOL, LOCATION_TOOL))
            max_rounds = max(max_rounds, 1)
        if self.config.web_search_enabled:
            tools.append(LOOKUP_TOOL)
            max_rounds = max(max_rounds, 1)
        timers = getattr(self, "timers", None)
        if timers is not None:
            tools.extend(TIMER_TOOLS)
            max_rounds = max(max_rounds, 3)
        household = getattr(self, "household", None)
        if household is not None:
            tools.extend(HOUSEHOLD_TOOLS)
            max_rounds = max(max_rounds, 3)
        user_texts = [m["content"] for m in self.conversation_history if m["role"] == "user" and isinstance(m.get("content"), str)]
        household_request_text = user_texts[-1] if user_texts else ""
        if household_request_text.strip().lower().rstrip('.!?') in ("first", "second", "first occurrence", "second occurrence"):
            household_request_text = " ".join(user_texts[-2:])
        timer_request = uuid.uuid4().hex
        usage = _empty_usage(self.config.chat_model)
        tool_rounds = 0

        while True:
            self._check_cancelled()
            self._bound_history(preparing_request=True)
            request = {
                "model": self.config.chat_model,
                "messages": [self.conversation_history[0],
                             {"role": "system", "content": lookup_instructions(self.config.web_search_enabled) + ("\n" + TIMER_INSTRUCTIONS if timers is not None else "") + ("\n" + household_instructions(household) if household is not None else "") + ("\n" + weather.instructions() if weather is not None else "")},
                             *self.conversation_history[1:]],
                **self._completion_options(self.config.max_tokens, self.config.temperature),
            }
            if self.history_limited:
                request["messages"][1]["content"] += (
                    "\nOlder exchanges have left the local context. Do not invent missing details "
                    "or assume an action was never executed because its receipt is absent. "
                    "Ask for clarification when needed; do not repeat actions without an explicit new request."
                )
            if tools and tool_rounds < max_rounds:
                request["tools"] = tools
                request["tool_choice"] = "auto"
            response = self.client.chat.completions.create(**request)
            self._check_cancelled()
            _add_usage(usage, response)
            message = response.choices[0].message
            tool_calls = list(getattr(message, "tool_calls", None) or [])
            if not tool_calls:
                content = message.content or ""
                usage["spoken_response"] = spoken_without_links(content)
                self.conversation_history.append({"role": "assistant", "content": content})
                return content, usage

            if tool_rounds >= max_rounds:
                raise RuntimeError("Tool round limit reached")

            self.conversation_history.append(_assistant_tool_message(message, tool_calls))
            if any(call.function.name in (LOOKUP_NAME, WEATHER_NAME, LOCATION_NAME) for call in tool_calls):
                return self._answer_lookup(tool_calls, usage)
            mutation_receipts = []
            blocked_actions = False
            storage_mutation = any((timers is not None and t.function.name in ("create_timer", "cancel_timer"))
                                   or (household is not None and t.function.name in HOUSEHOLD_MUTATIONS) for t in tool_calls)
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
                    try:
                        self._check_cancelled()
                    except PlaybackStopped:
                        result = json.dumps({"is_error": True, "error": "Cancelled before execution"})
                    else:
                        name = tool_call.function.name
                        if household is not None and name in HOUSEHOLD_NAMES:
                            key = timer_request + hashlib.sha256((name + json.dumps(arguments, sort_keys=True)).encode()).hexdigest()
                            receipt = household_action(household, name, arguments, key, household_request_text)
                            result = json.dumps(receipt)
                            if name in HOUSEHOLD_MUTATIONS or not receipt["ok"]:
                                mutation_receipts.append(receipt['message'])
                            if not receipt["ok"]:
                                storage_mutation = True
                        elif timers is not None and name in TIMER_NAMES:
                            key = timer_request + hashlib.sha256(json.dumps(arguments, sort_keys=True).encode()).hexdigest()
                            receipt = timer_action(timers, name, arguments, key)
                            result = json.dumps(receipt)
                            if name != "list_timers":
                                mutation_receipts.append(receipt['message'])
                        elif storage_mutation:
                            blocked_actions = True
                            result = json.dumps({"is_error":True, "error":"Local saved changes do not execute co-requested app actions."})
                        else:
                            result = manager.call_tool(name, arguments)
                self.conversation_history.append(
                    {"role": "tool", "tool_call_id": tool_call.id, "content": result}
                )
            if storage_mutation:
                answer = " ".join(mutation_receipts) or "I couldn't confirm that change. Please try again."
                if blocked_actions:
                    answer += " I haven't performed any other action."
                self.conversation_history.append({"role":"assistant", "content":answer})
                return answer, usage
            tool_rounds += 1

    def _answer_lookup(self, tool_calls, usage: dict) -> tuple[str, dict]:
        """Return one evidence/explicit location result; never dispatch co-requested actions."""
        evidence = None
        blocked_actions = False
        for call in tool_calls:
            if call.function.name in (LOOKUP_NAME, WEATHER_NAME, LOCATION_NAME) and evidence is None:
                try:
                    arguments = json.loads(call.function.arguments or "{}")
                    key = {WEATHER_NAME: "period", LOCATION_NAME: "city"}.get(call.function.name, "query")
                    query = arguments.get(key) if isinstance(arguments, dict) else None
                except (json.JSONDecodeError, TypeError):
                    query = None
                try:
                    self._check_cancelled()
                except PlaybackStopped:
                    evidence = unavailable("cancelled")
                else:
                    if call.function.name in (WEATHER_NAME, LOCATION_NAME):
                        weather = getattr(self, "weather", None)
                        action = weather.set_city if weather is not None and call.function.name == LOCATION_NAME else weather.lookup if weather is not None else None
                        evidence = action(query) if action is not None else unavailable("weather_disabled")
                    else:
                        evidence = (lookup(self.client, self.config, query) if self.config.web_search_enabled
                                    else unavailable("disabled"))
                # Only a bounded answer/source summary enters ordinary conversation.
                result = {key: evidence[key] for key in ("status", "answer", "sources", "retrieved_at")}
                result["untrusted_evidence"] = True
            else:
                blocked_actions |= call.function.name not in (LOOKUP_NAME, WEATHER_NAME)
                result = {"is_error": True, "error": "Only one lookup or explicit weather-city selection is allowed. Ask separately for another action."}
            self.conversation_history.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result)})
        answer, spoken = evidence["answer"], evidence["spoken_answer"]
        if blocked_actions:
            note = " I haven't performed any other action."
            answer += note
            spoken += note
        search_usage = evidence.get("usage", {})
        usage["prompt_tokens"] += search_usage.get("input_tokens", 0)
        usage["completion_tokens"] += search_usage.get("output_tokens", 0)
        usage["total_tokens"] += search_usage.get("total_tokens", 0)
        usage["lookup"] = evidence
        usage["spoken_response"] = spoken
        self.conversation_history.append({"role": "assistant", "content": answer})
        print(f"Current-information lookup: {evidence['status']}; cited sources: {len(evidence['sources'])}.")
        return answer, usage

    def mark_response_output_finished(self) -> None:
        """Record when the last response finished being presented to the user."""
        self.last_response_output_finished_at = time.time()

    def remember_app_response(self, user_message: str, response: str) -> None:
        """Retain an interrupted app's completed result without running its action again."""
        self.conversation_history.extend([
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": response},
        ])
        self._bound_history()

    def compact_conversation(self, reason: str) -> bool:
        """Discard inactive context; there is no archive retrieval service."""
        count = len(self.conversation_history) - 1
        if not count:
            return False
        self._initialize_conversation()
        print(f"Reset inactive chat context; discarded {count} messages.")
        return True

    def _prepare_conversation_for(self, user_message: str) -> None:
        if not self._has_active_chat_context():
            return

        if self._idle_timeout_exceeded():
            self.compact_conversation("idle_timeout")
            return

        if self.config.conversation_relevance_threshold <= 0:
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
                **self._completion_options(80, 0),
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or "{}"
            parsed = json.loads(content)
            return _clamp_float(parsed.get("relatedness"))
        except Exception as e:
            print(f"Conversation relevance check skipped ({type(e).__name__})")
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
                **self._completion_options(120, 0),
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
    
    def generate_speech(self, text: str, output_path: str, voice: str = "alloy") -> dict:
        """Write completed speech: WAV for Realtime, MP3 for legacy Speech API."""
        if self.config.tts_backend == "realtime":
            from .realtime_speech import generate_realtime_speech
            return generate_realtime_speech(self.config, text, output_path, voice)
        if self.config.tts_backend != "speech":
            raise ValueError("tts_backend must be realtime or speech")
        response = self.client.audio.speech.create(
            model=self.config.tts_model, voice=voice, input=text,
        )
        with private_audio(output_path):
            pass
        try:
            response.stream_to_file(output_path)
        except Exception:
            Path(output_path).unlink(missing_ok=True)
            raise
        return {}

    async def stream_speech(self, text, voice, write_pcm):
        from .realtime_speech import render_realtime_speech
        return await render_realtime_speech(self.config, text, voice, write_pcm)

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
        self.last_response_output_finished_at = None
        weather = getattr(self, "weather", None)
        if weather is not None:
            weather.pending_period = None


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
