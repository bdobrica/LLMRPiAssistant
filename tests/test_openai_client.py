import json
import time
import unittest
from types import SimpleNamespace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

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
    def test_retention_limits_reject_unbounded_or_invalid_configuration(self):
        for settings in ({"conversation_max_turns": 0}, {"conversation_max_turns": True},
                         {"conversation_max_bytes": 1023}, {"conversation_max_bytes": -1}):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                OpenAIConfig(api_key="synthetic", **settings)

    def test_oversized_input_never_reaches_provider(self):
        client = self.create_client([], conversation_max_bytes=1024)
        with self.assertRaisesRegex(Exception, "size limit"):
            client.get_chat_response("x" * 2000, continue_conversation=True)
        self.assertEqual(client.client.chat.completions.calls, [])
        self.assertLess(len(json.dumps(client.conversation_history[1:]).encode()), 1024)

    def test_retention_evicts_whole_tool_exchange_and_keeps_recent_context(self):
        tool = SimpleNamespace(id="roll-1", function=SimpleNamespace(name="roll", arguments="{}"))
        client = self.create_client([SimpleNamespace(content=None, tool_calls=[tool]),
                                     "Six.", "A manifold.", "Compact.", "Cube."],
                                    conversation_max_turns=3)
        manager = Mock()
        manager.config.max_tool_rounds = 1
        manager.openai_tools.return_value = []
        manager.call_tool.return_value = '{"result":6}'
        client.mcp_manager = manager
        for question in ("Roll", "Manifold?", "Compact?", "Cube?"):
            client.get_chat_response(question, continue_conversation=True)
        manager.call_tool.assert_called_once_with("roll", {})
        self.assertEqual([m["role"] for m in client.conversation_history],
                         ["system", "user", "assistant", "user", "assistant", "user", "assistant"])
        self.assertEqual([m["content"] for m in client.conversation_history[1::2]],
                         ["Manifold?", "Compact?", "Cube?"])
        request = client.client.chat.completions.calls[-1]
        self.assertNotIn("roll-1", json.dumps(request["messages"]))
        self.assertIn("Older exchanges", request["messages"][1]["content"])

    def test_byte_cap_counts_utf8_and_preserves_recent_app_receipt(self):
        client = self.create_client([], conversation_max_bytes=1024)
        for index in range(100):
            client.remember_app_response(f"Question {index}", "é" * 200)
            self.assertLessEqual(len(json.dumps(client.conversation_history[1:], ensure_ascii=False).encode()), 1024)
        self.assertEqual(client.conversation_history[-2]["content"], "Question 99")
        self.assertFalse(hasattr(client, "compacted_contexts"))

    def test_oversized_response_is_delivered_but_not_retained(self):
        client = self.create_client(["x" * 2000, "Please clarify."], conversation_max_bytes=1024)
        answer, _ = client.get_chat_response("Synthetic question", continue_conversation=True)
        self.assertEqual(answer, "x" * 2000)
        self.assertLess(len(json.dumps(client.conversation_history[1:]).encode()), 1024)
        self.assertIn("may already have run", client.conversation_history[-1]["content"])
        client.get_chat_response("What was it?", continue_conversation=True)
        self.assertNotIn("x" * 2000, json.dumps(client.client.chat.completions.calls[-1]))

    def test_oversized_tool_result_does_not_trigger_another_call_or_replay(self):
        tool = SimpleNamespace(id="large-result", function=SimpleNamespace(name="act", arguments="{}"))
        client = self.create_client([SimpleNamespace(content=None, tool_calls=[tool]), "Please clarify."],
                                    conversation_max_bytes=1024)
        manager = Mock()
        manager.config.max_tool_rounds = 2
        manager.openai_tools.return_value = []
        manager.call_tool.return_value = "x" * 2000
        client.mcp_manager = manager
        with self.assertRaisesRegex(Exception, "size limit"):
            client.get_chat_response("Act", continue_conversation=True)
        self.assertEqual(len(client.client.chat.completions.calls), 1)
        client.get_chat_response("What happened?", continue_conversation=True)
        manager.call_tool.assert_called_once_with("act", {})
        self.assertLess(len(json.dumps(client.conversation_history[1:]).encode()), 1024)

    def test_failed_tool_round_retains_unknown_execution_receipt(self):
        tool = SimpleNamespace(id="failed-result", function=SimpleNamespace(name="act", arguments="{}"))
        client = self.create_client([SimpleNamespace(content=None, tool_calls=[tool]), "I cannot confirm."],
                                    conversation_max_turns=2)
        manager = Mock()
        manager.config.max_tool_rounds = 1
        manager.openai_tools.return_value = []
        manager.call_tool.side_effect = RuntimeError("Synthetic lost result")
        client.mcp_manager = manager
        with self.assertRaisesRegex(Exception, "Synthetic lost result"):
            client.get_chat_response("Act", continue_conversation=True)
        receipt = client.conversation_history[-1]
        self.assertEqual(receipt["tool_call_id"], "failed-result")
        self.assertIn("may already have run", receipt["content"])
        client.get_chat_response("Did it run?", continue_conversation=True)
        manager.call_tool.assert_called_once()

    def test_repeated_resets_discard_text_and_clear_retention_notice(self):
        client = self.create_client([], conversation_max_turns=1)
        for _ in range(100):
            client.remember_app_response("old synthetic", "old synthetic answer")
            client.remember_app_response("new synthetic", "new synthetic answer")
            self.assertTrue(client.history_limited)
            with patch('builtins.print'):
                client.compact_conversation("test")
            self.assertEqual(len(client.conversation_history), 1)
            self.assertFalse(client.history_limited)
            self.assertFalse(hasattr(client, "compacted_contexts"))

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
        playback.play_stream.side_effect = [PlaybackInterrupted(), True]
        with TemporaryDirectory() as directory:
            output = Path(directory) / "reply.wav"
            client.generate_speech = Mock()
            config = SimpleNamespace(openai=client.config, audio_output=AudioOutputConfig(tts_output_path=str(output)))
            handler = VoiceCommandHandler(config, client, apps, Mock(), playback, Mock())
            with self.assertRaises(PlaybackInterrupted):
                handler.process("unused.wav")
            self.assertFalse(output.exists())
            self.assertTrue(handler.process("unused.wav", continue_conversation=True))
            client.generate_speech.assert_not_called()
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
        self.assertFalse(hasattr(client, "compacted_contexts"))

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
        self.assertFalse(hasattr(client, "compacted_contexts"))
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
        self.assertFalse(hasattr(client, "compacted_contexts"))
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
        self.assertFalse(hasattr(client, "compacted_contexts"))
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
