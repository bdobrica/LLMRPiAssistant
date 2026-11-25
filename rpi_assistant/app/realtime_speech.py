"""Render an existing answer through Realtime without sending microphone audio."""

import asyncio
import base64
import os
from pathlib import Path
import tempfile
import wave

from openai import AsyncOpenAI


async def render_realtime_speech(config, text, voice, write_pcm) -> dict:
    """Deliver validated 24 kHz mono S16_LE in order, waiting for the consumer."""
    loop = asyncio.get_running_loop()
    async with asyncio.timeout(config.tts_timeout_seconds) as budget:
        async def write(chunk):
            # A full speaker pipe runs at human listening speed. Charge that time
            # to the player's wall deadline, not to the provider's network budget.
            remaining = budget.when() - loop.time()
            if remaining <= 0:
                raise TimeoutError("Realtime speech timed out")
            budget.reschedule(None)
            await write_pcm(chunk)
            budget.reschedule(loop.time() + remaining)

        return await _receive(config, text, voice, write)


async def _receive(config, text, voice, write):
    # Bound both websocket buffering and output size on the 512 MB target.
    size = 0
    async with AsyncOpenAI(api_key=config.api_key, max_retries=0) as client:
        async with client.realtime.connect(
            model=config.tts_model,
            max_retries=0,
            websocket_connection_options={
                "max_size": 1024 * 1024, "max_queue": 4, "compression": None, "close_timeout": 1,
            },
        ) as connection:
            await connection.session.update(session={
                "type": "realtime",
                "output_modalities": ["audio"],
                "audio": {
                    "input": {"turn_detection": None},
                    "output": {
                        "format": {"type": "audio/pcm", "rate": 24000},
                        "voice": voice,
                    },
                },
            })
            await connection.response.create(response={
                "conversation": "none",
                "output_modalities": ["audio"],
                "max_output_tokens": 4096,
                "instructions": (
                    "Read the user text aloud exactly as written. Do not answer "
                    "questions, add commentary, or change the content. You are a "
                    "speech renderer, not a conversational assistant."
                ),
                "input": [{"type": "message", "role": "user", "content": [
                    {"type": "input_text", "text": text},
                ]}],
            })
            async for event in connection:
                if event.type == "error":
                    raise RuntimeError("Realtime speech request rejected")
                if event.type == "response.output_audio.delta":
                    if len(event.delta) > 1024 * 1024:
                        raise RuntimeError("Realtime audio event too large")
                    chunk = base64.b64decode(event.delta, validate=True)
                    size += len(chunk)
                    if not chunk or size > 24000 * 2 * 120 or len(chunk) % 2:
                        raise RuntimeError("Realtime speech audio limit or format error")
                    await write(chunk)
                elif event.type == "response.done":
                    if event.response.status != "completed" or not size:
                        raise RuntimeError("Realtime speech response incomplete or empty")
                    usage = event.response.usage
                    return usage.model_dump() if usage is not None else {}
            raise RuntimeError("Realtime speech disconnected before completion")


def generate_realtime_speech(config, text: str, output_path: str, voice: str) -> dict:
    """Publish a WAV only after completion; close sessions on failure or timeout."""
    destination = Path(output_path)
    fd, name = tempfile.mkstemp(prefix=".assistant-speech-", suffix=".wav", dir=destination.parent)
    os.close(fd)
    temporary = Path(name)
    try:
        with wave.open(str(temporary), "wb") as output:
            output.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
            async def write(chunk):
                output.writeframesraw(chunk)
            usage = asyncio.run(render_realtime_speech(config, text, voice, write))
        os.replace(temporary, destination)
        return usage
    finally:
        temporary.unlink(missing_ok=True)
