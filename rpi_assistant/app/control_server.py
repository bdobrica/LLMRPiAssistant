"""Trusted-LAN control page; no remote assets, cloud requests or CORS."""

from http.server import BaseHTTPRequestHandler, HTTPServer
import ipaddress
import json
from pathlib import Path
import threading
from urllib.parse import urlsplit
from .admin_auth import DeviceAuth
from .household import HouseholdInputError
from .phone_settings import SettingsError


PAGE_DIR = Path(__file__).parent / "control_page"
# Only these literal routes and assets are served.
PAGES = {
    "/": ("Home", "home"),
    "/timers": ("Timers", "household"),
    "/reminders": ("Reminders", "household"),
    "/shopping": ("Shopping", "household"),
    "/settings": ("Settings", "settings"),
    "/privacy": ("Privacy", "settings"),
}
ASSETS = {"/" + name: "text/javascript; charset=utf-8"
          for name in ("controls.js", "home.js", "household.js", "settings.js", "advanced.js")}
ASSETS["/controls.css"] = "text/css; charset=utf-8"


def render_page(path):
    advanced = path == "/admin/settings"
    title, script = ("Advanced", "advanced") if advanced else PAGES[path]
    links = []
    for href, (label, _) in PAGES.items():
        current = ' aria-current="page"' if href == path or (advanced and href == "/settings") else ''
        links.append(f'<a href="{href}"{current}>{label}</a>')
    layout = (PAGE_DIR / "index.html").read_text(encoding="utf-8")
    content = (PAGE_DIR / (title.lower() + ".html")).read_text(encoding="utf-8")
    return (layout.replace("{{title}}", title).replace("{{script}}", script)
            .replace("{{nav}}", "\n".join(links)).replace("{{content}}", content).encode())


class ControlServer(HTTPServer):
    allow_reuse_address = True

    def __init__(self, config, controls, *, allowed_network=None):
        self.controls = controls
        self.auth = DeviceAuth()
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

    def _reply(self, code, body, content_type='application/json', challenge=None):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        if challenge:
            self.send_header("WWW-Authenticate", challenge)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(data)

    def _authenticated(self):
        auth = self.server.auth
        peer = self.client_address[0]
        if not auth.key:
            self._reply(503, {"error": "Device sign-in unavailable. Install the updated assistant service."})
        elif auth.accepts(self.headers.get("Authorization"), peer, self.command, self.path):
            return True
        else:
            self._reply(401, {"error": "Sign in as admin with the device setup code."},
                        challenge=auth.challenge(peer))
        return False

    def do_GET(self):
        if not self._host_allowed():
            return self._reply(403, {"error": "Use the device IP address."})
        if self.path == '/status':
            return self._reply(200, self.server.controls.status())
        if self.path in ('/admin/settings', '/admin/options'):
            if not self._authenticated():
                return
            if self.path == '/admin/settings':
                return self._reply(200, render_page(self.path), 'text/html; charset=utf-8')
            try:
                return self._reply(200, self.server.controls.settings.options())
            except Exception:
                return self._reply(503, {"error": "Unable to read the settings. Check the local INI."})
        if self.path in PAGES:
            return self._reply(200, render_page(self.path), 'text/html; charset=utf-8')
        if self.path in ASSETS:
            asset = PAGE_DIR / self.path[1:]
            return self._reply(200, asset.read_bytes(), ASSETS[self.path])
        return self._reply(404, {"error": "Not found"})

    def do_POST(self):
        origin = self.headers.get('Origin')
        if (not self._host_allowed() or self.headers.get('X-Assistant-Control') != '1'
                or (origin is not None and origin != 'http://' + self.headers['Host'])):
            return self._reply(403, {"error": "Use the local control page."})
        admin = self.path == '/admin/change'
        if not admin and self.path != '/control':
            return self._reply(404, {"error": "Not found"})
        if admin and not self._authenticated():
            return
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= (65536 if admin else 4096):
                raise ValueError("Invalid request size")
            payload = json.loads(self.rfile.read(size))
            if not isinstance(payload, dict):
                raise ValueError("Expected an object")
            action = payload.get('action')
            if (action in ("settings_apply", "settings_undo", "settings_advanced", "privacy_delete")) != admin:
                return self._reply(403, {"error": "Use the authenticated settings page."})
            message = self.server.controls.command(action, payload.get('value'))
            self._reply(200, {"message": message, **self.server.controls.status()})
        except (HouseholdInputError, SettingsError) as exc:
            self._reply(400, {"error": str(exc)})
        except (ValueError, TypeError):
            self._reply(400, {"error": "Invalid control request"})
        except Exception as exc:
            self._reply(503, {"error": f"Control failed ({type(exc).__name__}); check status and retry."})
