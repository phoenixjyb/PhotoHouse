#!/usr/bin/env python3
"""Apply the reviewed a0 -> b1 memoir editorial schema to one offline DB.

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
import apply_memory_collaboration_schema as collaboration
import apply_memory_sources_schema as sources

full = sources.full
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from sqlalchemy import Column, Integer, MetaData, Table, Text
from sqlalchemy.dialects.sqlite import dialect
from sqlalchemy.schema import CreateTable
from app.access.memory_book_editorial_schema import (
    BOOK_TABLE, REFS_TABLE, add_book_editorial_tables)
from app.access.memory_source_refs import add_source_ref_table

FROM_REVISION = 'a0c9d2e4f817'
TO_REVISION = 'b1d7e4a9c230'
NEW_TABLES = (BOOK_TABLE, REFS_TABLE)


def _prerequisite_metadata():
    metadata = MetaData()
    Table('access_accounts', metadata, Column('id', Text, primary_key=True))
    Table('access_libraries', metadata, Column('id', Text, primary_key=True))
    Table('access_memory_stories', metadata, Column('id', Text, primary_key=True))
    collaboration.add_collaboration_tables(metadata)
    Table('access_memory_revisions', metadata,
          Column('story_id', Text, primary_key=True),
          Column('revision', Integer, primary_key=True))
    add_source_ref_table(metadata)
    return metadata


PREREQUISITES = _prerequisite_metadata()


def _expected_editorial_objects():
    """Render the authoritative model builder into a private in-memory schema.

    This captures its tables, indexes and DDL event triggers directly, so the
    operator has no second hand-maintained trigger contract.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool

    metadata = MetaData()
    Table('access_memory_book_revisions', metadata,
          Column('book_id', Text, primary_key=True),
          Column('revision', Integer, primary_key=True))
    Table('access_memory_revisions', metadata,
          Column('story_id', Text, primary_key=True),
          Column('revision', Integer, primary_key=True))
    Table('access_memory_contributions', metadata,
          Column('id', Text, primary_key=True))
    editorial, refs = add_book_editorial_tables(metadata)
    engine = create_engine('sqlite://', poolclass=StaticPool)
    try:
        with engine.begin() as connection:
            editorial.create(connection)
            refs.create(connection)
            rows = connection.exec_driver_sql(
                "SELECT type,name,tbl_name,sql FROM sqlite_master "
                "WHERE type IN ('table','index','trigger') "
                "AND name NOT LIKE 'sqlite_%'").all()
            return {(kind, name, table, sql) for kind, name, table, sql in rows}
    finally:
        engine.dispose()


EDITORIAL_OBJECTS = _expected_editorial_objects()
EDITORIAL_INDEXES = frozenset(name for kind, name, _table, _sql in EDITORIAL_OBJECTS
                              if kind == 'index')
EDITORIAL_TRIGGERS = frozenset(name for kind, name, _table, _sql in EDITORIAL_OBJECTS
                               if kind == 'trigger')
if ({name for kind, name, _table, _sql in EDITORIAL_OBJECTS if kind == 'table'} != set(NEW_TABLES)
        or len(EDITORIAL_INDEXES) != 2 or len(EDITORIAL_TRIGGERS) != 2):
    raise full.small.Refused('Unexpected editorial model object count')


def _normalize_sql(sql):
    """Normalize formatting outside literals while preserving literal bytes."""
    source = sql.strip()
    normalized = []
    in_literal = False
    pending_space = False
    index = 0
    while index < len(source):
        char = source[index]
        if in_literal:
            normalized.append(char)
            if char == "'":
                if index + 1 < len(source) and source[index + 1] == "'":
                    normalized.append("'")
                    index += 1
                else:
                    in_literal = False
        elif char == "'":
            if pending_space and normalized:
                normalized.append(' ')
            pending_space = False
            normalized.append(char)
            in_literal = True
        elif char in ('"', '`'):
            # SQLite identifier quoting is immaterial to this model comparison.
            index += 1
            continue
        elif char.isspace():
            pending_space = True
        else:
            if pending_space and normalized:
                normalized.append(' ')
            pending_space = False
            normalized.append(char.casefold())
        index += 1
    result = ''.join(normalized).rstrip()
    if result.endswith(';'):
        result = result[:-1].rstrip()
    return result


