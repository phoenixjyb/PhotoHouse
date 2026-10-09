"""Synthetic SQLite checks for the future reviewed-edition schema builder."""
from pathlib import Path
import json
import sys
import unittest
import uuid

from sqlalchemy import (Column, ForeignKey, Integer, MetaData, Table, Text,
                        create_engine, event, inspect)
from sqlalchemy.exc import IntegrityError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))

from app.access.memory_book_edition_schema import (  # noqa: E402
    EDITION_TABLE,
    MAX_CHILDREN_JSON_BYTES,
    MAX_CHAPTER_IDS_JSON_BYTES,
    MAX_MANUSCRIPT_JSON_BYTES,
    MAX_SOURCE_ROWS,
    MAX_SOURCE_ID_BYTES,
    SOURCES_TABLE,
    add_book_edition_tables,
    sqlite_edition_schema_contract,
)


def ident(number):
    return str(uuid.UUID(int=number))


def parents(metadata):
    Table('access_accounts', metadata,
          Column('id', Text, primary_key=True))
    Table('access_libraries', metadata,
          Column('id', Text, primary_key=True))
    Table('access_memory_books', metadata,
          Column('id', Text, primary_key=True),
          Column('library_id', Text, ForeignKey('access_libraries.id'), nullable=False))
    Table('access_memory_book_revisions', metadata,
          Column('book_id', Text, ForeignKey('access_memory_books.id', ondelete='CASCADE'),
                 primary_key=True),
          Column('revision', Integer, primary_key=True))
    Table('access_memory_stories', metadata,
          Column('id', Text, primary_key=True))
    Table('access_memory_contributions', metadata,
          Column('id', Text, primary_key=True),
          Column('story_id', Text, ForeignKey('access_memory_stories.id'), nullable=False))


