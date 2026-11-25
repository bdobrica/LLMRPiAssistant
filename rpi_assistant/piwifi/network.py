"""Bounded NetworkManager operations that never report commands or secret output."""

from configparser import ConfigParser
import io
import os
from pathlib import Path
import re
import subprocess
import uuid

HOTSPOT = 'piwifi-hotspot'
PROFILE_DIR = Path('/etc/NetworkManager/system-connections')


class NetworkError(RuntimeError):
    pass


def run(arguments, *, wait=10):
    try:
        result = subprocess.run(['nmcli', '--wait', str(wait), *arguments],
                                capture_output=True, text=True, timeout=wait + 5,
                                env={**os.environ, 'LC_ALL': 'C'})
        if result.returncode:
            raise NetworkError('NetworkManager could not complete the request.')
        return result.stdout.rstrip('\n')
    except (OSError, subprocess.SubprocessError):
        raise NetworkError('NetworkManager is unavailable or the request timed out.') from None


def fields(line):
    """Decode nmcli terse escaped colons/backslashes without splitting SSIDs."""
    values, part, escaped = [], '', False
    for char in line:
        if escaped:
            part += char
            escaped = False
        elif char == '\\':
            escaped = True
        elif char == ':':
            values.append(part)
            part = ''
        else:
            part += char
    values.append(part)
    return values


def validate(ssid, password):
    if (not isinstance(ssid, str) or not 1 <= len(ssid.encode('utf-8')) <= 32
            or any(ord(char) < 32 or ord(char) == 127 for char in ssid)):
        raise ValueError('Enter a network name of 1–32 UTF-8 bytes without control characters.')
    if not isinstance(password, str) or (password and not (
            8 <= len(password) <= 63 and all(32 <= ord(char) <= 126 for char in password)
            or re.fullmatch(r'[a-fA-F0-9]{64}', password))):
        raise ValueError('Use an 8–63 character Wi-Fi password, 64 hexadecimal digits, or leave blank for an open network.')


def private_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as target:
        target.write(content)
        target.flush()
        os.fsync(target.fileno())


def create_profile(ssid, password, iface, *, hotspot=False, address='192.168.4.1/24', directory=PROFILE_DIR):
    validate(ssid, password)
    identifier = str(uuid.uuid4())
    name = HOTSPOT if hotspot else 'PiAssistant Wi-Fi ' + identifier[:8]
    arguments = ['--offline', 'connection', 'add', 'type', 'wifi', 'ifname', iface,
                 'con-name', name, 'ssid', ssid, 'connection.uuid', identifier, 'connection.autoconnect', 'no']
    if hotspot:
        arguments += ['wifi.mode', 'ap', 'wifi.band', 'bg', 'ipv4.method', 'shared',
                      'ipv4.addresses', address, 'ipv6.method', 'disabled']
    # NetworkManager serializes SSIDs correctly, including colons/backslashes.
    # Secret material is then added to the private keyfile, never command arguments.
    parser = ConfigParser(interpolation=None)
    parser.read_string(run(arguments))
    if password:
        parser['wifi-security'] = {'key-mgmt': 'wpa-psk', 'psk-flags': '0',
                                   'psk': password.replace('\\', '\\\\').replace(' ', '\\s')}
    content = io.StringIO()
    parser.write(content, space_around_delimiters=False)
    path = Path(directory) / ('piwifi-' + identifier + '.nmconnection')
    private_write(path, content.getvalue())
    try:
        run(['connection', 'load', str(path)])
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return identifier, path


def client_connected(iface):
    for line in run(['-t', '-f', 'DEVICE,TYPE,STATE,CONNECTION', 'device']).splitlines():
        row = fields(line)
        if len(row) == 4 and row[0] == iface:
            return row[1] == 'wifi' and row[2] == 'connected' and row[3] != HOTSPOT
    return False


def connect(ssid, password, iface, *, directory=PROFILE_DIR):
    identifier, path = create_profile(ssid, password, iface, directory=directory)
    try:
        run(['connection', 'up', 'uuid', identifier, 'ifname', iface], wait=30)
        run(['connection', 'modify', 'uuid', identifier, 'connection.autoconnect', 'yes'])
    except Exception:
        try:
            run(['connection', 'delete', 'uuid', identifier])
        finally:
            path.unlink(missing_ok=True)
        raise NetworkError('Could not join Wi-Fi. Check the network and password, then try again.') from None


def scan(iface):
    rows = run(['-t', '-f', 'SSID', 'device', 'wifi', 'list', 'ifname', iface, '--rescan', 'no']).splitlines()
    return list(dict.fromkeys(fields(row)[0] for row in rows if row))[:100]


def main():
    """Manager helper: keep the setup code out of shell variables and process args."""
    import sys
    from .credentials import load
    try:
        if sys.argv[1:] != ['hotspot']:
            raise ValueError()
        credentials = load()
        try:
            run(['connection', 'delete', 'id', HOTSPOT])
        except NetworkError:
            pass
        create_profile(os.environ.get('AP_SSID', 'PiAssistant-Setup-' + credentials['device_id']),
                       credentials['code'], os.environ.get('IFACE', 'wlan0'), hotspot=True,
                       address=os.environ.get('AP_ADDR', '192.168.4.1/24'))
        run(['connection', 'up', 'id', HOTSPOT])
    except Exception:
        raise SystemExit('Could not start the private setup hotspot; check NetworkManager and setup configuration.') from None


if __name__ == '__main__':
    main()
