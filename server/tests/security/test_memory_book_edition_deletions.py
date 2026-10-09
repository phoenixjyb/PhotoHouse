"""Synthetic erasure storage checks; no primary/family database is opened."""
import json
from pathlib import Path
import sys
import unittest
import uuid

from sqlalchemy import Column, Integer, MetaData, Table, Text, create_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
from app.access.memory_book_edition_schema import add_book_edition_tables, EDITION_TABLE, SOURCES_TABLE
from app.access.memory_book_edition_deletions import (
    EditionDeletionError, EditionDeletionCounts,
    invalidate_editions_for_contribution, verify_edition_schema,
)


def ident(n):
    return str(uuid.UUID(int=n))


class MemoirEditionDeletionTests(unittest.TestCase):
    def setUp(self):
        metadata = MetaData()
        Table('access_memory_books', metadata, Column('id', Text, primary_key=True), Column('library_id', Text))
        Table('access_memory_book_revisions', metadata, Column('book_id', Text, primary_key=True), Column('revision', Integer, primary_key=True))
        Table('access_libraries', metadata, Column('id', Text, primary_key=True))
        Table('access_accounts', metadata, Column('id', Text, primary_key=True))
        Table('access_memory_stories', metadata, Column('id', Text, primary_key=True))
        Table('access_memory_contributions', metadata, Column('id', Text, primary_key=True), Column('story_id', Text))
        add_book_edition_tables(metadata)
        engine = create_engine('sqlite://')
        self.addCleanup(engine.dispose)
        metadata.create_all(engine)
        raw = engine.raw_connection()
        self.addCleanup(raw.close)
        self.db = raw.driver_connection
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('PRAGMA secure_delete=ON')
        self.db.execute("INSERT INTO access_accounts VALUES(?)", (ident(1),))
        for library in ('family-a', 'family-b'):
            self.db.execute('INSERT INTO access_libraries VALUES(?)', (library,))
        for book, library in ((ident(2), 'family-a'), (ident(3), 'family-b')):
            self.db.execute('INSERT INTO access_memory_books VALUES(?,?)', (book, library))
            for revision in (1, 2):
                self.db.execute('INSERT INTO access_memory_book_revisions VALUES(?,?)', (book, revision))
        for story in (ident(4), ident(5)):
            self.db.execute('INSERT INTO access_memory_stories VALUES(?)', (story,))
        for cid, story in ((ident(6), ident(4)), (ident(7), ident(4)), (ident(8), ident(5))):
            self.db.execute('INSERT INTO access_memory_contributions VALUES(?,?)', (cid, story))
        self.db.commit()

    def edition(self, number, *, revision=1, library='family-a', book=None, cid=ident(6), story=ident(4)):
        book = book or (ident(2) if library == 'family-a' else ident(3))
        values = (ident(number), book, revision, library, ident(1), ident(1000 + number),
            'a' * 64, 'b' * 64, 'stories', json.dumps([{'id': story, 'revision': '1'}]),
            json.dumps({'title': 'DEPENDENT GENERATED WORDS', 'chapters': [], 'questions': []}),
            ident(2000 + number), 'c' * 64, 10, 'current')
        self.db.execute(f'INSERT INTO {EDITION_TABLE} VALUES({",".join("?" for _ in values)})', values)
        self.db.execute(f'''INSERT INTO {SOURCES_TABLE}
            (edition_id,ordinal,source_id,kind,asset_id,source_digest,chapter_ids_json,contribution_id,contribution_story_id)
            VALUES(?,0,?,'family',NULL,?,'[]',?,?)''',
            (ident(number), 'contribution-' + cid, 'd' * 64, cid, story))
        self.db.execute(f'''INSERT INTO {SOURCES_TABLE}
            (edition_id,ordinal,source_id,kind,asset_id,source_digest,chapter_ids_json,contribution_id,contribution_story_id)
            VALUES(?,1,'editorial-extra','editorial',NULL,?,'[]',NULL,NULL)''', (ident(number), 'e' * 64))
        self.db.commit()
        return ident(number)

    def erase(self, **kwargs):
        return invalidate_editions_for_contribution(self.db,
            kwargs.get('cid', ident(6)), kwargs.get('story', ident(4)), kwargs.get('library', 'family-a'))

    def test_exact_schema_is_verified_and_no_source_citation_is_required_for_purge(self):
        verify_edition_schema(self.db)
        first = self.edition(20)
        second = self.edition(21, revision=2)
        untouched = self.edition(22, cid=ident(7))
        other = self.edition(23, library='family-b', cid=ident(8), story=ident(5))
        self.db.execute('BEGIN IMMEDIATE')
        counts = self.erase()
        self.assertEqual(EditionDeletionCounts(2, 4), counts)
        for eid in (first, second):
            self.assertEqual(('source_invalidated', None), self.db.execute(
                f'SELECT state,manuscript_json FROM {EDITION_TABLE} WHERE id=?', (eid,)).fetchone())
            self.assertEqual(0, self.db.execute(f'SELECT count(*) FROM {SOURCES_TABLE} WHERE edition_id=?', (eid,)).fetchone()[0])
        for eid in (untouched, other):
            self.assertIn('DEPENDENT GENERATED WORDS', self.db.execute(
                f'SELECT manuscript_json FROM {EDITION_TABLE} WHERE id=?', (eid,)).fetchone()[0])
        self.assertEqual(EditionDeletionCounts(), self.erase())
        self.assertTrue(self.db.in_transaction)
        self.db.commit()

    def test_foreign_keys_disabled_missing_parent_copy_still_scrubs_historical_prose(self):
        eid = self.edition(20)
        self.db.execute('PRAGMA foreign_keys=OFF')
        self.db.execute('DELETE FROM access_memory_books WHERE id=?', (ident(2),))
        self.db.execute('DELETE FROM access_memory_contributions WHERE id=?', (ident(6),))
        self.db.commit()
        self.db.execute('BEGIN IMMEDIATE')
        self.assertEqual(EditionDeletionCounts(1, 2), self.erase())
        self.assertIsNone(self.db.execute(f'SELECT manuscript_json FROM {EDITION_TABLE} WHERE id=?', (eid,)).fetchone()[0])
        self.db.rollback()
        self.assertIsNotNone(self.db.execute(f'SELECT manuscript_json FROM {EDITION_TABLE} WHERE id=?', (eid,)).fetchone()[0])

    def test_transaction_secure_delete_and_canonical_scope_are_required(self):
        self.edition(20)
        with self.assertRaises(EditionDeletionError): self.erase()
        self.db.execute('BEGIN IMMEDIATE')
        with self.assertRaises(EditionDeletionError): self.erase(cid='bad')
        self.db.rollback()
        self.db.execute('PRAGMA secure_delete=OFF')
        self.db.execute('BEGIN IMMEDIATE')
        with self.assertRaises(EditionDeletionError): self.erase()
        self.db.rollback()

    def test_missing_or_replaced_immutability_trigger_refuses_mutation(self):
        eid = self.edition(20)
        self.db.execute('DROP TRIGGER trg_memory_book_edition_immutable')
        self.db.commit()
        self.db.execute('BEGIN IMMEDIATE')
        with self.assertRaises(EditionDeletionError): self.erase()
        self.assertEqual('current', self.db.execute(f'SELECT state FROM {EDITION_TABLE} WHERE id=?', (eid,)).fetchone()[0])
        self.db.rollback()
        self.db.execute(f'''CREATE TRIGGER trg_memory_book_edition_immutable BEFORE UPDATE ON {EDITION_TABLE}
            BEGIN SELECT 1; END''')
        self.db.commit()
        self.db.execute('BEGIN IMMEDIATE')
        with self.assertRaises(EditionDeletionError): self.erase()
        self.db.rollback()

    def test_partial_schema_or_missing_required_index_fails_closed(self):
        self.edition(20)
        self.db.execute('DROP INDEX ix_memory_book_edition_source_contribution')
        self.db.commit()
        self.db.execute('BEGIN IMMEDIATE')
        with self.assertRaises(EditionDeletionError): self.erase()
        self.db.rollback()
        self.db.execute(f'DROP TABLE {SOURCES_TABLE}')
        self.db.commit()
        self.db.execute('BEGIN IMMEDIATE')
        with self.assertRaises(EditionDeletionError): self.erase()
        self.db.rollback()

    def test_legacy_schema_no_op_still_does_not_own_the_transaction(self):
        self.db.execute(f'DROP TABLE {SOURCES_TABLE}')
        self.db.execute(f'DROP TABLE {EDITION_TABLE}')
        self.db.commit()
        self.db.execute('BEGIN IMMEDIATE')
        self.assertEqual(EditionDeletionCounts(), self.erase())
        self.assertTrue(self.db.in_transaction)
        self.db.rollback()

    def test_wrong_library_or_story_does_not_scrub_an_unrelated_edition(self):
        eid = self.edition(20)
        self.db.execute('BEGIN IMMEDIATE')
        self.assertEqual(EditionDeletionCounts(), self.erase(library='family-b'))
        self.assertEqual(EditionDeletionCounts(), self.erase(story=ident(5)))
        self.assertIsNotNone(self.db.execute(f'SELECT manuscript_json FROM {EDITION_TABLE} WHERE id=?', (eid,)).fetchone()[0])
        self.db.rollback()


if __name__ == '__main__':
    unittest.main()
