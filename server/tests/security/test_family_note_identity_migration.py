"""Real SQLite/Alembic checks for additive family-note identity lineage."""
import json
from pathlib import Path
import re
import sqlite3
import sys
import unittest
import uuid

from alembic import command
from sqlalchemy import Column, Integer, MetaData, Table, Text, inspect

import test_memory_book_edition_migration as edition_fixture
import test_orm_migrations as migration_fixture

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from app.access.family_note_identity import create_note_identity  # noqa: E402
from app.access.family_note_identity_schema import (  # noqa: E402
    EDITION_NOTES,
    IDENTITIES,
    IDENTITY_REVISION,
    IDENTITY_TABLES,
    SCOPES,
    add_family_note_identity_tables,
    sqlite_family_note_identity_contract,
)
from app.access.metadata import migration_metadata  # noqa: E402
from app.access.memory_book_edition_schema import EDITION_TABLE, SOURCES_TABLE  # noqa: E402
from app.db import Base  # noqa: E402

C2 = 'c2e6b8a1d490'
LIBRARY = edition_fixture.editorial_fixture.LIBRARY
NOTE_ID = str(uuid.UUID(int=9904))
EDITION_ID = str(uuid.UUID(int=9905))


def normalized_sql(value):
    return re.sub(r'\s+', ' ', value).strip()


def schema_objects(connection):
    return set(connection.exec_driver_sql(
        "SELECT type,name,tbl_name,sql FROM sqlite_master "
        "WHERE name NOT LIKE 'sqlite_%' AND name != 'alembic_version'").all())


def rows_snapshot(connection):
    tables = set(inspect(connection).get_table_names()) - {'alembic_version'}
    return {
        table: tuple(sorted(repr(tuple(row)) for row in
                            connection.exec_driver_sql(f'SELECT * FROM "{table}"').all()))
        for table in sorted(tables)
    }


