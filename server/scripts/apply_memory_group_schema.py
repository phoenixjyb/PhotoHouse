"""Guarded offline additive schema application to e7; read-only review by default.

No service control, backup creation/restoration, source installation, feature
activation or worker start. Execute only inside an independently approved
stopped-writer operation, with a separate reviewed private offline backup.
"""
import json
from pathlib import Path
import re
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rehearse_fullsize_database as full

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.access.memory_group_schema import (TABLE, REVISION_TABLE,
    verify_memory_group_schema)
from app.access.private_storage import require_private_file

FROM_REVISION = 'd1f6a8c3e920'
TO_REVISION = 'e7c1a9d5b304'
NEW_TABLES = frozenset((TABLE, REVISION_TABLE))
STEPS = (
    ('b1d7e4a9c230', ('access_memory_book_editorial', 'access_memory_book_editorial_refs')),
    ('c2e6b8a1d490', ('access_memory_book_editions', 'access_memory_book_edition_sources')),
    ('d1f6a8c3e920', ('access_family_note_identities', 'access_family_note_scopes',
                    'access_memory_book_edition_family_notes')),
    (TO_REVISION, (TABLE, REVISION_TABLE)),
)
SOURCE_REVISIONS = ('a0c9d2e4f817', *(revision for revision, _ in STEPS[:-1]))


def _additions(from_revision):
    if type(from_revision) is not str or from_revision not in SOURCE_REVISIONS:
        raise full.small.Refused('Explicit supported source revision required')
    return tuple(name for _, names in STEPS[SOURCE_REVISIONS.index(from_revision):]
                 for name in names)

REQUIRED_TABLES = frozenset(('assets', 'tasks', 'access_accounts', 'access_sessions',
    'access_libraries', 'access_memberships', 'access_asset_libraries',
    'access_uploads', 'access_upload_transfers', 'access_stories',
    'access_story_revisions'))


def _objects(db):
    return frozenset(db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master "
        "WHERE type IN ('table','index','trigger','view') AND name NOT LIKE 'sqlite_%'"))


def _expected_addition(from_revision):
    """Render authoritative builders including triggers added to old tables.

    Baseline table DDL is not treated as migration output. Only the exact new
    objects emitted by the pending builders are admitted in the real target.
    """
    from sqlalchemy import create_engine
    from app.access.metadata import migration_metadata
    from app.db import Base
    metadata = migration_metadata(Base.metadata)
    additions = _additions(from_revision)
    engine = create_engine('sqlite://')
    try:
        with engine.begin() as connection:
            # D1 attaches two triggers to the existing story table. Its DDL
            # must precede identity-table creation even without an FK edge.
            metadata.tables['access_stories'].create(connection)
            metadata.create_all(connection, tables=[table for table in metadata.sorted_tables
                                                   if table.name not in additions])
            before = _objects(connection.connection.driver_connection)
            for name in additions:
                metadata.tables[name].create(connection)
            return _objects(connection.connection.driver_connection) - before
    finally:
        engine.dispose()


def _source(db, budget, from_revision):
    additions = set(_additions(from_revision))
    if full.validate(db, budget) != from_revision:
        raise full.small.Refused('Exact reviewed source revision required')
    tables = full.schema(db)
    installed = {name for _, names in STEPS for name in names} - additions
    if not (REQUIRED_TABLES | installed) <= set(tables) or additions & set(tables):
        raise full.small.Refused('Complete source without pending schema tables required')
    if db.execute("SELECT 1 FROM tasks WHERE state='running' LIMIT 1").fetchone():
        raise full.small.Refused('All running tasks must be drained')
    return tables


