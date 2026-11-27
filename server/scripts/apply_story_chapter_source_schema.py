#!/usr/bin/env python3
"""Expand the F2 story source reference table in one SQLite transaction."""

import argparse
import json
from pathlib import Path
import sqlite3
import stat
import time


REVISION = 'f2a8c5d1e640'
TABLE = 'access_memory_contribution_refs'
REPLACEMENT = TABLE + '_v2'
INDEX = 'ix_memory_contribution_refs_source'
INDEX_SQL = f'CREATE INDEX {INDEX} ON {TABLE} (contribution_id)'
COLUMNS = 'story_id, revision, chapter_id, ordinal, contribution_id'
LEGACY_LIMIT = "CHECK (chapter_id IN ('chapter-1','chapter-2','chapter-3','chapter-4','chapter-5','chapter-6'))"
CHAPTER_IDS = ','.join(f"'chapter-{number}'" for number in range(1, 13))
EXPANDED_LIMIT = f'CONSTRAINT memory_contribution_refs_chapters_v2 CHECK (chapter_id IN ({CHAPTER_IDS}))'
LEGACY_SQL = f"""
CREATE TABLE {TABLE} (
    story_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    chapter_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    contribution_id TEXT NOT NULL,
    PRIMARY KEY (story_id, revision, chapter_id, ordinal),
    FOREIGN KEY(story_id, revision) REFERENCES access_memory_revisions (story_id, revision) ON DELETE CASCADE,
    FOREIGN KEY(contribution_id) REFERENCES access_memory_contributions (id) ON DELETE CASCADE,
    CHECK (revision > 0 AND ordinal BETWEEN 0 AND 11),
    UNIQUE (story_id, revision, chapter_id, contribution_id),
    {LEGACY_LIMIT}
)
"""
EXPANDED_SQL = LEGACY_SQL.replace(LEGACY_LIMIT, EXPANDED_LIMIT)
ROW_LIMIT = 50_000


class Refused(RuntimeError):
    pass


def normal_sql(sql):
    return ' '.join(sql.replace('"', '').split()).casefold()


def database_identity(database):
    if not database.is_absolute() or database.resolve(strict=True) != database:
        raise Refused('database_path_not_direct')
    for path in (database, *database.parents):
        info = path.lstat()
        if getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise Refused('database_path_reparse')
        if path == database:
            if not stat.S_ISREG(info.st_mode):
                raise Refused('database_not_regular')
            identity = (info.st_dev, info.st_ino)
    return identity


def inspect_table(db):
    if db.execute('SELECT version_num FROM alembic_version').fetchall() != [(REVISION,)]:
        raise Refused('unexpected_primary_revision')
    objects = {(kind, name): sql for kind, name, sql in db.execute("""
        SELECT type, name, sql FROM sqlite_master
        WHERE sql IS NOT NULL AND (instr(lower(sql), ?) > 0 OR name = ?)
        """, (TABLE, REPLACEMENT))}
    if objects.keys() != {('table', TABLE), ('index', INDEX)}:
        raise Refused('unexpected_reference_schema_dependencies')
    if normal_sql(objects['index', INDEX]) != normal_sql(INDEX_SQL):
        raise Refused('unexpected_reference_index')
    table_sql = normal_sql(objects['table', TABLE])
    if table_sql not in (normal_sql(LEGACY_SQL), normal_sql(EXPANDED_SQL)):
        raise Refused('unexpected_reference_table')
    count = db.execute(f'SELECT count(*) FROM {TABLE}').fetchone()[0]
    if count > ROW_LIMIT:
        raise Refused('reference_row_limit')
    if db.execute(f'PRAGMA foreign_key_check({TABLE})').fetchone() is not None:
        raise Refused('reference_foreign_key_failure')
    return table_sql == normal_sql(EXPANDED_SQL), count


def apply(database, *, execute=False):
    before = database_identity(database)
    connection = sqlite3.connect(database.as_uri() + ('?mode=rw' if execute else '?mode=ro'),
                                 uri=True, isolation_level=None, timeout=2)
    try:
        connection.execute('PRAGMA foreign_keys=ON')
        if execute:
            connection.execute('PRAGMA synchronous=FULL')
            if connection.execute('PRAGMA journal_mode').fetchone()[0] not in ('delete', 'wal'):
                raise Refused('unexpected_journal_mode')
        deadline = time.monotonic() + 3
        connection.set_progress_handler(lambda: time.monotonic() >= deadline, 1000)
        connection.execute('BEGIN IMMEDIATE' if execute else 'BEGIN')
        expanded, count = inspect_table(connection)
        if execute and not expanded:
            connection.execute(EXPANDED_SQL.replace(f'CREATE TABLE {TABLE} ', f'CREATE TABLE {REPLACEMENT} ', 1))
            connection.execute(f'INSERT INTO {REPLACEMENT} ({COLUMNS}) SELECT {COLUMNS} FROM {TABLE}')
            if connection.execute(f'SELECT count(*) FROM {REPLACEMENT}').fetchone()[0] != count:
                raise Refused('reference_copy_count_mismatch')
            if connection.execute(
                    f'SELECT {COLUMNS} FROM {TABLE} EXCEPT SELECT {COLUMNS} FROM {REPLACEMENT} LIMIT 1'
            ).fetchone() is not None:
                raise Refused('reference_copy_mismatch')
            connection.execute(f'DROP TABLE {TABLE}')
            connection.execute(f'ALTER TABLE {REPLACEMENT} RENAME TO {TABLE}')
            connection.execute(INDEX_SQL)
            if inspect_table(connection) != (True, count):
                raise Refused('expanded_schema_verification_failed')
        if database_identity(database) != before or time.monotonic() >= deadline:
            raise Refused('database_identity_or_time_limit')
        connection.commit()
        return {'status': 'PASS', 'applied': bool(execute and not expanded),
                'expanded': bool(execute or expanded), 'primary_revision': REVISION,
                'references_preserved': count}
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    try:
        result = apply(args.database, execute=args.execute)
    except (Refused, OSError, sqlite3.Error) as error:
        code = str(error) if isinstance(error, Refused) else type(error).__name__
        print(json.dumps({'status': 'REFUSED', 'code': code}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
