"""Content-free, external deletion journal for replay after restoring SQLite backups.

Initialize the sidecar explicitly on a private, durable volume. Every live deletion
must run in a primary ``BEGIN IMMEDIATE`` transaction, append its tombstone here,
then erase the original and commit the primary transaction. On restore, replay this
journal offline before opening the API or workers.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import uuid
from collections.abc import Mapping


class OriginalDeletionError(RuntimeError):
    """A fail-closed journal, namespace, original, or replay validation error."""


class JournalUnavailable(OriginalDeletionError):
    """Generic failure type for runtime/API boundaries; messages contain no private data."""


_HEX64 = re.compile(r'^[0-9a-f]{64}$')
_BATCH = re.compile(r'^[0-9a-f]{32}$')
_MAX_RECORDS = 100_000
_MAX_JOURNAL_BYTES = 128 * 1024 * 1024
_MAX_ID = 128
_FORMAT = 'photohouse-original-deletion-journal-v1'
_FORMAT_V2 = 'photohouse-original-deletion-journal-v2'
_RECORD_COLUMNS = ('seq','collection','library_id','object_id','original_kind','original_sha256',
                   'batch','asset_id','story_id','occurred_at','prev_digest','digest')
_MARKER = 'access_original_deletion_state'


def _canonical_uuid(value):
    try:
        if type(value) is not str or str(uuid.UUID(value)) != value:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise OriginalDeletionError('Invalid deletion journal namespace or identifier') from None
    return value


def _bounded_id(value):
    if type(value) is not str:
        raise OriginalDeletionError('Deletion scope is invalid')
    try:
        size = len(value.encode('utf-8', errors='strict'))
    except UnicodeEncodeError:
        raise OriginalDeletionError('Deletion scope is invalid') from None
    if not 1 <= size <= _MAX_ID:
        raise OriginalDeletionError('Deletion scope is invalid')
    return value


def _digest(value):
    return hashlib.sha256(value).hexdigest()


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True,
                      separators=(',', ':'), allow_nan=False).encode('ascii')


def _genesis(namespace):
    return _digest(_json([_FORMAT, namespace]))


def _no_symlink_path(path):
    """Reject a symlink anywhere in the absolute path, without resolving it."""
    raw = os.fspath(path)
    if not isinstance(raw, str) or not os.path.isabs(raw):
        raise OriginalDeletionError('Deletion journal path must be absolute')
    candidate = Path(os.path.abspath(raw))
    current = Path(candidate.anchor)
    for part in candidate.parts[1:]:
        current = current / part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(mode):
            raise OriginalDeletionError('Deletion journal path cannot contain symlinks')
    return candidate


def _private_directory(path):
    try:
        from .private_storage import require_private_directory
        require_private_directory(path)
    except (ImportError, OSError, ValueError, PermissionError):
        raise OriginalDeletionError('Deletion journal directory is unavailable or not private') from None


def _check_sidecars(path):
    for suffix in ('-journal', '-wal', '-shm'):
        if os.path.lexists(str(path) + suffix):
            raise OriginalDeletionError('Deletion journal has an unexpected sidecar')


def _primary_file(db, journal_path):
    try:
        rows = db.execute('PRAGMA database_list').fetchall()
    except sqlite3.Error:
        raise OriginalDeletionError('Primary database is unavailable') from None
    main = next((row[2] for row in rows if row[1] == 'main'), '')
    if not main or os.path.realpath(main) == os.path.realpath(journal_path):
        raise OriginalDeletionError('Deletion journal must be separate from the primary database')
    return Path(main)


def _columns(db, table):
    try:
        return {row[1] for row in db.execute('PRAGMA table_info(' + table + ')')}
    except sqlite3.Error:
        raise OriginalDeletionError('Deletion source is unavailable') from None


def _source_row(db, collection, object_id):
    table = 'access_upload_annotations' if collection == 'upload' else 'access_memory_contributions'
    try:
        cursor = db.execute('SELECT * FROM ' + table + ' WHERE id=?', (object_id,))
        row = cursor.fetchone()
    except sqlite3.Error:
        raise OriginalDeletionError('Deletion source is unavailable') from None
    if row is None:
        return None
    return dict(zip((column[0] for column in cursor.description), row))


def _original_bytes(row):
    kind = row.get('kind')
    if kind == 'text':
        value = row.get('original_text')
        if type(value) is not str or row.get('original_audio') is not None:
            raise OriginalDeletionError('Original text is unavailable')
        try:
            return value.encode('utf-8', errors='strict')
        except UnicodeEncodeError:
            raise OriginalDeletionError('Original text is invalid') from None
    if kind == 'audio':
        value = row.get('original_audio')
        if type(value) is not bytes or row.get('original_text') is not None:
            raise OriginalDeletionError('Original audio is unavailable')
        return value
    raise OriginalDeletionError('Original kind is invalid')


def _verify_original(row, collection, expected=None):
    if row is None:
        return None
    if collection == 'upload':
        required = {'id', 'library_id', 'batch', 'asset_id', 'kind', 'sha256',
                    'original_text', 'original_audio'}
        scope = ('id', 'library_id', 'batch', 'asset_id')
    else:
        required = {'id', 'library_id', 'story_id', 'kind', 'sha256',
                    'original_text', 'original_audio'}
        scope = ('id', 'library_id', 'story_id')
    if not required <= set(row):
        raise OriginalDeletionError('Deletion source fields are incomplete')
    if expected is not None and any(row[name] != expected.get(name) for name in scope):
        raise OriginalDeletionError('Deletion source scope changed')
    digest = row.get('sha256')
    if type(digest) is not str or not _HEX64.fullmatch(digest):
        raise OriginalDeletionError('Original digest is invalid')
    if _digest(_original_bytes(row)) != digest:
        raise OriginalDeletionError('Original digest mismatch')
    # SQLite CHECK constraints enforce these too; repeat them at the destructive boundary.
    _bounded_id(row['library_id'])
    if collection == 'upload':
        if (type(row['batch']) is not str or not _BATCH.fullmatch(row['batch'])
                or (row['asset_id'] is not None and (type(row['asset_id']) is not int or row['asset_id'] <= 0))):
            raise OriginalDeletionError('Upload deletion scope is invalid')
    else:
        _canonical_uuid(row['story_id'])
    _canonical_uuid(row['id'])
    return digest


def erase_memory_original(db, contribution_id, story_id, library_id, now):
    """Scrub AI copies of a contribution while preserving the story and manual inputs.

    This helper is also intended for the live owner-delete route. Call only after
    appending the external tombstone, inside the same primary write transaction.
    """
    _canonical_uuid(contribution_id)
    _canonical_uuid(story_id)
    if not db.in_transaction:
        raise OriginalDeletionError('Memory erasure requires a primary write transaction')
    try:
        if db.execute('PRAGMA secure_delete').fetchone()[0] != 1:
            raise OriginalDeletionError('Primary secure deletion must be enabled first')
    except sqlite3.Error:
        raise JournalUnavailable('Memory erasure is unavailable') from None
    _bounded_id(library_id)
    row = _source_row(db, 'memory', contribution_id)
    if row is not None and (row.get('story_id') != story_id or row.get('library_id') != library_id):
        raise OriginalDeletionError('Memory deletion scope changed')
    if row is not None:
        _verify_original(row, 'memory')
    if type(now) is not int or now < 0:
        raise OriginalDeletionError('Deletion time is invalid')
    # Jobs retain no prompt, source text, model reply, or lease after source deletion.
    book_scope = '''book_id IN (SELECT b.id FROM access_memory_books b
        WHERE b.library_id=? AND json_valid(b.content) AND EXISTS (
            SELECT 1 FROM json_each(CASE WHEN json_valid(b.content)
                THEN b.content ELSE '{"story_ids":[]}' END,'$.story_ids') refs
            WHERE refs.value=?))'''
    scope = 'story_id=? OR ' + book_scope
    args = (story_id, library_id, story_id)
    try:
        db.execute('''UPDATE access_memory_jobs SET state=CASE
            WHEN state IN ('queued','running') THEN 'cancelled' ELSE state END,
            input_json='{}',output_json=NULL,error_code=NULL,lease_id=NULL,lease_until=NULL,updated_at=?
            WHERE (''' + scope + ')', (now, *args))
        db.execute('''UPDATE access_memory_turns SET reply_text=NULL,reply_kind=NULL
            WHERE conversation_id IN (SELECT id FROM access_memory_conversations
                WHERE story_id=? OR book_id IN (SELECT b.id FROM access_memory_books b
                    WHERE b.library_id=? AND json_valid(b.content) AND EXISTS (
                        SELECT 1 FROM json_each(CASE WHEN json_valid(b.content)
                            THEN b.content ELSE '{"story_ids":[]}' END,'$.story_ids') refs
                        WHERE refs.value=?)))''', args)
        # Delete explicitly as well as relying on CASCADE so an older restored copy
        # with foreign_keys disabled cannot leave an orphaned derived transcript.
        # The side table was added after the f7 collaboration schema. Legacy f7
        # databases remain deletable without attempting a query against it.
        # The optional future editorial tables remain absent on legacy a0.
        # Use the common eraser for both owner deletion and restore replay so
        # foreign-key-disabled backups cannot revive reviewed memoir citations.
        from .memory_book_editorial_deletions import (EditorialDeletionError,
                                                      invalidate_for_contribution)
        try:
            invalidate_for_contribution(db, contribution_id, story_id, library_id)
        except EditorialDeletionError:
            raise JournalUnavailable('Memory erasure is unavailable') from None
        from .memory_book_edition_deletions import (EditionDeletionError,
            invalidate_editions_for_contribution)
        try:
            invalidate_editions_for_contribution(db, contribution_id, story_id, library_id)
        except EditionDeletionError:
            raise JournalUnavailable('Memory erasure is unavailable') from None
        from .memory_source_refs import table_exists
        if table_exists(db):
            db.execute('DELETE FROM access_memory_contribution_refs WHERE contribution_id=?',
                       (contribution_id,))
        db.execute('DELETE FROM access_memory_contribution_derivations WHERE contribution_id=?',
                   (contribution_id,))
        # Authored story chapters and manual conversation input remain.
        db.execute('DELETE FROM access_memory_contributions WHERE id=?', (contribution_id,))
    except sqlite3.Error:
        raise JournalUnavailable('Memory erasure is unavailable') from None


def _deletions_ddl(version):
    if version == 1:
        return '''CREATE TABLE deletions (
                    seq INTEGER PRIMARY KEY CHECK(seq>0), collection TEXT NOT NULL CHECK(collection IN ('upload','memory')),
                    library_id TEXT NOT NULL, object_id TEXT NOT NULL, original_kind TEXT NOT NULL CHECK(original_kind IN ('text','audio')),
                    original_sha256 TEXT NOT NULL CHECK(length(original_sha256)=64 AND original_sha256 NOT GLOB '*[^0-9a-f]*'),
                    batch TEXT, asset_id INTEGER, story_id TEXT, occurred_at INTEGER NOT NULL CHECK(occurred_at>=0),
                    prev_digest TEXT NOT NULL CHECK(length(prev_digest)=64 AND prev_digest NOT GLOB '*[^0-9a-f]*'),
                    digest TEXT NOT NULL CHECK(length(digest)=64 AND digest NOT GLOB '*[^0-9a-f]*'),
                    UNIQUE(collection,library_id,object_id),
                    CHECK((collection='upload' AND batch IS NOT NULL AND story_id IS NULL)
                        OR (collection='memory' AND batch IS NULL AND asset_id IS NULL AND story_id IS NOT NULL)))'''
    return '''CREATE TABLE deletions (
        seq INTEGER PRIMARY KEY CHECK(seq>0), collection TEXT NOT NULL CHECK(collection IN ('upload','memory','family_note')),
        library_id TEXT NOT NULL, object_id TEXT NOT NULL, original_kind TEXT NOT NULL CHECK(original_kind IN ('text','audio')),
        original_sha256 TEXT NOT NULL CHECK(length(original_sha256)=64 AND original_sha256 NOT GLOB '*[^0-9a-f]*'),
        batch TEXT, asset_id INTEGER, story_id TEXT, occurred_at INTEGER NOT NULL CHECK(occurred_at>=0),
        prev_digest TEXT NOT NULL CHECK(length(prev_digest)=64 AND prev_digest NOT GLOB '*[^0-9a-f]*'),
        digest TEXT NOT NULL CHECK(length(digest)=64 AND digest NOT GLOB '*[^0-9a-f]*'), family_binding_json TEXT,
        UNIQUE(collection,library_id,object_id),
        CHECK((collection='upload' AND batch IS NOT NULL AND story_id IS NULL AND family_binding_json IS NULL)
          OR (collection='memory' AND batch IS NULL AND asset_id IS NULL AND story_id IS NOT NULL AND family_binding_json IS NULL)
          OR (collection='family_note' AND batch IS NULL AND asset_id>0 AND story_id IS NULL
              AND original_kind='text' AND family_binding_json IS NOT NULL)))'''


class OriginalDeletionJournal:
    """Append-only external hash-chain with an explicitly bound primary marker."""

    def __init__(self, path, namespace):
        self.path = _no_symlink_path(path)
        self.namespace = _canonical_uuid(namespace)
        self._validate_file()
        self.head()  # bind supplied namespace to the verified ledger metadata

    @classmethod
    def initialize(cls, path, namespace, *, format_version=1):
        """Exclusively create a new private ledger; never create parent directories."""
        if type(format_version) is not int or format_version not in {1, 2}:
            raise OriginalDeletionError('Deletion journal version is invalid')
        namespace = _canonical_uuid(namespace)
        target = _no_symlink_path(path)
        _private_directory(target.parent)
        if os.path.lexists(target):
            raise OriginalDeletionError('Deletion journal already exists')
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if hasattr(os, 'O_NOFOLLOW'):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(target, flags, 0o600)
        except OSError:
            raise OriginalDeletionError('Could not exclusively create deletion journal') from None
        try:
            if os.name == 'posix':
                os.fchmod(fd, 0o600)
            os.fsync(fd)
        finally:
            os.close(fd)
        try:
            from .private_storage import require_private_file
            require_private_file(target)
            instance = cls.__new__(cls)
            instance.path, instance.namespace = target, namespace
            db = instance._connect(validate=False)
            try:
                db.execute('PRAGMA journal_mode=DELETE')
                db.execute('PRAGMA synchronous=FULL')
                db.execute('PRAGMA secure_delete=ON')
                db.execute('BEGIN IMMEDIATE')
                db.execute('''CREATE TABLE journal_meta (
                    id INTEGER PRIMARY KEY CHECK(id=1), format TEXT NOT NULL,
                    namespace TEXT NOT NULL, head_seq INTEGER NOT NULL CHECK(head_seq>=0),
                    head_digest TEXT NOT NULL CHECK(length(head_digest)=64 AND head_digest NOT GLOB '*[^0-9a-f]*'))''')
                db.execute(_deletions_ddl(format_version))
                db.execute('CREATE INDEX ix_deletions_library_seq ON deletions(library_id,seq)')
                db.execute('INSERT INTO journal_meta VALUES (1,?,?,0,?)',
                           (_FORMAT if format_version == 1 else _FORMAT_V2, namespace, _genesis(namespace)))
                db.commit()
                db.execute('PRAGMA journal_mode=DELETE')
                if db.execute('PRAGMA synchronous').fetchone()[0] != 2:
                    raise OriginalDeletionError('Deletion journal durability setting failed')
            finally:
                db.close()
            _check_sidecars(target)
            file_fd = os.open(target, os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0))
            try:
                os.fsync(file_fd)
            finally:
                os.close(file_fd)
            from .private_storage import sync_directory
            sync_directory(target.parent)
            return cls(target, namespace)
        except BaseException:
            # Remove only the file we created; the parent directory is never created.
            for suffix in ('-journal', '-wal', '-shm'):
                try:
                    os.unlink(str(target) + suffix)
                except FileNotFoundError:
                    pass
            try:
                os.unlink(target)
            except FileNotFoundError:
                pass
            raise

    def _validate_file(self):
        _private_directory(self.path.parent)
        try:
            info = self.path.lstat()
            if info.st_size > _MAX_JOURNAL_BYTES:
                raise OriginalDeletionError('Deletion journal exceeds its bounded size')
            from .private_storage import require_private_file
            require_private_file(self.path)
        except OriginalDeletionError:
            raise
        except (ImportError, OSError, ValueError, PermissionError):
            raise OriginalDeletionError('Deletion journal file is unavailable or not private') from None
        _check_sidecars(self.path)

    def _connect(self, *, validate=True):
        if validate:
            self._validate_file()
        uri = self.path.as_uri() + '?mode=rw'
        try:
            db = sqlite3.connect(uri, uri=True, timeout=10, isolation_level=None)
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA query_only=OFF')
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('PRAGMA synchronous=FULL')
            if db.execute('PRAGMA journal_mode').fetchone()[0].lower() != 'delete':
                db.close()
                raise OriginalDeletionError('Deletion journal must use DELETE journaling')
            if db.execute('PRAGMA synchronous').fetchone()[0] != 2:
                db.close()
                raise OriginalDeletionError('Deletion journal must use FULL synchronization')
            return db
        except OriginalDeletionError:
            raise
        except sqlite3.Error:
            raise OriginalDeletionError('Deletion journal is unavailable or invalid') from None

    @staticmethod
    def _verify_columns(db, meta):
        expected = set(_RECORD_COLUMNS)
        if meta['format'] == _FORMAT_V2:
            expected.add('family_binding_json')
        if _columns(db, 'deletions') != expected:
            raise OriginalDeletionError('Deletion journal format is invalid')

    def upgrade_family_format(self, primary_db, *, expected_head, precommit_guard=None):
        """Explicit offline capability upgrade; keeps all V1 bytes and marker digests.

        The caller must hold the primary write transaction. No automatic upgrade,
        primary commit, note adoption or deletion occurs here. The optional offline
        guard runs under the journal write lock before any capability DDL.
        """
        if not primary_db.in_transaction:
            raise OriginalDeletionError('Upgrade requires a primary write transaction')
        _primary_file(primary_db, self.path)
        from .family_note_identity import identity_enabled
        if not identity_enabled(primary_db):
            raise OriginalDeletionError('Family note identity schema is required')
        marker = self._primary_marker(primary_db)
        ledger = self._connect()
        try:
            ledger.execute('BEGIN IMMEDIATE')
            meta, _history = self._meta(ledger)
            head = (self.namespace, meta['head_seq'], meta['head_digest'])
            if head != expected_head or marker != head[1:]:
                raise OriginalDeletionError('Journal changed after reviewed plan')
            if precommit_guard is not None:
                precommit_guard(primary_db)
            if meta['format'] == _FORMAT_V2:
                ledger.commit()
                return head
            ledger.execute('DROP INDEX ix_deletions_library_seq')
            ledger.execute('ALTER TABLE deletions RENAME TO legacy_deletions')
            ledger.execute(_deletions_ddl(2))
            names = ','.join(_RECORD_COLUMNS)
            ledger.execute('INSERT INTO deletions (' + names + ') SELECT ' + names + ' FROM legacy_deletions')
            ledger.execute('DROP TABLE legacy_deletions')
            ledger.execute('CREATE INDEX ix_deletions_library_seq ON deletions(library_id,seq)')
            ledger.execute('UPDATE journal_meta SET format=? WHERE id=1', (_FORMAT_V2,))
            checked, _history = self._meta(ledger)
            if (self.namespace, checked['head_seq'], checked['head_digest']) != head:
                raise OriginalDeletionError('Deletion journal upgrade changed history')
            ledger.commit()
            return head
        except BaseException:
            ledger.rollback()
            raise
        finally:
            ledger.close()

    def require_family_format(self):
        ledger = self._connect()
        try:
            ledger.execute('BEGIN')
            meta, _ = self._meta(ledger)
            if meta['format'] != _FORMAT_V2:
                raise OriginalDeletionError('Family note deletion requires journal version 2')
        finally:
            ledger.close()

    def family_record(self, primary_db, note_id):
        """Internal content-free committed receipt for an exact idempotent retry."""
        _canonical_uuid(note_id)
        self.assert_current(primary_db)
        ledger = self._connect()
        try:
            ledger.execute('BEGIN')
            meta, _ = self._meta(ledger)
            if self._primary_marker(primary_db) != (meta['head_seq'], meta['head_digest']):
                raise OriginalDeletionError('Primary deletion marker differs from journal head')
            rows = ledger.execute("SELECT * FROM deletions WHERE collection='family_note' AND object_id=?",
                                  (note_id,)).fetchall()
            if len(rows) > 1:
                raise OriginalDeletionError('Family note deletion history is ambiguous')
            return dict(rows[0]) if rows else None
        finally:
            ledger.close()

    def _meta(self, db):
        try:
            objects = {(row[0], row[1]) for row in db.execute(
                "SELECT type,name FROM sqlite_master WHERE type IN ('table','view','trigger') "
                "AND name NOT LIKE 'sqlite_%'")}
            if objects != {('table','journal_meta'),('table','deletions')}:
                raise OriginalDeletionError('Deletion journal format is invalid')
            if {row[1] for row in db.execute('PRAGMA table_info(journal_meta)')} != {
                    'id','format','namespace','head_seq','head_digest'}:
                raise OriginalDeletionError('Deletion journal format is invalid')
            rows = db.execute('SELECT id,format,namespace,head_seq,head_digest FROM journal_meta').fetchall()
        except sqlite3.Error:
            raise OriginalDeletionError('Deletion journal format is invalid') from None
        if len(rows) != 1 or rows[0]['id'] != 1 or rows[0]['format'] not in {_FORMAT, _FORMAT_V2}:
            raise OriginalDeletionError('Deletion journal format is invalid')
        meta = rows[0]
        self._verify_columns(db, meta)
        if meta['namespace'] != self.namespace:
            raise OriginalDeletionError('Deletion journal namespace mismatch')
        if (type(meta['head_seq']) is not int or not 0 <= meta['head_seq'] <= _MAX_RECORDS
                or type(meta['head_digest']) is not str or not _HEX64.fullmatch(meta['head_digest'])):
            raise OriginalDeletionError('Deletion journal head is invalid')
        cursor = db.execute('SELECT * FROM deletions ORDER BY seq')
        previous = _genesis(self.namespace)
        history = [previous]
        seen = set()
        number = 0
        while True:
            batch = cursor.fetchmany(256)
            if not batch:
                break
            for row in batch:
                number += 1
                record = dict(row)
                if record['seq'] != number or record['prev_digest'] != previous:
                    raise OriginalDeletionError('Deletion journal hash chain mismatch')
                self._validate_record(record)
                if meta['format'] == _FORMAT and record['collection'] == 'family_note':
                    raise OriginalDeletionError('Deletion journal format is invalid')
                key = (record['collection'], record['library_id'], record['object_id'])
                if key in seen:
                    raise OriginalDeletionError('Duplicate deletion journal object')
                seen.add(key)
                expected = _record_digest(previous, record)
                if record['digest'] != expected:
                    raise OriginalDeletionError('Deletion journal hash chain mismatch')
                previous = expected
                history.append(previous)
        if number != meta['head_seq']:
            raise OriginalDeletionError('Deletion journal sequence gap')
        if previous != meta['head_digest']:
            raise OriginalDeletionError('Deletion journal head mismatch')
        return meta, history

    def _fast_meta(self, db):
        """Check current watermarks in bounded time; replay still validates full history."""
        try:
            objects = {(row[0], row[1]) for row in db.execute(
                "SELECT type,name FROM sqlite_master WHERE type IN ('table','view','trigger') "
                "AND name NOT LIKE 'sqlite_%'")}
            if objects != {('table','journal_meta'),('table','deletions')}:
                raise OriginalDeletionError('Deletion journal format is invalid')
            if {row[1] for row in db.execute('PRAGMA table_info(journal_meta)')} != {
                    'id','format','namespace','head_seq','head_digest'}:
                raise OriginalDeletionError('Deletion journal format is invalid')
            meta_rows = db.execute('SELECT id,format,namespace,head_seq,head_digest FROM journal_meta').fetchall()
            if len(meta_rows) != 1 or meta_rows[0]['id'] != 1:
                raise OriginalDeletionError('Deletion journal format is invalid')
            meta = meta_rows[0]
            self._verify_columns(db, meta)
            if (meta['format'] not in {_FORMAT, _FORMAT_V2} or meta['namespace'] != self.namespace
                    or type(meta['head_seq']) is not int or not 0 <= meta['head_seq'] <= _MAX_RECORDS
                    or type(meta['head_digest']) is not str or not _HEX64.fullmatch(meta['head_digest'])):
                raise OriginalDeletionError('Deletion journal head is invalid')
            count, minimum, maximum = db.execute(
                'SELECT count(*),min(seq),max(seq) FROM deletions').fetchone()
            if count != meta['head_seq'] or (count and (minimum != 1 or maximum != count)):
                raise OriginalDeletionError('Deletion journal sequence gap')
            if count == 0:
                if meta['head_digest'] != _genesis(self.namespace):
                    raise OriginalDeletionError('Deletion journal head mismatch')
            else:
                row = db.execute('SELECT * FROM deletions WHERE seq=?',(count,)).fetchone()
                record = dict(row)
                self._validate_record(record)
                if (record['digest'] != meta['head_digest']
                        or record['prev_digest'] != _genesis(self.namespace) and count == 1
                        or _record_digest(record['prev_digest'], record) != record['digest']):
                    raise OriginalDeletionError('Deletion journal head mismatch')
                if count > 1:
                    prior = db.execute('SELECT digest FROM deletions WHERE seq=?',(count-1,)).fetchone()
                    if prior is None or prior[0] != record['prev_digest']:
                        raise OriginalDeletionError('Deletion journal head mismatch')
            return meta
        except OriginalDeletionError:
            raise
        except sqlite3.Error:
            raise JournalUnavailable('Deletion journal is unavailable or invalid') from None

    @staticmethod
    def _validate_record(record):
        if (type(record.get('seq')) is not int or not 1 <= record['seq'] <= _MAX_RECORDS
                or type(record.get('prev_digest')) is not str or not _HEX64.fullmatch(record['prev_digest'])
                or type(record.get('digest')) is not str or not _HEX64.fullmatch(record['digest'])
                or record.get('collection') not in {'upload', 'memory', 'family_note'}
                or record.get('original_kind') not in {'text', 'audio'}
                or type(record.get('object_id')) is not str
                or len(record['object_id']) > _MAX_ID
                or type(record.get('original_sha256')) is not str
                or not _HEX64.fullmatch(record['original_sha256'])
                or type(record.get('occurred_at')) is not int or record['occurred_at'] < 0):
            raise OriginalDeletionError('Deletion journal record is invalid')
        _bounded_id(record['library_id'])
        _canonical_uuid(record['object_id'])
        if record['collection'] != 'family_note' and record.get('family_binding_json') is not None:
            raise OriginalDeletionError('Unexpected family note binding')
        if record['collection'] == 'family_note':
            from .family_note_deletions import parse_family_binding
            parse_family_binding(record.get('family_binding_json'))
            if (record.get('batch') is not None or record.get('story_id') is not None
                    or type(record.get('asset_id')) is not int or not 1 <= record['asset_id'] <= 2**63-1
                    or record['original_kind'] != 'text'):
                raise OriginalDeletionError('Family note deletion record is invalid')
        elif record['collection'] == 'upload':
            if (type(record.get('batch')) is not str or not _BATCH.fullmatch(record['batch'])
                    or (record.get('asset_id') is not None and
                        (type(record['asset_id']) is not int or record['asset_id'] <= 0))
                    or record.get('story_id') is not None):
                raise OriginalDeletionError('Upload deletion record is invalid')
        else:
            if record.get('batch') is not None or record.get('asset_id') is not None:
                raise OriginalDeletionError('Memory deletion record is invalid')
            _canonical_uuid(record.get('story_id'))

    def _primary_marker(self, db):
        required = {'id', 'namespace', 'applied_seq', 'applied_digest'}
        if not required <= _columns(db, _MARKER):
            raise OriginalDeletionError('Primary deletion marker is unavailable')
        rows = db.execute(f'SELECT id,namespace,applied_seq,applied_digest FROM {_MARKER}').fetchall()
        if len(rows) != 1 or rows[0][0] != 1:
            raise OriginalDeletionError('Primary deletion marker is missing or ambiguous')
        row = rows[0]
        if row[1] != self.namespace:
            raise OriginalDeletionError('Primary deletion namespace mismatch')
        if type(row[2]) is not int or row[2] < 0 or type(row[3]) is not str or not _HEX64.fullmatch(row[3]):
            raise OriginalDeletionError('Primary deletion marker is invalid')
        return row[2], row[3]

    def head(self):
        """Return the content-free (namespace, sequence, digest) journal head."""
        db = self._connect()
        try:
            db.execute('BEGIN')
            meta, _ = self._meta(db)
            return self.namespace, meta['head_seq'], meta['head_digest']
        except sqlite3.Error:
            raise OriginalDeletionError('Deletion journal is unavailable or invalid') from None
        finally:
            db.close()

    def history_digest(self, sequence):
        """Return a verified content-free digest for a sequence in this chain."""
        if type(sequence) is not int or sequence < 0:
            raise OriginalDeletionError('Deletion journal sequence is invalid')
        db = self._connect()
        try:
            db.execute('BEGIN')
            meta, history = self._meta(db)
            if sequence > meta['head_seq']:
                raise OriginalDeletionError('Deletion journal sequence is beyond head')
            return history[sequence]
        except sqlite3.Error:
            raise OriginalDeletionError('Deletion journal is unavailable or invalid') from None
        finally:
            db.close()

    def bind(self, primary_db, *, precommit_guard=None):
        """Explicitly bind a truly empty primary to an empty journal exactly once."""
        _primary_file(primary_db, self.path)
        if primary_db.in_transaction:
            raise OriginalDeletionError('Primary database transaction is already active')
        if primary_db.execute('PRAGMA foreign_keys').fetchone()[0] != 1:
            raise OriginalDeletionError('Primary database foreign keys must be enabled')
        primary_db.execute('BEGIN IMMEDIATE')
        try:
            if precommit_guard is not None:
                precommit_guard(primary_db)
            journal = self._connect()
            try:
                journal.execute('BEGIN')
                meta, _ = self._meta(journal)
                if meta['head_seq'] != 0:
                    raise OriginalDeletionError('Only an empty deletion journal can be bound')
                if primary_db.execute(f'SELECT count(*) FROM {_MARKER}').fetchone()[0] != 0:
                    raise OriginalDeletionError('Primary database is already bound')
                existing_tables = {row[0] for row in primary_db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")}
                for table in ('access_upload_annotations', 'access_memory_contributions'):
                    if table not in existing_tables:
                        raise OriginalDeletionError('Required original tables are unavailable')
                    if primary_db.execute('SELECT count(*) FROM ' + table).fetchone()[0]:
                        raise OriginalDeletionError('Primary database originals prevent binding')
                from .family_note_identity_schema import IDENTITY_TABLES
                for table in IDENTITY_TABLES:
                    if table in existing_tables and primary_db.execute('SELECT 1 FROM ' + table + ' LIMIT 1').fetchone():
                        raise OriginalDeletionError('Family note history prevents binding')
                primary_db.execute(f'INSERT INTO {_MARKER} (id,namespace,applied_seq,applied_digest) VALUES (1,?,?,?)',
                                   (self.namespace, 0, meta['head_digest']))
                journal.commit()
            finally:
                journal.close()
            primary_db.commit()
        except BaseException as exc:
            primary_db.rollback()
            if isinstance(exc, sqlite3.Error):
                raise JournalUnavailable('Could not bind deletion journal') from None
            raise

    def assert_current(self, primary_db):
        """Require the primary marker to match the external head using bounded checks.

        This routine verifies the journal schema, sequence watermark/count, primary
        marker and final record. ``head()``, ``append()`` and ``replay()`` validate
        the full hash chain; restore replay is always a full-history verification.
        """
        _primary_file(primary_db, self.path)
        marker_seq, marker_digest = self._primary_marker(primary_db)
        ledger = self._connect()
        try:
            ledger.execute('BEGIN')
            meta = self._fast_meta(ledger)
        finally:
            ledger.close()
        if marker_seq != meta['head_seq'] or marker_digest != meta['head_digest']:
            raise OriginalDeletionError('Primary deletion marker differs from journal head')
        return self.namespace, meta['head_seq'], meta['head_digest']

    def review(self, primary_db):
        """Read-only full-chain and pending-source review; returns no row identifiers."""
        _primary_file(primary_db, self.path)
        if primary_db.in_transaction:
            raise OriginalDeletionError('Primary database transaction is already active')
        primary_db.execute('PRAGMA query_only=ON')
        primary_db.execute('BEGIN')
        ledger = None
        try:
            marker_seq, marker_digest = self._primary_marker(primary_db)
            ledger = self._connect()
            ledger.execute('BEGIN')
            meta, history = self._meta(ledger)
            if marker_seq > meta['head_seq'] or history[marker_seq] != marker_digest:
                raise OriginalDeletionError('Primary marker is outside journal history')
            pending = {}
            for row in ledger.execute('SELECT * FROM deletions WHERE seq>? ORDER BY seq', (marker_seq,)):
                record = dict(row)
                self._verify_record(primary_db, record)
                pending[(record['collection'], record['object_id'])] = record
            integrity = primary_db.execute('PRAGMA quick_check').fetchone()
            if integrity is None or integrity[0] != 'ok':
                raise OriginalDeletionError('Primary integrity check failed')
            violations = primary_db.execute('PRAGMA foreign_key_check').fetchall()
            if violations and not self._replayable_fk_violations(primary_db, violations, pending):
                raise OriginalDeletionError('Primary foreign-key review failed')
            return {'sequence': meta['head_seq'], 'digest': meta['head_digest'],
                    'pending_count': meta['head_seq'] - marker_seq}
        except OriginalDeletionError:
            raise
        except sqlite3.Error:
            raise JournalUnavailable('Deletion review is unavailable') from None
        finally:
            if ledger is not None:
                ledger.rollback()
                ledger.close()
            primary_db.rollback()
            primary_db.execute('PRAGMA query_only=OFF')

    @staticmethod
    def _replayable_fk_violations(db, violations, pending):
        """Permit only known orphaned children that their pending delete will erase."""
        parent_column = {
            'access_annotation_tag_proposals': ('annotation_id', 'upload'),
            'access_annotation_derivations': ('annotation_id', 'upload'),
            'access_memory_contribution_derivations': ('contribution_id', 'memory'),
        }
        try:
            for table, rowid, _parent, _fkid in violations:
                if table == 'access_story_revisions':
                    if _parent != 'access_stories' or type(rowid) is not int:
                        return False
                    row = db.execute('SELECT story_id FROM access_story_revisions WHERE rowid=?', (rowid,)).fetchone()
                    if row is None or ('family_note', row[0]) not in pending:
                        return False
                    continue
                if table == 'access_memory_book_editorial_refs':
                    # Only a missing contribution covered by the exact newer
                    # tombstone is recoverable. A missing book/story revision
                    # is independent corruption and must still stop review.
                    if _parent != 'access_memory_contributions' or type(rowid) is not int:
                        return False
                    row = db.execute('''SELECT r.contribution_id,r.story_id,b.library_id
                        FROM access_memory_book_editorial_refs r
                        JOIN access_memory_books b ON b.id=r.book_id WHERE r.rowid=?''',
                        (rowid,)).fetchone()
                    if row is None:
                        return False
                    record = pending.get(('memory', row[0]))
                    if (not isinstance(record, Mapping) or record.get('story_id') != row[1]
                            or record.get('library_id') != row[2]):
                        return False
                    continue
                if table == 'access_memory_book_edition_sources':
                    # The exact pending contribution tombstone may also repair
                    # source closure rows in a reviewed AI edition. No unrelated
                    # missing book/story/account parent becomes replayable.
                    if _parent != 'access_memory_contributions' or type(rowid) is not int:
                        return False
                    from .memory_book_edition_deletions import (EditionDeletionError,
                                                               verify_edition_schema)
                    try:
                        verify_edition_schema(db)
                    except EditionDeletionError:
                        return False
                    row = db.execute('''SELECT r.contribution_id,r.contribution_story_id,
                        e.library_id,b.library_id,r.source_id,r.kind
                        FROM access_memory_book_edition_sources r
                        JOIN access_memory_book_editions e ON e.id=r.edition_id
                        JOIN access_memory_books b ON b.id=e.book_id WHERE r.rowid=?''',
                        (rowid,)).fetchone()
                    if row is None:
                        return False
                    record = pending.get(('memory', row[0]))
                    if (not isinstance(record, Mapping) or record.get('story_id') != row[1]
                            or record.get('library_id') != row[2] or row[2] != row[3]
                            or row[4] != 'contribution-' + row[0]
                            or row[5] not in {'family', 'transcript'}):
                        return False
                    continue
                spec = parent_column.get(table)
                if spec is None or type(rowid) is not int:
                    return False
                column, collection = spec
                row = db.execute('SELECT ' + column + ' FROM ' + table + ' WHERE rowid=?',
                                 (rowid,)).fetchone()
                if row is None or (collection, row[0]) not in pending:
                    return False
            return True
        except sqlite3.Error:
            return False

    def append(self, primary_db, collection, row, occurred_at):
        """Durably append a content-free tombstone before caller erases the original.

        ``primary_db`` must be owned by an active ``BEGIN IMMEDIATE`` transaction.
        This method updates its marker but does not commit that transaction.
        """
        if collection not in {'upload', 'memory', 'family_note'} or not (
                isinstance(row, Mapping) or callable(getattr(row, 'keys', None))):
            raise OriginalDeletionError('Deletion request is invalid')
        try:
            row = dict(row)
        except (TypeError, ValueError):
            raise OriginalDeletionError('Deletion request is invalid') from None
        if type(occurred_at) is not int or occurred_at < 0:
            raise OriginalDeletionError('Deletion time is invalid')
        if not primary_db.in_transaction:
            raise OriginalDeletionError('Append requires a primary write transaction')
        _primary_file(primary_db, self.path)
        if primary_db.execute('PRAGMA secure_delete').fetchone()[0] != 1:
            raise OriginalDeletionError('Primary secure deletion must be enabled first')
        marker_seq, marker_digest = self._primary_marker(primary_db)
        object_id = row.get('id')
        _canonical_uuid(object_id)
        if collection == 'family_note':
            from .family_note_deletions import prepare_family_tombstone, preflight_family_erasure
            candidate = prepare_family_tombstone(primary_db, object_id, row.get('revision'), occurred_at)
            preflight_family_erasure(primary_db, candidate)
        else:
            current = _source_row(primary_db, collection, object_id)
            if current is None:
                raise OriginalDeletionError('Original is already absent')
            source_digest = _verify_original(current, collection, row)
            if (current.get('kind') != row.get('kind') or row.get('sha256') != source_digest
                    or type(current.get('kind')) is not str):
                raise OriginalDeletionError('Deletion source kind changed')
            candidate = _journal_fields(collection, current, source_digest, occurred_at)

        ledger = self._connect()
        try:
            ledger.execute('BEGIN IMMEDIATE')
            meta, history = self._meta(ledger)
            if collection == 'family_note' and meta['format'] != _FORMAT_V2:
                raise OriginalDeletionError('Family note deletion requires journal version 2')
            existing_row=ledger.execute('''SELECT * FROM deletions
                WHERE collection=? AND library_id=? AND object_id=?''',
                (collection,candidate['library_id'],object_id)).fetchone()
            existing=dict(existing_row) if existing_row is not None else None
            if marker_seq == meta['head_seq'] and marker_digest == meta['head_digest']:
                if existing:
                    # A committed marker and a still-present row is an impossible split state.
                    raise OriginalDeletionError('Deletion was already committed for this original')
                entry = {**candidate, 'seq': meta['head_seq'] + 1,
                         'prev_digest': meta['head_digest']}
                entry['digest'] = _record_digest(entry['prev_digest'], entry)
                self._validate_record(entry)
                names = list(_RECORD_COLUMNS)
                if meta['format'] == _FORMAT_V2:
                    names.append('family_binding_json')
                ledger.execute('INSERT INTO deletions (' + ','.join(names) + ') VALUES (' +
                    ','.join('?' for _ in names) + ')', tuple(entry.get(name) for name in names))
                ledger.execute('UPDATE journal_meta SET head_seq=?,head_digest=? WHERE id=1',
                               (entry['seq'], entry['digest']))
                ledger.commit()  # durable before the primary transaction can erase original bytes
                primary_db.execute(f'UPDATE {_MARKER} SET applied_seq=?,applied_digest=? WHERE id=1',
                                   (entry['seq'], entry['digest']))
                return self._public_record(entry)
            # A crash after the external append but before primary commit leaves exactly
            # one uncommitted marker step. Allow only its exact retry, then advance marker.
            if (existing is not None and meta['head_seq'] == marker_seq + 1
                    and existing['seq'] == meta['head_seq']
                    and existing['prev_digest'] == marker_digest
                    and existing['digest'] == meta['head_digest']
                    and _same_tombstone(existing, candidate)):
                ledger.commit()
                primary_db.execute(f'UPDATE {_MARKER} SET applied_seq=?,applied_digest=? WHERE id=1',
                                   (meta['head_seq'], meta['head_digest']))
                return self._public_record(existing)
            raise OriginalDeletionError('Primary deletion marker differs from journal head')
        except OriginalDeletionError:
            if ledger.in_transaction:
                ledger.rollback()
            raise
        except (sqlite3.Error, UnicodeError):
            if ledger.in_transaction:
                ledger.rollback()
            raise OriginalDeletionError('Deletion journal append failed') from None
        finally:
            ledger.close()

    def replay(self, primary_db, *, expected_head=None, precommit_guard=None):
        """Apply all newer tombstones to a restored primary before service startup."""
        primary_path=_primary_file(primary_db, self.path)
        if primary_db.in_transaction:
            raise OriginalDeletionError('Primary database transaction is already active')
        _check_sidecars(primary_path)
        try:
            if primary_db.execute('PRAGMA journal_mode').fetchone()[0].lower() != 'delete':
                raise OriginalDeletionError('Restored primary must use DELETE journaling')
            primary_db.execute('PRAGMA synchronous=FULL')
            if primary_db.execute('PRAGMA synchronous').fetchone()[0] != 2:
                raise OriginalDeletionError('Restored primary durability setting failed')
        except sqlite3.Error:
            raise JournalUnavailable('Restored primary is unavailable') from None
        if primary_db.execute('PRAGMA foreign_keys').fetchone()[0] != 1:
            raise OriginalDeletionError('Primary database foreign keys must be enabled')
        if primary_db.execute('PRAGMA secure_delete=ON').fetchone()[0] != 1:
            raise OriginalDeletionError('Primary secure deletion is unavailable')
        primary_db.execute('BEGIN EXCLUSIVE')
        ledger = None
        try:
            marker_seq, marker_digest = self._primary_marker(primary_db)
            ledger = self._connect()
            ledger.execute('BEGIN')  # lock journal snapshot after taking primary EXCLUSIVE
            meta, history = self._meta(ledger)
            current_head = (self.namespace, meta['head_seq'], meta['head_digest'])
            if expected_head is not None and current_head != expected_head:
                raise OriginalDeletionError('Journal changed after reviewed plan')
            if marker_seq > meta['head_seq'] or history[marker_seq] != marker_digest:
                raise OriginalDeletionError('Restored primary marker is outside journal history')
            if precommit_guard is not None:
                precommit_guard(primary_db)
            count = 0
            cursor=ledger.execute('SELECT * FROM deletions WHERE seq>? ORDER BY seq',(marker_seq,))
            while True:
                batch=cursor.fetchmany(256)
                if not batch:
                    break
                for row in batch:
                    self._apply_record(primary_db,dict(row))
                    count += 1
            primary_db.execute(f'UPDATE {_MARKER} SET applied_seq=?,applied_digest=? WHERE id=1',
                               (meta['head_seq'], meta['head_digest']))
            if primary_db.execute('PRAGMA foreign_key_check').fetchone() is not None:
                raise OriginalDeletionError('Deletion replay violates foreign keys')
            integrity = primary_db.execute('PRAGMA quick_check').fetchone()
            if integrity is None or integrity[0] != 'ok':
                raise OriginalDeletionError('Deletion replay integrity check failed')
            primary_db.commit()
            return self.namespace, meta['head_seq'], meta['head_digest'], count
        except OriginalDeletionError:
            primary_db.rollback()
            raise
        except (sqlite3.Error, UnicodeError):
            primary_db.rollback()
            raise OriginalDeletionError('Deletion replay failed') from None
        finally:
            if ledger is not None:
                try:
                    ledger.commit()
                finally:
                    ledger.close()

    def _apply_record(self, db, record):
        if record['collection'] == 'family_note':
            self._validate_record(record)
            from .family_note_deletions import erase_family_note_original
            erase_family_note_original(db, record)
            return
        row = self._verify_record(db, record)
        collection = record['collection']
        if row is None:
            if collection == 'upload':
                # A legacy/partial deletion may have removed the parent but left
                # derived rows when foreign keys were disabled during restore.
                db.execute('DELETE FROM access_annotation_tag_proposals WHERE annotation_id=?',
                           (record['object_id'],))
                db.execute('DELETE FROM access_annotation_derivations WHERE annotation_id=?',
                           (record['object_id'],))
            else:
                erase_memory_original(db,record['object_id'],record['story_id'],
                                      record['library_id'],record['occurred_at'])
            return  # exact tombstone already applied to this restored copy
        if collection == 'upload':
            db.execute('DELETE FROM access_annotation_tag_proposals WHERE annotation_id=?', (record['object_id'],))
            db.execute('DELETE FROM access_annotation_derivations WHERE annotation_id=?', (record['object_id'],))
            db.execute('DELETE FROM access_upload_annotations WHERE id=?', (record['object_id'],))
        else:
            erase_memory_original(db, record['object_id'], record['story_id'],
                                  record['library_id'], record['occurred_at'])

    def _verify_record(self, db, record):
        self._validate_record(record)
        collection = record['collection']
        if collection == 'family_note':
            from .family_note_deletions import preflight_family_erasure
            return preflight_family_erasure(db, record)[2]
        row = _source_row(db, collection, record['object_id'])
        if row is None:
            return None
        expected = {'id': record['object_id'], 'library_id': record['library_id']}
        if collection == 'upload':
            expected.update(batch=record['batch'], asset_id=record['asset_id'])
        else:
            expected['story_id'] = record['story_id']
        digest = _verify_original(row, collection, expected)
        if (digest != record['original_sha256'] or row['kind'] != record['original_kind']):
            raise OriginalDeletionError('Restored original differs from deletion tombstone')
        return row

    @staticmethod
    def _public_record(record):
        return {key: record[key] for key in ('seq','collection','library_id','object_id',
            'original_kind','original_sha256','batch','asset_id','story_id','occurred_at','digest')}


def _journal_fields(collection, row, digest, occurred_at):
    base = {'collection': collection, 'library_id': row['library_id'], 'object_id': row['id'],
            'original_kind': row['kind'], 'original_sha256': digest, 'batch': None,
            'asset_id': None, 'story_id': None, 'occurred_at': occurred_at}
    if collection == 'upload':
        base.update(batch=row['batch'], asset_id=row['asset_id'])
    else:
        base['story_id'] = row['story_id']
    return base


def _record_digest(previous, record):
    body = {key: record[key] for key in ('seq','collection','library_id','object_id',
        'original_kind','original_sha256','batch','asset_id','story_id','occurred_at')}
    if record['collection'] == 'family_note':
        body['family_binding_json'] = record['family_binding_json']
        body['format'] = _FORMAT_V2
    return _digest(bytes.fromhex(previous) + _json(body))


def _same_tombstone(existing, candidate):
    if existing.get('family_binding_json') != candidate.get('family_binding_json'):
        return False
    return all(existing[name] == candidate[name] for name in (
        'collection','library_id','object_id','original_kind','original_sha256',
        'batch','asset_id','story_id'))
