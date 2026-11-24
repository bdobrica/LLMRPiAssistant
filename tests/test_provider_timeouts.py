from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

from rpi_assistant.app.config import OpenAIConfig
from rpi_assistant.app.connectivity import check_internet_connection
from rpi_assistant.app.openai_client import OpenAIClient


class ProviderTimeoutTests(unittest.TestCase):
    def test_actual_sdk_times_out_and_does_not_retry_stalled_or_503_requests(self):
        class ServerHandler(BaseHTTPRequestHandler):
            requests = 0
            stall = True

            def log_message(self, *args):
                pass

            def do_POST(self):
                type(self).requests += 1
                self.rfile.read(int(self.headers["Content-Length"]))
                if self.stall:
                    time.sleep(0.4)
                try:
                    self.send_response(503)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"error":{"message":"injected outage"}}')
                except (BrokenPipeError, ConnectionResetError):
                    pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), ServerHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        client = OpenAIClient(OpenAIConfig(
            api_key="test", request_timeout_seconds=0.1,
            conversation_idle_timeout_seconds=0, conversation_relevance_threshold=0,
        ))
        client.client.base_url = f"http://127.0.0.1:{server.server_port}/v1/"
        try:
            for stall in (True, False):
                ServerHandler.stall = stall
                before = ServerHandler.requests
                start = time.monotonic()
                with self.assertRaises(Exception):
                    client.get_chat_response("Synthetic timeout check")
                self.assertLess(time.monotonic() - start, 2)
                self.assertEqual(ServerHandler.requests - before, 1)
        finally:
            client.client.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_connectivity_probe_closes_socket_without_changing_process_timeout(self):
        connection = MagicMock()
        with patch("socket.create_connection", return_value=connection) as create, patch("socket.setdefaulttimeout") as global_timeout:
            self.assertTrue(check_internet_connection(timeout=3))
        create.assert_called_once_with(("8.8.8.8", 53), timeout=3)
        connection.__exit__.assert_called_once()
        global_timeout.assert_not_called()
