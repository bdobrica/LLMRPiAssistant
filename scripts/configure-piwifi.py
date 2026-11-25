#!/usr/bin/env python3
"""Install private provisioning configuration without displaying credentials."""

from datetime import datetime, timezone
import ipaddress
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rpi_assistant.piwifi.credentials import initialize


def configure(project, venv, *, root=Path('/'), environment=None):
    environment = os.environ if environment is None else environment
    def target(path):
        return root / path.lstrip('/')
    config_path = target('/etc/default/piwifi')
    previous = {}
    if config_path.exists():
        for line in config_path.read_text().splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                key, value = line.split('=', 1)
                if key in ('IFACE', 'AP_SSID', 'AP_ADDR', 'FLASK_PORT', 'AP_NO_CLIENT_TIMEOUT', 'AP_WIFI_RETRY_INTERVAL'):
                    words = shlex.split(value)
                    if len(words) == 1:
                        previous[key] = words[0]
        # Replace the old default AP cycling intervals; retain explicit nondefaults.
        if previous.get('AP_NO_CLIENT_TIMEOUT') == '30': previous['AP_NO_CLIENT_TIMEOUT'] = '300'
        if previous.get('AP_WIFI_RETRY_INTERVAL') == '15': previous['AP_WIFI_RETRY_INTERVAL'] = '120'
        if previous.get('FLASK_PORT') == '8080': previous['FLASK_PORT'] = '80'
    credentials = initialize(target('/etc/piwifi/setup.json'))
    defaults = {'IFACE': 'wlan0', 'AP_SSID': 'PiAssistant-Setup-' + credentials['device_id'],
                'AP_ADDR': '192.168.4.1/24', 'FLASK_PORT': '80',
                'AP_NO_CLIENT_TIMEOUT': '300', 'AP_WIFI_RETRY_INTERVAL': '120'}
    values = {key: environment.get(key, previous.get(key, default)) for key, default in defaults.items()}
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,15}', values['IFACE']): raise ValueError('Invalid interface')
    if not 1 <= len(values['AP_SSID'].encode()) <= 32 or any(ord(c) < 32 for c in values['AP_SSID']): raise ValueError('Invalid setup SSID')
    address = ipaddress.ip_interface(values['AP_ADDR'])
    if address.version != 4 or not address.ip.is_private: raise ValueError('Use a private IPv4 setup address')
    if not 1 <= int(values['FLASK_PORT']) <= 65535: raise ValueError('Invalid setup port')
    for key in ('AP_NO_CLIENT_TIMEOUT', 'AP_WIFI_RETRY_INTERVAL'):
        if not 0 <= int(values[key]) <= 86400: raise ValueError('Invalid setup interval')
    project, venv = Path(project).resolve(), Path(venv).resolve()
    for path in (project, venv):
        if any(c in str(path) for c in '\n\r%$'): raise ValueError('Unsupported installation path')
    values.update(PYTHONPATH=str(project), PIWIFI_PYTHON=str(venv/'bin/python'))
    manager_override = target('/etc/systemd/system/piwifi-manager.service.d/override.conf')
    flask_override = target('/etc/systemd/system/piwifi-flask.service.d/override.conf')
    updates = {
        config_path: ('# Private setup configuration. Credentials are in /etc/piwifi/setup.json.\n' +
                      ''.join(key+'='+json.dumps(value, ensure_ascii=False)+'\n' for key, value in values.items()), 0o600),
        manager_override: ('[Service]\n# Settings come from /etc/default/piwifi; no secrets in unit properties.\n', 0o600),
        flask_override: ('[Service]\nWorkingDirectory='+str(project)+'\nExecStart=\nExecStart='+
                         json.dumps(str(venv/'bin/python'))+' -m rpi_assistant.piwifi.webapp\n', 0o600),
        target('/usr/local/bin/piwifi-setup-code'): ('#!/bin/sh\nset -eu\nexport PYTHONPATH='+shlex.quote(str(project))+
               '\n# This explicit command is the only routine that prints the device code.\n'+
               'exec '+shlex.quote(str(venv/'bin/python'))+' -c '+shlex.quote(
                   'import os,shlex,sys; from pathlib import Path; '
                   'p=Path("/etc/default/piwifi"); '
                   'pairs=[line.split("=",1) for line in p.read_text().splitlines() if "=" in line and not line.startswith("#")]; '
                   'os.environ.update({k:shlex.split(v)[0] for k,v in pairs if k in ("AP_SSID","AP_ADDR","FLASK_PORT")}); '
                   'from rpi_assistant.piwifi.credentials import main; sys.argv=["setup-code","show"]; main()')+'\n', 0o755),
    }
    for filename in ('piwifi-flask.service', 'piwifi-manager.service'):
        updates[target('/etc/systemd/system/'+filename)] = ((project/'systemd'/filename).read_text(), 0o644)
    updates[target('/usr/local/bin/piwifi-manager.sh')] = ((project/'scripts/piwifi-manager.sh').read_text(), 0o755)
    backup = target('/var/backups/piwifi') / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup.mkdir(mode=0o700, parents=True)
    for path in updates:
        if path.exists():
            saved = backup / path.relative_to(root)
            saved.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            shutil.copy2(path, saved)
    try:
        for path, (text, mode) in updates.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(path.name+'.piwifi-new')
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w') as output:
                output.write(text)
                output.flush(); os.fsync(output.fileno())
            temporary.chmod(mode); temporary.replace(path)
    except Exception:
        for path in updates:
            saved = backup / path.relative_to(root)
            if saved.exists(): shutil.copy2(saved, path)
            else: path.unlink(missing_ok=True)
            path.with_name(path.name+'.piwifi-new').unlink(missing_ok=True)
        raise
    return backup


if __name__ == '__main__':
    try:
        backup = configure(Path(sys.argv[1]), Path(sys.argv[2]))
        print('Private provisioning configuration installed. Previous files: '+str(backup))
        print('Retrieve the device code explicitly with: sudo piwifi-setup-code')
    except Exception:
        raise SystemExit('Wi-Fi setup configuration failed; check paths, settings and permissions. No credentials were printed.') from None
