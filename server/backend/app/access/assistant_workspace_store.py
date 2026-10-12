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
MAX_CARDS = 40
MAX_RECEIPTS = 20
MAX_INPUT_BYTES = 1024
MAX_REPLY_BYTES = 8192
MAX_SCOPE_ID_BYTES = 128
MAX_EXPECTED_REVISION = (1 << 63) - 2
APPLICATION_ID = 1346914882
SCHEMA_VERSION = 1

_SCHEMA_SQL = '''
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


def _payload_fingerprint(payload):
    packed = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                        separators=(',', ':'), allow_nan=False).encode('utf-8')
    return hashlib.sha256(packed).hexdigest()


def initialize(path, *, clock=time.time):
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
            objects = db.execute("SELECT type,name,sql FROM sqlite_master "
                                 "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name").fetchall()
            schema_db = sqlite3.connect(':memory:')
            try:
                schema_db.executescript(_SCHEMA_SQL)
                expected_objects = schema_db.execute(
                    "SELECT type,name,sql FROM sqlite_master "
                    "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name").fetchall()
            finally:
                schema_db.close()
            actual_shape = [(row['type'], row['name'], _normalized_sql(row['sql'] or ''))
                            for row in objects]
            expected_shape = [(row[0], row[1], _normalized_sql(row[2] or ''))
                              for row in expected_objects]
            if actual_shape != expected_shape:
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

    def list_threads(self, account_id, library_id, *, limit=50):
        account_id, library_id = _scope(account_id), _scope(library_id)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('Invalid limit')
        now = int(self.clock())
        with self.connection() as db:
            rows = db.execute('''SELECT t.*, (SELECT count(*) FROM exchanges e
                WHERE e.thread_id=t.thread_id AND e.expires_at>?) AS exchange_count
                FROM threads t WHERE t.account_id=? AND t.library_id=? AND t.expires_at>?
                ORDER BY t.updated_at DESC,t.thread_id LIMIT ?''',
                              (now, account_id, library_id, now, limit)).fetchall()
            return [self._thread(row, row['exchange_count']) for row in rows]

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
            return dict(version=1, thread=self._thread(row, len(exchanges)),
                        exchanges=[self._exchange(item) for item in exchanges])

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
            removed_exchanges = db.execute('DELETE FROM exchanges WHERE expires_at<=?', (now,)).rowcount
            removed_threads = db.execute('DELETE FROM threads WHERE expires_at<=?', (now,)).rowcount
            db.commit()
            return dict(exchanges=removed_exchanges, threads=removed_threads)
