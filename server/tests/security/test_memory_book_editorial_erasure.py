"""Synthetic owner deletion and paired restore replay with reserved sidecars."""
import json
import sqlite3
import unittest
import uuid

from sqlalchemy import create_engine

import test_original_deletion_integration as fixture
from app import db as models
from app.access.metadata import migration_metadata
from app.access.memory_book_editorial_schema import add_book_editorial_tables
from app.access.memory_books import MemoryBooks
from app.access.service import AccessService
from app.access.original_deletions import OriginalDeletionError


class EditorialErasureIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.OriginalDeletionIntegrationTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        fixture.OriginalDeletionIntegrationTests.tearDownClass()

    def setUp(self):
        self.f = fixture.OriginalDeletionIntegrationTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.item = self.f.base.create(token=self.f.f.owner_token)
        self.story = self.f.base.story
        with self.f.database() as connection:
            access = AccessService(connection, clock=lambda: self.f.f.now)
            books = MemoryBooks(access)
            body = dict(title='合成回忆录', language='zh', introduction='手写序言',
                        story_ids=self.story, revision='0', mutation_id=str(uuid.uuid4()))
            first = books.save(self.f.f.owner_token, 'family-a', body)
            books.save(self.f.f.owner_token, 'family-a',
                       {**body, 'revision': '1', 'mutation_id': str(uuid.uuid4())}, first['id'])
            self.book = first['id']
        metadata = migration_metadata(models.Base.metadata)
        editorial, refs = add_book_editorial_tables(metadata)
        engine = create_engine('sqlite:///' + str(self.f.f.path))
        try:
            editorial.create(engine, checkfirst=True)
            refs.create(engine, checkfirst=True)
        finally:
            engine.dispose()
        self.text = '[{"text":"家人手写的过渡，删除来源后保留供审阅"}]'
        with self.f.f.connection() as connection:
            for revision in (1, 2):
                connection.execute('INSERT INTO access_memory_book_editorial VALUES(?,?,?,?,?)',
                    (self.book, revision, json.dumps([{'story_id': self.story, 'revision': '1'}]),
                     self.text, 'current'))
                connection.execute('INSERT INTO access_memory_book_editorial_refs VALUES(?,?,?,?,?,?,?,?)',
                    (self.book, revision, 'introduction', 0, self.story, 1, 'chapter-1', self.item['id']))
            connection.commit()

    def delete(self):
        response = self.f.client.delete(
            f'/memory-community/v1/stories/{self.story}/contributions/{self.item["id"]}?library=family-a',
            headers={'Authorization': 'Bearer ' + self.f.f.owner_token})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.f.journal.head()[1], 1)

    def assert_erased(self, connection):
        self.assertEqual(connection.execute('SELECT count(*) FROM access_memory_book_editorial_refs').fetchone()[0], 0)
        self.assertEqual(connection.execute('SELECT state,transitions_json FROM access_memory_book_editorial ORDER BY book_revision').fetchall(),
                         [('source_invalidated', self.text), ('source_invalidated', self.text)])
        self.assertEqual(connection.execute('SELECT count(*) FROM access_memory_contributions WHERE id=?',
                                           (self.item['id'],)).fetchone()[0], 0)
        self.assertEqual(connection.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_owner_delete_invalidates_all_historical_refs_without_erasing_authored_text(self):
        self.delete()
        with self.f.f.connection() as connection:
            self.assert_erased(connection)

    def test_paired_replay_cleans_fk_disabled_backup_even_after_original_was_removed(self):
        backup = self.f.root / 'synthetic-predelete.sqlite'
        with sqlite3.connect(self.f.f.path) as source, sqlite3.connect(backup) as target:
            source.backup(target)
        self.delete()
        with sqlite3.connect(backup) as restored:
            restored.execute('PRAGMA foreign_keys=OFF')
            restored.execute('DELETE FROM access_memory_contributions WHERE id=?', (self.item['id'],))
            restored.commit()
            self.assertEqual(restored.execute('SELECT count(*) FROM access_memory_book_editorial_refs').fetchone()[0], 2)
            restored.execute('PRAGMA foreign_keys=ON')
            self.assertEqual(self.f.journal.review(restored)['pending_count'], 1)
            self.assertEqual(self.f.journal.replay(restored)[3], 1)
            self.assert_erased(restored)
            self.assertEqual(self.f.journal.replay(restored)[3], 0)

    def test_replay_review_rejects_orphan_reference_with_foreign_library_scope(self):
        backup = self.f.root / 'synthetic-foreign-scope.sqlite'
        with sqlite3.connect(self.f.f.path) as source, sqlite3.connect(backup) as target:
            source.backup(target)
        self.delete()
        with sqlite3.connect(backup) as restored:
            restored.execute('PRAGMA foreign_keys=OFF')
            restored.execute('DELETE FROM access_memory_contributions WHERE id=?', (self.item['id'],))
            restored.execute("UPDATE access_memory_books SET library_id='family-b' WHERE id=?", (self.book,))
            restored.commit()
            restored.execute('PRAGMA foreign_keys=ON')
            with self.assertRaisesRegex(OriginalDeletionError, 'foreign-key review failed'):
                self.f.journal.review(restored)
            self.assertEqual(restored.execute('SELECT count(*) FROM access_memory_book_editorial_refs').fetchone()[0], 2)
            self.assertEqual(restored.execute("SELECT count(*) FROM access_memory_book_editorial WHERE state='current'").fetchone()[0], 2)


if __name__ == '__main__':
    unittest.main()