def _schema_objects(db):
    return {(kind, name, table, sql) for kind, name, table, sql in db.execute(
        "SELECT type,name,tbl_name,sql FROM sqlite_master "
        "WHERE type IN ('table','index','view','trigger') AND name NOT LIKE 'sqlite_%'")}


def _actual_indexes(db, table_name):
    actual = {}
    for _seq, name, unique, origin, _partial in db.execute(
            'PRAGMA index_list(' + full.quoted(table_name) + ')'):
        if origin == 'c':
            columns = tuple(row[2] for row in db.execute(
                'PRAGMA index_info(' + full.quoted(name) + ')'))
            row = db.execute("SELECT sql FROM sqlite_master WHERE type='index' AND name=?",
                             (name,)).fetchone()
            actual[name] = (columns, bool(unique), _normalize_sql(row[0]) if row else None)
    return actual


def _foreign_key_contracts_from_metadata(table):
    contracts = []
    for constraint in table.foreign_key_constraints:
        elements = list(constraint.elements)
        contracts.append((constraint.referred_table.name,
                          tuple(element.parent.name for element in elements),
                          tuple(element.column.name for element in elements),
                          (constraint.ondelete or 'NO ACTION').upper()))
    return sorted(contracts)


def _foreign_key_contracts_from_db(db, table_name):
    grouped = {}
    for row in db.execute('PRAGMA foreign_key_list(' + full.quoted(table_name) + ')'):
        ident, seq, table, local, remote, _update, ondelete, _match = row
        grouped.setdefault(ident, {'table': table, 'local': [], 'remote': [], 'delete': ondelete})
        grouped[ident]['local'].append((seq, local))
        grouped[ident]['remote'].append((seq, remote))
    result = []
    for item in grouped.values():
        result.append((item['table'], tuple(value for _seq, value in sorted(item['local'])),
                       tuple(value for _seq, value in sorted(item['remote'])),
                       item['delete'].upper()))
    return sorted(result)


def _validate_table_contract(db, expected, label):
    tables = full.schema(db)
    actual = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                        (expected.name,)).fetchone()
    compiled = str(CreateTable(expected).compile(dialect=dialect()))
    if (tuple(tables.get(expected.name, ())) != tuple(column.name for column in expected.columns)
            or not actual or _normalize_sql(actual[0]) != _normalize_sql(compiled)):
        raise full.small.Refused('Unexpected ' + label + ' table metadata')
    wanted_indexes = {index.name: (tuple(column.name for column in index.columns), bool(index.unique))
                      for index in expected.indexes}
    actual_indexes = {name: (columns, unique) for name, (columns, unique, _sql)
                      in _actual_indexes(db, expected.name).items()}
    if actual_indexes != wanted_indexes:
        raise full.small.Refused('Unexpected ' + label + ' indexes')
    if _foreign_key_contracts_from_db(db, expected.name) != _foreign_key_contracts_from_metadata(expected):
        raise full.small.Refused('Unexpected ' + label + ' foreign keys')


def _source(db, budget):
    if full.validate(db, budget) != FROM_REVISION:
        raise full.small.Refused('Reviewed a0 source revision required')
    tables = full.schema(db)
    expected_names = set(collaboration.NEW_TABLES) | {sources.TABLE}
    if set(NEW_TABLES) & set(tables):
        raise full.small.Refused('Unexpected partial b1 editorial schema')
    required_names = (set(collaboration.BASE_ACCESS_TABLES) | set(collaboration.E6_TABLES)
                      | set(expected_names))
    if not required_names <= set(tables):
        raise full.small.Refused('Reviewed a0 saved-memory schema required')
    if 'tasks' not in tables or db.execute(
            "SELECT 1 FROM tasks WHERE state='running' LIMIT 1").fetchone():
        raise full.small.Refused('All running tasks must be drained')
    for name, expected in PREREQUISITES.tables.items():
        if name in expected_names:
            _validate_table_contract(db, expected, 'a0 prerequisite')
    if sources.TABLE not in PREREQUISITES.tables:
        raise full.small.Refused('Source-reference contract unavailable')
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
        source_objects = _schema_objects(source)
        if full.fingerprint(source, tables, budget)[0] != digest:
            raise full.small.Refused('Source changed since backup')
        with full.read_source(backup, budget, offline=True) as saved:
            if (_source(saved, budget) != tables
                    or _schema_objects(saved) != source_objects
                    or full.fingerprint(saved, tables, budget)[0] != digest):
                raise full.small.Refused('Reviewed backup mismatch')
    return identity, backup_identity


