"""Local conversation-data lifecycle, separate from saved household information."""

from contextlib import contextmanager
import logging
import os
from pathlib import Path
import stat
import tempfile
import threading
import time


@contextmanager
def private_audio(path):
    """Create owner-only audio without following a pre-existing symlink."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if info.st_uid != os.geteuid() or not stat.S_ISREG(info.st_mode):
            raise PermissionError("Audio path is not an owned regular file")
        os.fchmod(fd, 0o600)
        os.ftruncate(fd, 0)
    except Exception:
        os.close(fd)
        raise
    with os.fdopen(fd, "wb") as output:
        yield output


def quiet_provider_logs():
    """Provider wire/debug logs may contain prompts or credentials, even on errors."""
    prefixes = ("openai", "httpx", "httpx2", "httpcore", "websockets", "mcp")
    for name in set(prefixes).union(logging.Logger.manager.loggerDict):
        if any(name == prefix or name.startswith(prefix + ".") for prefix in prefixes):
            logger = logging.getLogger(name)
            logger.handlers.clear()
            logger.addHandler(logging.NullHandler())
            logger.propagate = False
            logger.setLevel(logging.CRITICAL + 1)


class ConversationPrivacy:
    def __init__(self, config, logger, controls):
        self.config, self.logger, self.controls = config, logger, controls
        self.error = None
        self.stop_event = threading.Event()
        self.thread = None

    def _audio_paths(self):
        output = Path(self.config.audio_output.tts_output_path).expanduser()
        yield Path(self.config.recording.output_path).expanduser()
        yield output
        yield from output.parent.glob('.assistant-speech-*.wav')
        for directory in Path(tempfile.gettempdir()).glob('assistant-mic-check-*'):
            if not directory.is_symlink() and directory.is_dir() and directory.stat().st_uid == os.geteuid():
                yield directory / 'check.wav'

    def clean_audio(self, *, stale_only=False):
        failures = 0
        for path in set(self._audio_paths()):
            try:
                info = path.lstat()
                if info.st_uid != os.geteuid() or not stat.S_ISREG(info.st_mode):
                    failures += 1
                    continue
                if stale_only and time.time() - info.st_mtime < 300:
                    continue
                path.unlink()
                if path.name == 'check.wav' and path.parent.name.startswith('assistant-mic-check-'):
                    try:
                        path.parent.rmdir()
                    except OSError:
                        pass
            except FileNotFoundError:
                pass
            except OSError:
                failures += 1
        self.error = "Some local audio could not be removed; check storage permissions." if failures else None
        return not failures

    def start(self):
        self.clean_audio()
        self.thread = threading.Thread(target=self._maintain, name='conversation-retention', daemon=True)
        self.thread.start()

    def _maintain(self):
        while not self.stop_event.wait(60):
            self.logger.prune()
            with self.controls.lock, self.controls.recorder.lock:
                recorder = self.controls.recorder
                if not self.controls.busy and not recorder.processing_active and not recorder.diagnostic_active and recorder.state != 'RECORD':
                    self.clean_audio(stale_only=True)

    def delete(self, confirmation):
        from .phone_settings import SettingsError
        if not isinstance(confirmation, dict) or set(confirmation) != {"confirm"} or confirmation.get("confirm") is not True:
            raise SettingsError("Confirm deletion of this installation's conversation data.")
        c = self.controls
        with c.recorder.lock:
            if c.busy or c.recorder.processing_active or getattr(c.recorder, 'diagnostic_active', False) or c.recorder.state == 'RECORD':
                raise SettingsError("Wait for the request or audio check to finish, then delete conversation data.")
            c._stop()
            c.client.reset_conversation()
            try:
                self.logger.delete()
                if not self.clean_audio():
                    raise OSError()
            except OSError:
                raise SettingsError("Conversation memory was cleared, but some local files could not be removed. Check permissions and retry.") from None
        return "Conversation memory and this installation's logs/audio were deleted. Saved household data, settings and keys were kept. Historical journal, other installations and provider records were not deleted."

    def status(self):
        return {"conversation_logging": self.config.logging.conversation_logging,
                "retention_days": self.config.logging.retention_days, "max_bytes": self.config.logging.max_bytes,
                "error": self.error or self.logger.error}

    def close(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=2)