def review(database, backup, digest, budget, from_revision=FROM_REVISION):
    _additions(from_revision)
    if type(digest) is not str or not re.fullmatch('[0-9a-f]{64}', digest):
        raise full.small.Refused('Exact reviewed backup digest required')
    require_private_file(database)
    require_private_file(backup)
    identity = full.small.identity(database)
    backup_identity = full.small.identity(backup)
    if identity == backup_identity or database == backup:
        raise full.small.Refused('Separate backup required')
    with full.read_source(database, budget, offline=True) as source:
        tables = _source(source, budget, from_revision)
        objects = _objects(source)
        if full.fingerprint(source, tables, budget)[0] != digest:
            raise full.small.Refused('Source changed since backup')
        with full.read_source(backup, budget, offline=True) as saved:
            if (_source(saved, budget, from_revision) != tables or _objects(saved) != objects
                    or full.fingerprint(saved, tables, budget)[0] != digest):
                raise full.small.Refused('Reviewed backup mismatch')
    return identity, backup_identity, objects


def apply(database, backup, digest, budget, *, execute=False, all_writers_stopped=False,
          from_revision=FROM_REVISION):
    additions = frozenset(_additions(from_revision))
    if type(execute) is not bool or type(all_writers_stopped) is not bool:
        raise full.small.Refused('Explicit operation choices required')
    if execute and not all_writers_stopped:
        raise full.small.Refused('Independent all-writer shutdown confirmation required')
    identity, backup_identity, source_objects = review(database, backup, digest, budget, from_revision)
    if not execute:
        return {'reviewed': True, 'applied': False, 'source_revision': from_revision,
                'target_revision': TO_REVISION, 'operational_quiescence_verified': False,
                'backup_restored': False, 'http_activated': False}
    expected_addition = _expected_addition(from_revision)
    if {row[2] for row in expected_addition if row[0] == 'table'} != additions:
        raise full.small.Refused('Unexpected group metadata closure')
    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool
    from alembic import command
    def connect():
        require_private_file(database)
        require_private_file(backup)
        full.small.no_sidecars(database)
        if full.small.identity(database) != identity:
            raise full.small.Refused('Target replaced')
        db = sqlite3.connect(database.as_uri() + '?mode=rw', uri=True, timeout=3)
        try:
            budget.configure(db)
            db.execute('PRAGMA synchronous=FULL')
            if db.execute('PRAGMA journal_mode').fetchone()[0] != 'delete':
                raise full.small.Refused('Offline DELETE journal required')
            return db
        except BaseException:
            db.close()
            raise

    engine = create_engine('sqlite://', creator=connect, poolclass=NullPool)
    try:
        with engine.connect() as connection:
            driver = connection.connection.driver_connection
            # Transaction exclusion does not prove operational shutdown: a
            # fenced-out old process could reconnect immediately after commit.
            connection.exec_driver_sql('BEGIN EXCLUSIVE')
            try:
                tables = _source(driver, budget, from_revision)
                if (_objects(driver) != source_objects
                        or full.fingerprint(driver, tables, budget)[0] != digest):
                    raise full.small.Refused('Target changed after review')
                with full.read_source(backup, budget, offline=True) as saved:
                    if (full.small.identity(backup) != backup_identity
                            or _objects(saved) != source_objects
                            or _source(saved, budget, from_revision) != tables
                            or full.fingerprint(saved, tables, budget)[0] != digest):
                        raise full.small.Refused('Backup changed after review')
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
                        or not verify_memory_group_schema(driver)
                        or _objects(driver) != source_objects | expected_addition):
                    raise full.small.Refused('Incomplete or unexpected transactional migration')
                if full.fingerprint(driver, preserved, budget)[0] != before_rows:
                    raise full.small.Refused('Existing data changed')
                if any(driver.execute('SELECT 1 FROM ' + full.quoted(name) + ' LIMIT 1').fetchone()
                       for name in additions):
                    raise full.small.Refused('Unexpected group backfill')
                with full.read_source(backup, budget, offline=True) as saved:
                    if (_objects(saved) != source_objects or _source(saved, budget, from_revision) != tables
                            or full.fingerprint(saved, tables, budget)[0] != digest):
                        raise full.small.Refused('Backup changed during migration')
                require_private_file(database)
                require_private_file(backup)
                if full.small.identity(database) != identity or full.small.identity(backup) != backup_identity:
                    raise full.small.Refused('Reviewed files replaced')
                budget.check()
                connection.commit()
            except BaseException:
                driver.set_progress_handler(None, 0)
                connection.rollback()
                raise
    finally:
        engine.dispose()
    return {'reviewed': True, 'applied': True, 'source_revision': from_revision,
            'revision': TO_REVISION, 'tables_preserved': len(counts),
            'rows_preserved': sum(counts.values()), 'new_tables_created': len(additions),
            'new_rows_created': 0, 'accounts_created': 0, 'assets_mapped': 0,
            'backup_restored': False, 'http_activated': False}


