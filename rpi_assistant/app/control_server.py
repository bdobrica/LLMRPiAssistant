"""Trusted-LAN control page; no remote assets, cloud requests or CORS."""

from http.server import BaseHTTPRequestHandler, HTTPServer
import ipaddress
import json
from pathlib import Path
import threading
from urllib.parse import urlsplit
from .household import HouseholdInputError
from .phone_settings import SettingsError


class ControlServer(HTTPServer):
    allow_reuse_address = True

    def __init__(self, config, controls, *, allowed_network=None):
        self.controls = controls
        self.restrict_network = allowed_network is not None
        self.allowed_network = allowed_network
        super().__init__((config.host, config.port), ControlHandler)
        self.thread = threading.Thread(target=self.serve_forever, name="local-controls", daemon=True)
        self.thread.start()

    def get_request(self):
        sock, address = super().get_request()
        sock.settimeout(3)
        return sock, address

    def close(self):
        self.shutdown()
        self.server_close()
        self.thread.join(timeout=4)


class ControlHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _host_allowed(self):
        try:
            if self.server.restrict_network:
                network = self.server.allowed_network
                if network is None or ipaddress.ip_address(self.client_address[0]) not in network:
                    return False
            hostname = urlsplit('http://' + self.headers.get('Host', '')).hostname
            if self.server.restrict_network and hostname != self.connection.getsockname()[0]:
                return False
            if hostname == 'localhost':
                return True
            ipaddress.ip_address(hostname)
            return True
        except (ValueError, TypeError):
            return False

    def _reply(self, code, body, content_type='application/json'):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if not self._host_allowed():
            return self._reply(403, {"error": "Use the device IP address."})
        if self.path == '/status':
            return self._reply(200, self.server.controls.status())
        assets = {'/': ('index.html', 'text/html; charset=utf-8'),
                  '/controls.js': ('controls.js', 'text/javascript; charset=utf-8'),
                  '/controls.css': ('controls.css', 'text/css; charset=utf-8')}
        if self.path not in assets:
            return self._reply(404, {"error": "Not found"})
        filename, content_type = assets[self.path]
        return self._reply(200, (Path(__file__).parent / 'control_page' / filename).read_bytes(), content_type)

    def do_POST(self):
        origin = self.headers.get('Origin')
        if (not self._host_allowed() or self.headers.get('X-Assistant-Control') != '1'
                or (origin is not None and origin != 'http://' + self.headers['Host'])):
            return self._reply(403, {"error": "Use the local control page."})
        if self.path != '/control':
            return self._reply(404, {"error": "Not found"})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 4096:
                raise ValueError("Invalid request size")
            payload = json.loads(self.rfile.read(size))
            if not isinstance(payload, dict):
                raise ValueError("Expected an object")
            message = self.server.controls.command(payload.get('action'), payload.get('value'))
            self._reply(200, {"message": message, **self.server.controls.status()})
        except (HouseholdInputError, SettingsError) as exc:
            self._reply(400, {"error": str(exc)})
        except (ValueError, TypeError):
            self._reply(400, {"error": "Invalid control request"})
        except Exception as exc:
            self._reply(503, {"error": f"Control failed ({type(exc).__name__}); check status and retry."})
