"""Play generated speech and bundled WAV/MP3 prompts on the configured device."""

from pathlib import Path
import asyncio
import os
import subprocess
import threading
import time


class PlaybackInterrupted(Exception):
    """The user stopped a spoken answer and wants to supply a correction."""


class PlaybackStopped(Exception):
    """Local stop/mute/new conversation cancelled output without a correction window."""


class AudioPlayback:
    """Serialize local prompts and replies, with bounded player processes."""

    def __init__(self, config):
        self.config = config
        self.lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._process = None
        self._interruptible = False
        self._interrupted = False
        self._generation = 0
        self._stopped = False
        self._cancel_stream = None

    def interrupt(self) -> bool:
        """Stop only the currently playing answer; repeated/idle presses do nothing."""
        with self._state_lock:
            process = self._process
            if not self._interruptible or self._interrupted or self._stopped:
                return False
            if process is None and self._cancel_stream is None:
                return False
            if process is not None and process.poll() is not None:
                return False
            self._interrupted = True
            self._generation += 1
            self._cancel_output()
            return True

    @property
    def generation(self):
        with self._state_lock:
            return self._generation

    def stop(self):
        """Invalidate queued output as well as killing the active player."""
        with self._state_lock:
            self._generation += 1
            self._stopped = True
            self._cancel_output()

    def _cancel_output(self):
        if self._process is not None and self._process.poll() is None:
            self._process.kill()
        if self._cancel_stream:
            self._cancel_stream()
            self._cancel_stream = None

    def play_stream(self, produce, *, expected_generation=None, timeout=150):
        """Own the speaker from provider connection through the final ALSA drain."""
        if not self.config.enabled:
            return False
        generation = self.generation if expected_generation is None else expected_generation
        deadline = time.monotonic() + timeout
        if not self.lock.acquire(timeout=timeout):
            raise TimeoutError("Audio output is busy")
        try:
            return asyncio.run(self._play_stream(produce, generation, deadline - time.monotonic()))
        finally:
            self.lock.release()

    async def _play_stream(self, produce, generation, timeout):
        loop = asyncio.get_running_loop()
        task = asyncio.current_task()
        process = None
        with self._state_lock:
            if generation != self._generation:
                raise PlaybackStopped()
            self._interruptible = True
            self._interrupted = self._stopped = False
            self._cancel_stream = lambda: loop.call_soon_threadsafe(task.cancel)

        async def write(chunk):
            nonlocal process
            with self._state_lock:
                if generation != self._generation:
                    raise asyncio.CancelledError()
                if process is None:
                    process = subprocess.Popen(stream_playback_command(self.config.device),
                                               stdin=subprocess.PIPE, bufsize=0,
                                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    self._process = process
                    os.set_blocking(process.stdin.fileno(), False)
            fd = process.stdin.fileno()
            data = memoryview(chunk)
            while data:
                try:
                    written = os.write(fd, data)
                except BlockingIOError:
                    ready = loop.create_future()
                    def writable():
                        if not ready.done():
                            ready.set_result(None)
                    loop.add_writer(fd, writable)
                    try:
                        await ready
                    finally:
                        loop.remove_writer(fd)
                else:
                    data = data[written:]

        try:
            async with asyncio.timeout(timeout):
                await produce(write)
                if process is None:
                    raise RuntimeError("Speech stream contained no audio")
                process.stdin.close()
                if await asyncio.to_thread(process.wait):
                    raise RuntimeError("Streaming player failed")
                return True
        finally:
            with self._state_lock:
                stopped, interrupted = self._stopped, self._interrupted
                self._cancel_stream = self._process = None
                self._interruptible = False
            if process is not None:
                if process.poll() is None:
                    process.kill()
                process.stdin.close()
                process.wait(timeout=2)
            if stopped:
                raise PlaybackStopped()
            if interrupted:
                raise PlaybackInterrupted()

    def play(self, path: str, *, backend: str, timeout: float = 150, interruptible: bool = False, expected_generation=None) -> bool:
        if not self.config.enabled:
            return False
        with self._state_lock:
            generation = self._generation if expected_generation is None else expected_generation
        if not self.lock.acquire(timeout=timeout):
            raise TimeoutError("Audio output is busy")
        try:
            command = speech_playback_command(backend, self.config.device, path)
            with self._state_lock:
                if generation != self._generation and (self._stopped or expected_generation is not None):
                    raise PlaybackStopped()
                if interruptible and generation != self._generation:
                    raise PlaybackInterrupted()  # An older queued answer must not resume.
                self._interrupted = False
                self._stopped = False
                self._interruptible = interruptible
                self._process = process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            try:
                _, stderr = process.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
                raise
            with self._state_lock:
                if self._stopped:
                    raise PlaybackStopped()
                if self._interrupted:
                    raise PlaybackInterrupted()
            if process.returncode:
                raise subprocess.CalledProcessError(process.returncode, command, stderr=stderr)
            return True
        finally:
            with self._state_lock:
                self._process = None
                self._interruptible = False
            self.lock.release()

    def prompt(self, filename: str, *, expected_generation=None) -> bool:
        path = Path(__file__).parent / "audio_prompts" / filename
        return self.play(str(path), backend="realtime" if path.suffix == ".wav" else "speech", timeout=10, expected_generation=expected_generation)


def speech_playback_command(backend: str, device: str, path: str) -> list[str]:
    if backend == "realtime":
        return ["aplay", "-D", device, path]
    if backend == "speech":
        return ["mpg123", "-a", device, path]
    raise ValueError("Unknown speech backend")


def stream_playback_command(device):
    # The named WM8960 plug converts this 24 kHz mono PCM to its S32_LE bus.
    return ["aplay", "-q", "-D", device, "-t", "raw", "-f", "S16_LE",
            "-r", "24000", "-c", "1", "--buffer-time=200000"]
