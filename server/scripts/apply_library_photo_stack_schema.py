"""Apply the explicitly reviewed additive photo-stack schema to offline SQLite.

Review is read-only by default. Execute mode expects an independently approved
all-writer shutdown and four separate private inputs: primary, primary backup,
deletion journal, and byte-identical journal backup. It never upgrades the
journal format, restores a backup, starts a worker, or activates a service.
"""
from __future__ import annotations

import hashlib
from contextlib import closing
from pathlib import Path
import re
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import apply_memory_group_schema as groups
import rehearse_fullsize_database as full

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.access.memory_group_schema import GROUP_REVISION, verify_memory_group_schema
from app.access.original_deletions import OriginalDeletionJournal
from app.access.photo_stack_schema import REVISION as STACK_REVISION, TABLES as STACK_TABLES, available as stack_available
from app.access.private_storage import require_private_file

A0_REVISION = 'a0c9d2e4f817'
E7_REVISION = GROUP_REVISION
TO_REVISION = STACK_REVISION
SOURCE_REVISIONS = (A0_REVISION, E7_REVISION)
JOURNAL_FORMATS = {
    'photohouse-original-deletion-journal-v1': 1,
    'photohouse-original-deletion-journal-v2': 2,
    'photohouse-original-deletion-journal-v3': 3,
    'photohouse-original-deletion-journal-v4': 4,
}

MAX_JOURNAL_BYTES = 64 * 1024**2

_GROUP_ADDITIONS = groups._additions(A0_REVISION)
_E7_REQUIRED_TABLES = frozenset(groups.REQUIRED_TABLES | {
    name for _revision, names in groups.STEPS for name in names
})


def _objects(db):
    return frozenset(db.execute(
        "SELECT type,name,tbl_name,sql FROM sqlite_master "
        "WHERE type IN ('table','index','trigger','view') AND name NOT LIKE 'sqlite_%'"))


def _additions(from_revision):
    if type(from_revision) is not str or from_revision not in SOURCE_REVISIONS:
        raise full.small.Refused('Explicit a0 or e7 source revision required')
    if from_revision == A0_REVISION:
        return tuple(_GROUP_ADDITIONS) + tuple(STACK_TABLES)
    return tuple(STACK_TABLES)


def _source(db, budget, from_revision):
    additions = set(_additions(from_revision))
    revision = full.validate(db, budget)
    if revision != from_revision:
        raise full.small.Refused('Exact reviewed source revision required')
    tables = full.schema(db)
    if additions & set(tables):
        raise full.small.Refused('Pending schema tables must be absent')
    if set(STACK_TABLES) & set(tables):
        raise full.small.Refused('Partial photo-stack schema refused')
    if from_revision == A0_REVISION:
        tables = groups._source(db, budget, A0_REVISION)
    else:
        if not _E7_REQUIRED_TABLES <= set(tables):
            raise full.small.Refused('Complete e7 source schema required')
        if not verify_memory_group_schema(db):
            raise full.small.Refused('Exact e7 memory-group schema required')
        if db.execute("SELECT 1 FROM tasks WHERE state='running' LIMIT 1").fetchone():
            raise full.small.Refused('All running tasks must be drained')
    return tables


def _expected_addition(from_revision):
    """Render the full Alembic chain's authoritative object delta."""
    from sqlalchemy import create_engine
    from app.access.metadata import migration_metadata
    from app.db import Base

    additions = _additions(from_revision)
    metadata = migration_metadata(Base.metadata)
    engine = create_engine('sqlite://')
    try:
        with engine.begin() as connection:
            # Family-note D1 emits triggers on this existing table.
            metadata.tables['access_stories'].create(connection)
            metadata.create_all(connection, tables=[table for table in metadata.sorted_tables
                                                   if table.name not in additions])
            before = _objects(connection.connection.driver_connection)
            for name in additions:
                metadata.tables[name].create(connection)
            return _objects(connection.connection.driver_connection) - before
    finally:
        engine.dispose()


def _digest_file(path, budget):
    digest = hashlib.sha256()
    total = 0
    with open(path, 'rb', buffering=0) as stream:
        while True:
            budget.check()
            block = stream.read(1024 * 1024)
            if not block:
                break
            total += len(block)
            if total > budget.max_bytes:
                raise full.small.Refused('Input exceeds explicit size budget')
            digest.update(block)
    return digest.hexdigest()


