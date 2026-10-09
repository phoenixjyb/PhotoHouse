"""Synthetic-only checks for additive, default-off editorial tables."""
from pathlib import Path
from dataclasses import asdict
import json
import sys
import unittest
import uuid

from sqlalchemy import (Column, Integer, MetaData, Table, Text, create_engine,
                        inspect)
from sqlalchemy.exc import IntegrityError
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from app.access.memory_book_editorial_schema import (  # noqa: E402
    BOOK_TABLE, EDITORIAL_REVISION, MAX_TRANSITION_JSON_BYTES, REFS_TABLE,
    add_book_editorial_tables)
from app.access.memory_book_editorial_contract import (  # noqa: E402
    ChildRevision, SourceIdentity, parse_mutation)


def parents(metadata):
    Table('access_memory_book_revisions', metadata,
          Column('book_id', Text, primary_key=True),
          Column('revision', Integer, primary_key=True))
    Table('access_memory_revisions', metadata,
          Column('story_id', Text, primary_key=True),
          Column('revision', Integer, primary_key=True))
    Table('access_memory_contributions', metadata,
          Column('id', Text, primary_key=True))


class MemoryBookEditorialSchemaTests(unittest.TestCase):
    def setUp(self):
        self.metadata = MetaData()
        parents(self.metadata)
        self.editorial, self.refs = add_book_editorial_tables(self.metadata)
        self.engine = create_engine('sqlite:///:memory:')
        self.addCleanup(self.engine.dispose)
        with self.engine.begin() as connection:
            connection.exec_driver_sql('PRAGMA foreign_keys=ON')
        self.metadata.create_all(self.engine)

    def seed(self):
        with self.engine.begin() as connection:
            connection.exec_driver_sql("INSERT INTO access_memory_book_revisions VALUES ('b',1)")
            connection.exec_driver_sql("INSERT INTO access_memory_revisions VALUES ('s',3)")
            connection.exec_driver_sql("INSERT INTO access_memory_contributions VALUES ('c')")
            connection.exec_driver_sql("INSERT INTO access_memory_book_editorial VALUES "
                "('b',1,'[{\"story_id\":\"s\",\"revision\":3}]','[]','current')")
            connection.exec_driver_sql("INSERT INTO access_memory_book_editorial_refs "
                "VALUES ('b',1,'introduction',0,'s',3,'chapter-1','c')")

    def test_additive_revision_and_tables_do_not_store_raw_sources(self):
        self.assertEqual(EDITORIAL_REVISION, 'b1d7e4a9c230')
        self.assertNotIn(BOOK_TABLE, {'access_memory_books', 'access_memory_book_revisions'})
        self.assertEqual(set(self.editorial.c.keys()), {
            'book_id', 'book_revision', 'children_json', 'transitions_json', 'state'})
        self.assertFalse({'original_text', 'transcript', 'audio', 'recording'} &
                         set(self.editorial.c.keys()) | {'original_text', 'transcript', 'audio', 'recording'} &
                         set(self.refs.c.keys()))

    def test_composite_revision_foreign_keys_and_valid_rows(self):
        self.seed()
        with self.engine.connect() as connection:
            self.assertEqual(connection.exec_driver_sql('PRAGMA foreign_key_check').all(), [])
            fks = inspect(connection).get_foreign_keys(BOOK_TABLE)
            self.assertTrue(any(fk['constrained_columns'] == ['book_id', 'book_revision'] and
                fk['referred_columns'] == ['book_id', 'revision'] for fk in fks))
            self.assertEqual(connection.exec_driver_sql(
                'SELECT state FROM access_memory_book_editorial').scalar_one(), 'current')

    def test_snapshot_and_refs_are_immutable_except_one_way_invalidation(self):
        self.seed()
        with self.assertRaises(IntegrityError):
            with self.engine.begin() as connection:
                connection.exec_driver_sql(
                    "UPDATE access_memory_book_editorial SET transitions_json='[1]' "
                    "WHERE book_id='b'")
        with self.engine.begin() as connection:
            connection.exec_driver_sql(
                "UPDATE access_memory_book_editorial SET state='source_invalidated' "
                "WHERE book_id='b'")
        with self.assertRaises(IntegrityError):
            with self.engine.begin() as connection:
                connection.exec_driver_sql(
                    "UPDATE access_memory_book_editorial SET state='current' WHERE book_id='b'")
        with self.assertRaises(IntegrityError):
            with self.engine.begin() as connection:
                connection.exec_driver_sql(
                    "UPDATE access_memory_book_editorial_refs SET ordinal=1 WHERE book_id='b'")

    def test_valid_contract_with_multibyte_transition_roundtrips_with_escaped_json(self):
        story_ids = [str(uuid.UUID(int=31)), str(uuid.UUID(int=32))]
        contribution_id = str(uuid.UUID(int=131))
        children = tuple(ChildRevision(story_id, '3') for story_id in story_ids)
        source = SourceIdentity(story_ids[0], '3', 'chapter-1', contribution_id)
        long_text = '界' * 1500  # 4,500 UTF-8 bytes: contract-valid, over 4 KiB.
        body = {
            'version': 1,
            'revision': '1',
            'mutation_id': str(uuid.UUID(int=501)),
            'children': [{'story_id': child.story_id, 'revision': child.revision}
                         for child in children],
            'introduction_source_refs': [],
            'transitions': [{
                'left_story_id': story_ids[0], 'right_story_id': story_ids[1],
                'text': long_text,
                'source_refs': [{'story_id': source.story_id,
                    'story_revision': source.story_revision,
                    'chapter_id': source.chapter_id,
                    'contribution_id': source.contribution_id}],
            }],
        }
        parsed = parse_mutation(json.dumps(body, ensure_ascii=False, separators=(',', ':')),
            current_book_revision='1', current_children=children,
            eligible_sources=frozenset({source}))
        transition_json = json.dumps([asdict(item) for item in parsed.transitions],
                                     ensure_ascii=True, separators=(',', ':'))
        self.assertGreater(len(long_text.encode('utf-8')), 4096)
        self.assertGreater(len(transition_json.encode('utf-8')), len(long_text.encode('utf-8')))
        self.assertLessEqual(len(transition_json.encode('utf-8')), MAX_TRANSITION_JSON_BYTES)

        with self.engine.begin() as connection:
            connection.exec_driver_sql(
                'INSERT INTO access_memory_book_revisions VALUES (?,1)', (str(uuid.UUID(int=701)),))
            connection.exec_driver_sql(
                'INSERT INTO access_memory_revisions VALUES (?,3)', (story_ids[0],))
            connection.exec_driver_sql(
                'INSERT INTO access_memory_revisions VALUES (?,3)', (story_ids[1],))
            connection.exec_driver_sql(
                'INSERT INTO access_memory_contributions VALUES (?)', (contribution_id,))
            connection.exec_driver_sql(
                'INSERT INTO access_memory_book_editorial '
                '(book_id,book_revision,children_json,transitions_json,state) '
                'VALUES (?,1,?,?,?)',
                (str(uuid.UUID(int=701)), json.dumps([asdict(child) for child in parsed.children]),
                 transition_json, 'current'))
            connection.exec_driver_sql(
                'INSERT INTO access_memory_book_editorial_refs VALUES (?,1,?,?,?,?,?,?)',
                (str(uuid.UUID(int=701)), 'transition-00', 0, source.story_id,
                 int(source.story_revision), source.chapter_id, source.contribution_id))
            stored = connection.exec_driver_sql(
                'SELECT transitions_json FROM access_memory_book_editorial').scalar_one()
        decoded = json.loads(stored)
        self.assertEqual(decoded[0]['text'], long_text)
        self.assertEqual(decoded[0]['source_refs'][0]['contribution_id'], contribution_id)

    def test_parent_revision_binding_rejects_missing_book_story_or_contribution(self):
        cases = [
            ("INSERT INTO access_memory_book_editorial VALUES ('missing',1,'[]','[]','current')",),
            ("INSERT INTO access_memory_book_editorial_refs VALUES "
             "('b',1,'transition-00',0,'missing',3,'chapter-1','c')",),
            ("INSERT INTO access_memory_book_editorial_refs VALUES "
             "('b',1,'transition-00',0,'s',3,'chapter-1','missing')",),
        ]
        self.seed()
        for (statement,) in cases:
            with self.subTest(statement=statement):
                with self.assertRaises(IntegrityError):
                    with self.engine.begin() as connection:
                        connection.exec_driver_sql(statement)

    def test_bounds_state_section_and_section_ordinal_uniqueness(self):
        self.seed()
        bad = [
            "INSERT INTO access_memory_book_editorial VALUES ('b',0,'[]','[]','current')",
            "INSERT INTO access_memory_book_editorial VALUES ('b',2,'[]','[]','invalid')",
            "INSERT INTO access_memory_book_editorial VALUES ('b',2,'','[]','current')",
            "INSERT INTO access_memory_book_editorial VALUES ('b',2,'[]','" + "x" * 4097 + "','current')",
            "INSERT INTO access_memory_book_editorial_refs VALUES ('b',1,'other',0,'s',3,'c','c')",
            "INSERT INTO access_memory_book_editorial_refs VALUES ('b',1,'introduction',0,'s',3,'chapter-1','c')",
            "INSERT INTO access_memory_book_editorial_refs VALUES ('b',1,'transition-00',12,'s',3,'chapter-1','c')",
        ]
        for statement in bad:
            with self.subTest(statement=statement[:90]):
                with self.assertRaises(IntegrityError):
                    with self.engine.begin() as connection:
                        connection.exec_driver_sql(statement)

    def test_builder_is_exactly_idempotent_and_rejects_partial_or_drifted_schema(self):
        again = add_book_editorial_tables(self.metadata)
        self.assertIs(again[0], self.editorial)
        self.assertIs(again[1], self.refs)

        partial = MetaData()
        parents(partial)
        from sqlalchemy import Column, Text
        Table(BOOK_TABLE, partial, Column('book_id', Text, primary_key=True))
        with self.assertRaisesRegex(ValueError, 'partial_installation'):
            add_book_editorial_tables(partial)

        drifted = MetaData()
        parents(drifted)
        add_book_editorial_tables(drifted)
        drifted.tables[BOOK_TABLE].append_column(Column('unexpected', Text))
        with self.assertRaisesRegex(ValueError, 'definition_mismatch'):
            add_book_editorial_tables(drifted)

    def test_creation_does_not_change_existing_parent_rows(self):
        old = MetaData()
        parents(old)
        old.create_all(self.engine)
        with self.engine.begin() as connection:
            connection.exec_driver_sql("INSERT INTO access_memory_book_revisions VALUES ('old',4)")
        fresh = MetaData()
        parents(fresh)
        add_book_editorial_tables(fresh)
        fresh.create_all(self.engine)
        with self.engine.connect() as connection:
            self.assertEqual(connection.exec_driver_sql(
                'SELECT book_id,revision FROM access_memory_book_revisions').all(), [('old', 4)])

    def test_historical_a0_upgrade_does_not_create_editorial_tables(self):
        backend = ROOT / 'backend'
        if str(backend) not in sys.path:
            sys.path.insert(0, str(backend))
            self.addCleanup(lambda: sys.path.remove(str(backend)))
        cfg = Config()
        cfg.set_main_option('script_location', str(backend / 'migrations'))
        revisions = ScriptDirectory.from_config(cfg)
        self.assertIn('b1d7e4a9c230', {revision.revision for revision in revisions.walk_revisions()})
        engine = create_engine('sqlite:///:memory:')
        self.addCleanup(engine.dispose)
        with engine.begin() as connection:
            cfg.attributes['connection'] = connection
            command.upgrade(cfg, 'a0c9d2e4f817')
        names = set(inspect(engine).get_table_names())
        self.assertNotIn(BOOK_TABLE, names)
        self.assertNotIn(REFS_TABLE, names)


if __name__ == '__main__':
    unittest.main()
