"""Non-blocking lifecycle adapter for LLMRPiAssistant.

This file is intentionally dependency-free so it can be copied into the
LLMRPiAssistant package without making that project depend on RPiFace.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
from contextlib import suppress
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

LIFECYCLE_STATES = frozenset({"idle", "listening", "thinking", "speaking"})


@dataclass(frozen=True, slots=True)
class _Command:
    path: str
    payload: dict[str, object]


class RPiFaceClient:
    """Best-effort, non-blocking client for RPiFace Core lifecycle updates."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8765",
        timeout_seconds: float = 0.3,
        *,
        enabled: bool = False,
        logger: logging.Logger | None = None,
    ) -> None:
        if not 0 < timeout_seconds < 1:
            raise ValueError("RPiFace timeout_seconds must be greater than 0 and less than 1")
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.enabled = enabled
        self._logger = logger or logging.getLogger(__name__)
        self._commands: queue.Queue[_Command | None] = queue.Queue(maxsize=1)
        self._worker: threading.Thread | None = None
        self._closed = False
        self._lock = threading.Lock()

        if enabled:
            self._worker = threading.Thread(
                target=self._run,
                name="rpiface-client",
                daemon=True,
            )
            self._worker.start()

    def set_state(self, state: str) -> None:
        """Queue a lifecycle state without waiting for network I/O."""
        if state not in LIFECYCLE_STATES:
            raise ValueError(f"Unsupported RPiFace lifecycle state: {state}")
        self._submit(_Command("/v1/state", {"state": state}))

    def expression(self, state: str, hold_seconds: float) -> None:
        """Queue an optional temporary expression, such as ``sad`` on failure."""
        if not state or hold_seconds <= 0:
            raise ValueError("RPiFace expression and hold_seconds must be set")
        self._submit(
            _Command(
                "/v1/expression",
                {"state": state, "hold_ms": round(hold_seconds * 1000)},
            )
        )

    def close(self) -> None:
        """Request worker shutdown without waiting beyond the HTTP timeout."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
        if self._worker is None:
            return
        self._replace_pending(None)
        self._worker.join(timeout=self.timeout_seconds + 0.1)

    def __enter__(self) -> RPiFaceClient:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _submit(self, command: _Command) -> None:
        with self._lock:
            if not self.enabled or self._closed:
                return
        self._replace_pending(command)

    def _replace_pending(self, command: _Command | None) -> None:
        try:
            self._commands.put_nowait(command)
            return
        except queue.Full:
            pass
        try:
            self._commands.get_nowait()
            self._commands.task_done()
        except queue.Empty:
            pass
        with suppress(queue.Full):
            self._commands.put_nowait(command)

    def _run(self) -> None:
        while True:
            command = self._commands.get()
            try:
                if command is None:
                    return
                self._send(command)
            finally:
                self._commands.task_done()

    def _send(self, command: _Command) -> None:
        request = Request(
            f"{self.base_url}{command.path}",
            data=json.dumps(command.payload).encode("utf-8"),
            method="PUT" if command.path == "/v1/state" else "POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds):  # noqa: S310
                pass
        except (HTTPError, URLError, OSError, TimeoutError) as exc:
            self._logger.warning("RPiFace update unavailable (%s)", type(exc).__name__)
