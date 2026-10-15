"""Private per-account assistant conversations and presentation preferences.

This store is deliberately separate from shared stories and the assistant
receipt journal. It stores only bounded text, typed read-only references, and
receipt IDs supplied by a trusted backend caller. It does not authorize or
revalidate those references and it never invokes a provider or network client.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import time
import uuid


RETENTION_SECONDS = 30 * 86400
MAX_THREADS = 10000
MAX_EXCHANGES = 100000
MAX_PREFERENCES = 100000
MAX_EXCHANGES_PER_THREAD = 200
MAX_REQUESTS = 100000
MAX_REQUESTS_PER_THREAD = 200
LEASE_SECONDS = 90
MAX_CARDS = 40
MAX_RECEIPTS = 20
HISTORY_PAGE_SIZE = 20
MAX_INPUT_BYTES = 1024
MAX_REPLY_BYTES = 8192
MAX_SCOPE_ID_BYTES = 128
MAX_EXPECTED_REVISION = (1 << 63) - 2
APPLICATION_ID = 1346914882
SCHEMA_VERSION = 2
V1_SCHEMA_VERSION = 1

_V1_SCHEMA_SQL = '''
PRAGMA application_id=1346914882;
PRAGMA user_version=1;
CREATE TABLE threads (
 thread_id TEXT PRIMARY KEY,
 account_id TEXT NOT NULL,
 library_id TEXT NOT NULL,
 created_at INTEGER NOT NULL,
 updated_at INTEGER NOT NULL,
 expires_at INTEGER NOT NULL,
 revision INTEGER NOT NULL CHECK(revision >= 0)
);
CREATE INDEX threads_scope ON threads(account_id,library_id,updated_at DESC,thread_id);
CREATE INDEX threads_expiry ON threads(expires_at);
CREATE TABLE exchanges (
 exchange_id TEXT PRIMARY KEY,
 thread_id TEXT NOT NULL REFERENCES threads(thread_id) ON DELETE CASCADE,
 account_id TEXT NOT NULL,
 library_id TEXT NOT NULL,
 request_id TEXT NOT NULL,
 revision INTEGER NOT NULL CHECK(revision > 0),
 created_at INTEGER NOT NULL,
 expires_at INTEGER NOT NULL,
 input_text TEXT NOT NULL,
 reply TEXT NOT NULL,
 card_refs TEXT NOT NULL,
 receipt_ids TEXT NOT NULL,
 payload_fingerprint TEXT NOT NULL,
 UNIQUE(account_id,library_id,request_id),
 UNIQUE(thread_id,revision)
);
CREATE INDEX exchanges_expiry ON exchanges(expires_at);
CREATE INDEX exchanges_thread ON exchanges(thread_id,revision);
CREATE TABLE preferences (
 account_id TEXT PRIMARY KEY,
 locale TEXT CHECK(locale IS NULL OR locale IN ('zh','en')),
 reply_length TEXT CHECK(reply_length IS NULL OR reply_length IN ('brief','standard')),
 voice_pace TEXT CHECK(voice_pace IS NULL OR voice_pace IN ('slow','normal')),
 revision INTEGER NOT NULL CHECK(revision > 0),
 updated_at INTEGER NOT NULL
);
'''

_SCHEMA_SQL = _V1_SCHEMA_SQL.replace('PRAGMA user_version=1;', 'PRAGMA user_version=2;') + '''
CREATE TABLE turn_requests (
 request_id TEXT NOT NULL,
 thread_id TEXT NOT NULL REFERENCES threads(thread_id) ON DELETE CASCADE,
 account_id TEXT NOT NULL,
 library_id TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('pending','completed','failed','interrupted')),
 created_at INTEGER NOT NULL,
 expires_at INTEGER NOT NULL,
 expected_revision INTEGER NOT NULL CHECK(expected_revision >= 0),
 input_text TEXT NOT NULL,
 lease_id TEXT,
 lease_expires_at INTEGER,
 revision INTEGER NOT NULL CHECK(revision >= 0),
 result_summary TEXT,
 error_code TEXT,
 UNIQUE(account_id,library_id,request_id),
 CHECK((status='pending' AND lease_id IS NOT NULL AND lease_expires_at IS NOT NULL
        AND result_summary IS NULL AND error_code IS NULL) OR
       (status='completed' AND lease_id IS NULL AND lease_expires_at IS NULL
        AND result_summary IS NOT NULL AND error_code IS NULL) OR
       (status IN ('failed','interrupted') AND lease_id IS NULL AND lease_expires_at IS NULL
        AND result_summary IS NULL AND error_code IS NOT NULL))
);
CREATE INDEX turn_requests_thread ON turn_requests(thread_id,created_at);
CREATE INDEX turn_requests_expiry ON turn_requests(expires_at);
CREATE INDEX turn_requests_pending ON turn_requests(thread_id,status,lease_expires_at);
CREATE TABLE thread_context (
 thread_id TEXT PRIMARY KEY REFERENCES threads(thread_id) ON DELETE CASCADE,
 account_id TEXT NOT NULL,
 library_id TEXT NOT NULL,
 created_at INTEGER NOT NULL,
 expires_at INTEGER NOT NULL,
 context_json TEXT NOT NULL
);
CREATE INDEX thread_context_expiry ON thread_context(expires_at);
'''


class WorkspaceStoreUnavailable(Exception):
    """The private store is absent, malformed, or cannot be safely opened."""


class WorkspaceStoreConflict(Exception):
    """A revision or idempotency key conflicts with committed state."""


class WorkspaceStoreMissing(Exception):
    """The requested private object is not present in this exact scope."""


def _uuid4(value, label='ID'):
    try:
        parsed = uuid.UUID(value)
        if parsed.version != 4 or str(parsed) != value:
            raise ValueError()
        return value
    except (ValueError, TypeError, AttributeError):
        raise ValueError(f'Invalid {label}') from None


def _expected_revision(value):
    if type(value) is not int or not 0 <= value <= MAX_EXPECTED_REVISION:
        raise ValueError('Invalid revision')
    return value


def _scope(value):
    if type(value) is not str or not value:
        raise ValueError('Invalid scope')
    try:
        if len(value.encode('utf-8')) > MAX_SCOPE_ID_BYTES:
            raise ValueError('Invalid scope')
    except UnicodeError:
        raise ValueError('Invalid scope') from None
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError('Invalid scope')
    return value


def _path(path, *, exists=True):
    try:
        path = Path(path)
        if not path.is_absolute() or '..' in path.parts or path == Path(path.anchor):
            raise WorkspaceStoreUnavailable()
        for parent in path.parents:
            if parent.is_symlink():
                raise WorkspaceStoreUnavailable()
        if exists and (not stat.S_ISREG(path.lstat().st_mode) or
                       path.resolve(strict=True) != path):
            raise WorkspaceStoreUnavailable()
        return path
    except (OSError, ValueError, TypeError):
        raise WorkspaceStoreUnavailable() from None


def _has_wal_sidecars(path):
    return any(os.path.lexists(str(path) + suffix) for suffix in ('-wal', '-shm'))


def _normalized_sql(value):
    return re.sub(r'\s+', ' ', value).strip().casefold()


def _iso(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat().replace('+00:00', 'Z')


def _text(value, maximum, *, empty=False):
    if type(value) is not str:
        raise ValueError('Invalid text')
    try:
        encoded = value.encode('utf-8')
    except UnicodeError:
        raise ValueError('Invalid text') from None
    if (len(encoded) > maximum or (not empty and not value.strip()) or
            any(ord(char) < 32 and char not in '\n\t' for char in value)):
        raise ValueError('Invalid text')
    return value


def _card_refs(value):
    if type(value) is not list or len(value) > MAX_CARDS:
        raise ValueError('Invalid card references')
    result = []
    for card in value:
        if type(card) is not dict or set(card) != {'type', 'id', 'revision', 'fingerprint'}:
            raise ValueError('Invalid card reference')
        if card['type'] not in ('media', 'album', 'story', 'memoir', 'timeline'):
            raise ValueError('Invalid card type')
        ident = card['id']
        if (type(ident) is not str or
                re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', ident) is None):
            raise ValueError('Invalid card ID')
        for field in ('revision', 'fingerprint'):
            if type(card[field]) is not str or re.fullmatch(r'[0-9a-f]{64}', card[field]) is None:
                raise ValueError('Invalid card binding')
        result.append(dict(card))
    return result


def _receipt_ids(value):
    if type(value) is not list or len(value) > MAX_RECEIPTS:
        raise ValueError('Invalid receipt IDs')
    result = [_uuid4(item, 'receipt ID') for item in value]
    if len(set(result)) != len(result):
        raise ValueError('Invalid receipt IDs')
    return result


def _json_value(value, maximum, label):
    try:
        packed = json.dumps(value, ensure_ascii=False, sort_keys=True,
                            separators=(',', ':'), allow_nan=False).encode('utf-8')
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise ValueError(f'Invalid {label}') from None
    if len(packed) > maximum:
        raise ValueError(f'Invalid {label}')
    return packed.decode('utf-8')


def _filters(value):
    if type(value) is not dict:
        raise ValueError('Invalid filters')
    return json.loads(_json_value(value, 16 * 1024, 'filters'))


def _context_value(value, library_id):
    if value is None:
        return None
    fields = {'library_id', 'binding', 'fingerprint', 'filters', 'visible_ids', 'total'}
    if (type(value) is not dict or set(value) - {'search_version'} != fields or value['library_id'] != library_id or
            ('search_version' in value and (type(value['search_version']) is not int or value['search_version'] not in (2, 3)))):
        raise ValueError('Invalid context')
    if any(type(value[name]) is not str or re.fullmatch(r'[0-9a-f]{64}', value[name]) is None
           for name in ('binding', 'fingerprint')):
        raise ValueError('Invalid context')
    filters = _filters(value['filters'])
    ids = value['visible_ids']
    if type(ids) is not list or len(ids) > 20:
        raise ValueError('Invalid context')
    max_id = (1 << 63) - 1
    for ident in ids:
        if (type(ident) is not str or re.fullmatch(r'[1-9][0-9]{0,18}', ident) is None
                or int(ident) > max_id):
            raise ValueError('Invalid context')
    if len(set(ids)) != len(ids):
        raise ValueError('Invalid context')
    if type(value['total']) is not int or not 0 <= value['total'] <= 100000:
        raise ValueError('Invalid context')
    if len(ids) != min(20, value['total']):
        raise ValueError('Invalid context')
    return dict(library_id=library_id, binding=value['binding'],
                fingerprint=value['fingerprint'], filters=filters,
                visible_ids=list(ids), total=value['total'],
                **({'search_version': value['search_version']} if 'search_version' in value else {}))


def _result_summary(value, library_id):
    fields = {'version', 'kind', 'reply', 'context', 'filters', 'total',
              'has_more', 'effect'}
    if type(value) is not dict or set(value) != fields:
        raise ValueError('Invalid result summary')
    if type(value['version']) is not int or value['version'] not in (1, 2, 3):
        raise ValueError('Invalid result summary')
    if value['kind'] not in ('results', 'open', 'clarification', 'unsupported'):
        raise ValueError('Invalid result summary')
    reply = _text(value['reply'], MAX_REPLY_BYTES)
    ctx = _context_value(value['context'], library_id)
    if ctx is not None and ctx.get('search_version', 1) != value['version']:
        raise ValueError('Invalid result summary')
    filters = None if value['filters'] is None else _filters(value['filters'])
    if type(value['total']) is not int or not 0 <= value['total'] <= 100000:
        raise ValueError('Invalid result summary')
    if type(value['has_more']) is not bool:
        raise ValueError('Invalid result summary')
    effect = value['effect']
    if (value['kind'] == 'open') != (effect is not None):
        raise ValueError('Invalid result summary')
    if effect is not None:
        if (type(effect) is not dict or set(effect) != {'type', 'asset_id'} or
                effect['type'] != 'open_asset' or value['kind'] != 'open' or
                ctx is None or effect['asset_id'] not in ctx['visible_ids']):
            raise ValueError('Invalid result summary')
    if ctx is not None and (filters != ctx['filters'] or value['total'] != ctx['total']):
        raise ValueError('Invalid result summary')
    if ctx is None and (filters is not None or value['total'] != 0 or value['has_more']):
        raise ValueError('Invalid result summary')
    if ctx is not None and value['has_more'] != (ctx['total'] > len(ctx['visible_ids'])):
        raise ValueError('Invalid result summary')
    result = dict(version=value['version'], kind=value['kind'], reply=reply, context=ctx,
                  filters=filters, total=value['total'], has_more=value['has_more'],
                  effect=None if effect is None else dict(effect))
    return json.loads(_json_value(result, 32 * 1024, 'result summary'))


def _stored_json(raw, maximum):
    try:
        if type(raw) is not str or len(raw.encode('utf-8')) > maximum:
            raise ValueError()
        return json.loads(raw)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise WorkspaceStoreUnavailable() from None


def _stored_context(raw, library_id):
    try:
        return _context_value(_stored_json(raw, 32 * 1024), library_id)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise WorkspaceStoreUnavailable() from None


def _stored_summary(raw, library_id):
    try:
        return _result_summary(_stored_json(raw, 32 * 1024), library_id)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise WorkspaceStoreUnavailable() from None


_SAFE_ERROR_CODES = frozenset({
    'assistant_unavailable', 'context_changed', 'request_cancelled',
    'access_denied', 'invalid_request', 'storage_unavailable', 'turn_interrupted',
})


def _payload_fingerprint(payload):
    packed = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                        separators=(',', ':'), allow_nan=False).encode('utf-8')
    return hashlib.sha256(packed).hexdigest()


def _schema_shape(db, schema_sql):
    objects = db.execute("SELECT type,name,sql FROM sqlite_master "
                         "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name").fetchall()
    schema_db = sqlite3.connect(':memory:')
    try:
        schema_db.executescript(schema_sql)
        expected_objects = schema_db.execute(
            "SELECT type,name,sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name").fetchall()
    finally:
        schema_db.close()
    actual_shape = [(row[0], row[1], _normalized_sql(row[2] or '')) for row in objects]
    expected_shape = [(row[0], row[1], _normalized_sql(row[2] or ''))
                      for row in expected_objects]
    return actual_shape == expected_shape


def _validate_v1_db(db):
    if (db.execute('PRAGMA application_id').fetchone()[0] != APPLICATION_ID or
            db.execute('PRAGMA user_version').fetchone()[0] != V1_SCHEMA_VERSION or
            db.execute('PRAGMA journal_mode').fetchone()[0] != 'delete'):
        raise WorkspaceStoreUnavailable()
    if not _schema_shape(db, _V1_SCHEMA_SQL):
        raise WorkspaceStoreUnavailable()


def initialize_v2(path, *, clock=time.time):
    """Exclusively create a new private DB; never initialize an existing file."""
    path = _path(path, exists=False)
    try:
        if _has_wal_sidecars(path):
            raise WorkspaceStoreUnavailable()
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        with sqlite3.connect(path) as db:
            if db.execute('PRAGMA journal_mode=DELETE').fetchone()[0] != 'delete':
                raise WorkspaceStoreUnavailable()
            if db.execute('PRAGMA secure_delete=ON').fetchone()[0] != 1:
                raise WorkspaceStoreUnavailable()
            db.executescript(_SCHEMA_SQL)
    except WorkspaceStoreUnavailable:
        raise
    except (OSError, sqlite3.Error):
        raise WorkspaceStoreUnavailable() from None
    return AssistantWorkspaceStore(path, clock=clock)


def initialize(path, *, clock=time.time):
    """Compatibility name for explicit creation of a fresh v2 store."""
    return initialize_v2(path, clock=clock)


def offline_upgrade_v1(path):
    """Atomically upgrade a validated v1 file while it is offline."""
    path = _path(path)
    try:
        if _has_wal_sidecars(path):
            raise WorkspaceStoreUnavailable()
        before = path.lstat()
        db = sqlite3.connect(path.as_uri() + '?mode=rw', uri=True, timeout=2,
                             isolation_level=None)
        try:
            after = path.lstat()
            if ((before.st_dev, before.st_ino) != (after.st_dev, after.st_ino) or
                    _has_wal_sidecars(path)):
                raise WorkspaceStoreUnavailable()
            db.execute('PRAGMA trusted_schema=OFF')
            db.execute('PRAGMA foreign_keys=ON')
            if db.execute('PRAGMA secure_delete=ON').fetchone()[0] != 1:
                raise WorkspaceStoreUnavailable()
            _validate_v1_db(db)
            db.execute('BEGIN IMMEDIATE')
            migration_sql = '''
CREATE TABLE turn_requests (
 request_id TEXT NOT NULL,
 thread_id TEXT NOT NULL REFERENCES threads(thread_id) ON DELETE CASCADE,
 account_id TEXT NOT NULL,
 library_id TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('pending','completed','failed','interrupted')),
 created_at INTEGER NOT NULL,
 expires_at INTEGER NOT NULL,
 expected_revision INTEGER NOT NULL CHECK(expected_revision >= 0),
 input_text TEXT NOT NULL,
 lease_id TEXT,
 lease_expires_at INTEGER,
 revision INTEGER NOT NULL CHECK(revision >= 0),
 result_summary TEXT,
 error_code TEXT,
 UNIQUE(account_id,library_id,request_id),
 CHECK((status='pending' AND lease_id IS NOT NULL AND lease_expires_at IS NOT NULL
        AND result_summary IS NULL AND error_code IS NULL) OR
       (status='completed' AND lease_id IS NULL AND lease_expires_at IS NULL
        AND result_summary IS NOT NULL AND error_code IS NULL) OR
       (status IN ('failed','interrupted') AND lease_id IS NULL AND lease_expires_at IS NULL
        AND result_summary IS NULL AND error_code IS NOT NULL))
);
CREATE INDEX turn_requests_thread ON turn_requests(thread_id,created_at);
CREATE INDEX turn_requests_expiry ON turn_requests(expires_at);
CREATE INDEX turn_requests_pending ON turn_requests(thread_id,status,lease_expires_at);
CREATE TABLE thread_context (
 thread_id TEXT PRIMARY KEY REFERENCES threads(thread_id) ON DELETE CASCADE,
 account_id TEXT NOT NULL,
 library_id TEXT NOT NULL,
 created_at INTEGER NOT NULL,
 expires_at INTEGER NOT NULL,
 context_json TEXT NOT NULL
);
CREATE INDEX thread_context_expiry ON thread_context(expires_at);
'''
            for statement in migration_sql.split(';'):
                if statement.strip():
                    db.execute(statement)
            db.execute('PRAGMA user_version=2')
            db.commit()
        except BaseException:
            if db.in_transaction:
                db.rollback()
            raise
        finally:
            db.close()
        return AssistantWorkspaceStore(path)
    except WorkspaceStoreUnavailable:
        raise
    except (OSError, sqlite3.Error, ValueError):
        raise WorkspaceStoreUnavailable() from None


class AssistantWorkspaceStore:
    def __init__(self, path, *, clock=time.time):
        # Opening an existing path is safe only in mode=rw; __init__ does not
        # create or migrate the file. initialize() is the sole creation path.
        self.path = _path(path)
        self.clock = clock
        with self.connection():
            pass

    @contextmanager
    def connection(self):
        db = None
        try:
            path = _path(self.path)
            if _has_wal_sidecars(path):
                raise WorkspaceStoreUnavailable()
            before = path.lstat()
            db = sqlite3.connect(path.as_uri() + '?mode=rw', uri=True, timeout=2,
                                 isolation_level=None)
            after = path.lstat()
            if ((before.st_dev, before.st_ino) != (after.st_dev, after.st_ino) or
                    _has_wal_sidecars(path)):
                raise WorkspaceStoreUnavailable()
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA trusted_schema=OFF')
            db.execute('PRAGMA foreign_keys=ON')
            if db.execute('PRAGMA secure_delete=ON').fetchone()[0] != 1:
                raise WorkspaceStoreUnavailable()
            if (db.execute('PRAGMA application_id').fetchone()[0] != APPLICATION_ID or
                    db.execute('PRAGMA user_version').fetchone()[0] != SCHEMA_VERSION or
                    db.execute('PRAGMA journal_mode').fetchone()[0] != 'delete'):
                raise WorkspaceStoreUnavailable()
            if not _schema_shape(db, _SCHEMA_SQL):
                raise WorkspaceStoreUnavailable()
            yield db
        except WorkspaceStoreUnavailable:
            raise
        except (OSError, sqlite3.Error, ValueError):
            raise WorkspaceStoreUnavailable() from None
        finally:
            if db is not None:
                if db.in_transaction:
                    try:
                        db.rollback()
                    except sqlite3.Error:
                        pass
                db.close()

    def _begin(self, db):
        db.execute('BEGIN IMMEDIATE')

    def _prune(self, db, now):
        # Old exchanges expire at their original turn timestamp. Thread expiry
        # follows the latest activity, so fresh turns cannot immortalize old ones.
        db.execute('DELETE FROM turn_requests WHERE expires_at<=?', (now,))
        db.execute('DELETE FROM thread_context WHERE expires_at<=?', (now,))
        db.execute('DELETE FROM exchanges WHERE expires_at<=?', (now,))
        db.execute('DELETE FROM threads WHERE expires_at<=?', (now,))
        return db.execute('SELECT changes()').fetchone()[0]

    @staticmethod
    def _thread(row, exchange_count=None):
        value = dict(thread_id=row['thread_id'], library_id=row['library_id'],
                     created_at=_iso(row['created_at']), updated_at=_iso(row['updated_at']),
                     expires_at=_iso(row['expires_at']), revision=row['revision'])
        if exchange_count is not None:
            value['exchange_count'] = exchange_count
        return value

    @staticmethod
    def _exchange(row):
        return dict(exchange_id=row['exchange_id'], request_id=row['request_id'],
                    revision=row['revision'], created_at=_iso(row['created_at']),
                    expires_at=_iso(row['expires_at']),
                    input_text=row['input_text'], reply=row['reply'],
                    cards=json.loads(row['card_refs']), receipts=json.loads(row['receipt_ids']),
                    fingerprint=row['payload_fingerprint'])

    def create_thread(self, account_id, library_id, thread_id=None):
        account_id, library_id = _scope(account_id), _scope(library_id)
        ident = str(uuid.uuid4()) if thread_id is None else _uuid4(thread_id, 'thread ID')
        now = int(self.clock())
        with self.connection() as db:
            self._begin(db)
            self._prune(db, now)
            if db.execute('SELECT count(*) FROM threads').fetchone()[0] >= MAX_THREADS:
                raise WorkspaceStoreUnavailable()
            try:
                db.execute('INSERT INTO threads VALUES (?,?,?,?,?,?,0)',
                           (ident, account_id, library_id, now, now,
                            now + RETENTION_SECONDS))
            except sqlite3.IntegrityError:
                raise WorkspaceStoreConflict() from None
            row = db.execute('SELECT * FROM threads WHERE thread_id=?', (ident,)).fetchone()
            result = self._thread(row, 0)
            db.commit()
            return result

    def list_threads(self, account_id, library_id, *, limit=50, include_labels=False):
        account_id, library_id = _scope(account_id), _scope(library_id)
        if (type(limit) is not int or not 1 <= limit <= 100 or
                type(include_labels) is not bool):
            raise ValueError('Invalid limit')
        # Labels are an explicit presentation opt-in. Keeping the default
        # projection unchanged preserves the original strict list contract.
        now = int(self.clock())
        with self.connection() as db:
            if include_labels:
                rows = db.execute('''SELECT t.*,
                    (SELECT count(*) FROM exchanges e WHERE e.thread_id=t.thread_id
                        AND e.account_id=t.account_id AND e.library_id=t.library_id AND e.expires_at>?) AS exchange_count,
                    (SELECT e.input_text FROM exchanges e WHERE e.thread_id=t.thread_id
                        AND e.account_id=t.account_id AND e.library_id=t.library_id AND e.expires_at>?
                        ORDER BY e.revision LIMIT 1) AS first_question
                    FROM threads t WHERE t.account_id=? AND t.library_id=? AND t.expires_at>?
                    ORDER BY t.updated_at DESC,t.thread_id LIMIT ?''',
                    (now, now, account_id, library_id, now, limit)).fetchall()
                result = []
                for row in rows:
                    item = self._thread(row, row['exchange_count'])
                    item['label'] = self._display_label(row['first_question'])
                    result.append(item)
                return result
            rows = db.execute('''SELECT t.*, (SELECT count(*) FROM exchanges e
                WHERE e.thread_id=t.thread_id AND e.expires_at>?) AS exchange_count
                FROM threads t WHERE t.account_id=? AND t.library_id=? AND t.expires_at>?
                ORDER BY t.updated_at DESC,t.thread_id LIMIT ?''',
                              (now, account_id, library_id, now, limit)).fetchall()
            return [self._thread(row, row['exchange_count']) for row in rows]

    @staticmethod
    def _display_label(value):
        if value is None:
            return None
        value = _text(value, MAX_INPUT_BYTES)
        collapsed = ' '.join(value.split())
        if len(collapsed) <= 64:
            return collapsed or None
        return collapsed[:63].rstrip() + '…'

    def get_thread(self, account_id, library_id, thread_id):
        account_id, library_id = _scope(account_id), _scope(library_id)
        thread_id = _uuid4(thread_id, 'thread ID')
        now = int(self.clock())
        with self.connection() as db:
            db.execute('BEGIN')
            row = db.execute('''SELECT * FROM threads WHERE thread_id=? AND account_id=?
                AND library_id=? AND expires_at>?''',
                             (thread_id, account_id, library_id, now)).fetchone()
            if row is None:
                raise WorkspaceStoreMissing()
            exchanges = db.execute('''SELECT * FROM exchanges WHERE thread_id=? AND account_id=?
                AND library_id=? AND expires_at>? ORDER BY revision''',
                                  (thread_id, account_id, library_id, now)).fetchall()
            latest = db.execute('''SELECT request_id FROM turn_requests WHERE thread_id=?
                AND account_id=? AND library_id=? AND status='completed' AND expires_at>?
                AND revision<=? ORDER BY revision DESC LIMIT 1''',
                (thread_id, account_id, library_id, now, row['revision'])).fetchone()
            return dict(version=1, thread=self._thread(row, len(exchanges)),
                        exchanges=[self._exchange(item) for item in exchanges],
                        latest_request_id=None if latest is None else latest['request_id'])

    def get_thread_history_page(self, account_id, library_id, thread_id,
                                snapshot_revision, before_revision):
        """Read one immutable page and its owning revision in a DB snapshot."""
        account_id, library_id = _scope(account_id), _scope(library_id)
        thread_id = _uuid4(thread_id, 'thread ID')
        snapshot_revision = _expected_revision(snapshot_revision)
        before_revision = _expected_revision(before_revision)
        if before_revision < 1 or before_revision > snapshot_revision:
            raise ValueError('Invalid history cursor')
        now = int(self.clock())
        with self.connection() as db:
            db.execute('BEGIN')
            thread = db.execute('''SELECT revision FROM threads WHERE thread_id=?
                AND account_id=? AND library_id=? AND expires_at>?''',
                (thread_id, account_id, library_id, now)).fetchone()
            if thread is None:
                raise WorkspaceStoreMissing()
            if thread['revision'] != snapshot_revision:
                raise WorkspaceStoreConflict()
            rows = db.execute('''SELECT * FROM exchanges WHERE thread_id=? AND account_id=?
                AND library_id=? AND expires_at>? AND revision<? ORDER BY revision DESC LIMIT ?''',
                (thread_id, account_id, library_id, now, before_revision,
                 HISTORY_PAGE_SIZE + 1)).fetchall()
            has_older = len(rows) > HISTORY_PAGE_SIZE
            page = rows[:HISTORY_PAGE_SIZE]
            page.reverse()
            return dict(version=1, thread_id=thread_id,
                        snapshot_revision=snapshot_revision,
                        before_revision=before_revision,
                        exchanges=[self._exchange(item) for item in page],
                        has_older_exchanges=has_older)

    def delete_thread(self, account_id, library_id, thread_id, expected_revision):
        account_id, library_id = _scope(account_id), _scope(library_id)
        thread_id = _uuid4(thread_id, 'thread ID')
        expected_revision = _expected_revision(expected_revision)
        with self.connection() as db:
            self._begin(db)
            self._prune(db, int(self.clock()))
            row = db.execute('''SELECT revision FROM threads WHERE thread_id=? AND account_id=?
                AND library_id=?''', (thread_id, account_id, library_id)).fetchone()
            if row is None:
                raise WorkspaceStoreMissing()
            if row['revision'] != expected_revision:
                raise WorkspaceStoreConflict()
            db.execute('DELETE FROM threads WHERE thread_id=? AND account_id=? AND library_id=?',
                       (thread_id, account_id, library_id))
            db.commit()
            return dict(thread_id=thread_id, deleted=True)

    def append_exchange(self, account_id, library_id, thread_id, request_id,
                        expected_revision, input_text, reply, cards, receipts):
        account_id, library_id = _scope(account_id), _scope(library_id)
        thread_id = _uuid4(thread_id, 'thread ID')
        request_id = _uuid4(request_id, 'request ID')
        expected_revision = _expected_revision(expected_revision)
        input_text = _text(input_text, MAX_INPUT_BYTES)
        reply = _text(reply, MAX_REPLY_BYTES)
        cards = _card_refs(cards)
        receipts = _receipt_ids(receipts)
        payload = dict(expected_revision=expected_revision, input_text=input_text,
                       reply=reply, cards=cards, receipts=receipts)
        fingerprint = _payload_fingerprint(payload)
        now = int(self.clock())
        with self.connection() as db:
            self._begin(db)
            self._prune(db, now)
            # Resolve a lost-response retry before testing its now-stale CAS.
            prior = db.execute('''SELECT * FROM exchanges WHERE account_id=? AND library_id=?
                AND request_id=?''', (account_id, library_id, request_id)).fetchone()
            if prior is not None:
                if prior['thread_id'] != thread_id or prior['payload_fingerprint'] != fingerprint:
                    raise WorkspaceStoreConflict()
                result = dict(thread_id=thread_id, revision=prior['revision'],
                              exchange=self._exchange(prior), replayed=True)
                db.commit()
                return result
            thread = db.execute('''SELECT * FROM threads WHERE thread_id=? AND account_id=?
                AND library_id=? AND expires_at>?''',
                                (thread_id, account_id, library_id, now)).fetchone()
            if thread is None:
                raise WorkspaceStoreMissing()
            if db.execute("SELECT 1 FROM turn_requests WHERE thread_id=? AND status='pending'",
                          (thread_id,)).fetchone() is not None:
                raise WorkspaceStoreConflict()
            if thread['revision'] != expected_revision:
                raise WorkspaceStoreConflict()
            if db.execute('SELECT count(*) FROM exchanges').fetchone()[0] >= MAX_EXCHANGES:
                raise WorkspaceStoreUnavailable()
            if db.execute('SELECT count(*) FROM exchanges WHERE thread_id=?',
                          (thread_id,)).fetchone()[0] >= MAX_EXCHANGES_PER_THREAD:
                raise WorkspaceStoreUnavailable()
            revision = expected_revision + 1
            exchange_id = str(uuid.uuid4())
            expires_at = now + RETENTION_SECONDS
            db.execute('''INSERT INTO exchanges(exchange_id,thread_id,account_id,library_id,request_id,
                revision,created_at,expires_at,input_text,reply,card_refs,receipt_ids,payload_fingerprint)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                       (exchange_id, thread_id, account_id, library_id, request_id, revision,
                        now, expires_at, input_text, reply,
                        json.dumps(cards, ensure_ascii=False, sort_keys=True, separators=(',', ':')),
                        json.dumps(receipts, separators=(',', ':')), fingerprint))
            db.execute('UPDATE threads SET updated_at=?,expires_at=?,revision=? WHERE thread_id=?',
                       (now, expires_at, revision, thread_id))
            row = db.execute('SELECT * FROM exchanges WHERE exchange_id=?', (exchange_id,)).fetchone()
            result = dict(thread_id=thread_id, revision=revision,
                          exchange=self._exchange(row), replayed=False)
            db.commit()
            return result

    @staticmethod
    def _turn_view(row, *, replayed=False):
        result_summary = (_stored_summary(row['result_summary'], row['library_id'])
                          if row['status'] == 'completed' else None)
        return dict(request_id=row['request_id'], thread_id=row['thread_id'],
                    status=row['status'], lease_id=row['lease_id'],
                    context=(None if result_summary is None else result_summary['context']),
                    revision=row['revision'], result_summary=result_summary,
                    error_code=row['error_code'], replayed=replayed)

    @staticmethod
    def _context_for(db, thread_id, account_id, library_id, now):
        row = db.execute('''SELECT context_json FROM thread_context WHERE thread_id=?
            AND account_id=? AND library_id=? AND expires_at>?''',
                         (thread_id, account_id, library_id, now)).fetchone()
        return (None if row is None else _stored_context(row['context_json'], library_id))

    @staticmethod
    def _reconcile_lease(db, row, now):
        if row['status'] == 'pending' and row['lease_expires_at'] <= now:
            revision = db.execute('SELECT revision FROM threads WHERE thread_id=?',
                                  (row['thread_id'],)).fetchone()
            current = row['revision'] if revision is None else revision['revision']
            db.execute('''UPDATE turn_requests SET status='interrupted',lease_id=NULL,
                lease_expires_at=NULL,revision=?,error_code='turn_interrupted'
                WHERE request_id=? AND account_id=? AND library_id=? AND status='pending' ''',
                       (current, row['request_id'], row['account_id'], row['library_id']))
            return db.execute('''SELECT * FROM turn_requests WHERE request_id=?
                AND account_id=? AND library_id=?''',
                              (row['request_id'], row['account_id'], row['library_id'])).fetchone()
        return row

    def begin_turn(self, account_id, library_id, thread_id, request_id,
                   expected_revision, input_text, *, existing_only=False):
        if type(existing_only) is not bool:
            raise ValueError('Invalid existing request lookup')
        account_id, library_id = _scope(account_id), _scope(library_id)
        thread_id = _uuid4(thread_id, 'thread ID')
        request_id = _uuid4(request_id, 'request ID')
        expected_revision = _expected_revision(expected_revision)
        input_text = _text(input_text, MAX_INPUT_BYTES)
        now = int(self.clock())
        with self.connection() as db:
            self._begin(db)
            self._prune(db, now)
            prior = db.execute('''SELECT * FROM turn_requests WHERE account_id=?
                AND library_id=? AND request_id=?''',
                               (account_id, library_id, request_id)).fetchone()
            if prior is not None:
                if (prior['thread_id'] != thread_id or prior['input_text'] != input_text or
                        prior['expected_revision'] != expected_revision):
                    raise WorkspaceStoreConflict()
                prior = self._reconcile_lease(db, prior, now)
                result = self._turn_view(prior, replayed=True)
                result['context'] = (self._context_for(db, thread_id, account_id,
                                                       library_id, now)
                                     if prior['status'] == 'pending' else None)
                db.commit()
                return result
            if existing_only:
                db.commit()
                return None
            thread = db.execute('''SELECT * FROM threads WHERE thread_id=? AND account_id=?
                AND library_id=? AND expires_at>?''',
                                (thread_id, account_id, library_id, now)).fetchone()
            if thread is None:
                raise WorkspaceStoreMissing()
            if thread['revision'] != expected_revision:
                raise WorkspaceStoreConflict()
            pending = db.execute("SELECT * FROM turn_requests WHERE thread_id=? AND status='pending'",
                                 (thread_id,)).fetchone()
            if pending is not None:
                pending = self._reconcile_lease(db, pending, now)
                if pending['status'] == 'pending':
                    raise WorkspaceStoreConflict()
            if (db.execute('SELECT count(*) FROM turn_requests').fetchone()[0] >= MAX_REQUESTS or
                    db.execute('SELECT count(*) FROM turn_requests WHERE thread_id=?',
                               (thread_id,)).fetchone()[0] >= MAX_REQUESTS_PER_THREAD):
                raise WorkspaceStoreUnavailable()
            lease_id = str(uuid.uuid4())
            db.execute('''INSERT INTO turn_requests(request_id,thread_id,account_id,library_id,
                status,created_at,expires_at,expected_revision,input_text,lease_id,
                lease_expires_at,revision,result_summary,error_code)
                VALUES (?,?,?,?, 'pending',?,?,?,?,?,?,?,NULL,NULL)''',
                       (request_id, thread_id, account_id, library_id, now,
                        now + RETENTION_SECONDS, expected_revision, input_text,
                        lease_id, now + LEASE_SECONDS, expected_revision))
            row = db.execute('''SELECT * FROM turn_requests WHERE account_id=?
                AND library_id=? AND request_id=?''',
                             (account_id, library_id, request_id)).fetchone()
            result = self._turn_view(row)
            result['context'] = self._context_for(db, thread_id, account_id, library_id, now)
            db.commit()
            return result

    def get_turn(self, account_id, library_id, thread_id, request_id):
        account_id, library_id = _scope(account_id), _scope(library_id)
        thread_id, request_id = _uuid4(thread_id, 'thread ID'), _uuid4(request_id, 'request ID')
        now = int(self.clock())
        with self.connection() as db:
            self._begin(db)
            self._prune(db, now)
            row = db.execute('''SELECT r.* FROM turn_requests r JOIN threads t
                ON t.thread_id=r.thread_id WHERE r.account_id=? AND r.library_id=?
                AND r.thread_id=? AND r.request_id=? AND t.expires_at>?''',
                             (account_id, library_id, thread_id, request_id, now)).fetchone()
            if row is None:
                raise WorkspaceStoreMissing()
            row = self._reconcile_lease(db, row, now)
            result = self._turn_view(row, replayed=True)
            result['context'] = (self._context_for(db, thread_id, account_id,
                                                   library_id, now)
                                 if row['status'] == 'pending' else None)
            db.commit()
            return result

    def _leased_request(self, db, account_id, library_id, thread_id, request_id,
                        lease_id, now):
        lease_id = _uuid4(lease_id, 'lease ID')
        row = db.execute('''SELECT r.* FROM turn_requests r JOIN threads t
            ON t.thread_id=r.thread_id WHERE r.account_id=? AND r.library_id=?
            AND r.thread_id=? AND r.request_id=? AND t.expires_at>?''',
                         (account_id, library_id, thread_id, request_id, now)).fetchone()
        if row is None:
            raise WorkspaceStoreMissing()
        if row['status'] != 'pending' or row['lease_id'] != lease_id:
            raise WorkspaceStoreConflict()
        if row['lease_expires_at'] <= now:
            self._reconcile_lease(db, row, now)
            return None
        return row

    def complete_turn(self, account_id, library_id, thread_id, request_id,
                      lease_id, result_summary, cards=None, receipts=None):
        account_id, library_id = _scope(account_id), _scope(library_id)
        thread_id, request_id = _uuid4(thread_id, 'thread ID'), _uuid4(request_id, 'request ID')
        summary = _result_summary(result_summary, library_id)
        cards = _card_refs([] if cards is None else cards)
        receipts = _receipt_ids([] if receipts is None else receipts)
        summary_json = _json_value(summary, 32 * 1024, 'result summary')
        now = int(self.clock())
        with self.connection() as db:
            self._begin(db)
            self._prune(db, now)
            row = self._leased_request(db, account_id, library_id, thread_id,
                                       request_id, lease_id, now)
            if row is None:
                row = db.execute('''SELECT * FROM turn_requests WHERE account_id=?
                    AND library_id=? AND thread_id=? AND request_id=?''',
                                 (account_id, library_id, thread_id, request_id)).fetchone()
                result = self._turn_view(row)
                result['context'] = None
                db.commit()
                return result
            thread = db.execute('SELECT * FROM threads WHERE thread_id=? AND account_id=? AND library_id=?',
                                (thread_id, account_id, library_id)).fetchone()
            if thread is None:
                raise WorkspaceStoreMissing()
            if thread['revision'] != row['expected_revision']:
                raise WorkspaceStoreConflict()
            if (db.execute('SELECT count(*) FROM exchanges').fetchone()[0] >= MAX_EXCHANGES or
                    db.execute('SELECT count(*) FROM exchanges WHERE thread_id=?',
                               (thread_id,)).fetchone()[0] >= MAX_EXCHANGES_PER_THREAD):
                raise WorkspaceStoreUnavailable()
            revision = row['expected_revision'] + 1
            created_at = row['created_at']
            expires_at = row['expires_at']
            exchange_id = str(uuid.uuid4())
            exchange_payload = dict(expected_revision=row['expected_revision'],
                                    input_text=row['input_text'], result_summary=summary,
                                    cards=cards, receipts=receipts)
            fingerprint = _payload_fingerprint(exchange_payload)
            db.execute('''INSERT INTO exchanges(exchange_id,thread_id,account_id,library_id,
                request_id,revision,created_at,expires_at,input_text,reply,card_refs,receipt_ids,
                payload_fingerprint) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                       (exchange_id, thread_id, account_id, library_id, request_id,
                        revision, created_at, expires_at, row['input_text'], summary['reply'],
                        json.dumps(cards, ensure_ascii=False, sort_keys=True, separators=(',', ':')),
                        json.dumps(receipts, separators=(',', ':')), fingerprint))
            db.execute('''UPDATE threads SET updated_at=?,expires_at=?,revision=?
                WHERE thread_id=?''', (now, now + RETENTION_SECONDS, revision, thread_id))
            if summary['context'] is not None:
                context_json = _json_value(summary['context'], 32 * 1024, 'context')
                current = db.execute('''SELECT created_at,expires_at,context_json
                    FROM thread_context WHERE thread_id=? AND account_id=? AND library_id=?
                    AND expires_at>?''', (thread_id, account_id, library_id, now)).fetchone()
                current_context = (None if current is None else
                                   _stored_context(current['context_json'], library_id))
                if current_context != summary['context']:
                    db.execute('''INSERT INTO thread_context(thread_id,account_id,library_id,
                        created_at,expires_at,context_json) VALUES (?,?,?,?,?,?)
                        ON CONFLICT(thread_id) DO UPDATE SET account_id=excluded.account_id,
                        library_id=excluded.library_id,created_at=excluded.created_at,
                        expires_at=excluded.expires_at,context_json=excluded.context_json''',
                               (thread_id, account_id, library_id, created_at, expires_at,
                                context_json))
            else:
                db.execute('DELETE FROM thread_context WHERE thread_id=?', (thread_id,))
            db.execute('''UPDATE turn_requests SET status='completed',lease_id=NULL,
                lease_expires_at=NULL,revision=?,result_summary=?,error_code=NULL
                WHERE request_id=? AND account_id=? AND library_id=?''',
                       (revision, summary_json, request_id, account_id, library_id))
            updated = db.execute('''SELECT * FROM turn_requests WHERE request_id=?
                AND account_id=? AND library_id=?''',
                                 (request_id, account_id, library_id)).fetchone()
            result = self._turn_view(updated)
            db.commit()
            return result

    def fail_turn(self, account_id, library_id, thread_id, request_id,
                  lease_id, error_code):
        account_id, library_id = _scope(account_id), _scope(library_id)
        thread_id, request_id = _uuid4(thread_id, 'thread ID'), _uuid4(request_id, 'request ID')
        if type(error_code) is not str or error_code not in _SAFE_ERROR_CODES:
            raise ValueError('Invalid error code')
        now = int(self.clock())
        with self.connection() as db:
            self._begin(db)
            self._prune(db, now)
            row = self._leased_request(db, account_id, library_id, thread_id,
                                       request_id, lease_id, now)
            if row is None:
                row = db.execute('''SELECT * FROM turn_requests WHERE account_id=?
                    AND library_id=? AND thread_id=? AND request_id=?''',
                                 (account_id, library_id, thread_id, request_id)).fetchone()
                result = self._turn_view(row)
                result['context'] = None
                db.commit()
                return result
            thread = db.execute('SELECT revision FROM threads WHERE thread_id=?',
                                (thread_id,)).fetchone()
            revision = row['expected_revision'] if thread is None else thread['revision']
            db.execute('''UPDATE turn_requests SET status='failed',lease_id=NULL,
                lease_expires_at=NULL,revision=?,result_summary=NULL,error_code=?
                WHERE request_id=? AND account_id=? AND library_id=?''',
                       (revision, error_code, request_id, account_id, library_id))
            updated = db.execute('''SELECT * FROM turn_requests WHERE request_id=?
                AND account_id=? AND library_id=?''',
                                 (request_id, account_id, library_id)).fetchone()
            result = self._turn_view(updated)
            result['context'] = None
            db.commit()
            return result

    def latest_turn_id(self, account_id, library_id, thread_id):
        account_id, library_id = _scope(account_id), _scope(library_id)
        thread_id = _uuid4(thread_id, 'thread ID')
        now = int(self.clock())
        with self.connection() as db:
            row = db.execute('''SELECT r.request_id FROM turn_requests r JOIN threads t
                ON t.thread_id=r.thread_id WHERE r.account_id=? AND r.library_id=?
                AND r.thread_id=? AND r.status='completed' AND r.expires_at>? AND t.expires_at>?
                ORDER BY r.revision DESC LIMIT 1''',
                             (account_id, library_id, thread_id, now, now)).fetchone()
            if row is None:
                # Keep missing and foreign threads indistinguishable from an empty history.
                return None
            return row['request_id']

    def get_preferences(self, account_id):
        account_id = _scope(account_id)
        with self.connection() as db:
            row = db.execute('SELECT * FROM preferences WHERE account_id=?',
                             (account_id,)).fetchone()
            if row is None:
                return dict(locale=None, reply_length=None, voice_pace=None, revision=0)
            return dict(locale=row['locale'], reply_length=row['reply_length'],
                        voice_pace=row['voice_pace'], revision=row['revision'])

    def update_preferences(self, account_id, expected_revision, updates):
        account_id = _scope(account_id)
        allowed = {'locale': frozenset({'zh', 'en'}),
                   'reply_length': frozenset({'brief', 'standard'}),
                   'voice_pace': frozenset({'slow', 'normal'})}
        expected_revision = _expected_revision(expected_revision)
        if type(updates) is not dict or not updates or set(updates) - set(allowed):
            raise ValueError('Invalid preferences')
        for key, value in updates.items():
            if value is not None and (type(value) is not str or value not in allowed[key]):
                raise ValueError('Invalid preference value')
        now = int(self.clock())
        with self.connection() as db:
            self._begin(db)
            self._prune(db, now)
            row = db.execute('SELECT * FROM preferences WHERE account_id=?',
                             (account_id,)).fetchone()
            current_revision = 0 if row is None else row['revision']
            if current_revision != expected_revision:
                raise WorkspaceStoreConflict()
            if row is None and db.execute('SELECT count(*) FROM preferences').fetchone()[0] >= MAX_PREFERENCES:
                raise WorkspaceStoreUnavailable()
            values = {key: (None if row is None else row[key]) for key in allowed}
            values.update(updates)
            revision = current_revision + 1
            db.execute('''INSERT INTO preferences(account_id,locale,reply_length,voice_pace,revision,updated_at)
                VALUES (?,?,?,?,?,?) ON CONFLICT(account_id) DO UPDATE SET locale=excluded.locale,
                reply_length=excluded.reply_length,voice_pace=excluded.voice_pace,
                revision=excluded.revision,updated_at=excluded.updated_at''',
                       (account_id, values['locale'], values['reply_length'],
                        values['voice_pace'], revision, now))
            result = dict(**values, revision=revision)
            db.commit()
            return result

    def reset_preferences(self, account_id, expected_revision):
        account_id = _scope(account_id)
        expected_revision = _expected_revision(expected_revision)
        now = int(self.clock())
        with self.connection() as db:
            self._begin(db)
            self._prune(db, now)
            row = db.execute('SELECT revision FROM preferences WHERE account_id=?',
                             (account_id,)).fetchone()
            current_revision = 0 if row is None else row['revision']
            if current_revision != expected_revision:
                raise WorkspaceStoreConflict()
            if row is None and db.execute('SELECT count(*) FROM preferences').fetchone()[0] >= MAX_PREFERENCES:
                raise WorkspaceStoreUnavailable()
            revision = current_revision + 1
            db.execute('''INSERT INTO preferences(account_id,locale,reply_length,voice_pace,revision,updated_at)
                VALUES (?,NULL,NULL,NULL,?,?) ON CONFLICT(account_id) DO UPDATE SET locale=NULL,
                reply_length=NULL,voice_pace=NULL,revision=excluded.revision,updated_at=excluded.updated_at''',
                       (account_id, revision, now))
            result = dict(locale=None, reply_length=None, voice_pace=None, revision=revision)
            db.commit()
            return result

    def prune(self):
        """Explicit maintenance entry point for a future scheduled operation."""
        now = int(self.clock())
        with self.connection() as db:
            self._begin(db)
            # A still-retained lease may be reconciled only after its own deadline.
            db.execute('''UPDATE turn_requests SET status='interrupted',lease_id=NULL,
                lease_expires_at=NULL,revision=coalesce((SELECT revision FROM threads t
                WHERE t.thread_id=turn_requests.thread_id),revision),error_code='turn_interrupted'
                WHERE status='pending' AND lease_expires_at<=?''', (now,))
            db.execute('DELETE FROM turn_requests WHERE expires_at<=?', (now,))
            db.execute('DELETE FROM thread_context WHERE expires_at<=?', (now,))
            removed_exchanges = db.execute('DELETE FROM exchanges WHERE expires_at<=?', (now,)).rowcount
            removed_threads = db.execute('DELETE FROM threads WHERE expires_at<=?', (now,)).rowcount
            db.commit()
            return dict(exchanges=removed_exchanges, threads=removed_threads)