class FamilyNoteIdentityMigrationTests(unittest.TestCase):
    def setUp(self):
        self.edition = edition_fixture.MemoryBookEditionMigrationTests()
        self.edition.setUp()
        self.addCleanup(self.edition.doCleanups)
        self.migration = self.edition.migration

    def _upgrade_to_c2(self):
        owner = self.edition._upgrade_to_b1_with_existing_editorial()
        self.migration.upgrade(C2)
        return owner

    def _downgrade_to_c2(self):
        with self.migration.engine.begin() as connection:
            cfg = migration_fixture.config()
            cfg.attributes['connection'] = connection
            command.downgrade(cfg, C2)

    def _insert_legacy_note(self, connection, owner):
        connection.exec_driver_sql('''INSERT INTO access_stories
            (id,asset_id,library_id,author_id,revision,title,text,language,byline,
             created_at,updated_at,deleted)
            VALUES(?,101,?, ?,1,'Synthetic note','Synthetic note text','en','Synthetic',30,30,0)''',
            (NOTE_ID, LIBRARY, owner))
        connection.exec_driver_sql('''INSERT INTO access_story_revisions
            (story_id,revision,editor_id,mutation_id,request_digest,title,text,language,
             byline,occurred_at,deleted)
            VALUES(?,1,?,?,?,'Synthetic note','Synthetic note text','en','Synthetic',30,0)''',
            (NOTE_ID, owner, str(uuid.UUID(int=9907)), 'e' * 64))

    def _insert_legacy_family_edition(self, connection, owner):
        self._insert_legacy_note(connection, owner)
        connection.exec_driver_sql(f'''INSERT INTO {EDITION_TABLE}
            (id,book_id,book_revision,library_id,creator_account_id,originating_job_id,
             job_result_sha256,source_fingerprint,context_profile,children_json,
             manuscript_json,mutation_id,request_digest,created_at,state)
            VALUES(?,?,1,?,?,?,'{'a' * 64}','{'b' * 64}','stories',?,
                   '{{"title":"Reviewed"}}',?,'{'c' * 64}',30,'current')''',
            (EDITION_ID, edition_fixture.BOOK, LIBRARY, owner,
             str(uuid.UUID(int=9908)),
             json.dumps([{'id': edition_fixture.STORY, 'revision': '1'}],
                        separators=(',', ':')),
             str(uuid.UUID(int=9909))))
        connection.exec_driver_sql(f'''INSERT INTO {SOURCES_TABLE}
            (edition_id,ordinal,source_id,kind,asset_id,source_digest,chapter_ids_json,
             contribution_id,contribution_story_id)
            VALUES(?,0,?,'family','101',?,'["chapter-1"]',NULL,NULL)''',
            (EDITION_ID, 'family-' + NOTE_ID, 'd' * 64))

    def _identity_connection(self):
        connection = sqlite3.connect(self.migration.path)
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('BEGIN IMMEDIATE')
        self.addCleanup(connection.close)
        return connection

    def test_builder_is_exact_idempotent_and_rejects_partial_or_drifted_metadata(self):
        def parent_metadata():
            metadata = MetaData()
            Table(SOURCES_TABLE, metadata,
                  Column('edition_id', Text, primary_key=True),
                  Column('ordinal', Integer, primary_key=True))
            return metadata

        metadata = parent_metadata()
        tables = add_family_note_identity_tables(metadata)
        self.assertEqual({table.name for table in tables}, IDENTITY_TABLES)
        self.assertEqual({table.name for table in add_family_note_identity_tables(metadata)},
                         IDENTITY_TABLES)

        partial = parent_metadata()
        add_family_note_identity_tables(partial)
        partial.remove(partial.tables[SCOPES])
        with self.assertRaisesRegex(ValueError, 'family_note_identity_schema_partial'):
            add_family_note_identity_tables(partial)

        drifted = parent_metadata()
        add_family_note_identity_tables(drifted)
        drifted.tables[IDENTITIES].append_column(Column('unexpected', Text))
        with self.assertRaisesRegex(ValueError, 'family_note_identity_schema_mismatch'):
            add_family_note_identity_tables(drifted)

    def test_migration_adds_only_identity_tables_without_startup_schema_or_backfill(self):
        owner = self._upgrade_to_c2()
        with self.migration.engine.begin() as connection:
            self._insert_legacy_family_edition(connection, owner)
            before_objects = schema_objects(connection)
            before_rows = rows_snapshot(connection)
            before_edition_schema = {
                name: connection.exec_driver_sql(
                    "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (name,)
                ).scalar_one()
                for name in (EDITION_TABLE, SOURCES_TABLE)
            }

        self.migration.upgrade(IDENTITY_REVISION)

        with self.migration.engine.connect() as connection:
            self.assertEqual(connection.exec_driver_sql(
                'SELECT version_num FROM alembic_version').scalar_one(), IDENTITY_REVISION)
            after_objects = schema_objects(connection)
            contract = sqlite_family_note_identity_contract()
            expected = {(kind, name) for kind, name, _ddl in contract}
            added = after_objects - before_objects
            self.assertEqual({(kind, name) for kind, name, _tbl, _sql in added}, expected)
            self.assertEqual({table: rows for table, rows in rows_snapshot(connection).items()
                              if table in before_rows}, before_rows)
            self.assertEqual(connection.exec_driver_sql(
                f'SELECT count(*) FROM {IDENTITIES}').scalar_one(), 0)
            self.assertEqual(connection.exec_driver_sql(
                f'SELECT count(*) FROM {SCOPES}').scalar_one(), 0)
            self.assertEqual(connection.exec_driver_sql(
                f'SELECT count(*) FROM {EDITION_NOTES}').scalar_one(), 0)
            self.assertEqual(connection.exec_driver_sql(
                f'SELECT source_id FROM {SOURCES_TABLE} WHERE edition_id=?',
                (EDITION_ID,)).scalar_one(), 'family-' + NOTE_ID)
            for name, before_sql in before_edition_schema.items():
                self.assertEqual(connection.exec_driver_sql(
                    "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                    (name,)).scalar_one(), before_sql)

            for kind, name, expected_sql in contract:
                actual_kind, actual_sql = connection.exec_driver_sql(
                    'SELECT type,sql FROM sqlite_master WHERE name=?', (name,)).one()
                self.assertEqual(actual_kind, kind)
                if kind == 'trigger':
                    actual_sql = actual_sql.replace('CREATE TRIGGER ',
                                                    'CREATE TRIGGER IF NOT EXISTS ', 1)
                self.assertEqual(normalized_sql(actual_sql), normalized_sql(expected_sql))
            self.assertEqual(connection.exec_driver_sql('PRAGMA foreign_key_check').all(), [])

        before_base = set(Base.metadata.tables)
        combined = migration_metadata(Base.metadata)
        self.assertTrue(IDENTITY_TABLES <= set(combined.tables))
        self.assertEqual(set(Base.metadata.tables), before_base)

    def test_base_create_all_does_not_install_identity_schema(self):
        from sqlalchemy import create_engine

        engine = create_engine('sqlite:///:memory:')
        self.addCleanup(engine.dispose)
        before = set(Base.metadata.tables)
        Base.metadata.create_all(engine)
        with engine.connect() as connection:
            self.assertFalse(IDENTITY_TABLES & set(inspect(connection).get_table_names()))
        self.assertEqual(set(Base.metadata.tables), before)

    def test_empty_downgrade_removes_only_identity_schema_and_preserves_c2(self):
        self._upgrade_to_c2()
        with self.migration.engine.connect() as connection:
            before_rows = rows_snapshot(connection)
        self.migration.upgrade(IDENTITY_REVISION)
        with self.migration.engine.connect() as connection:
            before_objects = schema_objects(connection)

        self._downgrade_to_c2()

        with self.migration.engine.connect() as connection:
            self.assertEqual(connection.exec_driver_sql(
                'SELECT version_num FROM alembic_version').scalar_one(), C2)
            self.assertEqual(before_objects - schema_objects(connection),
                             {obj for obj in before_objects if obj[1] in
                              {name for _kind, name, _sql in sqlite_family_note_identity_contract()}})
            self.assertEqual(rows_snapshot(connection), before_rows)
            self.assertFalse(IDENTITY_TABLES & set(inspect(connection).get_table_names()))
            self.assertEqual(connection.exec_driver_sql('PRAGMA foreign_key_check').all(), [])

    def test_populated_identity_downgrade_refuses_without_changing_data_or_revision(self):
        owner = self._upgrade_to_c2()
        self.migration.upgrade(IDENTITY_REVISION)
        with self.migration.engine.begin() as connection:
            self._insert_legacy_family_edition(connection, owner)

        db = self._identity_connection()
        create_note_identity(db, NOTE_ID)
        identity = db.execute(f'SELECT identity_id FROM {IDENTITIES} WHERE note_id=?',
                              (NOTE_ID,)).fetchone()[0]
        db.execute(f'''INSERT INTO {EDITION_NOTES}
            (edition_id,ordinal,identity_id,scope_ordinal) VALUES(?,0,?,0)''',
            (EDITION_ID, identity))
        db.commit()

        with self.migration.engine.connect() as connection:
            before_rows = rows_snapshot(connection)
            before_objects = schema_objects(connection)
        with self.assertRaisesRegex(RuntimeError, 'reviewed offline backup restoration'):
            self._downgrade_to_c2()
        with self.migration.engine.connect() as connection:
            self.assertEqual(connection.exec_driver_sql(
                'SELECT version_num FROM alembic_version').scalar_one(), IDENTITY_REVISION)
            self.assertEqual(rows_snapshot(connection), before_rows)
            self.assertEqual(schema_objects(connection), before_objects)
            self.assertEqual(connection.exec_driver_sql('PRAGMA foreign_key_check').all(), [])


if __name__ == '__main__':
    unittest.main()
