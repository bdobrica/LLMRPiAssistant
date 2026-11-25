"""One recoverable service restart. The previous INI stays active on disk until ready."""

import json
import os
from pathlib import Path
import threading

from .config import parse_config
from .config_editor import EditorError, read_ini


def bytes_or_none(text):
    return text.encode() if text is not None else None


def state_moves(old, new):
    """Move existing stores while their connections are closed, including SQLite journals."""
    moves = []
    for section in ("timers", "household", "controls", "weather"):
        src = Path(getattr(old, section).state_path).expanduser()
        dst = Path(getattr(new, section).state_path).expanduser()
        if src.absolute() == dst.absolute():
            continue
        if src.is_symlink() or dst.is_symlink():
            raise EditorError("Choose regular state files. A state path is a symbolic link.")
        pairs = [(src, dst)]
        if section in ("timers", "household"):
            pairs.extend((Path(str(src) + suffix), Path(str(dst) + suffix))
                         for suffix in ("-journal", "-wal", "-shm"))
        elif section == "controls":
            pairs.append((src.with_suffix(".speaker.json"), dst.with_suffix(".speaker.json")))
        for source, target in pairs:
            if source.resolve() == target.resolve():
                continue
            if os.path.lexists(target) or source.is_symlink() or (source.exists() and not source.is_file()):
                raise EditorError("Choose an unused destination for saved data. Existing files are never overwritten.")
            moves.append((str(source.absolute()), str(target.absolute())))
    targets = [Path(b).resolve() for _, b in moves]
    sources = {Path(a).resolve() for a, _ in moves}
    if len(set(targets)) != len(targets) or sources.intersection(targets):
        raise EditorError("Each store needs a new destination separate from the previous stores.")
    return moves


def relocate(moves):
    """A hard link followed by unlink is recoverable and cannot overwrite another file."""
    for source, target in moves:
        source, target = Path(source), Path(target)
        if not source.exists():
            continue
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not target.exists():
            os.link(source, target, follow_symlinks=False)
        if not source.samefile(target):
            raise OSError("State destination already in use")
        sync_directory(target.parent)
        source.unlink()
        sync_directory(source.parent)


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def check_paths(old, new, config_path, *, undo):
    stores = [Path(getattr(new, s).state_path).expanduser().resolve()
              for s in ("household", "controls", "timers", "weather")]
    reserved = [config_path.resolve(), *stores, stores[1].with_suffix(".speaker.json"),
                stores[1].with_suffix(".tmp")]
    for db in (stores[0], stores[2]):
        reserved.extend(Path(str(db) + ext) for ext in ("-journal", "-wal", "-shm"))
    for section, key, suffixes in (("audio_output", "tts_output_path", {".wav", ".mp3"}),
                                   ("recording", "output_path", {".wav"}),
                                   ("logging", "log_file", {".log", ".jsonl"})):
        raw = getattr(getattr(new, section), key)
        path = Path(raw).expanduser()
        if raw != getattr(getattr(old, section), key):
            previous_log = undo and section == "logging" and path.is_file() and not path.is_symlink()
            if (os.path.lexists(path) and not previous_log) or path.suffix.lower() not in suffixes:
                raise EditorError(f"Choose an unused {', '.join(sorted(suffixes))} file for {section}.{key}.")
        reserved.append(path.resolve())
    if len(set(reserved)) != len(reserved) or any(
        p.name.startswith(config_path.name + ".phone-") and p.parent == config_path.resolve().parent for p in reserved
    ):
        raise EditorError("Configuration, logs, audio and each saved store need separate paths.")


class SettingsTrial:
    def __init__(self, path):
        self.path = Path(path)
        self.journal = self.path.with_name(self.path.name + ".phone-trial.json")
        self.result = self.path.with_name(self.path.name + ".phone-result")
        self.undo = self.path.with_name(self.path.name + ".phone-undo.json")
        self.timer = None
        self.record = None

    @staticmethod
    def write(path, data):
        from .phone_settings import atomic_write
        if data is None:
            path.unlink(missing_ok=True)
        else:
            atomic_write(path, data)

    def store(self, record):
        self.write(self.journal, json.dumps(record).encode())

    def arm(self, before, after, touched, *, undo=False):
        if self.journal.exists():
            raise EditorError("A settings restart is already in progress.")
        old = parse_config(read_ini(before), allow_missing_api_key=True)
        new = parse_config(read_ini(after), allow_missing_api_key=True)
        check_paths(old, new, self.path, undo=undo)
        state_moves(old, new)
        self.store({"phase": "armed", "before": before.decode() if before is not None else None,
                    "after": after.decode() if after is not None else None,
                    "fields": sorted(touched), "undo": undo})
        return new

    def begin(self):
        """Called before hardware or storage is opened, using the service's actual environment."""
        if not self.journal.exists():
            return None
        record = json.loads(self.journal.read_bytes())
        self.record = record
        if record["phase"] == "committing":
            current = self.path.read_bytes() if self.path.exists() else None
            if current in (bytes_or_none(record["before"]), bytes_or_none(record["after"])):
                self.finish()
            else:
                relocate([(b, a) for a, b in reversed(record["moves"])])
                self._done("Settings changed outside the phone during restart. External edit retained.")
            return None
        if record["phase"] == "testing":
            relocate([(b, a) for a, b in reversed(record["moves"])])
            self._done("The settings trial failed. Previous configuration and saved data restored.")
            return None
        before, after = (bytes_or_none(record[key]) for key in ("before", "after"))
        if before != (self.path.read_bytes() if self.path.exists() else None):
            self._done("Restart cancelled because the configuration was edited elsewhere.")
            return None
        try:
            old = parse_config(read_ini(before), allow_missing_api_key=True)
            new = parse_config(read_ini(after), allow_missing_api_key=True)
            check_paths(old, new, self.path, undo=record["undo"])
            record["moves"] = state_moves(old, new)
        except Exception:
            self._done("Restart validation failed. Previous settings retained.")
            return None
        record["phase"] = "testing"
        self.store(record)
        relocate(record["moves"])
        return new

    def watch(self, exit_process=os._exit):
        # systemd starts the old configuration if this candidate hangs during initialization.
        self.timer = threading.Timer(90, lambda: exit_process(75))
        self.timer.daemon = True
        self.timer.start()

    def finish(self):
        from .phone_settings import revision
        record = self.record
        before, after = (bytes_or_none(record[key]) for key in ("before", "after"))
        current = self.path.read_bytes() if self.path.exists() else None
        if current != before and not (record["phase"] == "committing" and current == after):
            raise EditorError("INI changed during restart.")
        record["phase"] = "committing"
        self.store(record)
        if record["undo"]:
            self.undo.unlink(missing_ok=True)
        else:
            self.write(self.undo, json.dumps({"config_text":record["before"], "restart":True,
                                              "fields":record["fields"], "applied_revision":revision(after)}).encode())
        self.write(self.path, after)
        self._done("Settings restored after restart." if record["undo"] else "Settings applied after restart.")

    def _done(self, message):
        if self.timer:
            self.timer.cancel()
        self.write(self.result, message.encode())
        self.journal.unlink()
        sync_directory(self.journal.parent)
        self.record = None