class _ReadOnlyJournal(OriginalDeletionJournal):
    """Bound full history inspection without granting any journal write path."""
    def __init__(self, path, namespace, budget):
        self.budget = budget
        self.selected_identity = full.small.identity(path)
        super().__init__(path, namespace)

    def _connect(self, *, validate=True):
        self.budget.check()
        if full.small.identity(self.path) != self.selected_identity:
            raise full.small.Refused('Journal replaced during review')
        if self.path.stat().st_size > min(self.budget.max_bytes, MAX_JOURNAL_BYTES):
            raise full.small.Refused('Journal exceeds bounded history profile')
        if validate:
            self._validate_file()
        db = sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True, timeout=3, isolation_level=None)
        try:
            db.row_factory = sqlite3.Row
            self.budget.configure(db)
            db.execute('PRAGMA query_only=ON')
            if (full.small.identity(self.path) != self.selected_identity
                    or db.execute('PRAGMA journal_mode').fetchone()[0] != 'delete'):
                raise full.small.Refused('Journal replaced or not offline')
            return db
        except BaseException:
            db.close()
            raise

    def _validate_record(self, record):
        self.budget.check()
        return super()._validate_record(record)


def _journal_format(journal, budget):
    path = journal.path
    db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=3)
    try:
        budget.configure(db)
        db.execute('PRAGMA query_only=ON')
        row = db.execute('SELECT format FROM journal_meta WHERE id=1').fetchone()
        if row is None or row[0] not in JOURNAL_FORMATS:
            raise full.small.Refused('Supported deletion journal format required')
        return row[0]
    except sqlite3.Error:
        raise full.small.Refused('Deletion journal format is invalid') from None
    finally:
        db.close()


def _review_history(path, journal, expected_head, budget):
    """Run the full chain and pending-source review on a fresh read-only primary."""
    before = full.small.identity(path)
    full.small.no_sidecars(path)
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=3,
                                 isolation_level=None)) as primary:
        budget.configure(primary)
        primary.execute('PRAGMA query_only=ON')
        if primary.execute('PRAGMA journal_mode').fetchone()[0].lower() != 'delete':
            raise full.small.Refused('Reviewed offline snapshot required')
        marker = journal._primary_marker(primary)
        if marker != expected_head[1:]:
            raise full.small.Refused('Primary deletion marker differs from expected journal head')
        try:
            review = journal.review(primary)
        except RuntimeError:
            raise full.small.Refused('Deletion history review failed') from None
        if ((review['sequence'], review['digest']) != expected_head[1:]
                or review['pending_count'] != 0):
            raise full.small.Refused('Deletion history is stale or has pending records')
        if full.small.identity(path) != before:
            raise full.small.Refused('Primary identity changed during history review')
        full.small.no_sidecars(path)
        return review


def _paths(database, backup, journal_path, journal_backup, budget):
    result = []
    for path, label in ((database, 'Primary'), (backup, 'Primary backup'),
                        (journal_path, 'Deletion journal'),
                        (journal_backup, 'Journal backup')):
        path = full.small.direct(Path(path))
        full.small.no_sidecars(path)
        try:
            require_private_file(path)
            identity = full.small.identity(path)
        except (OSError, ValueError, PermissionError):
            raise full.small.Refused(label + ' is unavailable or not private') from None
        if not path.is_file():
            raise full.small.Refused(label + ' must be a regular file')
        result.append((path, identity))
    if len({identity for _path, identity in result}) != 4:
        raise full.small.Refused('All four inputs must be separate files')
    for path, _identity in result:
        if path.stat().st_size > budget.max_bytes:
            raise full.small.Refused('Input exceeds explicit size budget')
    return tuple(result)


