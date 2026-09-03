"""Unrelated MCP server used to prove generic client routing."""

import os

import anyio
import mcp_types
from mcp.server import MCPServer
from mcp.shared.message import SessionMessage

server = MCPServer("generic-test")


@server.tool()
async def echo_text(text: str) -> dict[str, str]:
    """Return text unchanged."""
    return {"echo": text}


async def run_stdio() -> None:
    incoming_send, incoming = anyio.create_memory_object_stream[
        SessionMessage | Exception
    ](0)
    outgoing, outgoing_receive = anyio.create_memory_object_stream[SessionMessage](0)

    async def read_stdin() -> None:
        async with incoming_send:
            buffer = b""
            while True:
                await anyio.wait_readable(0)
                chunk = os.read(0, 65_536)
                if not chunk:
                    return
                lines = (buffer + chunk).split(b"\n")
                buffer = lines.pop()
                for line in lines:
                    message = mcp_types.jsonrpc_message_adapter.validate_json(
                        line, by_name=False
                    )
                    await incoming_send.send(SessionMessage(message))

    async def write_stdout() -> None:
        async with outgoing_receive:
            async for message in outgoing_receive:
                encoded = (
                    message.message.model_dump_json(by_alias=True, exclude_unset=True)
                    + "\n"
                ).encode()
                while encoded:
                    await anyio.wait_writable(1)
                    encoded = encoded[os.write(1, encoded) :]

    async with anyio.create_task_group() as tasks:
        tasks.start_soon(read_stdin)
        tasks.start_soon(write_stdout)
        await server._lowlevel_server.run(
            incoming,
            outgoing,
            server._lowlevel_server.create_initialization_options(),
        )
        tasks.cancel_scope.cancel()


if __name__ == "__main__":
    anyio.run(run_stdio)
