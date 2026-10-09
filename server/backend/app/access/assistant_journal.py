"""Private, explicitly initialized assistant receipts; never stores audio or secrets."""
from contextlib import contextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
import stat
import time
import uuid

RETENTION_SECONDS = 30 * 86400
MAX_RECORDS = 100000
SCHEMA = '''
PRAGMA application_id=1346914881;
PRAGMA user_version=1;
CREATE TABLE requests (
 request_id TEXT PRIMARY KEY, account_id TEXT NOT NULL, library_id TEXT NOT NULL,
 operation TEXT NOT NULL CHECK(operation IN ('turn','transcribe','speech')),
 parent_request_id TEXT, status TEXT NOT NULL CHECK(status IN ('received','succeeded','failed','interrupted')),
 created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
 http_status INTEGER, error_code TEXT, input_text TEXT, recognized_text TEXT,
 result_kind TEXT, result_total INTEGER, client_outcome TEXT
);
CREATE INDEX expiry ON requests(expires_at);
CREATE TABLE events (
 request_id TEXT NOT NULL REFERENCES requests(request_id) ON DELETE CASCADE,
 stage TEXT NOT NULL, occurred_at INTEGER NOT NULL, PRIMARY KEY(request_id,stage)
);
'''


class JournalUnavailable(Exception):
    pass


class JournalConflict(Exception):
    pass


class JournalMissing(Exception):
    pass


def request_id(value):
    try:
        parsed = uuid.UUID(value)
        if parsed.version != 4 or str(parsed) != value:
            raise ValueError()
        return value
    except (ValueError, TypeError, AttributeError):
        raise ValueError('Invalid request ID') from None


def _path(path, *, exists=True):
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts or path == Path(path.anchor):
        raise JournalUnavailable()
    for parent in path.parents:
        if parent.is_symlink():
            raise JournalUnavailable()
    if exists and (not stat.S_ISREG(path.lstat().st_mode)
                   or path.resolve(strict=True) != path):
        raise JournalUnavailable()
    return path


def initialize(path):
    """Deliberate exclusive creation only; callers own host ACL provisioning."""
    path = _path(path, exists=False)
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    # Do not delete on error: report the failed initialization for operator review.
    with sqlite3.connect(path) as db:
        db.execute('PRAGMA journal_mode=DELETE')
        db.execute('PRAGMA secure_delete=ON')
        db.executescript(SCHEMA)
    return Journal(path)


