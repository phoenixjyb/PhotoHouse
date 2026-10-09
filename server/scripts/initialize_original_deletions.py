#!/usr/bin/env python3
"""Review or explicitly bind an external deletion journal to an offline collaboration primary.

Review is read-only. Execution creates a new journal exclusively and binds it
only after a locked recheck of an identical separate backup. It never stops a
writer, changes feature flags, starts a worker or activates a service.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'scripts'))

import apply_memory_collaboration_schema as schema_check  # noqa: E402
import rehearse_fullsize_database as full  # noqa: E402
from app.access.original_deletions import OriginalDeletionJournal  # noqa: E402
from app.access.private_storage import require_private_directory  # noqa: E402
from app.access.memory_book_edition_schema import (  # noqa: E402
    EDITION_REVISION,
    EDITION_TABLE,
    SOURCES_TABLE,
)

from app.access.runtime import (REQUIRED_REVISION, COLLABORATION_REVISIONS,
                                SOURCE_REFERENCE_REVISIONS)

REVISION = REQUIRED_REVISION


def _citation_schema():
    from sqlalchemy import Column, Integer, MetaData, Table, Text
    from app.access.memory_source_refs import add_source_ref_table
    metadata = MetaData()
    Table('access_memory_revisions', metadata, Column('story_id', Text, primary_key=True),
          Column('revision', Integer, primary_key=True))
    Table('access_memory_contributions', metadata, Column('id', Text, primary_key=True))
    table = add_source_ref_table(metadata)
    return {table.name: table}


def _edition_schema():
    from app.access.memory_book_edition_schema import add_book_edition_tables
    from app.access.metadata import migration_metadata
    from app.db import Base

    metadata = migration_metadata(Base.metadata)
    editions, sources = add_book_edition_tables(metadata)
    return {table.name: table for table in (editions, sources)}



def _namespace(value):
    try:
        if type(value) is not str or str(uuid.UUID(value)) != value:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise full.small.Refused('Canonical journal namespace required') from None
    return value


def _journal_target(path):
    full.small.direct(path)
    require_private_directory(path.parent)
    if os.path.lexists(path):
        raise full.small.Refused('Journal target must not exist')
    full.small.no_sidecars(path)
    return path


def _database_state(db, budget):
    revision = full.validate(db, budget)
    if revision not in COLLABORATION_REVISIONS:
        raise full.small.Refused('Supported collaboration schema required')
    tables = full.schema(db)
    expected_tables = dict(schema_check.EXPECTED)
    if revision in SOURCE_REFERENCE_REVISIONS:
        expected_tables.update(_citation_schema())
    edition_tables = {}
    if revision == EDITION_REVISION:
        edition_tables = _edition_schema()
        expected_tables.update(edition_tables)
    if not set(expected_tables) <= set(tables):
        raise full.small.Refused('Complete collaboration schema required')
    if revision == EDITION_REVISION:
        from app.access.memory_book_edition_deletions import (
            EditionDeletionError, verify_edition_schema,
        )
        from app.access.memory_book_edition_schema import sqlite_edition_schema_contract
        try:
            verify_edition_schema(db)
        except (EditionDeletionError, sqlite3.Error, ValueError):
            raise full.small.Refused('Unexpected memoir edition schema') from None
        actual_edition_triggers = {row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name IN (?,?)",
            (EDITION_TABLE, SOURCES_TABLE))}
        expected_edition_triggers = {
            name for kind, name, _sql in sqlite_edition_schema_contract() if kind == 'trigger'
        }
        if actual_edition_triggers != expected_edition_triggers:
            raise full.small.Refused('Unexpected memoir edition trigger metadata')
    expected_indexes = {}
    for name, expected in expected_tables.items():
        actual = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                            (name,)).fetchone()
        compiled = str(schema_check.CreateTable(expected).compile(
            dialect=schema_check.dialect()))
        if (tuple(tables[name]) != tuple(column.name for column in expected.columns)
                or not actual or schema_check._normalize_sql(actual[0]) !=
                schema_check._normalize_sql(compiled)):
            raise full.small.Refused('Unexpected collaboration table metadata')
        expected_indexes[name] = {
            index.name: (tuple(column.name for column in index.columns), bool(index.unique))
            for index in expected.indexes
        }
    for table_name, wanted in expected_indexes.items():
        actual = {}
        for _seq, name, unique, origin, _partial in db.execute(
                'PRAGMA index_list(' + full.quoted(table_name) + ')'):
            columns = tuple(row[2] for row in db.execute(
                'PRAGMA index_info(' + full.quoted(name) + ')'))
            if origin == 'c':
                actual[name] = (columns, bool(unique))
        if actual != wanted:
            raise full.small.Refused('Unexpected collaboration index metadata')
    tables_without_edition = tuple(name for name in expected_tables
                                   if name not in {EDITION_TABLE, SOURCES_TABLE})
    if tables_without_edition and db.execute("SELECT 1 FROM sqlite_master WHERE type='trigger' "
                   "AND tbl_name IN (" + ','.join('?' for _ in tables_without_edition) + ") LIMIT 1",
                   tables_without_edition).fetchone():
        raise full.small.Refused('Unexpected collaboration trigger metadata')
    originals = {}
    for table in ('access_upload_annotations', 'access_memory_contributions'):
        originals[table] = db.execute('SELECT count(*) FROM ' + full.quoted(table)).fetchone()[0]
    marker_rows = db.execute('SELECT count(*) FROM access_original_deletion_state').fetchone()[0]
    edition_rows = 0
    if revision == EDITION_REVISION:
        edition_rows = sum(db.execute('SELECT count(*) FROM ' + full.quoted(table)).fetchone()[0]
                           for table in (EDITION_TABLE, SOURCES_TABLE))
    fingerprint, counts = full.fingerprint(db, tables, budget)
    return {'revision': revision, 'tables': tables, 'fingerprint': fingerprint, 'counts': counts,
            'originals': originals, 'marker_rows': marker_rows,
            'edition_rows': edition_rows}


def _read_state(path, budget):
    with full.read_source(path, budget, offline=True) as db:
        return _database_state(db, budget)


def _review(database, backup, journal_path, namespace, budget):
    namespace = _namespace(namespace)
    database, backup = full.small.direct(database), full.small.direct(backup)
    journal_path = _journal_target(journal_path)
    full.small.no_sidecars(database)
    full.small.no_sidecars(backup)
    primary_identity = full.small.identity(database)
    backup_identity = full.small.identity(backup)
    if primary_identity == backup_identity:
        raise full.small.Refused('Primary and backup must be separate files')

    primary = _read_state(database, budget)
    saved = _read_state(backup, budget)
    if (primary['tables'] != saved['tables'] or
            primary['fingerprint'] != saved['fingerprint']):
        raise full.small.Refused('Primary and rollback backup must match')
    if any(primary['originals'].values()):
        raise full.small.Refused('Original tables must be empty before binding')
    if primary['edition_rows']:
        raise full.small.Refused('Reviewed memoir editions must be empty before binding')
    if primary['marker_rows']:
        raise full.small.Refused('Primary deletion marker must be empty')
    return {'database': database, 'backup': backup, 'journal': journal_path,
            'namespace': namespace, 'revision': primary['revision'], 'primary_identity': primary_identity,
            'backup_identity': backup_identity, 'tables': primary['tables'],
            'fingerprint': primary['fingerprint'], 'counts': primary['counts'],
            'originals': primary['originals'], 'marker_rows': primary['marker_rows']}


def _public_plan(reviewed, *, status, journal_sequence=None, journal_digest=None,
                 marker_rows=None):
    return {'status': status, 'schema_revision': reviewed['revision'],
            'table_count': len(reviewed['tables']),
            'primary_rows': sum(reviewed['counts'].values()),
            'original_rows': sum(reviewed['originals'].values()),
            'marker_rows': reviewed['marker_rows'] if marker_rows is None else marker_rows,
            'logical_fingerprint': reviewed['fingerprint'],
            'journal_sequence': journal_sequence,
            'journal_digest': journal_digest}


def initialize(database, backup, journal_path, namespace, budget, *,
               execute=False, all_writers_stopped=False, state=None):
    if execute and not all_writers_stopped:
        raise full.small.Refused('Execution requires --all-writers-stopped')
    if not execute and all_writers_stopped:
        raise full.small.Refused('--all-writers-stopped requires --execute')
    reviewed = _review(database, backup, journal_path, namespace, budget)
    if not execute:
        return _public_plan(reviewed, status='reviewed')

    state = state if state is not None else {}
    journal = OriginalDeletionJournal.initialize(reviewed['journal'], reviewed['namespace'])
    state['journal'] = journal
    state['reviewed'] = reviewed
    journal_identity = full.small.identity(reviewed['journal'])
    initial_head = journal.head()
    state['journal_head'] = initial_head

    full.small.no_sidecars(reviewed['database'])
    full.small.no_sidecars(reviewed['backup'])
    if (full.small.identity(reviewed['database']) != reviewed['primary_identity'] or
            full.small.identity(reviewed['backup']) != reviewed['backup_identity']):
        raise full.small.Refused('Reviewed file identity changed before binding')
    uri = reviewed['database'].as_uri() + '?mode=rw'
    db = sqlite3.connect(uri, uri=True, timeout=10, isolation_level=None)
    try:
        budget.configure(db)
        db.execute('PRAGMA synchronous=FULL')
        if (db.execute('PRAGMA foreign_keys').fetchone()[0] != 1 or
                db.execute('PRAGMA synchronous').fetchone()[0] != 2 or
                db.execute('PRAGMA journal_mode').fetchone()[0].lower() != 'delete'):
            raise full.small.Refused('Offline primary settings changed')

        def locked_recheck(primary_db):
            if not primary_db.in_transaction:
                raise full.small.Refused('Primary write lock is required')
            if (full.small.identity(reviewed['database']) != reviewed['primary_identity'] or
                    full.small.identity(reviewed['backup']) != reviewed['backup_identity'] or
                    full.small.identity(reviewed['journal']) != journal_identity):
                raise full.small.Refused('Reviewed file identity changed')
            current = _database_state(primary_db, budget)
            if (current['tables'] != reviewed['tables'] or
                    current['fingerprint'] != reviewed['fingerprint'] or
                    current['marker_rows'] != 0 or current['edition_rows'] != 0 or
                    any(current['originals'].values())):
                raise full.small.Refused('Locked primary changed after review')
            saved = _read_state(reviewed['backup'], budget)
            if (saved['tables'] != reviewed['tables'] or
                    saved['fingerprint'] != reviewed['fingerprint'] or
                    saved['edition_rows'] != 0):
                raise full.small.Refused('Rollback backup changed after review')
            if journal.head() != initial_head:
                raise full.small.Refused('New journal changed after initialization')
            if (full.small.identity(reviewed['database']) != reviewed['primary_identity'] or
                    full.small.identity(reviewed['backup']) != reviewed['backup_identity'] or
                    full.small.identity(reviewed['journal']) != journal_identity):
                raise full.small.Refused('Reviewed file identity changed during recheck')

        journal.bind(db, precommit_guard=locked_recheck)
        state['bound'] = True
        full.small.no_sidecars(reviewed['database'])
        if (full.small.identity(reviewed['database']) != reviewed['primary_identity'] or
                full.small.identity(reviewed['backup']) != reviewed['backup_identity'] or
                full.small.identity(reviewed['journal']) != journal_identity):
            raise full.small.Refused('Bound file identity changed')
        journal.assert_current(db)
        marker = db.execute('''SELECT namespace,applied_seq,applied_digest
            FROM access_original_deletion_state WHERE id=1''').fetchone()
        head = journal.head()
        if marker is None or tuple(marker) != (reviewed['namespace'], head[1], head[2]):
            raise full.small.Refused('Bound marker verification failed')
        result = _public_plan(reviewed, status='bound', journal_sequence=head[1],
                              journal_digest=head[2], marker_rows=1)
        state['result'] = result
        return result
    finally:
        db.close()


def _parser():
    parser = full.small.Parser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--backup', type=Path, required=True,
                        help='separate identical collaboration rollback copy')
    parser.add_argument('--journal', type=Path, required=True,
                        help='new journal target in an existing private directory')
    parser.add_argument('--namespace', required=True,
                        help='operator-reviewed canonical dataset UUID')
    parser.add_argument('--max-bytes', type=int, default=1024 * 1024 * 1024)
    parser.add_argument('--timeout-seconds', type=int, default=300)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--all-writers-stopped', action='store_true')
    return parser


def main(argv=None):
    parser = _parser()
    state = {}
    try:
        args = parser.parse_args(argv)
        result = initialize(args.database, args.backup, args.journal, args.namespace,
            full.Budget(args.max_bytes, args.timeout_seconds), execute=args.execute,
            all_writers_stopped=args.all_writers_stopped, state=state)
        print(json.dumps(result, sort_keys=True))
        return 0
    except KeyboardInterrupt:
        report = state.get('result') or _failure_report(state)
        print(json.dumps(report, sort_keys=True))
        print('Original-deletion initialization interrupted; preserve all inputs.', file=sys.stderr)
        return 130
    except Exception:
        report = _failure_report(state)
        print(json.dumps(report, sort_keys=True))
        if state.get('journal') is not None and not state.get('bound'):
            print('Binding failed; preserve the newly created empty journal for review.', file=sys.stderr)
        elif state.get('bound'):
            print('Binding completed but final verification failed; preserve all files and review offline.', file=sys.stderr)
        else:
            print('Original-deletion initialization refused; no paths or source data are reported.', file=sys.stderr)
        return 2


def _failure_report(state):
    reviewed = state.get('reviewed')
    journal = state.get('journal')
    if reviewed is None:
        return {'status': 'refused'}
    if journal is None:
        return _public_plan(reviewed, status='refused')
    try:
        _namespace(journal.namespace)
        namespace, sequence, digest = journal.head()
    except Exception:
        namespace, sequence, digest = journal.namespace, None, None
    return _public_plan(reviewed,
        status='bound_verification_incomplete' if state.get('bound') else 'journal_created_unbound',
        journal_sequence=sequence, journal_digest=digest,
        marker_rows=1 if state.get('bound') else 0)


if __name__ == '__main__':
    raise SystemExit(main())
