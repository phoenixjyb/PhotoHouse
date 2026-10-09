"""Synthetic owner deletion and paired restore replay scrub reviewed AI prose."""
import json
import sqlite3
import unittest
import uuid

from sqlalchemy import create_engine

import test_memory_book_editorial_erasure as fixture
from app import db as models
from app.access.metadata import migration_metadata
from app.access.memory_book_edition_schema import add_book_edition_tables, EDITION_TABLE, SOURCES_TABLE
from app.access.original_deletions import OriginalDeletionError


class MemoirEditionErasureIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): fixture.EditorialErasureIntegrationTests.setUpClass()
    @classmethod
    def tearDownClass(cls): fixture.EditorialErasureIntegrationTests.tearDownClass()

    def setUp(self):
        self.editorial = fixture.EditorialErasureIntegrationTests()
        self.editorial.setUp()
        self.addCleanup(self.editorial.doCleanups)
        self.ctx = self.editorial.f
        self.library = self.ctx.f
        self.item = self.editorial.item
        self.story = self.editorial.story
        self.book = self.editorial.book
        metadata = migration_metadata(models.Base.metadata)
        editions, sources = add_book_edition_tables(metadata)
        engine = create_engine('sqlite:///' + str(self.library.path))
        try:
            editions.create(engine, checkfirst=True)
            sources.create(engine, checkfirst=True)
        finally: engine.dispose()
        with self.library.connection() as db:
            owner_id = db.execute('SELECT author_id FROM access_memory_books WHERE id=?', (self.book,)).fetchone()[0]
            for revision in (1, 2):
                eid = str(uuid.uuid4())
                values = (eid, self.book, revision, 'family-a', owner_id,
                    str(uuid.uuid4()), 'a' * 64, 'b' * 64, 'stories',
                    json.dumps([{'id': self.story, 'revision': '1'}]),
                    json.dumps({'title': 'GENERATED SOURCE-DERIVED TEXT', 'chapters': [], 'questions': []}),
                    str(uuid.uuid4()), 'c' * 64, self.library.now, 'current')
                db.execute(f'INSERT INTO {EDITION_TABLE} VALUES({",".join("?" for _ in values)})', values)
                db.execute(f'''INSERT INTO {SOURCES_TABLE}
                    (edition_id,ordinal,source_id,kind,asset_id,source_digest,chapter_ids_json,contribution_id,contribution_story_id)
                    VALUES(?,0,?,'family',NULL,?,'[]',?,?)''',
                    (eid, 'contribution-' + self.item['id'], 'd' * 64, self.item['id'], self.story))
            db.commit()

    def assert_erased(self, db):
        self.editorial.assert_erased(db)
        self.assertEqual([('source_invalidated', None), ('source_invalidated', None)],
            db.execute(f'SELECT state,manuscript_json FROM {EDITION_TABLE} ORDER BY book_revision').fetchall())
        self.assertEqual(0, db.execute(f'SELECT count(*) FROM {SOURCES_TABLE}').fetchone()[0])

    def test_owner_delete_scrubs_all_ai_editions_and_preserves_manual_editorial_text(self):
        self.editorial.delete()
        with self.library.connection() as db: self.assert_erased(db)

    def test_restore_replay_scrubs_old_editions_even_when_source_parent_is_already_absent(self):
        backup = self.ctx.root / 'synthetic-edition-predelete.sqlite'
        with sqlite3.connect(self.library.path) as source, sqlite3.connect(backup) as target:
            source.backup(target)
        self.editorial.delete()
        with sqlite3.connect(backup) as restored:
            restored.execute('PRAGMA foreign_keys=OFF')
            restored.execute('DELETE FROM access_memory_contributions WHERE id=?', (self.item['id'],))
            restored.commit()
            restored.execute('PRAGMA foreign_keys=ON')
            self.assertEqual(1, self.ctx.journal.review(restored)['pending_count'])
            self.assertEqual(1, self.ctx.journal.replay(restored)[3])
            self.assert_erased(restored)
            self.assertEqual(0, self.ctx.journal.replay(restored)[3])

    def test_drifted_schema_refuses_owner_delete_without_committing_partial_erasure(self):
        with self.library.connection() as db:
            db.execute('DROP TRIGGER trg_memory_book_edition_immutable'); db.commit()
        response = self.ctx.client.delete(
            f'/memory-community/v1/stories/{self.story}/contributions/{self.item["id"]}?library=family-a',
            headers={'Authorization': 'Bearer ' + self.library.owner_token})
        self.assertEqual(503, response.status_code)
        # Journal append is durable; the primary transaction must remain unapplied.
        self.assertEqual(1, self.ctx.journal.head()[1])
        with self.library.connection() as db:
            self.assertEqual(1, db.execute('SELECT count(*) FROM access_memory_contributions WHERE id=?', (self.item['id'],)).fetchone()[0])
            self.assertEqual(2, db.execute(f"SELECT count(*) FROM {EDITION_TABLE} WHERE state='current'").fetchone()[0])
            self.assertEqual(0, db.execute('SELECT applied_seq FROM access_original_deletion_state').fetchone()[0])

    def test_restore_review_refuses_missing_book_parent_independent_of_contribution_tombstone(self):
        backup = self.ctx.root / 'synthetic-edition-missing-book.sqlite'
        with sqlite3.connect(self.library.path) as source, sqlite3.connect(backup) as target:
            source.backup(target)
        self.editorial.delete()
        with sqlite3.connect(backup) as restored:
            restored.execute('PRAGMA foreign_keys=OFF')
            restored.execute('DELETE FROM access_memory_contributions WHERE id=?', (self.item['id'],))
            restored.execute('DELETE FROM access_memory_books WHERE id=?', (self.book,))
            restored.commit()
            restored.execute('PRAGMA foreign_keys=ON')
            with self.assertRaisesRegex(OriginalDeletionError, 'foreign-key review failed'):
                self.ctx.journal.review(restored)
            self.assertEqual(2, restored.execute(f"SELECT count(*) FROM {EDITION_TABLE} WHERE state='current'").fetchone()[0])


if __name__ == '__main__': unittest.main()