class MemoryBookEditionSchemaTests(unittest.TestCase):
    def setUp(self):
        self.metadata = MetaData()
        parents(self.metadata)
        self.editions, self.sources = add_book_edition_tables(self.metadata)
        self.engine = create_engine('sqlite:///:memory:')

        @event.listens_for(self.engine, 'connect')
        def enable_foreign_keys(dbapi_connection, _record):
            dbapi_connection.execute('PRAGMA foreign_keys=ON')

        self.addCleanup(self.engine.dispose)
        self.metadata.create_all(self.engine)
        self.book_id = ident(1)
        self.library_id = 'library-a'
        self.account_id = ident(2)
        self.story_id = ident(3)
        self.contribution_id = ident(4)
        self.edition_id = ident(5)
        with self.engine.begin() as connection:
            connection.execute(self.metadata.tables['access_accounts'].insert(),
                               {'id': self.account_id})
            connection.execute(self.metadata.tables['access_libraries'].insert(),
                               {'id': self.library_id})
            connection.execute(self.metadata.tables['access_memory_books'].insert(),
                               {'id': self.book_id, 'library_id': self.library_id})
            connection.execute(self.metadata.tables['access_memory_book_revisions'].insert(),
                               {'book_id': self.book_id, 'revision': 7})
            connection.execute(self.metadata.tables['access_memory_stories'].insert(),
                               {'id': self.story_id})
            connection.execute(self.metadata.tables['access_memory_contributions'].insert(),
                               {'id': self.contribution_id, 'story_id': self.story_id})

    def edition_values(self, **overrides):
        value = {
            'id': self.edition_id,
            'book_id': self.book_id,
            'book_revision': 7,
            'library_id': self.library_id,
            'creator_account_id': self.account_id,
            'originating_job_id': ident(6),
            'job_result_sha256': 'a' * 64,
            'source_fingerprint': 'b' * 64,
            'context_profile': 'stories',
            'children_json': json.dumps([{'id': self.story_id, 'revision': '3'}],
                                        separators=(',', ':')),
            'manuscript_json': json.dumps({'version': 1, 'title': 'Family'},
                                          ensure_ascii=True, separators=(',', ':')),
            'mutation_id': ident(7),
            'request_digest': 'c' * 64,
            'created_at': 100,
            'state': 'current',
        }
        value.update(overrides)
        return value

    def source_values(self, edition_id=None, **overrides):
        value = {
            'edition_id': self.edition_id if edition_id is None else edition_id,
            'ordinal': 0,
            'source_id': 'contribution-' + self.contribution_id,
            'kind': 'family',
            'asset_id': None,
            'source_digest': 'd' * 64,
            'chapter_ids_json': json.dumps([self.story_id + '-chapter-1'],
                                           separators=(',', ':')),
            'contribution_id': self.contribution_id,
            'contribution_story_id': self.story_id,
        }
        value.update(overrides)
        return value

    def insert_edition(self, connection, **overrides):
        connection.execute(self.editions.insert(), self.edition_values(**overrides))

    def test_required_schema_columns_foreign_keys_and_indexes(self):
        self.assertEqual(set(self.editions.c.keys()), {
            'id', 'book_id', 'book_revision', 'library_id', 'creator_account_id',
            'originating_job_id', 'job_result_sha256', 'source_fingerprint',
            'context_profile', 'children_json', 'manuscript_json', 'mutation_id',
            'request_digest', 'created_at', 'state'})
        self.assertEqual(set(self.sources.c.keys()), {
            'edition_id', 'ordinal', 'source_id', 'kind', 'asset_id',
            'source_digest', 'chapter_ids_json', 'contribution_id',
            'contribution_story_id'})
        with self.engine.connect() as connection:
            edition_fks = inspect(connection).get_foreign_keys(EDITION_TABLE)
            self.assertTrue(any(fk['constrained_columns'] == ['book_id', 'book_revision']
                and fk['referred_columns'] == ['book_id', 'revision'] for fk in edition_fks))
            source_fks = inspect(connection).get_foreign_keys(SOURCES_TABLE)
            self.assertTrue(any(fk['constrained_columns'] == ['contribution_id']
                and fk['referred_table'] == 'access_memory_contributions'
                for fk in source_fks))
            indexes = {item['name'] for item in inspect(connection).get_indexes(EDITION_TABLE)}
            self.assertIn('ix_memory_book_edition_book_revision', indexes)
            self.assertIn('ix_memory_book_edition_library_created', indexes)
            indexes = {item['name'] for item in inspect(connection).get_indexes(SOURCES_TABLE)}
            self.assertIn('ix_memory_book_edition_source_contribution', indexes)

    def test_sqlite_schema_contract_is_deterministic_and_matches_created_triggers(self):
        first = sqlite_edition_schema_contract()
        second = sqlite_edition_schema_contract()
        self.assertEqual(first, second)
        self.assertTrue(all(len(item) == 3 for item in first))
        trigger_sql = {name: sql for kind, name, sql in first if kind == 'trigger'}
        self.assertIn('source_invalidated', trigger_sql['trg_memory_book_edition_immutable'])
        self.assertIn(SOURCES_TABLE,
                      trigger_sql['trg_memory_book_edition_sources_immutable'])
        self.assertEqual({kind for kind, _name, _sql in first},
                         {'table', 'index', 'trigger'})
        with self.engine.connect() as connection:
            actual = dict(connection.exec_driver_sql(
                "SELECT name,sql FROM sqlite_master WHERE type='trigger'").all())
        self.assertEqual(set(actual), set(trigger_sql))
        for name, sql in trigger_sql.items():
            normalized_actual = actual[name].replace('CREATE TRIGGER ', 'CREATE TRIGGER IF NOT EXISTS ', 1)
            self.assertEqual(normalized_actual, sql)

    def test_valid_edition_and_full_contribution_provenance_insert(self):
        with self.engine.begin() as connection:
            self.insert_edition(connection)
            connection.execute(self.sources.insert(), self.source_values())
            self.assertEqual(connection.exec_driver_sql(
                f'SELECT state FROM {EDITION_TABLE}').scalar_one(), 'current')
            self.assertEqual(connection.exec_driver_sql(
                f'SELECT contribution_story_id FROM {SOURCES_TABLE}').scalar_one(),
                self.story_id)

    def test_edition_metadata_and_prose_are_immutable_except_one_way_scrub(self):
        with self.engine.begin() as connection:
            self.insert_edition(connection)
            connection.execute(self.sources.insert(), self.source_values())

        for column, value in (('book_revision', 8), ('originating_job_id', ident(8)),
                              ('manuscript_json', '{"title":"changed"}')):
            with self.subTest(column=column):
                with self.assertRaises(IntegrityError):
                    with self.engine.begin() as connection:
                        connection.exec_driver_sql(
                            f'UPDATE {EDITION_TABLE} SET {column}=? WHERE id=?',
                            (value, self.edition_id))

        with self.engine.begin() as connection:
            connection.exec_driver_sql(
                f"UPDATE {EDITION_TABLE} SET state='source_invalidated', manuscript_json=NULL "
                'WHERE id=?', (self.edition_id,))
            connection.exec_driver_sql(
                f'DELETE FROM {SOURCES_TABLE} WHERE edition_id=?', (self.edition_id,))
            self.assertIsNone(connection.exec_driver_sql(
                f'SELECT manuscript_json FROM {EDITION_TABLE} WHERE id=?',
                (self.edition_id,)).scalar_one())

        for statement, parameters in (
            (f"UPDATE {EDITION_TABLE} SET state='current', manuscript_json='{{}}' WHERE id=?",
             (self.edition_id,)),
            (f"UPDATE {EDITION_TABLE} SET created_at=101 WHERE id=?", (self.edition_id,)),
        ):
            with self.assertRaises(IntegrityError):
                with self.engine.begin() as connection:
                    connection.exec_driver_sql(statement, parameters)

    def test_source_rows_are_immutable_and_contribution_delete_cascades_after_scrub(self):
        with self.engine.begin() as connection:
            self.insert_edition(connection)
            connection.execute(self.sources.insert(), self.source_values())
        with self.assertRaises(IntegrityError):
            with self.engine.begin() as connection:
                connection.exec_driver_sql(
                    f"UPDATE {SOURCES_TABLE} SET source_id='rewritten' WHERE edition_id=?",
                    (self.edition_id,))

        with self.engine.begin() as connection:
            connection.exec_driver_sql(
                f"UPDATE {EDITION_TABLE} SET state='source_invalidated', manuscript_json=NULL "
                'WHERE id=?', (self.edition_id,))
            connection.exec_driver_sql(
                'DELETE FROM access_memory_contributions WHERE id=?',
                (self.contribution_id,))
            self.assertEqual(connection.exec_driver_sql(
                f'SELECT count(*) FROM {SOURCES_TABLE}').scalar_one(), 0)
            self.assertEqual(connection.exec_driver_sql(
                f'SELECT state FROM {EDITION_TABLE} WHERE id=?',
                (self.edition_id,)).scalar_one(), 'source_invalidated')

    def test_state_bounds_context_digests_and_contribution_pair(self):
        invalid_editions = [
            {'book_revision': 0},
            {'created_at': -1},
            {'context_profile': 'unknown'},
            {'job_result_sha256': 'A' * 64},
            {'source_fingerprint': 'b' * 63},
            {'request_digest': 'g' * 64},
            {'state': 'source_invalidated'},
            {'manuscript_json': None},
        ]
        for overrides in invalid_editions:
            with self.subTest(overrides=overrides):
                with self.assertRaises(IntegrityError):
                    with self.engine.begin() as connection:
                        self.insert_edition(connection, **overrides)

        with self.engine.begin() as connection:
            self.insert_edition(connection)
        invalid_sources = [
            {'ordinal': MAX_SOURCE_ROWS},
            {'source_id': 'x' * (MAX_SOURCE_ID_BYTES + 1)},
            {'kind': 'unknown'},
            {'source_digest': 'D' * 64},
            {'contribution_id': None},
        ]
        for overrides in invalid_sources:
            with self.subTest(source_overrides=overrides):
                with self.assertRaises(IntegrityError):
                    with self.engine.begin() as connection:
                        connection.execute(self.sources.insert(), self.source_values(**overrides))

    def test_exact_json_byte_bounds_for_children_manuscript_and_source_chapters(self):
        children = '[' + (' ' * (MAX_CHILDREN_JSON_BYTES - 2)) + ']'
        manuscript_text = 'a' * (MAX_MANUSCRIPT_JSON_BYTES - len('{"x":""}'))
        manuscript = json.dumps({'x': manuscript_text}, ensure_ascii=True,
                                separators=(',', ':'))
        chapter_ids = '[' + (' ' * (MAX_CHAPTER_IDS_JSON_BYTES - 2)) + ']'
        self.assertEqual(len(children.encode('utf-8')), MAX_CHILDREN_JSON_BYTES)
        self.assertEqual(len(manuscript.encode('ascii')), MAX_MANUSCRIPT_JSON_BYTES)
        self.assertEqual(len(chapter_ids.encode('utf-8')), MAX_CHAPTER_IDS_JSON_BYTES)

        with self.engine.begin() as connection:
            self.insert_edition(connection, children_json=children,
                                manuscript_json=manuscript)
            connection.execute(self.sources.insert(), self.source_values(
                source_id='s' * MAX_SOURCE_ID_BYTES,
                asset_id='a' * 128, chapter_ids_json=chapter_ids,
                contribution_id=None, contribution_story_id=None))

        for number, overrides in (
            (8, {'children_json': children + ' '}),
            (9, {'manuscript_json': manuscript + ' '}),
        ):
            with self.assertRaises(IntegrityError):
                with self.engine.begin() as connection:
                    self.insert_edition(connection, id=ident(number),
                                        mutation_id=ident(number + 100), **overrides)
        with self.assertRaises(IntegrityError):
            with self.engine.begin() as connection:
                connection.execute(self.sources.insert(), self.source_values(
                    ordinal=1, source_id='over-chapter-limit',
                    chapter_ids_json=chapter_ids + ' ',
                    contribution_id=None, contribution_story_id=None))

    def test_reference_identity_uniqueness_and_foreign_keys(self):
        with self.engine.begin() as connection:
            self.insert_edition(connection)
            connection.execute(self.sources.insert(), self.source_values())
        bad = [
            self.source_values(ordinal=1),
            self.source_values(source_id='contribution-' + ident(11), ordinal=MAX_SOURCE_ROWS),
            self.source_values(source_id='contribution-' + ident(12),
                               ordinal=2,
                               contribution_id=ident(99), contribution_story_id=self.story_id),
            self.source_values(source_id='contribution-' + ident(13),
                               ordinal=3,
                               contribution_id=self.contribution_id,
                               contribution_story_id=ident(98)),
        ]
        for value in bad:
            with self.subTest(source=value):
                with self.assertRaises(IntegrityError):
                    with self.engine.begin() as connection:
                        connection.execute(self.sources.insert(), value)

    def test_builder_is_exactly_idempotent_and_rejects_partial_or_drifted_tables(self):
        again = add_book_edition_tables(self.metadata)
        self.assertIs(again[0], self.editions)
        self.assertIs(again[1], self.sources)

        partial = MetaData()
        parents(partial)
        Table(EDITION_TABLE, partial, Column('id', Text, primary_key=True))
        with self.assertRaisesRegex(ValueError, 'partial_installation'):
            add_book_edition_tables(partial)

        drifted = MetaData()
        parents(drifted)
        add_book_edition_tables(drifted)
        drifted.tables[EDITION_TABLE].append_column(Column('unexpected', Text))
        with self.assertRaisesRegex(ValueError, 'definition_mismatch'):
            add_book_edition_tables(drifted)

        missing_parent = MetaData()
        Table('access_memory_books', missing_parent, Column('id', Text, primary_key=True))
        with self.assertRaisesRegex(ValueError, 'prerequisite_missing'):
            add_book_edition_tables(missing_parent)


if __name__ == '__main__':
    unittest.main()
