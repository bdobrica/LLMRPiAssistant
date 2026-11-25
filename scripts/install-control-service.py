#!/usr/bin/env python3
"""Install the unprivileged service and migrate the former phone-port defaults."""

from configparser import ConfigParser
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rpi_assistant.app.admin_auth import verifier
from rpi_assistant.piwifi.credentials import initialize


def migrate_config(text):
    parser = ConfigParser(interpolation=None)
    parser.read_string(text)  # Reject malformed/duplicate sections before writing anything.
    lines, in_controls = [], False
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith('['):
            in_controls = line.strip().split(']', 1)[0].lower() == '[controls'
        if in_controls:
            for key, old, new in (('host', '0.0.0.0', 'lan'), ('port', '8767', '80')):
                line = re.sub(r'^(\s*'+key+r'\s*[=:]\s*)'+re.escape(old)+r'(\s*)$',
                              lambda match: match[1]+new+match[2], line, flags=re.IGNORECASE)
        lines.append(line)
    return ''.join(lines)


def install(project, python, *, root=Path('/')):
    project, python = Path(project).resolve(), Path(python).absolute()
    for value in (str(project), str(python)):
        if any(char in value for char in '\n\r%$'):
            raise ValueError('Unsupported installation path')
    unit = root/'etc/systemd/system/rpi-assistant.service'
    config = project/'rpi_assistant/config.ini'
    text = (project/'systemd/rpi-assistant.service').read_text()
    # Preserve an existing explicitly configured service user (default is pi).
    if unit.exists():
        users = re.findall(r'^User=(.+)$', unit.read_text(), flags=re.MULTILINE)
        if users:
            user = users[-1].strip()
            if user in ('root', '0') or not re.fullmatch(r'[a-zA-Z0-9_-]+', user):
                raise ValueError('Configure a non-root service user before installation')
            text = re.sub(r'^User=.*$', 'User='+user, text, flags=re.MULTILINE)
    text = re.sub(r'^WorkingDirectory=.*$', lambda _: 'WorkingDirectory='+str(project), text, flags=re.MULTILINE)
    text = re.sub(r'^ExecStart=.*$', lambda _: 'ExecStart='+json.dumps(str(python))+' -m rpi_assistant.app', text, flags=re.MULTILINE)
    updates = {unit: text}
    # Units with low-port capability have already migrated. Respect later edits,
    # including a deliberate return to the old high port.
    if config.exists() and not (unit.exists() and 'AmbientCapabilities=CAP_NET_BIND_SERVICE' in unit.read_text()):
        original = config.read_text()
        migrated = migrate_config(original)
        if original != migrated:
            updates[config] = migrated
    # Only the verifier goes into the unprivileged service's credential directory.
    credential = root/'etc/rpi-assistant/phone-admin.digest'
    code = initialize(root/'etc/piwifi/setup.json')['code']
    updates[credential] = verifier(code) + '\n'
    backup = root/'var/backups/rpi-assistant-controls'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup.mkdir(parents=True, mode=0o700)
    saved = {}
    for index, path in enumerate(updates):
        if path.exists():
            target = backup/(str(index)+'-'+path.name)
            shutil.copy2(path, target)
            target.chmod(0o600)
            saved[path] = (target, path.stat())
    def atomic_write(path, data, mode, owner=None):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name+'.controls-new')
        try:
            fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, 'w') as output:
                output.write(data)
                output.flush(); os.fsync(output.fileno())
            temporary.chmod(mode)
            if owner is not None:
                os.chown(temporary, owner.st_uid, owner.st_gid)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    changed = []
    try:
        for path, data in updates.items():
            owner = saved[path][1] if path in saved else None
            atomic_write(path, data, 0o644 if path == unit else 0o600, owner)
            changed.append(path)
    except Exception:
        for path in reversed(changed):
            if path in saved:
                source, owner = saved[path]
                atomic_write(path, source.read_text(), owner.st_mode & 0o777, owner)
            else:
                path.unlink(missing_ok=True)
        raise
    return backup


if __name__ == '__main__':
    try:
        backup = install(Path(sys.argv[1]), Path(sys.argv[2]))
        print('Phone service configuration installed; previous files saved privately in '+str(backup))
        print('Reload systemd and restart the service to apply. Custom ports/loopback-only hosts are retained.')
    except Exception:
        raise SystemExit('Service installation failed; check paths, INI syntax and permissions. Configuration contents were not printed.') from None
