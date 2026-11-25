"""Persistent local countdowns and bounded, offline audible alerts."""

import json
import math
from pathlib import Path
import sqlite3
import threading
import time
import uuid

from .playback import PlaybackStopped, PlaybackInterrupted


def boot_id():
    try:
        return Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    except OSError:
        return str(uuid.uuid4())


class Timers:
    def __init__(self, path, alert_seconds=120, *, wall=time.time, monotonic=time.monotonic, boot=None):
        self.wall, self.monotonic = wall, monotonic
        self.boot = boot or boot_id()
        self.alert_seconds = alert_seconds
        self.lock = threading.RLock()
        self.error = None
        self.db = None
        try:
            path = Path(path).expanduser()
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            self.db = sqlite3.connect(path, timeout=2, check_same_thread=False)
            path.chmod(0o600)
            self.db.row_factory = sqlite3.Row
            self.db.execute('PRAGMA synchronous=FULL')
            self.db.execute('''CREATE TABLE IF NOT EXISTS timers (
                id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL, label TEXT NOT NULL,
                seconds INTEGER NOT NULL, created REAL NOT NULL, due REAL NOT NULL,
                boot TEXT NOT NULL, deadline REAL NOT NULL, state TEXT NOT NULL,
                ring_until REAL, ring_boot TEXT, ring_deadline REAL)''')
            self.db.commit()
        except (OSError, sqlite3.Error):
            self.error = 'Timer storage is unavailable. No new timer can be confirmed.'

    def _ready(self):
        if self.error:
            raise RuntimeError(self.error)

    def create(self, seconds, label='', request_id=None):
        if type(seconds) is not int or not 1 <= seconds <= 604800:
            raise ValueError('How long should I set the timer for? Choose a duration from one second to seven days.')
        if not isinstance(label, str) or len(label) > 64:
            raise ValueError('Timer names must be at most 64 characters.')
        label = ' '.join(label.split()) or 'Timer'
        request_id = request_id or uuid.uuid4().hex
        with self.lock:
            self._ready()
            existing = self.db.execute('SELECT * FROM timers WHERE request_id=?', (request_id,)).fetchone()
            if existing:
                return self._view(existing)
            count = self.db.execute("SELECT count(*) FROM timers WHERE state IN ('pending','ringing')").fetchone()[0]
            if count >= 32:
                raise ValueError('There are already 32 active timers. Cancel one first.')
            now, mono = self.wall(), self.monotonic()
            identifier = uuid.uuid4().hex[:12]
            with self.db:
                self.db.execute('INSERT INTO timers VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                                (identifier, request_id, label, seconds, now, now+seconds,
                                 self.boot, mono+seconds, 'pending', None, None, None))
                self._prune()
            # Returning from the transaction means the durable commit succeeded.
            return self._view(self.db.execute('SELECT * FROM timers WHERE id=?', (identifier,)).fetchone())

    def _prune(self):
        self.db.execute("DELETE FROM timers WHERE state IN ('cancelled','missed') AND id NOT IN "
                        "(SELECT id FROM timers WHERE state IN ('cancelled','missed') ORDER BY created DESC LIMIT 32)")

    def _remaining(self, row):
        if row['boot'] == self.boot:
            return row['deadline'] - self.monotonic()
        return row['due'] - self.wall()

    def _view(self, row):
        return {key: row[key] for key in ('id','label','seconds','due','state')} | {
            'remaining_seconds': max(0, math.ceil(self._remaining(row))),
        }

    def list(self):
        with self.lock:
            self._ready()
            return [self._view(row) for row in self.db.execute(
                "SELECT * FROM timers WHERE state!='cancelled' ORDER BY due LIMIT 64")]

    def tick(self):
        with self.lock:
            self._ready()
            now, mono = self.wall(), self.monotonic()
            rows = self.db.execute("SELECT * FROM timers WHERE state IN ('pending','ringing')").fetchall()
            with self.db:
                changed = False
                for row in rows:
                    if row['state'] == 'pending' and self._remaining(row) <= 0:
                        changed = True
                        self.db.execute("UPDATE timers SET state='ringing', ring_until=?, ring_boot=?, ring_deadline=? WHERE id=?",
                                        (now+self.alert_seconds, self.boot, mono+self.alert_seconds, row['id']))
                    elif row['state'] == 'ringing':
                        remaining = (row['ring_deadline']-mono if row['ring_boot']==self.boot else row['ring_until']-now)
                        if remaining <= 0:
                            changed = True
                            self.db.execute("UPDATE timers SET state='missed' WHERE id=?", (row['id'],))
                if changed:
                    self._prune()
            return self.list()

    def cancel(self, identifier):
        with self.lock:
            self._ready()
            if not isinstance(identifier, str):
                raise ValueError('Choose a timer ID or all.')
            if identifier == 'all':
                rows = self.db.execute("SELECT id FROM timers WHERE state IN ('pending','ringing','missed')").fetchall()
            else:
                rows = self.db.execute("SELECT id FROM timers WHERE id=? AND state IN ('pending','ringing','missed')", (identifier,)).fetchall()
            if not rows:
                raise ValueError('That timer is no longer active.')
            with self.db:
                self.db.executemany("UPDATE timers SET state='cancelled' WHERE id=?", [(r['id'],) for r in rows])
                self._prune()
            return len(rows)

    def close(self):
        with self.lock:
            if self.db:
                self.db.close()
                self.db = None


