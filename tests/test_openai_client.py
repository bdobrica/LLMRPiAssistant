import json
import time
import unittest
from types import SimpleNamespace

from rpi_assistant.app.config import OpenAIConfig
from rpi_assistant.app.openai_client import OpenAIClient


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
