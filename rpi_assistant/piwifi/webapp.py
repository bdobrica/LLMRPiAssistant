"""Authenticated phone provisioning, served only on the setup network."""

from datetime import timedelta
import hmac
import ipaddress
import os
from pathlib import Path
import secrets
import socket
import threading
import time

from flask import Flask, abort, render_template, request, send_file, session
from werkzeug.exceptions import HTTPException
from werkzeug.serving import WSGIRequestHandler, make_server

from . import network


class ConnectionJob:
    def __init__(self, iface, marker=Path('/run/piwifi/connecting')):
        self.iface, self.marker = iface, marker
        self.lock = threading.Lock()
        self.busy = False
        self.message = ''

    def start(self, ssid, password):
        network.validate(ssid, password)
        with self.lock:
            if self.busy:
                raise ValueError('A connection attempt is already running. Please wait.')
            # The manager must not restore the AP while NetworkManager is joining.
            self.marker.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            self.marker.unlink(missing_ok=True)
            network.private_write(self.marker, str(int(time.time()) + 120))
            self.busy = True
            self.message = 'Connecting. The setup network will disconnect. Rejoin your home Wi-Fi if successful; otherwise reconnect to setup and retry.'
            try:
                threading.Thread(target=self._connect, args=(ssid, password), name='wifi-join', daemon=True).start()
            except Exception:
                self.busy = False
                self.marker.unlink(missing_ok=True)
                raise

    def _connect(self, ssid, password):
        try:
            time.sleep(1)  # Allow the phone to receive the acknowledgement first.
            network.connect(ssid, password, self.iface)
            self.message = 'Joined Wi-Fi. Setup is closing. Reconnect your phone to your home Wi-Fi.'
        except Exception:
            self.message = 'Could not join Wi-Fi. Check the network name and password, then try again.'
            try:
                if not network.client_connected(self.iface):
                    network.run(['connection', 'up', 'id', network.HOTSPOT])
            except Exception:
                self.message = 'Connection failed and setup recovery is pending. Rejoin the setup network when it returns.'
        finally:
            with self.lock:
                self.busy = False
                self.marker.unlink(missing_ok=True)


def create_app(*, host=None, job=None, setup_network=None):
    host = host or str(ipaddress.ip_interface(os.environ.get('AP_ADDR', '192.168.4.1/24')).ip)
    setup_network = ipaddress.ip_network(setup_network or os.environ.get('AP_ADDR', '192.168.4.1/24'), strict=False)
    iface = os.environ.get('IFACE', 'wlan0')
    job = job or ConnectionJob(iface)
    app = Flask(__name__, static_folder=None)
    app.config.update(SECRET_KEY=secrets.token_hex(32), MAX_CONTENT_LENGTH=4096,
                      MAX_FORM_MEMORY_SIZE=4096, MAX_FORM_PARTS=8,
                      SESSION_COOKIE_NAME='piwifi_setup', SESSION_COOKIE_HTTPONLY=True,
                      SESSION_COOKIE_SAMESITE='Strict', PERMANENT_SESSION_LIFETIME=timedelta(minutes=15),
                      SESSION_REFRESH_EACH_REQUEST=False, TRUSTED_HOSTS=[host])
    app.logger.disabled = True

    def csrf():
        if 'csrf' not in session:
            session['csrf'] = secrets.token_hex(32)
        return session['csrf']

    @app.before_request
    def protect():
        # Joining the WPA-protected setup network is the authentication step.
        # The page binds only to its address and refuses clients outside its subnet.
        try:
            if ipaddress.ip_address(request.remote_addr) not in setup_network:
                abort(403, description='setup_network_required')
        except ValueError:
            abort(403, description='setup_network_required')
        # No supported action accepts credentials, tokens or other state in URLs.
        if request.query_string:
            abort(400)
        if request.method == 'POST':
            origin = request.headers.get('Origin')
            if (origin is not None and origin != request.host_url.rstrip('/')) or request.headers.get('Sec-Fetch-Site') == 'cross-site':
                abort(403, description='foreign_origin')
            expected, supplied = session.get('csrf', ''), request.form.get('csrf', '')
            if (not expected or len(supplied) != 64 or not supplied.isascii()
                    or not hmac.compare_digest(expected, supplied)):
                abort(403, description='expired_form')
            if any(len(request.form.getlist(key)) != 1 for key in request.form):
                abort(400)

    @app.after_request
    def headers(response):
        response.headers.update({'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
                                 # no-referrer makes real HTML forms send Origin:null.
                                 'Referrer-Policy': 'same-origin',
                                 'Content-Security-Policy': "default-src 'none'; script-src 'self'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"})
        return response

    def page(error='', status=200):
        ssids = []
        if not job.busy:
            try:
                ssids = network.scan(iface)
            except Exception:
                error = error or 'Network scan unavailable. You can enter the network name manually.'
        return render_template('index.html', csrf=csrf(),
                               error=error, ssids=ssids, busy=job.busy, message=job.message), status

    @app.get('/')
    def index():
        return page()

    @app.get('/setup.js')
    def setup_script():
        return send_file(Path(__file__).parent/'static/setup.js', mimetype='application/javascript')

    @app.post('/connect')
    def connect():
        if set(request.form) != {'csrf', 'ssid', 'password'}:
            abort(400)
        try:
            job.start(request.form['ssid'], request.form['password'])
        except ValueError as error:
            return page(str(error), 400)
        except Exception:
            return page('Could not start setup. Check the device and try again.', 503)
        return page(status=202)

    @app.errorhandler(Exception)
    def failed(error):
        # Never render subprocess exceptions, request bodies or debug tracebacks.
        messages = {
            'setup_network_required': 'Join this device’s protected setup Wi-Fi to use this page.',
            'foreign_origin': 'Open the setup address directly in your browser and try again.',
            'expired_form': 'This setup form expired or its browser cookie is missing. Refresh the page and try again.',
            'invalid_request': 'The setup request was invalid or too large. Refresh the page and try again.',
            'service_error': 'Setup could not complete the request. Refresh and retry; if it persists, check the device.'}
        status = error.code if isinstance(error, HTTPException) else 503
        reason = getattr(error, 'description', '')
        if reason not in messages:
            reason = 'invalid_request' if status < 500 else 'service_error'
        print(f'Wi-Fi setup rejected request ({reason}, HTTP {status}).', flush=True)
        return messages[reason] + ' <a href="/">Return to setup</a>', status

    return app


class QuietRequestHandler(WSGIRequestHandler):
    def log(self, *args, **kwargs):
        pass  # URLs and malformed request lines can themselves contain secrets.


def main():
    try:
        os.umask(0o077)
        host = str(ipaddress.ip_interface(os.environ.get('AP_ADDR', '192.168.4.1/24')).ip)
        app = create_app(host=host)
        print('Private Wi-Fi setup is ready.', flush=True)
        server = make_server(host, int(os.environ.get('FLASK_PORT', '80')), app, threaded=True,
                             request_handler=QuietRequestHandler)
        server.socket.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE,
                                 os.environ.get('IFACE', 'wlan0').encode() + b'\0')
        server.serve_forever()
    except Exception:
        raise SystemExit('Wi-Fi setup unavailable; check setup credentials, network and service configuration.') from None


if __name__ == '__main__':
    main()