def _review(database, backup, journal_path, journal_backup, digest, namespace,
            expected_sequence, expected_digest, journal_sha256, budget, from_revision):
    if (type(digest) is not str or re.fullmatch(r'[0-9a-f]{64}', digest) is None
            or type(journal_sha256) is not str
            or re.fullmatch(r'[0-9a-f]{64}', journal_sha256) is None):
        raise full.small.Refused('Explicit canonical primary and journal hashes required')
    if (type(expected_sequence) is not int or expected_sequence < 0
            or type(expected_digest) is not str
            or re.fullmatch(r'[0-9a-f]{64}', expected_digest) is None):
        raise full.small.Refused('Explicit canonical journal head required')
    _additions(from_revision)
    paths = _paths(database, backup, journal_path, journal_backup, budget)
    (database, primary_identity), (backup, backup_identity), (journal_path, journal_identity), \
        (journal_backup, journal_backup_identity) = paths
    journal = _ReadOnlyJournal(journal_path, namespace, budget)
    expected_head = (journal.namespace, expected_sequence, expected_digest)
    if journal.head() != expected_head:
        raise full.small.Refused('Journal head differs from explicit expected values')
    journal_format = _journal_format(journal, budget)
    journal_hash = _digest_file(journal_path, budget)
    if journal_hash != journal_sha256 or _digest_file(journal_backup, budget) != journal_hash:
        raise full.small.Refused('Journal backup bytes differ from reviewed journal')
    if _journal_format(_ReadOnlyJournal(journal_backup, namespace, budget), budget) != journal_format:
        raise full.small.Refused('Journal backup format differs from reviewed journal')

    with full.read_source(database, budget, offline=True) as source:
        tables = _source(source, budget, from_revision)
        source_objects = _objects(source)
        if full.fingerprint(source, tables, budget)[0] != digest:
            raise full.small.Refused('Primary changed since review')
        with full.read_source(backup, budget, offline=True) as saved:
            if (_source(saved, budget, from_revision) != tables
                    or _objects(saved) != source_objects
                    or full.fingerprint(saved, tables, budget)[0] != digest):
                raise full.small.Refused('Primary backup differs from reviewed source')
    history = _review_history(database, journal, expected_head, budget)
    backup_history = _review_history(backup, journal, expected_head, budget)
    if history != backup_history:
        raise full.small.Refused('Primary backup deletion history differs')
    primary_backup_hash = _digest_file(backup, budget)
    identities = (primary_identity, backup_identity, journal_identity, journal_backup_identity)
    if (tuple(full.small.identity(path) for path, _identity in paths) != identities
            or _digest_file(journal_path, budget) != journal_hash
            or _digest_file(journal_backup, budget) != journal_hash):
        raise full.small.Refused('Reviewed input changed during review')
    return {
        'paths': paths, 'identities': identities, 'tables': tables,
        'objects': source_objects, 'primary_backup_sha256': primary_backup_hash,
        'journal': journal, 'journal_head': expected_head,
        'journal_format': journal_format, 'journal_sha256': journal_hash,
        'digest': digest, 'history': history,
    }


def _report(checked, from_revision, *, applied=False, counts=None,
            operational_quiescence_attested=False):
    return {
        'reviewed': True, 'applied': applied, 'source_revision': from_revision,
        'target_revision': TO_REVISION,
        'new_tables_created': len(_additions(from_revision)) if applied else 0,
        'new_tables_planned': len(_additions(from_revision)),
        'journal_format_version': JOURNAL_FORMATS[checked['journal_format']],
        'journal_format_upgrade_required': False,
        'photo_stack_history_ready': True,
        'family_note_erasure_format_ready': JOURNAL_FORMATS[checked['journal_format']] >= 2,
        'journal_upgrade_performed': False,
        'tables_preserved': len(counts) if counts is not None else None,
        'rows_preserved': sum(counts.values()) if counts is not None else None,
        'journal_unchanged': applied, 'primary_backup_unchanged': applied,
        'journal_backup_unchanged': applied,
        'operational_quiescence_attested': operational_quiescence_attested,
        'operational_quiescence_verified': False, 'backup_restored': False,
        'http_activated': False, 'worker_started': False,
    }


def review(database, backup, journal_path, journal_backup, digest, namespace,
           expected_sequence, expected_digest, journal_sha256, budget,
           *, from_revision=A0_REVISION):
    """Review four private files without writes; callable API defaults to review."""
    checked = _review(database, backup, journal_path, journal_backup, digest,
                      namespace, expected_sequence, expected_digest,
                      journal_sha256, budget, from_revision)
    return _report(checked, from_revision)