def _iso(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat().replace('+00:00', 'Z')


class Journal:
    def __init__(self, path, *, clock=time.time):
        self.path = Path(path)
        self.clock = clock
        with self.connection():
            pass

    @contextmanager
    def connection(self):
        db = None
        try:
            path = _path(self.path)
            before = path.lstat()
            db = sqlite3.connect(path.as_uri() + '?mode=rw', uri=True, timeout=2)
            after = path.lstat()
            if (before.st_dev,before.st_ino) != (after.st_dev,after.st_ino):
                raise JournalUnavailable()
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA trusted_schema=OFF')
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('PRAGMA secure_delete=ON')
            if (db.execute('PRAGMA application_id').fetchone()[0] != 1346914881
                    or db.execute('PRAGMA user_version').fetchone()[0] != 1
                    or db.execute('PRAGMA journal_mode').fetchone()[0] != 'delete'):
                raise JournalUnavailable()
            columns = [row[1] for row in db.execute('PRAGMA table_info(requests)')]
            if columns != ['request_id','account_id','library_id','operation','parent_request_id',
                           'status','created_at','updated_at','expires_at','http_status','error_code',
                           'input_text','recognized_text','result_kind','result_total','client_outcome']:
                raise JournalUnavailable()
            yield db
            db.commit()
        except (OSError, sqlite3.Error, ValueError):
            raise JournalUnavailable() from None
        finally:
            if db is not None:
                db.close()

    def begin(self, identity, library, operation, ident, parent=None, text=None):
        request_id(ident)
        if parent is not None:
            request_id(parent)
        if operation not in ('turn', 'transcribe', 'speech'):
            raise ValueError('Invalid operation')
        if text is not None and (type(text) is not str or len(text.encode('utf-8')) > 1024):
            raise ValueError('Invalid input')
        now = int(self.clock())
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM requests WHERE expires_at<=?', (now,))
            if db.execute('SELECT 1 FROM requests WHERE request_id=?', (ident,)).fetchone():
                raise JournalConflict()
            if parent is not None:
                expected = {'turn':'transcribe', 'speech':'turn'}.get(operation)
                row = db.execute('''SELECT operation,status FROM requests WHERE request_id=?
                    AND account_id=? AND library_id=? AND expires_at>?''',
                    (parent, identity, library, now)).fetchone()
                if not row or row['operation'] != expected or row['status'] != 'succeeded':
                    raise JournalMissing()
            if db.execute('SELECT count(*) FROM requests').fetchone()[0] >= MAX_RECORDS:
                raise JournalUnavailable()
            db.execute('''INSERT INTO requests(request_id,account_id,library_id,operation,parent_request_id,
                status,created_at,updated_at,expires_at,input_text) VALUES (?,?,?,?,?,'received',?,?,?,?)''',
                (ident, identity, library, operation, parent, now, now, now+RETENTION_SECONDS, text))
            db.execute('INSERT INTO events VALUES (?,?,?)', (ident, 'received', now))

    def stage(self, ident, stage):
        if stage not in ('validated', 'provider_started', 'provider_completed', 'action_started'):
            raise ValueError('Invalid stage')
        with self.connection() as db:
            db.execute('INSERT OR IGNORE INTO events SELECT request_id,?,? FROM requests '
                       "WHERE request_id=? AND status='received' AND expires_at>?",
                       (stage, int(self.clock()), ident, int(self.clock())))

    def finish(self, ident, status, *, http_status, error=None, transcript=None, kind=None, total=None):
        if status not in ('succeeded','failed'):
            raise ValueError('Invalid status')
        if transcript is not None and (type(transcript) is not str or len(transcript.encode('utf-8')) > 4096):
            raise JournalUnavailable()
        now = int(self.clock())
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            changed = db.execute('''UPDATE requests SET status=?,updated_at=?,http_status=?,error_code=?,
                recognized_text=?,result_kind=?,result_total=? WHERE request_id=? AND status='received'
                AND expires_at>?''', (status, now, http_status, error, transcript, kind, total, ident, now)).rowcount
            if changed != 1:
                raise JournalUnavailable()
            db.execute('INSERT INTO events VALUES (?,?,?)', (ident, status, now))

    def get(self, ident, identity, library):
        request_id(ident)
        with self.connection() as db:
            row = db.execute('''SELECT * FROM requests WHERE request_id=? AND account_id=?
                AND library_id=? AND expires_at>?''', (ident, identity, library, int(self.clock()))).fetchone()
            if row is None:
                raise JournalMissing()
            return self.envelope(row)

    @staticmethod
    def envelope(row):
        return dict(version=1, **{key: (_iso(row[key]) if key in ('created_at','updated_at','expires_at') else row[key])
            for key in ('request_id','operation','parent_request_id','status','created_at','updated_at',
                        'expires_at','http_status','error_code','input_text','recognized_text','result_kind',
                        'result_total','client_outcome')})

    def outcome(self, ident, identity, library, outcome):
        if outcome not in ('displayed','open_requested','failed','cancelled'):
            raise ValueError('Invalid outcome')
        now = int(self.clock())
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('''SELECT status,client_outcome FROM requests WHERE request_id=? AND account_id=?
                AND library_id=? AND expires_at>?''', (ident, identity, library, now)).fetchone()
            if row is None:
                raise JournalMissing()
            if (row['status'] == 'received' or (row['client_outcome'] is not None
                    and row['client_outcome'] != outcome
                    and (row['client_outcome'], outcome) != ('displayed','open_requested'))):
                raise JournalConflict()
            if row['client_outcome'] != outcome:
                db.execute('UPDATE requests SET client_outcome=?,updated_at=? WHERE request_id=?', (outcome,now,ident))
            db.execute('INSERT OR IGNORE INTO events VALUES (?,?,?)', (ident,'client_'+outcome,now))
        return dict(version=1, request_id=ident, client_outcome=outcome)

    def maintenance(self, *, interrupt=False):
        now = int(self.clock())
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            removed = db.execute('DELETE FROM requests WHERE expires_at<=?', (now,)).rowcount
            if interrupt:
                db.execute("INSERT OR IGNORE INTO events SELECT request_id,'interrupted',? FROM requests WHERE status='received'", (now,))
                db.execute("UPDATE requests SET status='interrupted',updated_at=?,error_code='server_interrupted' WHERE status='received'", (now,))
            return removed

    def inspect(self, *, limit=20, include_input=False, ident=None):
        if ident is not None:
            request_id(ident)
        with self.connection() as db:
            count = db.execute('SELECT count(*) FROM requests WHERE expires_at>?', (int(self.clock()),)).fetchone()[0]
            rows = db.execute('SELECT * FROM requests WHERE expires_at>? AND (? IS NULL OR request_id=?) '
                              'ORDER BY created_at DESC,request_id LIMIT ?',
                              (int(self.clock()), ident, ident, limit)).fetchall()
            items = [self.envelope(row) for row in rows]
            for item, row in zip(items, rows):
                item['account_id'] = row['account_id']
                item['library_id'] = row['library_id']
                if not include_input:
                    item.pop('input_text'); item.pop('recognized_text')
                item['stages'] = [dict(stage=r['stage'], occurred_at=_iso(r['occurred_at'])) for r in db.execute(
                    'SELECT stage,occurred_at FROM events WHERE request_id=? ORDER BY occurred_at,rowid', (row['request_id'],))]
            return dict(version=1, count=count, items=items)
