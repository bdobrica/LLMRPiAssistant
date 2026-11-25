"""Play generated speech and bundled WAV/MP3 prompts on the configured device."""

from pathlib import Path
import subprocess
import threading


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

    def interrupt(self) -> bool:
        """Stop only the currently playing answer; repeated/idle presses do nothing."""
        with self._state_lock:
            process = self._process
            if not self._interruptible or self._interrupted or process is None or process.poll() is not None:
                return False
            self._interrupted = True
            self._generation += 1
            try:
                # Stop the player immediately; do not drain queued speech on SIGTERM.
                process.kill()
            except ProcessLookupError:
                pass  # It finished between poll() and kill(); still honor the correction.
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
            if self._process is not None and self._process.poll() is None:
                try:
                    self._process.kill()
                except ProcessLookupError:
                    pass

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
