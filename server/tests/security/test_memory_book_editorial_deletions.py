"""Synthetic-only tests for the future editorial deletion companion."""
from pathlib import Path
import json
import sys
import unittest
import uuid

from sqlalchemy import Column, Integer, MetaData, Table, Text, create_engine

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from app.access.memory_book_editorial_schema import (  # noqa: E402
    BOOK_TABLE, REFS_TABLE, add_book_editorial_tables)
from app.access.memory_book_editorial_deletions import (  # noqa: E402
    EditorialDeletionError, EditorialDeletionCounts, invalidate_for_contribution)


def ident(number):
    return str(uuid.UUID(int=number))


class EditorialDeletionTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        self.addCleanup(self.engine.dispose)
        metadata = MetaData()
        Table('access_memory_books', metadata,
              Column('id', Text, primary_key=True), Column('library_id', Text, nullable=False))
        Table('access_memory_book_revisions', metadata,
              Column('book_id', Text, primary_key=True),
              Column('revision', Integer, primary_key=True))
        Table('access_memory_revisions', metadata,
              Column('story_id', Text, primary_key=True),
              Column('revision', Integer, primary_key=True))
        Table('access_memory_contributions', metadata,
              Column('id', Text, primary_key=True))
        self.sidecar, self.refs = add_book_editorial_tables(metadata)
        metadata.create_all(self.engine)
        self.db = self.engine.raw_connection().driver_connection
        self.db.execute('PRAGMA foreign_keys=OFF')
        self.db.execute('PRAGMA secure_delete=ON')
        self.story = ident(11)
        self.foreign_story = ident(12)
        self.contribution = ident(101)
        self.other_contribution = ident(102)
        self.book = ident(201)
        self.other_book = ident(202)
        self.foreign_book = ident(203)
        self._seed()

    def _seed(self):
        db = self.db
        db.execute("INSERT INTO access_memory_books VALUES (?, 'library-a')", (self.book,))
        db.execute("INSERT INTO access_memory_books VALUES (?, 'library-a')", (self.other_book,))
        db.execute("INSERT INTO access_memory_books VALUES (?, 'library-b')", (self.foreign_book,))
        db.execute("INSERT INTO access_memory_contributions VALUES (?)", (self.contribution,))
        db.execute("INSERT INTO access_memory_contributions VALUES (?)", (self.other_contribution,))
        for story in (self.story, self.foreign_story):
            db.execute('INSERT INTO access_memory_revisions VALUES (?, 3)', (story,))
        for book, revisions in ((self.book, (1, 2, 3)),
                                 (self.other_book, (1,)),
                                 (self.foreign_book, (1,))):
            for revision in revisions:
                db.execute('INSERT INTO access_memory_book_revisions VALUES (?, ?)',
                           (book, revision))
                state = 'source_invalidated' if book == self.book and revision == 3 else 'current'
                children = json.dumps([{'story_id': self.story, 'revision': 3}])
                prose = json.dumps([{'left_story_id': self.story,
                    'right_story_id': self.foreign_story, 'text': 'authored transition',
                    'source_refs': []}])
                db.execute(f'INSERT INTO {BOOK_TABLE} VALUES (?, ?, ?, ?, ?)',
                           (book, revision, children, prose, state))
        # Target contribution in two current and one previously invalidated
        # historical revision, plus an orphan ref from an FK-off restored copy.
        for revision in (1, 2, 3):
            db.execute(f'INSERT INTO {REFS_TABLE} VALUES (?, ?, ?, 0, ?, 3, ?, ?)',
                (self.book, revision, 'transition-00', self.story, 'chapter-1', self.contribution))
        db.execute(f'INSERT INTO {REFS_TABLE} VALUES (?, 99, ?, 0, ?, 3, ?, ?)',
            (self.book, 'transition-00', self.story, 'chapter-1', self.contribution))
        # Unrelated source and foreign-library reference must remain intact.
        db.execute(f'INSERT INTO {REFS_TABLE} VALUES (?, 1, ?, 1, ?, 3, ?, ?)',
            (self.other_book, 'transition-00', self.story, 'chapter-2', self.other_contribution))
        db.execute(f'INSERT INTO {REFS_TABLE} VALUES (?, 1, ?, 0, ?, 3, ?, ?)',
            (self.foreign_book, 'transition-00', self.story, 'chapter-1', self.contribution))
        db.commit()

    def begin(self):
        self.db.execute('PRAGMA secure_delete=ON')
        self.db.execute('BEGIN IMMEDIATE')

    def test_invalidates_all_scoped_history_before_deleting_refs_idempotently(self):
        self.begin()
        result = invalidate_for_contribution(
            self.db, self.contribution, self.story, 'library-a')
        self.assertEqual(result, EditorialDeletionCounts(sidecars_invalidated=2, refs_deleted=4))
        self.assertTrue(self.db.in_transaction)
        self.assertEqual(self.db.execute(f'SELECT book_revision,state FROM {BOOK_TABLE} '
            'WHERE book_id=? ORDER BY book_revision', (self.book,)).fetchall(),
            [(1, 'source_invalidated'), (2, 'source_invalidated'),
             (3, 'source_invalidated')])
        # Authored transition and ordered child snapshot remain byte-for-byte.
        self.assertEqual(self.db.execute(f'SELECT children_json,transitions_json FROM {BOOK_TABLE} '
            'WHERE book_id=? AND book_revision=1', (self.book,)).fetchone(),
            (json.dumps([{'story_id': self.story, 'revision': 3}]),
             json.dumps([{'left_story_id': self.story, 'right_story_id': self.foreign_story,
                         'text': 'authored transition', 'source_refs': []}])))
        self.assertEqual(self.db.execute(f'SELECT contribution_id FROM {REFS_TABLE} '
            'ORDER BY book_id,book_revision').fetchall(),
            [(self.other_contribution,), (self.contribution,)])
        self.assertEqual(invalidate_for_contribution(
            self.db, self.contribution, self.story, 'library-a'), EditorialDeletionCounts())
        self.assertTrue(self.db.in_transaction)
        self.db.rollback()

    def test_foreign_library_scope_is_untouched(self):
        self.begin()
        result = invalidate_for_contribution(
            self.db, self.contribution, self.story, 'library-a')
        self.assertEqual(result, EditorialDeletionCounts(2, 4))
        self.assertEqual(self.db.execute(f'SELECT state FROM {BOOK_TABLE} '
            'WHERE book_id=? AND book_revision=1', (self.foreign_book,)).fetchone(), ('current',))
        self.assertEqual(self.db.execute(f'SELECT count(*) FROM {REFS_TABLE} '
            'WHERE book_id=?', (self.foreign_book,)).fetchone(), (1,))
        self.db.rollback()

    def test_invalid_scope_and_missing_transaction_fail_without_ending_caller_transaction(self):
        with self.assertRaises(EditorialDeletionError):
            invalidate_for_contribution(self.db, 'not-uuid', self.story, 'library-a')
        self.begin()
        with self.assertRaises(EditorialDeletionError):
            invalidate_for_contribution(self.db, self.contribution, self.story, 'x' * 129)
        self.assertTrue(self.db.in_transaction)
        self.assertEqual(self.db.execute(f'SELECT count(*) FROM {REFS_TABLE}').fetchone(), (6,))
        self.db.rollback()

    def test_secure_delete_is_required_before_any_mutation(self):
        self.db.execute('PRAGMA secure_delete=OFF')
        self.db.execute('BEGIN IMMEDIATE')
        with self.assertRaisesRegex(EditorialDeletionError, 'secure_delete_required'):
            invalidate_for_contribution(
                self.db, self.contribution, self.story, 'library-a')
        self.assertEqual(self.db.execute(f"SELECT count(*) FROM {BOOK_TABLE} "
            "WHERE state='current'").fetchone(), (4,))
        self.assertEqual(self.db.execute(f'SELECT count(*) FROM {REFS_TABLE}').fetchone(), (6,))
        self.assertTrue(self.db.in_transaction)
        self.db.rollback()

    def test_legacy_database_with_neither_table_is_noop(self):
        db = __import__('sqlite3').connect(':memory:')
        self.addCleanup(db.close)
        db.execute('PRAGMA secure_delete=ON')
        db.execute('BEGIN IMMEDIATE')
        result = invalidate_for_contribution(db, self.contribution, self.story, 'library-a')
        self.assertEqual(result, EditorialDeletionCounts())
        self.assertTrue(db.in_transaction)
        db.rollback()

    def test_partial_or_malformed_future_schema_fails_closed(self):
        db = __import__('sqlite3').connect(':memory:')
        self.addCleanup(db.close)
        db.execute(f'CREATE TABLE {BOOK_TABLE} (book_id TEXT)')
        db.execute('PRAGMA secure_delete=ON')
        db.execute('BEGIN IMMEDIATE')
        with self.assertRaisesRegex(EditorialDeletionError, 'schema_partial'):
            invalidate_for_contribution(db, self.contribution, self.story, 'library-a')
        db.rollback()

        bad = __import__('sqlite3').connect(':memory:')
        self.addCleanup(bad.close)
        bad.execute(f'CREATE TABLE {BOOK_TABLE} (book_id TEXT)')
        bad.execute(f'CREATE TABLE {REFS_TABLE} (book_id TEXT)')
        bad.execute('PRAGMA secure_delete=ON')
        bad.execute('BEGIN IMMEDIATE')
        with self.assertRaisesRegex(EditorialDeletionError, 'schema_invalid'):
            invalidate_for_contribution(bad, self.contribution, self.story, 'library-a')
        self.assertTrue(bad.in_transaction)
        bad.rollback()


if __name__ == '__main__':
    unittest.main()
