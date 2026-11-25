"""HTTP Digest (RFC 7616, SHA-256) for the device owner's settings changes."""

import hashlib
import hmac
import os
from pathlib import Path
import re
import secrets
import time
from urllib.request import parse_http_list, parse_keqv_list

REALM = "Pi Assistant settings"
USER = "admin"


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def verifier(code):
    return digest(f"{USER}:{REALM}:{code}")


class DeviceAuth:
    """Each HTTPServer serves one request at a time and owns its nonce cache."""

    def __init__(self, key=None):
        if key is None:
            directory = os.environ.get("CREDENTIALS_DIRECTORY")
            try:
                key = (Path(directory) / "phone-admin").read_text().strip() if directory else ""
            except OSError:
                key = ""
        self.key = key if re.fullmatch("[0-9a-f]{64}", key) else None
        self.nonces = {}

    def challenge(self, peer):
        now = time.monotonic()
        self.nonces = {k: v for k, v in self.nonces.items() if v[1] > now}
        if len(self.nonces) >= 64:
            self.nonces.pop(next(iter(self.nonces)))
        nonce = secrets.token_hex(24)
        self.nonces[nonce] = (peer, now + 300, 0)
        return f'Digest realm="{REALM}", algorithm=SHA-256, qop="auth", nonce="{nonce}", domain="/admin/"'

    def accepts(self, header, peer, method, uri):
        if not self.key or not header or not header.startswith("Digest ") or len(header) > 2048:
            return False
        try:
            p = parse_keqv_list(parse_http_list(header[7:]))
            nonce, nc, cnonce = p["nonce"], p["nc"], p["cnonce"]
            address, expiry, last = self.nonces[nonce]
            if (address != peer or expiry <= time.monotonic() or not re.fullmatch("[0-9a-fA-F]{8}", nc)
                    or int(nc, 16) <= last or not cnonce or p["uri"] != uri or p["realm"] != REALM
                    or p["qop"] != "auth" or p["username"] != USER or p["algorithm"].upper() != "SHA-256"):
                return False
            expected = digest(f"{self.key}:{nonce}:{nc}:{cnonce}:auth:{digest(method + ':' + uri)}")
            if not hmac.compare_digest(expected, p["response"]):
                return False
            self.nonces[nonce] = (address, expiry, int(nc, 16))
            return True
        except (ValueError, KeyError, TypeError):
            return False
