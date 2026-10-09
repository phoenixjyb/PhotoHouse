"""Real SQLite/Alembic checks for reviewed memoir edition migration."""
import json
from pathlib import Path
import re
import sys
import unittest
import uuid

from alembic import command
from sqlalchemy import event, inspect
from sqlalchemy import create_engine

import test_memory_book_editorial_migration as editorial_fixture
import test_orm_migrations as migration_fixture

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from app.access.memory_book_edition_schema import (  # noqa: E402
    EDITION_TABLE,
    SOURCES_TABLE,
    add_book_edition_tables,
    sqlite_edition_schema_contract,
)
from app.access.metadata import migration_metadata  # noqa: E402
from app.db import Base  # noqa: E402

REVISION = 'c2e6b8a1d490'
DOWN_REVISION = 'b1d7e4a9c230'
EDITION_TABLES = {EDITION_TABLE, SOURCES_TABLE}
BOOK = editorial_fixture.BOOK
STORY = editorial_fixture.STORY
CONTRIBUTION = editorial_fixture.CONTRIBUTION


def normalized_sql(value):
    return re.sub(r'\s+', ' ', value).strip()


class MemoryBookEditionMigrationTests(unittest.TestCase):
    def setUp(self):
        self.editorial = editorial_fixture.MemoryBookEditorialMigrationTests()
        self.editorial.setUp()
        self.addCleanup(self.editorial.doCleanups)
        self.migration = self.editorial.migration

    def _upgrade_to_b1_with_existing_editorial(self):
        owner = self.editorial._upgrade_a0_with_historical_rows()
        self.migration.upgrade(DOWN_REVISION)
        with self.migration.engine.begin() as connection:
            connection.exec_driver_sql('''INSERT INTO access_memory_book_editorial
                (book_id,book_revision,children_json,transitions_json,state)
                VALUES(?,1,?,'[]','current')''',
                (BOOK, json.dumps([{'story_id': STORY, 'revision': '1'}],
                                  separators=(',', ':'))))
            connection.exec_driver_sql('''INSERT INTO access_memory_book_editorial_refs
                (book_id,book_revision,section_key,ordinal,story_id,story_revision,
                 chapter_id,contribution_id)
                VALUES(?,1,'introduction',0,?,1,'chapter-1',?)''',
                (BOOK, STORY, CONTRIBUTION))
        return owner

    def _snapshot_existing_rows(self):
        with self.migration.engine.connect() as connection:
            tables = set(inspect(connection).get_table_names()) - {'alembic_version'}
            return {
                table: tuple(sorted(repr(tuple(row)) for row in
                    connection.exec_driver_sql(f'SELECT * FROM "{table}"').all()))
                for table in sorted(tables)
            }

    def _upgrade(self):
        self.migration.upgrade(REVISION)

    def _downgrade_to_b1(self):
        with self.migration.engine.begin() as connection:
            cfg = migration_fixture.config()
            cfg.attributes['connection'] = connection
            command.downgrade(cfg, DOWN_REVISION)

    def _insert_edition(self, connection, owner, edition_id=None):
        edition_id = edition_id or str(uuid.UUID(int=9901))
        connection.exec_driver_sql(f'''INSERT INTO {EDITION_TABLE}
            (id,book_id,book_revision,library_id,creator_account_id,originating_job_id,
             job_result_sha256,source_fingerprint,context_profile,children_json,
             manuscript_json,mutation_id,request_digest,created_at,state)
            VALUES(?,?,1,?,?,?,'{'a' * 64}','{'b' * 64}','stories',?,'{{"title":"Reviewed"}}',?,
                   '{'c' * 64}',30,'current')''',
            (edition_id, BOOK, editorial_fixture.LIBRARY, owner,
             str(uuid.UUID(int=9902)),
             json.dumps([{'id': STORY, 'revision': '1'}], separators=(',', ':')),
             str(uuid.UUID(int=9903))))
        return edition_id

    def _insert_source(self, connection, edition_id):
        connection.exec_driver_sql(f'''INSERT INTO {SOURCES_TABLE}
            (edition_id,ordinal,source_id,kind,asset_id,source_digest,chapter_ids_json,
             contribution_id,contribution_story_id)
            VALUES(?,0,?,'family',NULL,?,'["chapter-1"]',?,?)''',
            (edition_id, 'contribution-' + CONTRIBUTION, 'd' * 64,
             CONTRIBUTION, STORY))

    def test_migration_metadata_adds_exact_tables_without_mutating_model_metadata(self):
        original_tables = set(Base.metadata.tables)
        combined = migration_metadata(Base.metadata)
        editions, sources = add_book_edition_tables(combined)
        self.assertEqual({editions.name, sources.name}, EDITION_TABLES)
        self.assertTrue(EDITION_TABLES <= set(combined.tables))
        self.assertEqual(set(Base.metadata.tables), original_tables)

        engine = create_engine('sqlite:///:memory:')
        self.addCleanup(engine.dispose)
        Base.metadata.create_all(engine)
        self.assertFalse(EDITION_TABLES & set(inspect(engine).get_table_names()))

    def test_b1_upgrade_adds_only_exact_edition_schema_and_preserves_all_existing_rows(self):
        self._upgrade_to_b1_with_existing_editorial()
        before_rows = self._snapshot_existing_rows()
        with self.migration.engine.connect() as connection:
            before_tables = set(inspect(connection).get_table_names())
            before_objects = set(connection.exec_driver_sql(
                "SELECT type,name,tbl_name,sql FROM sqlite_master "
                "WHERE name NOT LIKE 'sqlite_%' AND name != 'alembic_version'").all())

        self._upgrade()

        with self.migration.engine.connect() as connection:
            self.assertEqual(connection.exec_driver_sql(
                'SELECT version_num FROM alembic_version').scalar_one(), REVISION)
            after_tables = set(inspect(connection).get_table_names())
            self.assertEqual(after_tables - before_tables, EDITION_TABLES)
            self.assertEqual(before_tables - after_tables, set())
            after_rows = self._snapshot_existing_rows()
            self.assertEqual({name: after_rows[name] for name in before_rows}, before_rows)
            self.assertEqual(connection.exec_driver_sql('PRAGMA foreign_key_check').all(), [])

            contract = sqlite_edition_schema_contract()
            expected_tables = {name: sql for kind, name, sql in contract if kind == 'table'}
            expected_indexes = {name: sql for kind, name, sql in contract if kind == 'index'}
            expected_triggers = {name: sql for kind, name, sql in contract if kind == 'trigger'}
            actual_tables = dict(connection.exec_driver_sql(
                "SELECT name,sql FROM sqlite_master WHERE type='table' "
                'AND name IN (?,?)', (EDITION_TABLE, SOURCES_TABLE)).all())
            self.assertEqual(set(actual_tables), set(expected_tables))
            for name, expected in expected_tables.items():
                self.assertEqual(normalized_sql(actual_tables[name]), normalized_sql(expected))

            actual_indexes = dict(connection.exec_driver_sql(
                "SELECT name,sql FROM sqlite_master WHERE type='index' "
                'AND tbl_name IN (?,?) AND name NOT LIKE \'sqlite_autoindex_%\'',
                (EDITION_TABLE, SOURCES_TABLE)).all())
            self.assertEqual(set(actual_indexes), set(expected_indexes))
            for name, expected in expected_indexes.items():
                self.assertEqual(normalized_sql(actual_indexes[name]), normalized_sql(expected))

            actual_triggers = dict(connection.exec_driver_sql(
                "SELECT name,sql FROM sqlite_master WHERE type='trigger' "
                'AND tbl_name IN (?,?)', (EDITION_TABLE, SOURCES_TABLE)).all())
            self.assertEqual(set(actual_triggers), set(expected_triggers))
            for name, expected in expected_triggers.items():
                normalized_actual = actual_triggers[name].replace(
                    'CREATE TRIGGER ', 'CREATE TRIGGER IF NOT EXISTS ', 1)
                self.assertEqual(normalized_sql(normalized_actual), normalized_sql(expected))

            after_objects = set(connection.exec_driver_sql(
                "SELECT type,name,tbl_name,sql FROM sqlite_master "
                "WHERE name NOT LIKE 'sqlite_%' AND name != 'alembic_version'").all())
            owned_objects = set(connection.exec_driver_sql(
                "SELECT type,name,tbl_name,sql FROM sqlite_master "
                "WHERE tbl_name IN (?,?) AND name NOT LIKE 'sqlite_%'",
                (EDITION_TABLE, SOURCES_TABLE)).all())
            self.assertEqual(after_objects - before_objects, owned_objects)

    def test_empty_upgrade_and_downgrade_drop_only_edition_tables_and_owned_objects(self):
        self._upgrade_to_b1_with_existing_editorial()
        before_rows = self._snapshot_existing_rows()
        self._upgrade()
        with self.migration.engine.connect() as connection:
            before_tables = set(inspect(connection).get_table_names())
            before_owned_objects = set(connection.exec_driver_sql(
                "SELECT type,name,tbl_name FROM sqlite_master "
                "WHERE tbl_name IN (?,?)", (EDITION_TABLE, SOURCES_TABLE)).all())
            self.assertEqual(connection.exec_driver_sql(
                f'SELECT count(*) FROM {EDITION_TABLE}').scalar_one(), 0)
            self.assertEqual(connection.exec_driver_sql(
                f'SELECT count(*) FROM {SOURCES_TABLE}').scalar_one(), 0)

        self._downgrade_to_b1()

        with self.migration.engine.connect() as connection:
            after_tables = set(inspect(connection).get_table_names())
            self.assertEqual(before_tables - after_tables, EDITION_TABLES)
            self.assertEqual(after_tables - before_tables, set())
            self.assertEqual(connection.exec_driver_sql(
                'SELECT version_num FROM alembic_version').scalar_one(), DOWN_REVISION)
            after_owned_objects = set(connection.exec_driver_sql(
                "SELECT type,name,tbl_name FROM sqlite_master "
                "WHERE tbl_name IN (?,?)", (EDITION_TABLE, SOURCES_TABLE)).all())
            self.assertEqual(before_owned_objects - after_owned_objects,
                             before_owned_objects)
            self.assertEqual(after_owned_objects, set())
            self.assertEqual(connection.exec_driver_sql('PRAGMA foreign_key_check').all(), [])
            self.assertEqual(self._snapshot_existing_rows(), before_rows)

    def test_downgrade_refuses_current_edition_and_sources_without_dropping_data(self):
        owner = self._upgrade_to_b1_with_existing_editorial()
        self._upgrade()
        edition_id = str(uuid.UUID(int=9911))
        with self.migration.engine.begin() as connection:
            self._insert_edition(connection, owner, edition_id)
            self._insert_source(connection, edition_id)
        with self.assertRaisesRegex(RuntimeError, 'reviewed offline backup restoration'):
            self._downgrade_to_b1()
        with self.migration.engine.connect() as connection:
            self.assertEqual(connection.exec_driver_sql(
                'SELECT version_num FROM alembic_version').scalar_one(), REVISION)
            self.assertEqual(connection.exec_driver_sql(
                f'SELECT state FROM {EDITION_TABLE} WHERE id=?',
                (edition_id,)).scalar_one(), 'current')
            self.assertEqual(connection.exec_driver_sql(
                f'SELECT source_id FROM {SOURCES_TABLE} WHERE edition_id=?',
                (edition_id,)).scalar_one(), 'contribution-' + CONTRIBUTION)
            self.assertEqual(connection.exec_driver_sql('PRAGMA foreign_key_check').all(), [])

    def test_downgrade_refuses_invalidated_edition_even_when_sources_are_empty(self):
        owner = self._upgrade_to_b1_with_existing_editorial()
        self._upgrade()
        edition_id = str(uuid.UUID(int=9921))
        with self.migration.engine.begin() as connection:
            self._insert_edition(connection, owner, edition_id)
            connection.exec_driver_sql(
                f"UPDATE {EDITION_TABLE} SET state='source_invalidated', "
                'manuscript_json=NULL WHERE id=?', (edition_id,))
        with self.assertRaisesRegex(RuntimeError, 'reviewed offline backup restoration'):
            self._downgrade_to_b1()
        with self.migration.engine.connect() as connection:
            self.assertEqual(connection.exec_driver_sql(
                'SELECT version_num FROM alembic_version').scalar_one(), REVISION)
            self.assertEqual(connection.exec_driver_sql(
                f'SELECT state,manuscript_json FROM {EDITION_TABLE} WHERE id=?',
                (edition_id,)).one(), ('source_invalidated', None))
            self.assertEqual(connection.exec_driver_sql(
                f'SELECT count(*) FROM {SOURCES_TABLE}').scalar_one(), 0)
            self.assertEqual(connection.exec_driver_sql('PRAGMA foreign_key_check').all(), [])

    def test_interrupted_upgrade_rolls_back_both_tables_and_preserves_all_b1_rows(self):
        self._upgrade_to_b1_with_existing_editorial()
        before_rows = self._snapshot_existing_rows()

        def interrupt(_conn, _cursor, statement, _parameters, _context, _executemany):
            if statement.lstrip().startswith(f'CREATE TABLE {SOURCES_TABLE}'):
                raise RuntimeError('Synthetic edition migration interruption')

        event.listen(self.migration.engine, 'before_cursor_execute', interrupt)
        try:
            with self.assertRaisesRegex(RuntimeError, 'Synthetic edition migration interruption'):
                self._upgrade()
        finally:
            event.remove(self.migration.engine, 'before_cursor_execute', interrupt)

        with self.migration.engine.connect() as connection:
            self.assertEqual(connection.exec_driver_sql(
                'SELECT version_num FROM alembic_version').scalar_one(), DOWN_REVISION)
            self.assertFalse(EDITION_TABLES & set(inspect(connection).get_table_names()))
            self.assertEqual(self._snapshot_existing_rows(), before_rows)
            self.assertEqual(connection.exec_driver_sql('PRAGMA foreign_key_check').all(), [])


if __name__ == '__main__':
    unittest.main()
