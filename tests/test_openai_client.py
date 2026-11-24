import json
import time
import unittest
from types import SimpleNamespace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

from rpi_assistant.app.config import AudioOutputConfig, OpenAIConfig
from rpi_assistant.app.openai_client import OpenAIClient
from rpi_assistant.app.playback import PlaybackInterrupted
from rpi_assistant.app.voice_command import VoiceCommandHandler


class FakeCompletions:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        content = self.responses.pop(0)
        message = (
            content
            if hasattr(content, "content")
            else SimpleNamespace(content=content, tool_calls=None)
        )
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message)],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )


class FakeClient:
    def __init__(self, responses):
        self.chat = SimpleNamespace(completions=FakeCompletions(responses))


class OpenAIClientConversationTests(unittest.TestCase):
    def test_interrupted_tool_answer_retains_result_and_correction_does_not_replay_action(self):
        tool = SimpleNamespace(id="completed-action", function=SimpleNamespace(name="utility__roll", arguments="{}"))
        client = self.create_client([
            SimpleNamespace(content=None, tool_calls=[tool]),
            "You rolled six. Here is an explanation.", "The result was six.",
        ], conversation_idle_timeout_seconds=0, conversation_relevance_threshold=0)
        manager = Mock()
        manager.config.max_tool_rounds = 1
        manager.openai_tools.return_value = [{"type": "function", "function": {"name": "utility__roll"}}]
        manager.call_tool.return_value = '{"result":6}'
        client.mcp_manager = manager
        client.transcribe_audio = Mock(side_effect=["Roll a die", "Just tell me that result; don't roll again."])
        apps = Mock()
        apps.handle.return_value = None
        apps.should_classify_app_intent.return_value = False
        playback = Mock()
        playback.play.side_effect = [PlaybackInterrupted(), True]
        with TemporaryDirectory() as directory:
            output = Path(directory) / "reply.wav"
            client.generate_speech = Mock(side_effect=lambda *args: output.write_bytes(b"fresh audio"))
            config = SimpleNamespace(openai=client.config, audio_output=AudioOutputConfig(tts_output_path=str(output)))
            handler = VoiceCommandHandler(config, client, apps, Mock(), playback, Mock())
            with self.assertRaises(PlaybackInterrupted):
                handler.process("unused.wav")
            self.assertFalse(output.exists())
            self.assertTrue(handler.process("unused.wav", continue_conversation=True))
        manager.call_tool.assert_called_once_with("utility__roll", {})
        self.assertEqual(len(client.client.chat.completions.calls), 3)
        results = [message for message in client.conversation_history if message["role"] == "tool"]
        self.assertEqual(results, [{"role": "tool", "tool_call_id": "completed-action", "content": '{"result":6}'}])
        playback.prompt.assert_not_called()

    def test_interrupted_app_result_becomes_available_to_contextual_correction(self):
        client = self.create_client(["Six was the result."])
        client.remember_app_response("Roll a die", "You rolled six.")
        client.get_chat_response("What was that result?", continue_conversation=True)
        self.assertEqual([message["content"] for message in client.conversation_history[1:3]],
                         ["Roll a die", "You rolled six."])
        self.assertEqual(len(client.client.chat.completions.calls), 1)

    def test_explicit_followup_bypasses_idle_and_relevance_resets(self):
        client = self.create_client(["manifold", "compact manifold", "cube"],
                                    conversation_idle_timeout_seconds=1,
                                    conversation_relevance_threshold=1)
        client.get_chat_response("What's a manifold?")
        client.last_response_output_finished_at = time.time() - 10
        client.get_chat_response("What about a compact manifold?", continue_conversation=True)
        client.get_chat_response("What about a cube?", continue_conversation=True)
        self.assertEqual(len(client.conversation_history), 7)
        self.assertEqual(len(client.client.chat.completions.calls), 3)
        self.assertEqual(client.compacted_contexts, [])

    def test_disabled_relevance_preserves_followup_without_extra_request(self):
        client = self.create_client(["manifold", "compact manifold", "cube"],
                                    conversation_idle_timeout_seconds=0,
                                    conversation_relevance_threshold=0)
        for question in ("What's a manifold?", "What about a compact manifold?", "What about a cube?"):
            client.get_chat_response(question)
        self.assertEqual(len(client.client.chat.completions.calls), 3)
        self.assertEqual(len(client.conversation_history), 7)
        request = client.client.chat.completions.calls[-1]
        self.assertEqual(request["reasoning_effort"], "none")
        self.assertEqual(request["max_completion_tokens"], 500)
        self.assertNotIn("max_tokens", request)

    def test_classifier_uses_supported_parameters_without_changing_history(self):
        client = self.create_client(['{"intent":"list_installed","confidence":1}'])
        result, _ = client.classify_app_intent("List my apps", {})
        self.assertEqual(result["intent"], "list_installed")
        self.assertEqual(len(client.conversation_history), 1)
        request = client.client.chat.completions.calls[0]
        self.assertEqual(request["reasoning_effort"], "none")
        self.assertEqual(request["max_completion_tokens"], 120)
        self.assertEqual(request["response_format"], {"type": "json_object"})

    def create_client(self, responses, **config_kwargs):
        config = OpenAIConfig(api_key="test-key", **config_kwargs)
        client = object.__new__(OpenAIClient)
        client.config = config
        client.client = FakeClient(responses)
        client.mcp_manager = None
        client.conversation_history = []
        client.compacted_contexts = []
        client.last_response_output_finished_at = None
        client._initialize_conversation()
        return client

    def test_idle_timeout_compacts_history_before_next_chat(self):
        client = self.create_client(
            ["new answer"],
            conversation_idle_timeout_seconds=300,
        )
        client.conversation_history.extend(
            [
                {"role": "user", "content": "old question"},
                {"role": "assistant", "content": "old answer"},
            ]
        )
        client.last_response_output_finished_at = time.time() - 301

        response, _ = client.get_chat_response("new question")

        self.assertEqual(response, "new answer")
        self.assertEqual(len(client.compacted_contexts), 1)
        self.assertEqual(client.compacted_contexts[0]["reason"], "idle_timeout")
        self.assertEqual(
            [message["content"] for message in client.conversation_history],
            ["You are a helpful voice assistant.", "new question", "new answer"],
        )

    def test_low_relevance_compacts_history_before_next_chat(self):
        client = self.create_client(
            [json.dumps({"relatedness": 0.1, "reason": "new topic"}), "new answer"],
            conversation_idle_timeout_seconds=0,
            conversation_relevance_threshold=0.35,
        )
        client.conversation_history.extend(
            [
                {"role": "user", "content": "tell me about sourdough"},
                {"role": "assistant", "content": "starter needs feeding"},
            ]
        )

        response, _ = client.get_chat_response("what is the weather")

        self.assertEqual(response, "new answer")
        self.assertEqual(len(client.compacted_contexts), 1)
        self.assertTrue(
            client.compacted_contexts[0]["reason"].startswith("low_relevance")
        )
        self.assertEqual(len(client.client.chat.completions.calls), 2)

    def test_high_relevance_keeps_history(self):
        client = self.create_client(
            [json.dumps({"relatedness": 0.9, "reason": "follow-up"}), "next answer"],
            conversation_idle_timeout_seconds=0,
            conversation_relevance_threshold=0.35,
        )
        client.conversation_history.extend(
            [
                {"role": "user", "content": "tell me about sourdough"},
                {"role": "assistant", "content": "starter needs feeding"},
            ]
        )

        response, _ = client.get_chat_response("how often should I feed it")

        self.assertEqual(response, "next answer")
        self.assertEqual(client.compacted_contexts, [])
        self.assertEqual(
            [message["content"] for message in client.conversation_history],
            [
                "You are a helpful voice assistant.",
                "tell me about sourdough",
                "starter needs feeding",
                "how often should I feed it",
                "next answer",
            ],
        )

    def test_mcp_tool_call_result_is_returned_to_model(self):
        tool_call = SimpleNamespace(
            id="call-1",
            function=SimpleNamespace(
                name="utility__echo_text", arguments='{"text":"hello"}'
            ),
        )
        client = self.create_client(
            [SimpleNamespace(content=None, tool_calls=[tool_call]), "done"],
            conversation_idle_timeout_seconds=0,
        )
        manager = SimpleNamespace(
            config=SimpleNamespace(max_tool_rounds=3),
            openai_tools=lambda: [
                {
                    "type": "function",
                    "function": {
                        "name": "utility__echo_text",
                        "description": "echo",
                        "parameters": {"type": "object"},
                    },
                }
            ],
            call_tool=lambda name, arguments: json.dumps(
                {"name": name, "arguments": arguments}
            ),
        )
        client.mcp_manager = manager

        response, usage = client.get_chat_response("echo hello")

        self.assertEqual(response, "done")
        self.assertEqual(usage["total_tokens"], 4)
        self.assertEqual(client.client.chat.completions.calls[0]["tool_choice"], "auto")
        tool_message = client.conversation_history[-2]
        self.assertEqual(tool_message["role"], "tool")
        self.assertEqual(tool_message["tool_call_id"], "call-1")
        self.assertIn("utility__echo_text", tool_message["content"])

    def test_tool_round_limit_forces_final_response_without_tools(self):
        first_call = SimpleNamespace(
            id="call-1",
            function=SimpleNamespace(name="utility__echo_text", arguments="{}"),
        )
        client = self.create_client(
            [SimpleNamespace(content=None, tool_calls=[first_call]), "limited"],
            conversation_idle_timeout_seconds=0,
        )
        client.mcp_manager = SimpleNamespace(
            config=SimpleNamespace(max_tool_rounds=1),
            openai_tools=lambda: [{"type": "function", "function": {"name": "x"}}],
            call_tool=lambda *_args: "{}",
        )

        response, _ = client.get_chat_response("use a tool")

        self.assertEqual(response, "limited")
        self.assertIn("tools", client.client.chat.completions.calls[0])
        self.assertNotIn("tools", client.client.chat.completions.calls[1])


if __name__ == "__main__":
    unittest.main()
