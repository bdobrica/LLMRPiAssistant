"""Play generated speech and bundled WAV/MP3 prompts on the configured device."""

from pathlib import Path
import subprocess
import threading


class AudioPlayback:
    """Serialize local prompts and replies, with bounded player processes."""

    def __init__(self, config):
        self.config = config
        self.lock = threading.Lock()

    def play(self, path: str, *, backend: str, timeout: float = 150) -> bool:
        if not self.config.enabled:
            return False
        if not self.lock.acquire(timeout=timeout):
            raise TimeoutError("Audio output is busy")
        try:
            subprocess.run(
                speech_playback_command(backend, self.config.device, path),
                check=True, capture_output=True, timeout=timeout,
            )
            return True
        finally:
            self.lock.release()

    def prompt(self, filename: str) -> bool:
        path = Path(__file__).parent / "audio_prompts" / filename
        return self.play(str(path), backend="realtime" if path.suffix == ".wav" else "speech", timeout=10)


def speech_playback_command(backend: str, device: str, path: str) -> list[str]:
    if backend == "realtime":
        return ["aplay", "-D", device, path]
    if backend == "speech":
        return ["mpg123", "-a", device, path]
    raise ValueError("Unknown speech backend")