def qualify_generated(output):
    """Exercise the guarded full chain on our own absent synthetic directory.

    Called under the generated worker qualifier's mandatory Windows Job. This
    function has no runtime database input and never asserts live quiescence.
    """
    import qualify_memory_groups as fixture
    from alembic import command
    from sqlalchemy import event
    target = Path(output)
    fixture._validate_output(target)
    target.mkdir(mode=0o700)
    from app.access.private_storage import require_private_directory
    require_private_directory(target)
    database, backup = target/'primary.sqlite', target/'a0-backup.sqlite'
    origin = SOURCE_REVISIONS[0]
    fixture._seed(database, revision=origin)
    fixture._backup(database, backup)
    before = fixture._snapshot(database)
    saved = backup.read_bytes()
    budget = full.Budget(128*1024**2, 120)
    with full.read_source(backup, budget, offline=True) as db:
        digest = full.fingerprint(db, full.schema(db), budget)[0]
    review(database, backup, digest, budget, origin)
    actual_upgrade = command.upgrade
    def interrupted(config, revision):
        connection = config.attributes['connection']
        def fail(_conn, _cursor, statement, *rest):
            if statement.lstrip().startswith('CREATE TABLE access_family_note_scopes'):
                raise RuntimeError('synthetic_chain_interruption')
        event.listen(connection, 'before_cursor_execute', fail)
        try:
            actual_upgrade(config, revision)
        finally:
            event.remove(connection, 'before_cursor_execute', fail)
    # Injection is confined to this generated invocation and restored even on
    # failure. Runtime apply never patches or overrides migration execution.
    from unittest.mock import patch
    try:
        with patch.object(command, 'upgrade', side_effect=interrupted):
            apply(database, backup, digest, budget, execute=True,
                  all_writers_stopped=True, from_revision=origin)
    except RuntimeError as error:
        if str(error) != 'synthetic_chain_interruption':
            raise
    else:
        raise RuntimeError('synthetic_chain_interruption_missing')
    if (fixture._snapshot(database) != before or fixture._revision(database) != [(origin,)]
            or backup.read_bytes() != saved):
        raise RuntimeError('synthetic_chain_rollback_failed')
    result = apply(database, backup, digest, full.Budget(128*1024**2, 120),
                   execute=True, all_writers_stopped=True, from_revision=origin)
    if backup.read_bytes() != saved or result['new_tables_created'] != 9:
        raise RuntimeError('synthetic_chain_backup_or_closure_failed')
    return {'source_revision': origin, 'revision': TO_REVISION,
            'new_tables_created': 9, 'new_rows_created': 0,
            'interruption_rollback_verified': True, 'backup_unchanged': True,
            'existing_rows_preserved': True}


def main(argv=None):
    parser = full.small.Parser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--backup', type=Path, required=True)
    parser.add_argument('--reviewed-backup-digest', required=True)
    parser.add_argument('--max-bytes', type=int, required=True)
    parser.add_argument('--timeout-seconds', type=int, required=True)
    parser.add_argument('--from-revision', choices=SOURCE_REVISIONS, default=FROM_REVISION)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--all-writers-stopped', action='store_true')
    try:
        args = parser.parse_args(argv)
        result = apply(args.database, args.backup, args.reviewed_backup_digest,
            full.Budget(args.max_bytes, args.timeout_seconds), execute=args.execute,
            all_writers_stopped=args.all_writers_stopped, from_revision=args.from_revision)
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
