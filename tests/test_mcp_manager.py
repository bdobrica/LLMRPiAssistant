import json
import importlib.util
import logging
import sys
import threading
import time
import unittest
from pathlib import Path

from rpi_assistant.app.config import MCPConfig, MCPServerConfig
from rpi_assistant.app.mcp_manager import MCPClientManager


class MCPClientManagerTests(unittest.TestCase):
    def test_real_stdio_discovery_and_generic_routing(self):
        generic_server = Path(__file__).parent / "support" / "generic_mcp_server.py"
        config = MCPConfig(
            enabled=True,
            timeout_seconds=20,
            servers=(
                MCPServerConfig(
                    name="other",
                    transport="stdio",
                    command=sys.executable,
                    args=(str(generic_server),),
                ),
                MCPServerConfig(
                    name="utility",
                    transport="stdio",
                    command=sys.executable,
                    args=(str(generic_server),),
                ),
            ),
        )
        manager = MCPClientManager(config)
        try:
            manager.start()
            names = {tool["function"]["name"] for tool in manager.openai_tools()}
            self.assertIn("other__echo_text", names)
            self.assertIn("utility__echo_text", names)
            result = json.loads(
                manager.call_tool("utility__echo_text", {"text": "hello"})
            )
            self.assertFalse(result["is_error"])
            self.assertEqual(result["structured_content"], {"echo": "hello"})
        finally:
            manager.close()

    @unittest.skipUnless(importlib.util.find_spec("rpiface"), "Optional rpiface package is not installed")
    def test_optional_rpiface_discovery(self):
        config = MCPConfig(enabled=True, timeout_seconds=20, servers=(
            MCPServerConfig("face", "stdio", command=sys.executable,
                            args=("-m", "rpiface.mcp.server")),
        ))
        manager = MCPClientManager(config)
        try:
            manager.start()
            names = {tool["function"]["name"] for tool in manager.openai_tools()}
            self.assertIn("face__set_mood", names)
        finally:
            manager.close()

    def test_broken_server_does_not_hide_healthy_server(self):
        generic_server = Path(__file__).parent / "support" / "generic_mcp_server.py"
        config = MCPConfig(
            enabled=True,
            timeout_seconds=10,
            servers=(
                MCPServerConfig("broken", "stdio", command="/missing/mcp-server"),
                MCPServerConfig(
                    "utility",
                    "stdio",
                    command=sys.executable,
                    args=(str(generic_server),),
                ),
            ),
        )
        manager = MCPClientManager(config)
        with self.assertLogs(level=logging.WARNING):
            manager.start()
        try:
            names = [tool["function"]["name"] for tool in manager.openai_tools()]
            self.assertEqual(names, ["utility__echo_text"])
        finally:
            manager.close()

    def test_timeout_returns_bounded_error(self):
        config = MCPConfig(enabled=True, timeout_seconds=0.05)
        manager = MCPClientManager(config)
        manager.start()
        manager._tools["slow__wait"] = type(
            "Tool",
            (),
            {"server_name": "slow", "remote_name": "wait"},
        )()
        manager.config = MCPConfig(
            enabled=True,
            timeout_seconds=0.05,
            servers=(MCPServerConfig("slow", "stdio", command="ignored"),),
        )

        async def slow_call(*_args):
            await __import__("asyncio").sleep(1)

        manager._call = slow_call
        started = time.monotonic()
        try:
            result = json.loads(manager.call_tool("slow__wait", {}))
        finally:
            manager.close()
        self.assertLess(time.monotonic() - started, 0.5)
        self.assertEqual(result["error"], "Tool call timed out")

    def test_close_cancels_active_call(self):
        manager = MCPClientManager(MCPConfig(enabled=True, timeout_seconds=5))
        manager.start()
        manager._tools["slow__wait"] = type(
            "Tool", (), {"server_name": "slow", "remote_name": "wait"}
        )()
        manager.config = MCPConfig(
            enabled=True,
            timeout_seconds=5,
            servers=(MCPServerConfig("slow", "stdio", command="ignored"),),
        )

        async def slow_call(*_args):
            await __import__("asyncio").sleep(10)

        manager._call = slow_call
        result = []
        worker = threading.Thread(
            target=lambda: result.append(manager.call_tool("slow__wait", {}))
        )
        worker.start()
        deadline = time.monotonic() + 1
        while manager._active_task is None and time.monotonic() < deadline:
            time.sleep(0.01)
        manager.close()
        worker.join(timeout=1)

        self.assertFalse(worker.is_alive())
        self.assertEqual(json.loads(result[0])["error"], "Tool call cancelled")


if __name__ == "__main__":
    unittest.main()
