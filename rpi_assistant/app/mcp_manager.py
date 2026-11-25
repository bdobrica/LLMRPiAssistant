"""Generic, failure-isolated MCP client manager.

The manager deliberately knows nothing about RPiFace. It discovers tools from
named MCP servers, namespaces them for the LLM, and routes calls back to the
server that owns each tool.
"""

import asyncio
import json
import logging
import os
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from .config import MCPConfig, MCPServerConfig

MAX_TOOL_RESULT_CHARS = 16_000


@dataclass(frozen=True)
class DiscoveredTool:
    server_name: str
    remote_name: str
    llm_name: str
    description: str
    input_schema: dict[str, Any]

    def as_openai_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.llm_name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }


class MCPClientManager:
    """Own MCP discovery/routing on a private asyncio loop."""

    def __init__(self, config: MCPConfig, logger: logging.Logger | None = None) -> None:
        self.config = config
        self._logger = logger or logging.getLogger(__name__)
        self._tools: dict[str, DiscoveredTool] = {}
        self._started = False
        self._cancelled = False
        self._active_task: asyncio.Task | None = None
        self._cancel_event = threading.Event()

    def start(self) -> None:
        """Discover all reachable servers; isolate and log individual failures."""
        if not self.config.enabled or self._started:
            return
        self._started = True
        self._cancelled = False
        self._cancel_event.clear()
        for server in self.config.servers:
            try:
                tools = self._submit(self._discover(server))
            except Exception as exc:  # noqa: BLE001 - isolate arbitrary server failures
                self._logger.warning(
                    "MCP server %s unavailable during discovery (%s)",
                    server.name,
                    type(exc).__name__,
                )
                continue
            for tool in tools:
                if tool.llm_name in self._tools:
                    self._logger.warning(
                        "Duplicate MCP tool name ignored: %s", tool.llm_name
                    )
                    continue
                self._tools[tool.llm_name] = tool

    def close(self) -> None:
        """Cancel an active operation and reject subsequent calls."""
        self._cancelled = True
        self._started = False
        self._cancel_event.set()

    def openai_tools(self) -> list[dict[str, Any]]:
        """Return provider schemas without transport configuration or credentials."""
        return [self._tools[name].as_openai_tool() for name in sorted(self._tools)]

    def call_tool(self, llm_name: str, arguments: dict[str, Any]) -> str:
        """Route one namespaced call and return bounded model-visible content."""
        tool = self._tools.get(llm_name)
        if tool is None:
            return _error_result("Unknown tool")
        server = next(
            (item for item in self.config.servers if item.name == tool.server_name),
            None,
        )
        if server is None:
            return _error_result("Tool server unavailable")
        try:
            result = self._submit(self._call(server, tool.remote_name, arguments))
        except TimeoutError:
            return _error_result("Tool call timed out")
        except asyncio.CancelledError:
            return _error_result("Tool call cancelled")
        except Exception as exc:  # noqa: BLE001 - isolate arbitrary server failures
            self._logger.warning(
                "MCP tool %s failed (%s)", llm_name, type(exc).__name__
            )
            return _error_result("Tool server unavailable")
        return _serialize_result(result)

    def _submit(self, coroutine: Any) -> Any:
        if not self._started or self._cancelled:
            coroutine.close()
            raise RuntimeError("MCP manager is not running")

        async def bounded() -> Any:
            task = asyncio.create_task(coroutine)
            self._active_task = task

            async def cancellation_watcher() -> None:
                while not self._cancel_event.is_set():
                    await asyncio.sleep(0.02)
                task.cancel()

            watcher = asyncio.create_task(cancellation_watcher())
            try:
                return await asyncio.wait_for(task, timeout=self.config.timeout_seconds)
            finally:
                watcher.cancel()
                await asyncio.gather(watcher, return_exceptions=True)
                self._active_task = None

        return asyncio.run(bounded())

    async def _discover(self, server: MCPServerConfig) -> list[DiscoveredTool]:
        async with _session(server, self.config.timeout_seconds) as session:
            result = await session.list_tools()
        return [
            DiscoveredTool(
                server_name=server.name,
                remote_name=tool.name,
                llm_name=_llm_tool_name(server.name, tool.name),
                description=tool.description or f"Tool {tool.name} from {server.name}",
                input_schema=tool.input_schema,
            )
            for tool in result.tools
        ]

    async def _call(
        self, server: MCPServerConfig, remote_name: str, arguments: dict[str, Any]
    ) -> Any:
        async with _session(server, self.config.timeout_seconds) as session:
            return await session.call_tool(
                remote_name,
                arguments,
                read_timeout_seconds=self.config.timeout_seconds,
            )


@asynccontextmanager
async def _session(server: MCPServerConfig, timeout: float) -> AsyncIterator[Any]:
    """Open and initialize one SDK session while keeping imports optional."""
    try:
        from mcp import Client, ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        from mcp.client.streamable_http import streamable_http_client
    except ImportError as exc:
        raise RuntimeError("MCP support is not installed") from exc

    if server.transport == "stdio":
        safe_names = {"PATH", "LANG", "LC_ALL", "PYTHONPATH"}
        inherited_names = safe_names.union(server.env_vars)
        environment = {
            name: os.environ[name] for name in inherited_names if name in os.environ
        }
        parameters = StdioServerParameters(
            command=server.command,
            args=list(server.args),
            env=environment,
        )
        # Server stderr is uncontrolled and may echo tool arguments/results.
        with open(os.devnull, "w") as errors:
            async with Client(stdio_client(parameters, errlog=errors), read_timeout_seconds=timeout, cache=None) as client:
                yield client
        return

    if not server.token_env:
        async with Client(server.url, read_timeout_seconds=timeout, cache=None) as client:
            yield client
        return

    try:
        import httpx2
    except ImportError as exc:
        raise RuntimeError("Streamable HTTP support is not installed") from exc
    headers = {}
    if server.token_env:
        token = os.environ.get(server.token_env)
        if not token:
            raise RuntimeError("MCP bearer token is unavailable")
        headers["Authorization"] = f"Bearer {token}"
    async with (
        httpx2.AsyncClient(headers=headers, timeout=timeout) as http_client,
        streamable_http_client(
            server.url,
            http_client=http_client,
        ) as (read_stream, write_stream),
        ClientSession(
            read_stream, write_stream, read_timeout_seconds=timeout
        ) as session,
    ):
        await session.initialize()
        yield session


def _llm_tool_name(server_name: str, tool_name: str) -> str:
    name = f"{server_name}__{tool_name}"
    if len(name) > 64:
        raise ValueError("Namespaced MCP tool name exceeds 64 characters")
    return name


def _serialize_result(result: Any) -> str:
    payload = {
        "is_error": bool(getattr(result, "is_error", False)),
        "structured_content": getattr(result, "structured_content", None),
        "content": [
            item.model_dump(mode="json", exclude_none=True)
            for item in getattr(result, "content", [])
            if getattr(item, "type", None) == "text"
        ],
    }
    encoded = json.dumps(payload, ensure_ascii=False, default=str)
    if len(encoded) > MAX_TOOL_RESULT_CHARS:
        return json.dumps({"is_error": True, "error": "Tool result was too large"})
    return encoded


def _error_result(message: str) -> str:
    return json.dumps({"is_error": True, "error": message})