def _target(db, budget, old_table_names):
    if full.validate(db, budget) != TO_REVISION:
        raise full.small.Refused('Incomplete b1 migration')
    tables = full.schema(db)
    if set(tables) != set(old_table_names) | set(NEW_TABLES):
        raise full.small.Refused('Unexpected b1 table set')
    expected_by_name = {}
    # Rebuild the same authoritative definitions to inspect table and FK metadata.
    metadata = MetaData()
    Table('access_memory_book_revisions', metadata,
          Column('book_id', Text, primary_key=True), Column('revision', Integer, primary_key=True))
    Table('access_memory_revisions', metadata,
          Column('story_id', Text, primary_key=True), Column('revision', Integer, primary_key=True))
    Table('access_memory_contributions', metadata, Column('id', Text, primary_key=True))
    expected_by_name.update((table.name, table) for table in add_book_editorial_tables(metadata))
    for name, expected in expected_by_name.items():
        _validate_table_contract(db, expected, 'editorial')
        if db.execute('SELECT 1 FROM ' + full.quoted(name) + ' LIMIT 1').fetchone():
            raise full.small.Refused('Unexpected editorial row')
    objects = _schema_objects(db)
    expected_auxiliary = {obj for obj in EDITORIAL_OBJECTS if obj[0] in ('index', 'trigger')}
    actual_auxiliary = {obj for obj in objects
                        if obj[0] in ('index', 'trigger')
                        and obj[1] in EDITORIAL_INDEXES | EDITORIAL_TRIGGERS}
    if actual_auxiliary != expected_auxiliary:
        raise full.small.Refused('Unexpected editorial index or trigger metadata')
    for kind, name, table, sql in EDITORIAL_OBJECTS:
        if kind == 'table':
            actual = next((obj for obj in objects if obj[0] == kind and obj[1] == name), None)
            if actual is None or _normalize_sql(actual[3]) != _normalize_sql(sql):
                raise full.small.Refused('Unexpected editorial table definition')
    if db.execute('PRAGMA foreign_key_check').fetchone() is not None:
        raise full.small.Refused('Editorial foreign-key verification failed')
    if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
        raise full.small.Refused('Editorial integrity verification failed')


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
                source_objects = _schema_objects(driver)
                with full.read_source(backup, budget, offline=True) as saved:
                    if (full.small.identity(backup) != backup_identity
                            or _source(saved, budget) != tables
                            or _schema_objects(saved) != source_objects
                            or full.fingerprint(saved, tables, budget)[0] != digest):
                        raise full.small.Refused('Backup changed after review')
                preserved = {name: columns for name, columns in tables.items()
                             if name != 'alembic_version'}
                expected_fingerprint, counts = full.fingerprint(driver, preserved, budget)
                config = full.small.migration_config()
                config.attributes['connection'] = connection
                command.upgrade(config, TO_REVISION)
                if not driver.in_transaction:
                    raise full.small.Refused('Migration escaped exclusive transaction')
                _target(driver, budget, set(tables))
                if full.fingerprint(driver, preserved, budget)[0] != expected_fingerprint:
                    raise full.small.Refused('Existing data changed')
                target_objects = _schema_objects(driver)
                expected_delta = EDITORIAL_OBJECTS
                if target_objects != source_objects | expected_delta:
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