def apply(database, backup, journal_path, journal_backup, digest, namespace,
          expected_sequence, expected_digest, journal_sha256, budget, *,
          execute=False, all_writers_stopped=False, from_revision=A0_REVISION):
    """Review by default; execute only with an explicit stopped-writer attestation."""
    if type(execute) is not bool or type(all_writers_stopped) is not bool:
        raise full.small.Refused('Explicit operation choices required')
    if execute and not all_writers_stopped:
        raise full.small.Refused('Independent all-writer shutdown confirmation required')
    if not execute and all_writers_stopped:
        raise full.small.Refused('--all-writers-stopped requires execute=True')
    checked = _review(database, backup, journal_path, journal_backup, digest,
                      namespace, expected_sequence, expected_digest,
                      journal_sha256, budget, from_revision)
    if not execute:
        return _report(checked, from_revision)

    additions = frozenset(_additions(from_revision))
    expected_addition = _expected_addition(from_revision)
    if ({row[2] for row in expected_addition if row[0] == 'table'} != additions
            or set(STACK_TABLES) != set(additions) & set(STACK_TABLES)):
        raise full.small.Refused('Unexpected photo-stack metadata closure')

    from alembic import command
    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool

    (database, identity), (backup_path, backup_identity), (journal_path, journal_identity), \
        (journal_backup_path, journal_backup_identity) = checked['paths']
    journal = checked['journal']
    expected_head = checked['journal_head']
    journal_hash = checked['journal_sha256']
    primary_backup_hash = checked['primary_backup_sha256']

    def connect():
        for path, expected in ((database, identity), (backup_path, backup_identity),
                               (journal_path, journal_identity),
                               (journal_backup_path, journal_backup_identity)):
            require_private_file(path)
            full.small.no_sidecars(path)
            if full.small.identity(path) != expected:
                raise full.small.Refused('Reviewed input replaced')
        db = sqlite3.connect(database.as_uri() + '?mode=rw', uri=True, timeout=3)
        try:
            budget.configure(db)
            db.execute('PRAGMA synchronous=FULL')
            if db.execute('PRAGMA journal_mode').fetchone()[0].lower() != 'delete':
                raise full.small.Refused('Offline DELETE journal required')
            return db
        except BaseException:
            db.close()
            raise

    engine = create_engine('sqlite://', creator=connect, poolclass=NullPool)
    try:
        with engine.connect() as connection:
            driver = connection.connection.driver_connection
            connection.exec_driver_sql('BEGIN EXCLUSIVE')
            try:
                tables = _source(driver, budget, from_revision)
                if (_objects(driver) != checked['objects']
                        or full.fingerprint(driver, tables, budget)[0] != digest):
                    raise full.small.Refused('Target changed after review')
                marker = journal._primary_marker(driver)
                if marker != expected_head[1:]:
                    raise full.small.Refused('Primary deletion marker changed')
                if (journal.head() != expected_head
                        or _journal_format(journal, budget) != checked['journal_format']
                        or _digest_file(journal_path, budget) != journal_hash
                        or _digest_file(journal_backup_path, budget) != journal_hash
                        or _digest_file(backup_path, budget) != primary_backup_hash):
                    raise full.small.Refused('Reviewed backup or journal changed')
                with full.read_source(backup_path, budget, offline=True) as saved:
                    if (_source(saved, budget, from_revision) != tables
                            or _objects(saved) != checked['objects']
                            or full.fingerprint(saved, tables, budget)[0] != digest):
                        raise full.small.Refused('Primary backup changed after review')
                backup_history = _review_history(backup_path, journal, expected_head, budget)
                if backup_history != checked['history']:
                    raise full.small.Refused('Deletion history changed after review')

                preserved = {name: columns for name, columns in tables.items()
                             if name != 'alembic_version'}
                before_rows, counts = full.fingerprint(driver, preserved, budget)
                config = full.small.migration_config()
                config.attributes['connection'] = connection
                command.upgrade(config, TO_REVISION)

                after_tables = full.schema(driver)
                if (not driver.in_transaction or full.validate(driver, budget) != TO_REVISION
                        or set(after_tables) != set(tables) | additions
                        or any(after_tables.get(name) != columns for name, columns in tables.items())
                        or not stack_available(driver)
                        or _objects(driver) != checked['objects'] | expected_addition):
                    raise full.small.Refused('Incomplete or unexpected transactional migration')
                if full.fingerprint(driver, preserved, budget)[0] != before_rows:
                    raise full.small.Refused('Existing data changed')
                if any(driver.execute('SELECT 1 FROM ' + full.quoted(name) + ' LIMIT 1').fetchone()
                       for name in additions):
                    raise full.small.Refused('Unexpected migration backfill')
                if journal._primary_marker(driver) != expected_head[1:]:
                    raise full.small.Refused('Migration changed primary deletion history')
                if (journal.head() != expected_head
                        or _journal_format(journal, budget) != checked['journal_format']
                        or _digest_file(journal_path, budget) != journal_hash
                        or _digest_file(journal_backup_path, budget) != journal_hash
                        or _digest_file(backup_path, budget) != primary_backup_hash):
                    raise full.small.Refused('Journal or backup changed during migration')
                if _review_history(backup_path, journal, expected_head, budget) != checked['history']:
                    raise full.small.Refused('Deletion history changed during migration')
                for path, expected in ((database, identity), (backup_path, backup_identity),
                                       (journal_path, journal_identity),
                                       (journal_backup_path, journal_backup_identity)):
                    require_private_file(path)
                    if full.small.identity(path) != expected:
                        raise full.small.Refused('Reviewed input replaced before commit')
                    if path != database:
                        full.small.no_sidecars(path)
                    elif any(Path(str(path) + suffix).exists() for suffix in ('-wal', '-shm')):
                        raise full.small.Refused('Unexpected primary WAL state')
                    # The transaction owns the primary's DELETE rollback
                    # journal. Other files must remain sidecar-free.
                budget.check()
                connection.commit()
            except BaseException:
                driver.set_progress_handler(None, 0)
                connection.rollback()
                raise
    finally:
        engine.dispose()

    report = _report(checked, from_revision, applied=True, counts=counts,
                     operational_quiescence_attested=True)
    report['revision'] = TO_REVISION
    report['new_rows_created'] = 0
    return report
