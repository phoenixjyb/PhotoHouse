#!/usr/bin/env python3
"""Apply the reviewed e6 -> f7 additive collaboration schema to one offline DB.

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

full = historical.full
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from sqlalchemy import Column, MetaData, Table, Text
from sqlalchemy.dialects.sqlite import dialect
from sqlalchemy.schema import CreateTable
from app.access.memory_collaboration_schema import add_collaboration_tables

FROM_REVISION = 'e6b2f8a1c903'
TO_REVISION = 'f7c3a9d2e614'
NEW_TABLES = (
    'access_memory_contributions',
    'access_memory_contribution_derivations',
    'access_memory_books',
    'access_memory_book_revisions',
    'access_memory_conversations',
    'access_memory_jobs',
    'access_memory_turns',
    'access_original_deletion_state',
)
E6_TABLES = {
    'access_memory_stories': ('id','library_id','author_id','revision','content','created_at','updated_at'),
    'access_memory_revisions': ('story_id','revision','editor_id','mutation_id','request_digest','content','occurred_at'),
}
BASE_ACCESS_TABLES = frozenset({
    'access_accounts','access_sessions','access_operators','access_libraries',
    'access_memberships','access_invitations','access_asset_libraries','access_audit',
    'access_admission_key','access_attempts','access_kdf_slot',
    'access_provisioning_receipts','access_stories','access_story_revisions',
    'access_person_libraries','access_album_libraries','access_uploads',
    'access_upload_transfers','access_upload_auto_policies','access_upload_annotations',
    'access_annotation_derivations','access_annotation_tag_proposals',
})


def _expected_tables():
    metadata = MetaData()
    for name in ('access_accounts','access_libraries','access_memory_stories'):
        Table(name, metadata, Column('id',Text,primary_key=True))
    return {table.name: table for table in add_collaboration_tables(metadata)}


EXPECTED = _expected_tables()


def _source(db, budget):
    if full.validate(db, budget) != FROM_REVISION:
        raise full.small.Refused('Reviewed e6 source revision required')
    tables = full.schema(db)
    if (not (BASE_ACCESS_TABLES | set(E6_TABLES)) <= set(tables) or set(NEW_TABLES) & set(tables)
            or any(tuple(tables[name]) != columns for name, columns in E6_TABLES.items())):
        raise full.small.Refused('Reviewed e6 saved-memory schema required')
    if 'tasks' not in tables or db.execute("SELECT 1 FROM tasks WHERE state='running' LIMIT 1").fetchone():
        raise full.small.Refused('All running tasks must be drained')
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
    return re.sub(r'\s+', ' ', sql.replace('"','').replace('`','').strip().rstrip(';')).casefold()


def _schema_objects(db):
    return {(kind,name,table,sql) for kind,name,table,sql in db.execute(
        "SELECT type,name,tbl_name,sql FROM sqlite_master "
        "WHERE type IN ('table','index','view','trigger') AND name NOT LIKE 'sqlite_%'")}


def _target(db, budget, expected_table_names):
    if full.validate(db, budget) != TO_REVISION:
        raise full.small.Refused('Incomplete f7 migration')
    tables = full.schema(db)
    if set(tables) != set(expected_table_names) | set(NEW_TABLES):
        raise full.small.Refused('Missing f7 collaboration table')
    for name, expected in EXPECTED.items():
        actual = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone()
        compiled = str(CreateTable(expected).compile(dialect=dialect()))
        if (tuple(tables[name]) != tuple(column.name for column in expected.columns)
                or not actual or _normalize_sql(actual[0]) != _normalize_sql(compiled)):
            raise full.small.Refused('Unexpected collaboration table metadata')
        if db.execute('SELECT 1 FROM ' + full.quoted(name) + ' LIMIT 1').fetchone():
            raise full.small.Refused('Unexpected collaboration row')

    expected_indexes = {}
    for table in EXPECTED.values():
        expected_indexes[table.name] = {
            index.name: (tuple(column.name for column in index.columns), bool(index.unique))
            for index in table.indexes
        }
    for table_name, wanted in expected_indexes.items():
        actual = {}
        for seq, name, unique, origin, partial in db.execute(
                'PRAGMA index_list(' + full.quoted(table_name) + ')'):
            columns = tuple(row[2] for row in db.execute('PRAGMA index_info(' + full.quoted(name) + ')'))
            if origin == 'c':
                actual[name] = (columns, bool(unique))
        if actual != wanted:
            raise full.small.Refused('Unexpected collaboration indexes')
    if db.execute('PRAGMA foreign_key_check').fetchone() is not None:
        raise full.small.Refused('Collaboration foreign-key verification failed')
    if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
        raise full.small.Refused('Collaboration integrity verification failed')


def apply(database, backup, digest, budget, *, execute=False, all_writers_stopped=False):
    if execute and not all_writers_stopped:
        raise full.small.Refused('Independent all-writer shutdown confirmation required')
    identity, backup_identity = review(database, backup, digest, budget)
    if not execute:
        return {'reviewed':True,'applied':False,'source_revision':FROM_REVISION,
                'target_revision':TO_REVISION,'operational_quiescence_verified':False}

    from alembic import command
    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool

    def connect():
        full.small.no_sidecars(database)
        if full.small.identity(database) != identity:
            raise full.small.Refused('Target replaced')
        db = sqlite3.connect(database.as_uri() + '?mode=rw',uri=True,timeout=3)
        budget.configure(db)
        db.execute('PRAGMA synchronous=FULL')
        if db.execute('PRAGMA journal_mode').fetchone()[0] != 'delete':
            db.close()
            raise full.small.Refused('Offline DELETE journal required')
        return db

    engine=create_engine('sqlite://',creator=connect,poolclass=NullPool)
    try:
        with engine.connect() as connection:
            driver=connection.connection.driver_connection
            connection.exec_driver_sql('BEGIN EXCLUSIVE')
            try:
                tables=_source(driver,budget)
                if full.fingerprint(driver,tables,budget)[0] != digest:
                    raise full.small.Refused('Target changed after review')
                with full.read_source(backup,budget,offline=True) as saved:
                    if (full.small.identity(backup) != backup_identity or _source(saved,budget) != tables
                            or full.fingerprint(saved,tables,budget)[0] != digest):
                        raise full.small.Refused('Backup changed after review')
                preserved={name:columns for name,columns in tables.items() if name != 'alembic_version'}
                source_objects=_schema_objects(driver)
                expected,counts=full.fingerprint(driver,preserved,budget)
                config=full.small.migration_config()
                config.attributes['connection']=connection
                command.upgrade(config,TO_REVISION)
                if not driver.in_transaction:
                    raise full.small.Refused('Migration escaped exclusive transaction')
                _target(driver,budget,set(tables))
                if full.fingerprint(driver,preserved,budget)[0] != expected:
                    raise full.small.Refused('Existing data changed')
                target_objects=_schema_objects(driver)
                allowed_new=NEW_TABLES + tuple(index.name for table in EXPECTED.values()
                                               for index in table.indexes)
                if (not source_objects <= target_objects
                        or target_objects-source_objects != {
                            item for item in target_objects-source_objects if item[1] in allowed_new}):
                    raise full.small.Refused('Existing schema changed')
                if (full.small.identity(database) != identity
                        or full.small.identity(backup) != backup_identity):
                    raise full.small.Refused('Reviewed files replaced')
                budget.check()
                connection.commit()
            except BaseException:
                driver.set_progress_handler(None,0)
                connection.rollback()
                raise
    finally:
        engine.dispose()
    full.small.no_sidecars(database)
    return {'reviewed':True,'applied':True,'revision':TO_REVISION,
            'tables_preserved':len(counts),'rows_preserved':sum(counts.values()),
            'collaboration_tables_created':len(NEW_TABLES),'new_rows_created':0,
            'http_activated':False,'feature_flags_enabled':False}


def main(argv=None):
    parser=full.small.Parser(description=__doc__,allow_abbrev=False)
    parser.add_argument('--database',type=Path,required=True)
    parser.add_argument('--backup',type=Path,required=True)
    parser.add_argument('--reviewed-backup-digest',required=True)
    parser.add_argument('--max-bytes',type=int,required=True)
    parser.add_argument('--timeout-seconds',type=int,required=True)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--all-writers-stopped',action='store_true')
    try:
        args=parser.parse_args(argv)
        result=apply(args.database,args.backup,args.reviewed_backup_digest,
            full.Budget(args.max_bytes,args.timeout_seconds),execute=args.execute,
            all_writers_stopped=args.all_writers_stopped)
        print(json.dumps(result,sort_keys=True)); return 0
    except KeyboardInterrupt:
        print('Migration interrupted; inspect schema and controller receipt before retrying.',file=sys.stderr)
        return 130
    except Exception:
        print('Migration refused or incomplete; inspect schema and controller receipt before retrying.',file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
