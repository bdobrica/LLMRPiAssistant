import logging
import subprocess
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from rpi_assistant.app.rpiface_client import RPiFaceClient


class _Handler(BaseHTTPRequestHandler):
    requests = []
    received = threading.Event()

    def do_PUT(self):  # noqa: N802
        body = self.rfile.read(int(self.headers["Content-Length"]))
        self.requests.append((self.path, body.decode()))
        self.send_response(200)
        self.end_headers()
        self.received.set()

    def log_message(self, *_args):
        pass


class RPiFaceClientTests(unittest.TestCase):
    def test_import_and_disabled_context_in_fresh_interpreter(self):
        result = subprocess.run(
            [sys.executable, "-c",
             "from rpi_assistant.app.rpiface_client import RPiFaceClient; "
             "client = RPiFaceClient(enabled=False); "
             "assert client.__enter__() is client; client.close()"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_disabled_by_default(self):
        client = RPiFaceClient()
        client.set_state("idle")
        self.assertIsNone(client._worker)

    def test_state_call_returns_before_http_completes(self):
        _Handler.requests = []
        _Handler.received.clear()
        server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        client = RPiFaceClient(
            f"http://127.0.0.1:{server.server_port}", 0.3, enabled=True
        )
        try:
            started = time.monotonic()
            client.set_state("listening")
            self.assertLess(time.monotonic() - started, 0.05)
            self.assertTrue(_Handler.received.wait(1))
            self.assertEqual(
                _Handler.requests,
                [("/v1/state", '{"state": "listening"}')],
            )
        finally:
            client.close()
            server.shutdown()
            server.server_close()

    def test_stopped_service_is_nonfatal(self):
        with self.assertLogs(level=logging.WARNING) as logs:
            client = RPiFaceClient("http://127.0.0.1:1", 0.1, enabled=True)
            client.set_state("thinking")
            deadline = time.monotonic() + 1
            while not logs.output and time.monotonic() < deadline:
                time.sleep(0.01)
            client.close()
        self.assertIn("RPiFace update unavailable", " ".join(logs.output))


if __name__ == "__main__":
    unittest.main()
