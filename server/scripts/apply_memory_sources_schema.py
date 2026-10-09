#!/usr/bin/env python3
"""Apply the reviewed e6 -> a0 saved-memory collaboration and source schema.

Read-only review by default. Execution requires a verified separate backup and
an explicit all-writers-stopped assertion. This does not stop services, install
source, enable application flags, start a worker, or activate an HTTP API.
"""
import json
from pathlib import Path
import re
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import apply_access_schema as historical
import apply_memory_collaboration_schema as collaboration

full = historical.full
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from sqlalchemy import Column, Integer, MetaData, Table, Text
from sqlalchemy.dialects.sqlite import dialect
from sqlalchemy.schema import CreateTable
from app.access.memory_source_refs import TABLE, add_source_ref_table

FROM_REVISION = 'e6b2f8a1c903'
TO_REVISION = 'a0c9d2e4f817'
NEW_TABLES = tuple(collaboration.NEW_TABLES) + (TABLE,)
NEW_INDEXES = tuple(index.name for table in collaboration.EXPECTED.values()
                    for index in table.indexes) + ('ix_memory_contribution_refs_source',)


def _expected_table():
    metadata = MetaData()
    Table('access_memory_revisions', metadata,
          Column('story_id', Text, primary_key=True),
          Column('revision', Integer, primary_key=True))
    Table('access_memory_contributions', metadata,
          Column('id', Text, primary_key=True))
    return add_source_ref_table(metadata)


EXPECTED = _expected_table()


def _source(db, budget):
    # The requested source is e6. This validator rejects both partial f7 and
    # partial a0 states, so retries cannot replay either migration halfway.
    tables = collaboration._source(db, budget)
    if TABLE in tables:
        raise full.small.Refused('Unexpected partial contribution reference schema')
    return tables


def review(database, backup, digest, budget):
    if not re.fullmatch('[0-9a-f]{64}', digest):
        raise full.small.Refused('Exact reviewed backup digest required')
    identity = full.small.identity(database)
    backup_identity = full.small.identity(backup)
    if identity == backup_identity or database == backup:
        raise full.small.Refused('Separate backup required')
    with full.read_source(database, budget, offline=True) as source:
        tables = _source(source, budget)
        if full.fingerprint(source, tables, budget)[0] != digest:
            raise full.small.Refused('Source changed since backup')
        with full.read_source(backup, budget, offline=True) as saved:
            if (_source(saved, budget) != tables
                    or full.fingerprint(saved, tables, budget)[0] != digest):
                raise full.small.Refused('Reviewed backup mismatch')
    return identity, backup_identity


def _normalize_sql(sql):
    return re.sub(r'\s+', ' ', sql.replace('"', '').replace('`', '').strip().rstrip(';')).casefold()


def _schema_objects(db):
    return {(kind, name, table, sql) for kind, name, table, sql in db.execute(
        "SELECT type,name,tbl_name,sql FROM sqlite_master "
        "WHERE type IN ('table','index','view','trigger') AND name NOT LIKE 'sqlite_%'")}


def _target(db, budget, old_table_names):
    if full.validate(db, budget) != TO_REVISION:
        raise full.small.Refused('Incomplete a0 migration')
    tables = full.schema(db)
    if set(tables) != set(old_table_names) | set(NEW_TABLES):
        raise full.small.Refused('Unexpected a0 table set')
    expected_indexes = {}
    for expected_table in collaboration.EXPECTED.values():
        actual = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                            (expected_table.name,)).fetchone()
        compiled = str(CreateTable(expected_table).compile(dialect=dialect()))
        if (tuple(tables[expected_table.name]) != tuple(column.name for column in expected_table.columns)
                or not actual or _normalize_sql(actual[0]) != _normalize_sql(compiled)):
            raise full.small.Refused('Unexpected collaboration table metadata')
        if db.execute('SELECT 1 FROM ' + full.quoted(expected_table.name) + ' LIMIT 1').fetchone():
            raise full.small.Refused('Unexpected collaboration row')
        expected_indexes[expected_table.name] = {
            index.name: (tuple(column.name for column in index.columns), bool(index.unique))
            for index in expected_table.indexes
        }
    for table_name, wanted in expected_indexes.items():
        actual_indexes = {}
        for _seq, name, unique, origin, _partial in db.execute(
                'PRAGMA index_list(' + full.quoted(table_name) + ')'):
            columns = tuple(row[2] for row in db.execute('PRAGMA index_info(' + full.quoted(name) + ')'))
            if origin == 'c':
                actual_indexes[name] = (columns, bool(unique))
        if actual_indexes != wanted:
            raise full.small.Refused('Unexpected collaboration indexes')
    actual = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (TABLE,)).fetchone()
    compiled = str(CreateTable(EXPECTED).compile(dialect=dialect()))
    if (tuple(tables[TABLE]) != tuple(column.name for column in EXPECTED.columns)
            or not actual or _normalize_sql(actual[0]) != _normalize_sql(compiled)):
        raise full.small.Refused('Unexpected contribution reference table metadata')
    if db.execute('SELECT 1 FROM ' + full.quoted(TABLE) + ' LIMIT 1').fetchone():
        raise full.small.Refused('Unexpected contribution reference row')
    expected_indexes = {index.name: (tuple(column.name for column in index.columns), bool(index.unique))
                        for index in EXPECTED.indexes}
    actual_indexes = {}
    for _seq, name, unique, origin, _partial in db.execute('PRAGMA index_list(' + full.quoted(TABLE) + ')'):
        columns = tuple(row[2] for row in db.execute('PRAGMA index_info(' + full.quoted(name) + ')'))
        if origin == 'c':
            actual_indexes[name] = (columns, bool(unique))
    if actual_indexes != expected_indexes:
        raise full.small.Refused('Unexpected contribution reference indexes')
    expected_fks = {
        ('access_memory_revisions', 'story_id', 'story_id', 'CASCADE'),
        ('access_memory_revisions', 'revision', 'revision', 'CASCADE'),
        ('access_memory_contributions', 'contribution_id', 'id', 'CASCADE'),
    }
    actual_fks = {(row[2], row[3], row[4], row[6]) for row in db.execute(
        'PRAGMA foreign_key_list(' + full.quoted(TABLE) + ')')}
    if actual_fks != expected_fks:
        raise full.small.Refused('Unexpected contribution reference foreign keys')
    if db.execute('PRAGMA foreign_key_check').fetchone() is not None:
        raise full.small.Refused('Contribution reference foreign-key verification failed')
    if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
        raise full.small.Refused('Contribution reference integrity verification failed')


