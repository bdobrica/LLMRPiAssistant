"""Private, bounded interaction records; conversation content is opt-in."""

from collections import deque
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile
import threading
import time

from .config import LoggingConfig


class InteractionLogger:
    def __init__(self, config: LoggingConfig):
        self.config = config
        self.log_file = Path(config.log_file).expanduser()
        self.lock = threading.RLock()
        self.error = None
        self.prune()

    def _retained(self):
        """Read at most the configured cap, skipping partial/invalid/expired rows."""
        if not self.log_file.exists():
            return b""
        if self.log_file.is_symlink():
            raise OSError("Log path must not be a symlink")
        cutoff = time.time() - self.config.retention_days * 86400
        with self.log_file.open("rb") as source:
            size = source.seek(0, os.SEEK_END)
            source.seek(max(0, size - self.config.max_bytes))
            if size > self.config.max_bytes:
                source.readline()
            lines = source.read(self.config.max_bytes).splitlines(keepends=True)
        kept = []
        for line in lines:
            try:
                stamp = datetime.fromisoformat(json.loads(line)["timestamp"])
                if stamp.tzinfo is None:
                    stamp = stamp.replace(tzinfo=timezone.utc)
                if cutoff <= stamp.timestamp() <= time.time() + 600:
                    kept.append(line if line.endswith(b"\n") else line+b"\n")
            except (ValueError, TypeError, KeyError, OverflowError):
                pass
        while kept and sum(map(len, kept)) > self.config.max_bytes:
            kept.pop(0)
        return b"".join(kept)

    def _clear_temporary(self):
        for path in self.log_file.parent.glob("."+self.log_file.name+".private-*"):
            if not path.is_symlink() and path.is_file() and path.stat().st_uid == os.geteuid():
                path.unlink()

    def _replace(self, data):
        self.log_file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix="."+self.log_file.name+".private-", dir=self.log_file.parent)
        try:
            with os.fdopen(fd, "wb") as target:
                target.write(data)
                target.flush()
                os.fsync(target.fileno())
            os.replace(name, self.log_file)
        finally:
            Path(name).unlink(missing_ok=True)

    def prune(self):
        with self.lock:
            try:
                self._clear_temporary()
                if self.log_file.exists():
                    retained = self._retained()
                    if len(retained) != self.log_file.stat().st_size:
                        self._replace(retained)
                    else:
                        self.log_file.chmod(0o600)
                self.error = None
            except Exception:
                self.error = "Local log maintenance failed; check file permissions."

    def _emit(self, kind, *, usage=None, duration=None, content=None, failure=None):
        usage = usage or {}
        entry = {"timestamp": datetime.now(timezone.utc).isoformat(), "type": kind}
        entry["usage"] = {key: value for key in ("prompt_tokens", "completion_tokens", "total_tokens")
                          if type(value := usage.get(key)) is int and value >= 0}
        if type(duration) in (int, float) and 0 <= duration <= 3600:
            entry["audio_duration_seconds"] = round(duration, 2)
        if failure:
            entry["failure"] = failure
        if self.config.conversation_logging and content:
            entry.update(content)
        line = (json.dumps(entry, ensure_ascii=True) + "\n").encode()
        if len(line) > min(65536, self.config.max_bytes):
            entry = {"timestamp": entry["timestamp"], "type": kind, "content_omitted": "record_size_limit"}
            line = (json.dumps(entry) + "\n").encode()
        with self.lock:
            try:
                retained = deque(self._retained().splitlines(keepends=True))
                size = sum(map(len, retained)) + len(line)
                while retained and size > self.config.max_bytes:
                    size -= len(retained.popleft())
                self._replace(b"".join(retained) + line)
                self.error = None
            except Exception:
                if self.error is None:
                    print("Local interaction log unavailable; conversation processing continues.")
                self.error = "Local log writing failed; check file permissions."

    def log_transcription(self, audio_file, transcription, model="", duration_seconds=None):
        self._emit("transcription", duration=duration_seconds, content={"transcription": transcription})

    def log_chat_completion(self, user_message, assistant_response, usage):
        self._emit("chat_completion", usage=usage,
                   content={"user_message": user_message, "assistant_response": assistant_response})

    def log_complete_interaction(self, audio_file, transcription, assistant_response, usage, duration_seconds=None):
        content = {"transcription": transcription, "assistant_response": assistant_response}
        if "lookup" in usage:
            content.update(lookup=usage["lookup"], spoken_response=usage.get("spoken_response", assistant_response))
        self._emit("voice_interaction", usage=usage, duration=duration_seconds, content=content)

    def log_error(self, error_message, context=None):
        match = re.fullmatch(r"(transcription|app routing|answer|speech|playback) failed \(([A-Za-z_]{1,60})\)", error_message)
        failure = {"stage": match[1], "category": match[2]} if match else {"category": "request_failure"}
        self._emit("error", failure=failure)

    def delete(self):
        with self.lock:
            self.log_file.unlink(missing_ok=True)
            self._clear_temporary()
            self.error = None

    def get_log_summary(self, last_n=10):
        with self.lock:
            self.prune()
            return [json.loads(line) for line in self._retained().splitlines()][-max(1, min(last_n, 100)):]
