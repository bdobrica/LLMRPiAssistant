"""Persistent, private setup code. Only the explicit show command prints it."""

import argparse
import json
import os
from pathlib import Path
import re
import secrets
import stat

DEFAULT_PATH = Path('/etc/piwifi/setup.json')


def load(path=DEFAULT_PATH):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.geteuid():
            raise ValueError('Setup credentials must be private and owned by the service user')
        value = json.loads(source.read(4096))
    if (value.get('version') != 1 or not re.fullmatch(r'[A-Z2-9]{4}(?:-[A-Z2-9]{4}){3}', value.get('code', ''))
            or not re.fullmatch(r'[a-f0-9]{6}', value.get('device_id', ''))):
        raise ValueError('Invalid setup credentials')
    return value


def initialize(path=DEFAULT_PATH):
    path = Path(path)
    if path.exists():
        return load(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    value = {'version': 1, 'code': '-'.join(''.join(secrets.choice(alphabet) for _ in range(4)) for _ in range(4)),
             'device_id': secrets.token_hex(3)}
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as target:
        json.dump(value, target)
        target.flush()
        os.fsync(target.fileno())
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('init', 'show'))
    args = parser.parse_args()
    try:
        value = initialize() if args.action == 'init' else load()
        if args.action == 'show':
            print('Setup Wi-Fi: ' + os.environ.get('AP_SSID', 'PiAssistant-Setup-' + value['device_id']))
            print('Setup Wi-Fi password: ' + value['code'])
            port = os.environ.get('FLASK_PORT', '80')
            print('Page: http://' + os.environ.get('AP_ADDR', '192.168.4.1/24').split('/')[0]
                  + ('' if port == '80' else ':' + port))
        else:
            print('Private device setup credentials are ready.')
    except Exception:
        raise SystemExit('Setup credentials unavailable; check the private file and its permissions.') from None


if __name__ == '__main__':
    main()