def apply(database, backup, digest, budget, *, execute=False, all_writers_stopped=False):
    if execute and not all_writers_stopped:
        raise full.small.Refused('Independent all-writer shutdown confirmation required')
    identity, backup_identity = review(database, backup, digest, budget)
    if not execute:
        return {'reviewed': True, 'applied': False, 'source_revision': FROM_REVISION,
                'target_revision': TO_REVISION, 'operational_quiescence_verified': False}
    from alembic import command
    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool

    def connect():
        full.small.no_sidecars(database)
        if full.small.identity(database) != identity:
            raise full.small.Refused('Target replaced')
        db = sqlite3.connect(database.as_uri() + '?mode=rw', uri=True, timeout=3)
        budget.configure(db)
        db.execute('PRAGMA synchronous=FULL')
        if db.execute('PRAGMA journal_mode').fetchone()[0] != 'delete':
            db.close()
            raise full.small.Refused('Offline DELETE journal required')
        return db

    engine = create_engine('sqlite://', creator=connect, poolclass=NullPool)
    try:
        with engine.connect() as connection:
            driver = connection.connection.driver_connection
            connection.exec_driver_sql('BEGIN EXCLUSIVE')
            try:
                tables = _source(driver, budget)
                if full.fingerprint(driver, tables, budget)[0] != digest:
                    raise full.small.Refused('Target changed after review')
                with full.read_source(backup, budget, offline=True) as saved:
                    if (full.small.identity(backup) != backup_identity
                            or _source(saved, budget) != tables
                            or full.fingerprint(saved, tables, budget)[0] != digest):
                        raise full.small.Refused('Backup changed after review')
                preserved = {name: columns for name, columns in tables.items()
                             if name != 'alembic_version'}
                expected_fingerprint, counts = full.fingerprint(driver, preserved, budget)
                old_objects = _schema_objects(driver)
                config = full.small.migration_config()
                config.attributes['connection'] = connection
                command.upgrade(config, TO_REVISION)
                if not driver.in_transaction:
                    raise full.small.Refused('Migration escaped exclusive transaction')
                _target(driver, budget, set(tables))
                if full.fingerprint(driver, preserved, budget)[0] != expected_fingerprint:
                    raise full.small.Refused('Existing data changed')
                new_objects = _schema_objects(driver)
                expected_new = {obj for obj in new_objects - old_objects
                                if obj[1] in set(NEW_TABLES + NEW_INDEXES)}
                if (not old_objects <= new_objects
                        or new_objects - old_objects != expected_new
                        or {obj[1] for obj in expected_new} != set(NEW_TABLES + NEW_INDEXES)):
                    raise full.small.Refused('Existing schema changed or unexpected schema object added')
                if (full.small.identity(database) != identity
                        or full.small.identity(backup) != backup_identity):
                    raise full.small.Refused('Reviewed files replaced')
                budget.check()
                connection.commit()
            except BaseException:
                driver.set_progress_handler(None, 0)
                connection.rollback()
                raise
    finally:
        engine.dispose()
    full.small.no_sidecars(database)
    return {'reviewed': True, 'applied': True, 'revision': TO_REVISION,
            'tables_preserved': len(counts), 'rows_preserved': sum(counts.values()),
            'new_tables_created': len(NEW_TABLES), 'new_rows_created': 0,
            'http_activated': False, 'feature_flags_enabled': False}


def main(argv=None):
    parser = full.small.Parser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--backup', type=Path, required=True)
    parser.add_argument('--reviewed-backup-digest', required=True)
    parser.add_argument('--max-bytes', type=int, required=True)
    parser.add_argument('--timeout-seconds', type=int, required=True)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--all-writers-stopped', action='store_true')
    try:
        args = parser.parse_args(argv)
        result = apply(args.database, args.backup, args.reviewed_backup_digest,
                       full.Budget(args.max_bytes, args.timeout_seconds),
                       execute=args.execute, all_writers_stopped=args.all_writers_stopped)
        print(json.dumps(result, sort_keys=True))
        return 0
    except KeyboardInterrupt:
        print('Migration interrupted; inspect schema and controller receipt before retrying.', file=sys.stderr)
        return 130
    except Exception:
        print('Migration refused or incomplete; inspect schema and controller receipt before retrying.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