def _tool(name, description, properties):
    return {'type':'function', 'function':{'name':name, 'description':description, 'strict':True,
            'parameters':{'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}}}


TIMER_TOOLS = [
    _tool('create_timer', 'Schedule a real local countdown. Use for an explicit timer request; ask for duration if missing. Maximum seven days.',
          {'seconds':{'type':'integer'}, 'label':{'type':'string','description':'Short name, or empty string.'}}),
    _tool('list_timers', 'Read actual timers, remaining seconds and IDs before answering timer status or resolving a named cancellation.', {}),
    _tool('cancel_timer', 'Cancel a real timer by exact ID from list_timers; all only when user explicitly asks to cancel all timers.',
          {'timer_id':{'type':'string'}}),
]
TIMER_NAMES = {item['function']['name'] for item in TIMER_TOOLS}
TIMER_INSTRUCTIONS = ('Use the local timer tools for countdowns. Never claim a timer was created or cancelled without a successful tool result. '
                      'For ambiguous durations or multiple matching timer names, ask a question. Do not invent timer IDs. '
                      'Use list_timers to resolve names or remaining time; do not calculate from old chat history. '
                      'Timers are durations, not calendar reminders. Do not use web search to schedule timers.')


def duration_text(seconds):
    parts = []
    for unit, size in (("hour", 3600), ("minute", 60), ("second", 1)):
        count, seconds = divmod(seconds, size)
        if count:
            parts.append(f"{count} {unit}{'s' if count != 1 else ''}")
    return " ".join(parts)


def timer_action(timers, name, arguments, request_id):
    """Deterministic receipts prevent a model from turning storage failure into success."""
    try:
        if name == 'create_timer':
            timer = timers.create(arguments.get('seconds'), arguments.get('label', ''), request_id)
            return {'ok':True, 'timer':timer, 'message':f"{timer['label']} set for {duration_text(timer['seconds'])}."}
        if name == 'cancel_timer':
            count = timers.cancel(arguments.get('timer_id'))
            return {'ok':True, 'message':f"Cancelled {count} timer{'s' if count != 1 else ''}."}
        if name == 'list_timers':
            return {'ok':True, 'timers':timers.list()}
        raise ValueError('Unknown timer command')
    except ValueError as exc:
        return {'ok':False, 'message':str(exc)}
    except Exception:
        return {'ok':False, 'message':"I couldn't save or read that timer. I can't confirm the change. Please check the local timer page."}


class TimerAlerts:
    def __init__(self, timers, controls, reminders=None):
        self.timers, self.controls = timers, controls
        self.reminders = reminders
        self.reminder_error = None
        self.stop_event = threading.Event()
        self.silenced = set()
        self.active = False
        self.error = None
        self.lock = threading.RLock()
        self.thread = threading.Thread(target=self._run, name='timer-alerts', daemon=True)

    def start(self):
        self.thread.start()

    @staticmethod
    def _key(row):
        return (row.get('kind', 'timer'), row['id'])

    def _reminder_rows(self, update=False):
        if self.reminders is None:
            return []
        try:
            rows = self.reminders.tick() if update else self.reminders.list()
            if update:
                self.reminder_error = None
            return rows
        except Exception:
            self.reminder_error = 'Reminder storage is unavailable; alerts cannot be confirmed.'
            return []

    def ringing(self):
        return [r for r in self.timers.list()+self._reminder_rows() if r['state']=='ringing' and self._key(r) not in self.silenced]

    def dismiss(self):
        with self.lock:
            rows = self.ringing()
            try:
                for row in rows:
                    store = self.reminders if row.get('kind') == 'reminder' else self.timers
                    store.cancel(row['id'])
            finally:
                self.silenced.update(self._key(r) for r in rows)
                self.controls.playback.stop()
            return bool(rows)

    def _run(self):
        next_chime = 0
        try:
            while not self.stop_event.is_set():
                if not self.controls.recorder.running:
                    self.stop_event.wait(.25)
                    continue
                try:
                    current = self.timers.tick()+self._reminder_rows(update=True)
                    self.silenced.intersection_update(self._key(r) for r in current)
                    with self.controls.lock:
                        rows = self.ringing()
                        if rows and not self.active:
                            self.controls._stop()
                            self.controls.recorder.begin_alert()
                            self.active = True
                        if not rows and self.active:
                            self.controls.recorder.end_alert()
                            self.active = False
                        generation = self.controls.playback.generation
                    if rows and time.monotonic() >= next_chime:
                        # A concurrent dismissal invalidates this exact queued chime.
                        self.controls.playback.prompt('timer.wav', expected_generation=generation)
                        next_chime = time.monotonic()+2
                    self.error = None
                except (PlaybackStopped, PlaybackInterrupted):
                    pass
                except Exception as exc:
                    self.error = f'Timer alert unavailable ({type(exc).__name__}). Check the timer page.'
                    if self.active:
                        self.controls.playback.stop()
                        self.controls.recorder.end_alert()
                        self.active = False
                self.stop_event.wait(.25)
        finally:
            if self.active:
                self.controls.recorder.end_alert()
                self.active = False

    def close(self):
        self.stop_event.set()
        if self.active:
            self.controls.playback.stop()
        if self.thread.ident is not None:
            self.thread.join(timeout=3)
