"""Desktop-only browser check; never install a browser on the Pi for this probe.

python tests/probe_piwifi_browser.py --chromium /path/to/chrome --screenshot /tmp/setup.png
Uses synthetic data and a fake join operation. Real NetworkManager/phone checks
are separate. The first pass reproduces the old header conflict; the second checks
the actual application headers, native form submission and password reveal control.
"""

import argparse
import base64
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from unittest.mock import patch
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from websockets.sync.client import connect
from werkzeug.serving import make_server
from rpi_assistant.piwifi import network, webapp


class SyntheticJoin:
    busy = False
    message = ''

    def start(self, ssid, password):
        assert (ssid, password) == ('Example home network', 'SyntheticBrowser794')
        self.busy = True
        self.message = 'Synthetic connection accepted.'


def probe(chromium, *, reproduce_old_header=False, manual=False, screenshot=None):
    job = SyntheticJoin()
    app = webapp.create_app(host='127.0.0.1', setup_network='127.0.0.0/8', job=job)
    seen = []
    original = app.wsgi_app

    def record(environ, start_response):
        def respond(status, headers, exc_info=None):
            if reproduce_old_header:
                headers = [(key, 'no-referrer' if key.lower() == 'referrer-policy' else value) for key, value in headers]
            if environ['REQUEST_METHOD'] == 'POST':
                seen.append((environ.get('HTTP_ORIGIN'), int(status.split()[0])))
            return start_response(status, headers, exc_info)
        return original(environ, respond)

    app.wsgi_app = record
    server = make_server('127.0.0.1', 0, app, threaded=True, request_handler=webapp.QuietRequestHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    address = 'http://127.0.0.1:' + str(server.server_port)
    with tempfile.TemporaryDirectory(prefix='setup-browser-') as directory, patch.object(network, 'scan', return_value=['Example home network']):
        browser = subprocess.Popen([chromium, '--headless', '--no-sandbox', '--disable-gpu', '--no-proxy-server',
                                    '--remote-debugging-port=0', '--user-data-dir='+directory],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            port_file = Path(directory)/'DevToolsActivePort'
            for _ in range(100):
                if port_file.exists(): break
                if browser.poll() is not None: raise RuntimeError('Desktop Chromium failed to start')
                time.sleep(.1)
            port = port_file.read_text().splitlines()[0]
            with urlopen(Request('http://127.0.0.1:'+port+'/json/new?'+address+'/', method='PUT'), timeout=5) as response:
                target = json.load(response)
            with connect(target['webSocketDebuggerUrl']) as socket:
                index = 0

                def call(method, params):
                    nonlocal index
                    index += 1
                    socket.send(json.dumps({'id': index, 'method': method, 'params': params}))
                    while True:
                        response = json.loads(socket.recv(timeout=10))
                        if response.get('id') == index:
                            if 'error' in response: raise RuntimeError('Browser command failed')
                            return response.get('result', {})

                def js(expression):
                    return call('Runtime.evaluate', {'expression': expression, 'returnByValue': True})['result'].get('value')

                call('Emulation.setDeviceMetricsOverride', {'width':390, 'height':844, 'deviceScaleFactor':1, 'mobile':True})
                for _ in range(100):
                    if js("document.readyState==='complete' && !!document.getElementById('password')"): break
                    time.sleep(.1)
                assert js("document.getElementById('code')===null"), 'Unexpected second login'
                def key(name, number):
                    for kind in ('keyDown', 'keyUp'):
                        call('Input.dispatchKeyEvent', {'type':kind, 'key':name, 'windowsVirtualKeyCode':number})
                js("document.getElementById('network').focus()")
                key('ArrowDown', 40)
                assert js("document.getElementById('network').value==='Example home network'"), 'Dropdown selection failed'
                key('End', 35)
                assert js("!document.getElementById('ssid').disabled && !document.getElementById('manual-network').hidden")
                js("document.getElementById('ssid').value='Example home network'")
                if not manual:
                    key('ArrowUp', 38)
                    assert js("document.getElementById('ssid').disabled && document.getElementById('manual-network').hidden")
                assert js("JSON.stringify(new FormData(document.querySelector('form')).getAll('ssid'))") == '["Example home network"]'
                js("document.getElementById('password').value='SyntheticBrowser794'")
                js("document.getElementById('show-password').click()")
                assert js("document.getElementById('password').type==='text' && document.getElementById('password').value==='SyntheticBrowser794'")
                js("document.getElementById('show-password').click()")
                assert js("document.getElementById('password').type==='password'")
                if screenshot:
                    size = call('Page.getLayoutMetrics', {})['cssContentSize']
                    result = call('Page.captureScreenshot', {'format':'png', 'captureBeyondViewport':True,
                                  'clip':{'x':0, 'y':0, 'width':size['width'], 'height':size['height'], 'scale':1}})
                    screenshot.parent.mkdir(parents=True, exist_ok=True)
                    screenshot.write_bytes(base64.b64decode(result['data']))
                js("document.querySelector('form').requestSubmit()")
                for _ in range(100):
                    if seen: break
                    time.sleep(.1)
                if reproduce_old_header:
                    assert seen == [('null', 403)] and not job.busy, seen
                    print('PASS reproduced old no-referrer / Origin:null form rejection in Chromium')
                else:
                    assert seen == [(address, 202)] and job.busy, seen
                    print('PASS actual headers, '+('manual network entry' if manual else 'native network dropdown')+', show/hide password and HTML form submission in Chromium')
        finally:
            browser.terminate()
            browser.wait(timeout=10)
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--chromium', required=True)
    parser.add_argument('--screenshot', type=Path)
    arguments = parser.parse_args()
    probe(arguments.chromium, reproduce_old_header=True)
    probe(arguments.chromium, screenshot=arguments.screenshot)
    probe(arguments.chromium, manual=True)
