"""Real SQLite/Alembic checks for the additive memoir editorial revision."""
import json
from pathlib import Path
import sqlite3
import sys
import unittest
import uuid

from alembic import command
from sqlalchemy import event, inspect

import test_orm_migrations as migration_fixture

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from app.access.bootstrap import bootstrap_owner  # noqa: E402

EDITORIAL = {'access_memory_book_editorial', 'access_memory_book_editorial_refs'}
OWNER_PHONE = '+12025550177'
OWNER_PASSWORD = 'Synthetic editorial migration passphrase!'
LIBRARY = 'synthetic-editorial-library'
STORY = str(uuid.UUID(int=8801))
BOOK = str(uuid.UUID(int=8802))
CONTRIBUTION = str(uuid.UUID(int=8803))


class MemoryBookEditorialMigrationTests(unittest.TestCase):
    def setUp(self):
        self.migration = migration_fixture.OrmMigrationTests()
        self.migration.setUp()
        self.addCleanup(self.migration.doCleanups)

    def _upgrade_a0_with_historical_rows(self):
        self.migration.seed_legacy()
        with sqlite3.connect(self.migration.path) as db:
            db.execute('''INSERT INTO captions
                (id,asset_id,text,model,user_edited,superseded)
                VALUES(501,101,'synthetic legacy caption','synthetic-model',1,0)''')
        self.migration.upgrade('a0c9d2e4f817')
        with sqlite3.connect(self.migration.path) as db:
            db.execute('PRAGMA foreign_keys=ON')
            owner = bootstrap_owner(db, phone=OWNER_PHONE, password=OWNER_PASSWORD,
                                    library_id=LIBRARY)
            db.execute('INSERT INTO access_asset_libraries(asset_id,library_id) VALUES(101,?)',
                       (LIBRARY,))
            story_content = json.dumps({
                'title': 'Synthetic chapter', 'theme': 'everyday', 'language': 'en',
                'asset_ids': ['101'], 'chapters': [{
                    'id': 'chapter-1', 'title': 'Synthetic chapter',
                    'narration': 'Authored synthetic text.', 'asset_ids': ['101'],
                    'evidence_ids': [],
                }], 'evidence_versions': {},
            }, sort_keys=True, separators=(',', ':'))
            db.execute('''INSERT INTO access_memory_stories
                (id,library_id,author_id,revision,content,created_at,updated_at)
                VALUES(?,?,?,1,?,10,10)''', (STORY, LIBRARY, owner, story_content))
            db.execute('''INSERT INTO access_memory_revisions
                (story_id,revision,editor_id,mutation_id,request_digest,content,occurred_at)
                VALUES(?,1,?,?,?, ?,10)''',
                (STORY, owner, str(uuid.UUID(int=8811)), 'synthetic-story-digest', story_content))
            book_content = json.dumps({
                'title': 'Synthetic legacy memoir', 'language': 'en',
                'introduction': 'Existing legacy introduction.', 'kind': 'memoir',
                'story_ids': [STORY],
            }, sort_keys=True, separators=(',', ':'))
            db.execute('''INSERT INTO access_memory_books
                (id,library_id,author_id,revision,content,created_at,updated_at)
                VALUES(?,?,?,1,?,20,20)''', (BOOK, LIBRARY, owner, book_content))
            db.execute('''INSERT INTO access_memory_book_revisions
                (book_id,revision,editor_id,mutation_id,request_digest,content,occurred_at)
                VALUES(?,1,?,?,?, ?,20)''',
                (BOOK, owner, str(uuid.UUID(int=8821)), 'synthetic-book-digest', book_content))
            db.execute('''INSERT INTO access_memory_contributions
                (id,story_id,library_id,author_id,kind,original_text,original_audio,
                 language,byline,sha256,duration_ms,local_processing_consent,chapter_id,
                 base_story_revision,state,mutation_id,request_digest,created_at,
                 reviewed_by_id,reviewed_at)
                VALUES(?,?,?,?,'text','Synthetic original contribution',NULL,'en','synthetic',?,
                       NULL,1,'chapter-1',1,'accepted',?,?,10,?,10)''',
                (CONTRIBUTION, STORY, LIBRARY, owner, 'a' * 64,
                 str(uuid.UUID(int=8831)), 'synthetic-contribution-digest', owner))
            db.execute('''INSERT INTO access_memory_contribution_refs
                (story_id,revision,chapter_id,ordinal,contribution_id)
                VALUES(?,1,'chapter-1',0,?)''', (STORY, CONTRIBUTION))
            db.commit()
        return owner

    def _downgrade_to_a0(self):
        with self.migration.engine.begin() as connection:
            cfg = migration_fixture.config()
            cfg.attributes['connection'] = connection
            command.downgrade(cfg, 'a0c9d2e4f817')

    def test_a0_to_b1_preserves_legacy_rows_without_editorial_backfill(self):
        self._upgrade_a0_with_historical_rows()
        with self.migration.engine.connect() as connection:
            before_assets = connection.exec_driver_sql(
                'SELECT id,path,hash_sha256,status FROM assets ORDER BY id').all()
            before_captions = connection.exec_driver_sql(
                'SELECT * FROM captions ORDER BY id').all()
            before_book = connection.exec_driver_sql(
                'SELECT id,library_id,author_id,revision,content FROM access_memory_books').all()
            before_book_revisions = connection.exec_driver_sql(
                'SELECT book_id,revision,mutation_id,request_digest,content '
                'FROM access_memory_book_revisions').all()
            before_refs = connection.exec_driver_sql(
                'SELECT story_id,revision,chapter_id,ordinal,contribution_id '
                'FROM access_memory_contribution_refs').all()

        self.migration.upgrade('b1d7e4a9c230')
        with self.migration.engine.connect() as connection:
            self.assertEqual(connection.exec_driver_sql(
                'SELECT version_num FROM alembic_version').scalar_one(), 'b1d7e4a9c230')
            self.assertEqual(connection.exec_driver_sql(
                'SELECT id,path,hash_sha256,status FROM assets ORDER BY id').all(), before_assets)
            self.assertEqual(connection.exec_driver_sql(
                'SELECT * FROM captions ORDER BY id').all(), before_captions)
            self.assertEqual(connection.exec_driver_sql(
                'SELECT id,library_id,author_id,revision,content FROM access_memory_books').all(),
                before_book)
            self.assertEqual(connection.exec_driver_sql(
                'SELECT book_id,revision,mutation_id,request_digest,content '
                'FROM access_memory_book_revisions').all(), before_book_revisions)
            self.assertEqual(connection.exec_driver_sql(
                'SELECT story_id,revision,chapter_id,ordinal,contribution_id '
                'FROM access_memory_contribution_refs').all(), before_refs)
            for table in sorted(EDITORIAL):
                self.assertEqual(connection.exec_driver_sql(
                    f'SELECT count(*) FROM {table}').scalar_one(), 0)
            self.assertEqual(connection.exec_driver_sql('PRAGMA foreign_key_check').all(), [])

    def test_empty_downgrade_to_a0_drops_only_the_two_editorial_tables(self):
        self._upgrade_a0_with_historical_rows()
        self.migration.upgrade('b1d7e4a9c230')
        with self.migration.engine.connect() as connection:
            before_tables = set(inspect(connection).get_table_names())
        self._downgrade_to_a0()
        with self.migration.engine.connect() as connection:
            after_tables = set(inspect(connection).get_table_names())
            self.assertEqual(before_tables - after_tables, EDITORIAL)
            self.assertEqual(after_tables - before_tables, set())
            self.assertEqual(connection.exec_driver_sql(
                'SELECT version_num FROM alembic_version').scalar_one(), 'a0c9d2e4f817')
            self.assertEqual(connection.exec_driver_sql(
                'SELECT content FROM access_memory_books WHERE id=?', (BOOK,)).scalar_one(),
                json.dumps({'title': 'Synthetic legacy memoir', 'language': 'en',
                    'introduction': 'Existing legacy introduction.', 'kind': 'memoir',
                    'story_ids': [STORY]}, sort_keys=True, separators=(',', ':')))
            self.assertEqual(connection.exec_driver_sql('PRAGMA foreign_key_check').all(), [])

    def test_populated_downgrade_refuses_and_preserves_revision_and_rows(self):
        self._upgrade_a0_with_historical_rows()
        self.migration.upgrade('b1d7e4a9c230')
        with self.migration.engine.begin() as connection:
            connection.exec_driver_sql('''INSERT INTO access_memory_book_editorial
                (book_id,book_revision,children_json,transitions_json,state)
                VALUES(?,1,?,'[]','current')''',
                (BOOK, json.dumps([{'story_id': STORY, 'revision': '1'}], separators=(',', ':'))))
            connection.exec_driver_sql('''INSERT INTO access_memory_book_editorial_refs
                (book_id,book_revision,section_key,ordinal,story_id,story_revision,
                 chapter_id,contribution_id)
                VALUES(?,1,'introduction',0,?,1,'chapter-1',?)''', (BOOK, STORY, CONTRIBUTION))
        with self.assertRaisesRegex(RuntimeError, 'editorial records require reviewed offline backup restoration'):
            self._downgrade_to_a0()
        with self.migration.engine.connect() as connection:
            self.assertEqual(connection.exec_driver_sql(
                'SELECT version_num FROM alembic_version').scalar_one(), 'b1d7e4a9c230')
            self.assertEqual(connection.exec_driver_sql(
                'SELECT state FROM access_memory_book_editorial WHERE book_id=?',
                (BOOK,)).scalar_one(), 'current')
            self.assertEqual(connection.exec_driver_sql(
                'SELECT contribution_id FROM access_memory_book_editorial_refs '
                'WHERE book_id=?', (BOOK,)).scalar_one(), CONTRIBUTION)
            self.assertEqual(connection.exec_driver_sql('PRAGMA foreign_key_check').all(), [])

    def test_interrupted_b1_table_creation_rolls_back_without_touching_a0_rows(self):
        self._upgrade_a0_with_historical_rows()

        def interrupt(_conn, _cursor, statement, _parameters, _context, _executemany):
            if statement.lstrip().startswith('CREATE TABLE access_memory_book_editorial_refs'):
                raise RuntimeError('Synthetic editorial migration interruption')

        event.listen(self.migration.engine, 'before_cursor_execute', interrupt)
        try:
            with self.assertRaisesRegex(RuntimeError, 'Synthetic editorial migration interruption'):
                self.migration.upgrade('b1d7e4a9c230')
        finally:
            event.remove(self.migration.engine, 'before_cursor_execute', interrupt)
        with self.migration.engine.connect() as connection:
            self.assertEqual(connection.exec_driver_sql(
                'SELECT version_num FROM alembic_version').scalar_one(), 'a0c9d2e4f817')
            self.assertFalse(EDITORIAL & set(inspect(connection).get_table_names()))
            self.assertEqual(connection.exec_driver_sql(
                'SELECT id,path,hash_sha256 FROM assets ORDER BY id').all(),
                [(101, 'synthetic/first.jpg', 'synthetic-hash'),
                 (102, 'synthetic/null-status.mp4', 'synthetic-second')])
            self.assertEqual(connection.exec_driver_sql(
                'SELECT content FROM access_memory_books WHERE id=?', (BOOK,)).scalar_one(),
                json.dumps({'title': 'Synthetic legacy memoir', 'language': 'en',
                    'introduction': 'Existing legacy introduction.', 'kind': 'memoir',
                    'story_ids': [STORY]}, sort_keys=True, separators=(',', ':')))
            self.assertEqual(connection.exec_driver_sql('PRAGMA foreign_key_check').all(), [])


if __name__ == '__main__':
    unittest.main()
