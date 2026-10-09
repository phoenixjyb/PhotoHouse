"""Synthetic e6 -> e7 migration and constraint coverage; never uses live data."""
from contextlib import closing
import importlib.util
from pathlib import Path
import sqlite3
import sys
import unittest

from alembic import command
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'backend'))

import prepare_access_database

SCHEMA = ROOT / 'backend/migrations/versions/f7c3a9d2e614_memory_collaboration.py'
spec = importlib.util.spec_from_file_location('memory_collaboration_migration', SCHEMA)
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)

NEW_TABLES = {
    'access_memory_contributions', 'access_memory_contribution_derivations',
    'access_memory_books', 'access_memory_book_revisions',
    'access_memory_conversations', 'access_memory_jobs', 'access_memory_turns',
    'access_original_deletion_state',
}


class MemoryCollaborationSchemaTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        self.connection = self.engine.connect()
        self.config = prepare_access_database.migration_config()
        self.config.attributes['connection'] = self.connection
        command.upgrade(self.config, 'e6b2f8a1c903')
        self.db = self.connection.connection.driver_connection
        self.db.execute("INSERT INTO access_accounts(id,phone_login,password_hash,state) "
                        "VALUES('owner','+12025550101','synthetic','active')")
        self.db.execute("INSERT INTO access_libraries(id,state,bootstrap_operator) "
                        "VALUES('family','active','owner')")
        self.db.execute("INSERT INTO access_memory_stories "
                        "(id,library_id,author_id,revision,content,created_at,updated_at) "
                        "VALUES('story','family','owner',1,?,1,2)",
                        ('{"asset_ids":[],"title":"Saved","kind":"essay","intro":"Intro"}',))
        self.db.execute("INSERT INTO access_memory_revisions "
                        "(story_id,revision,editor_id,mutation_id,request_digest,content,occurred_at) "
                        "VALUES('story',1,'owner','existing-mutation','existing-digest','{}',2)")
        self.connection.commit()
        self.before = self._preserved()
        command.upgrade(self.config, migration.revision)

    def tearDown(self):
        self.connection.close()
        self.engine.dispose()

    def _preserved(self):
        return {
            'account': tuple(self.db.execute(
                "SELECT id,phone_login,password_hash,state FROM access_accounts WHERE id='owner'").fetchone()),
            'library': tuple(self.db.execute(
                "SELECT id,state,bootstrap_operator FROM access_libraries WHERE id='family'").fetchone()),
            'story': tuple(self.db.execute(
                "SELECT id,library_id,author_id,revision,content,created_at,updated_at "
                "FROM access_memory_stories WHERE id='story'").fetchone()),
            'revision': tuple(self.db.execute(
                "SELECT story_id,revision,editor_id,mutation_id,request_digest,content,occurred_at "
                "FROM access_memory_revisions WHERE story_id='story'").fetchone()),
        }

    def test_upgrade_preserves_e6_rows_and_creates_eight_empty_tables(self):
        names = {row[0] for row in self.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue(NEW_TABLES <= names)
        self.assertEqual(self._preserved(), self.before)
        self.assertEqual(self.db.execute('PRAGMA foreign_key_check').fetchall(), [])
        for table in NEW_TABLES:
            self.assertEqual(self.db.execute('SELECT count(*) FROM ' + table).fetchone()[0], 0)

    def test_contribution_shape_uniqueness_and_derivation_cascade(self):
        self.db.execute("""INSERT INTO access_memory_contributions
            (id,story_id,library_id,author_id,kind,original_text,language,byline,sha256,
             local_processing_consent,base_story_revision,state,mutation_id,request_digest,created_at)
            VALUES('c1','story','family','owner','text','A memory','zh','Owner',?,0,1,
                   'pending','m1','d1',3)""", ('a' * 64,))
        self.db.execute("""INSERT INTO access_memory_contribution_derivations
            (contribution_id,revision,state,created_at,updated_at)
            VALUES('c1',1,'waiting',3,3)""")
        self.assertEqual(self.db.execute(
            "SELECT tags FROM access_memory_contribution_derivations WHERE contribution_id='c1'").fetchone()[0], '[]')
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("""INSERT INTO access_memory_contributions
                (id,story_id,library_id,author_id,kind,original_text,language,byline,sha256,
                 local_processing_consent,base_story_revision,state,mutation_id,request_digest,created_at)
                VALUES('c2','story','family','owner','text','Again','zh','Owner',?,0,1,
                       'pending','m1','d2',4)""", ('b' * 64,))

        def insert_bad(identifier, story_id, kind, text, audio, duration, state, mutation):
            self.db.execute("""INSERT INTO access_memory_contributions
                (id,story_id,library_id,author_id,kind,original_text,original_audio,language,byline,
                 sha256,duration_ms,local_processing_consent,base_story_revision,state,mutation_id,
                 request_digest,created_at) VALUES(?,?,'family','owner',?,?,?,'zh','Owner',?, ?,0,1,?,?,?,4)""",
                (identifier, story_id, kind, text, audio, 'c' * 64, duration,
                 state, mutation, 'd3'))

        self.db.execute("""INSERT INTO access_memory_contributions
            (id,story_id,library_id,author_id,kind,original_audio,language,byline,sha256,duration_ms,
             local_processing_consent,base_story_revision,state,mutation_id,request_digest,created_at)
            VALUES('audio','story','family','owner','audio',X'0102','und','Owner',?,30000,1,1,'pending','m-audio','d-audio',4)""",
            ('d' * 64,))
        for args in (
                ('bad-text-audio', 'story', 'text', None, b'\x01\x02', 100, 'pending', 'm-bad-a'),
                ('bad-audio-text', 'story', 'audio', 'must be null', b'\x01\x02', 100, 'pending', 'm-bad-b'),
                ('null-duration', 'story', 'audio', None, b'\x01\x02', None, 'pending', 'm-null-duration'),
                ('bad-duration', 'story', 'audio', None, b'\x01\x02', 30001, 'pending', 'm-bad-c'),
                ('bad-kind', 'story', 'video', None, b'\x01\x02', 1, 'pending', 'm-bad-d'),
                ('bad-fk', 'missing-story', 'text', 'Text', None, None, 'pending', 'm-bad-e')):
            with self.assertRaises(sqlite3.IntegrityError):
                insert_bad(*args)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("""INSERT INTO access_memory_contributions
                (id,story_id,library_id,author_id,kind,original_text,language,byline,sha256,
                 local_processing_consent,base_story_revision,state,mutation_id,request_digest,created_at)
                VALUES('bad-author','story','family','missing-account','text','Text','zh','Byline',?,0,1,
                       'pending','m-bad-author','d',4)""", ('e' * 64,))
        self.db.execute("DELETE FROM access_memory_contributions WHERE id='c1'")
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM access_memory_contribution_derivations WHERE contribution_id='c1'").fetchone()[0], 0)

    def test_books_conversations_jobs_and_turns_enforce_scope_shapes_and_uniqueness(self):
        self.db.execute("""INSERT INTO access_memory_books
            (id,library_id,author_id,revision,content,created_at,updated_at)
            VALUES('book','family','owner',1,'{}',1,2)""")
        self.db.execute("""INSERT INTO access_memory_book_revisions
            (book_id,revision,editor_id,mutation_id,request_digest,content,occurred_at)
            VALUES('book',1,'owner','bm1','bd1','{}',2)""")
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("""INSERT INTO access_memory_book_revisions
                (book_id,revision,editor_id,mutation_id,request_digest,content,occurred_at)
                VALUES('book',2,'owner','bm1','bd2','{}',3)""")
        self.db.execute("""INSERT INTO access_memory_conversations
            (id,library_id,actor_id,story_id,created_at,expires_at)
            VALUES('conv','family','owner','story',1,2)""")
        for sql in (
                "INSERT INTO access_memory_conversations(id,library_id,actor_id,created_at,expires_at) "
                "VALUES('neither','family','owner',1,2)",
                "INSERT INTO access_memory_conversations(id,library_id,actor_id,story_id,book_id,created_at,expires_at) "
                "VALUES('both','family','owner','story','book',1,2)",
                "INSERT INTO access_memory_conversations(id,library_id,actor_id,story_id,created_at,expires_at) "
                "VALUES('expired','family','owner','story',2,2)"):
            with self.assertRaises(sqlite3.IntegrityError):
                self.db.execute(sql)
        self.db.execute("""INSERT INTO access_memory_jobs
            (id,library_id,actor_id,story_id,conversation_id,kind,state,mutation_id,request_digest,
             base_revision,source_fingerprint,input_json,created_at,updated_at,expires_at)
            VALUES('job','family','owner','story','conv','narrative','queued','jm1','jd1',1,'fp','{}',1,2,3)""")
        for sql in (
                "INSERT INTO access_memory_jobs(id,library_id,actor_id,kind,state,mutation_id,request_digest,base_revision,source_fingerprint,input_json,created_at,updated_at,expires_at) VALUES('neither-job','family','owner','narrative','queued','jm2','jd2',1,'fp','{}',1,2,3)",
                "INSERT INTO access_memory_jobs(id,library_id,actor_id,story_id,book_id,kind,state,mutation_id,request_digest,base_revision,source_fingerprint,input_json,created_at,updated_at,expires_at) VALUES('both-job','family','owner','story','book','narrative','queued','jm3','jd3',1,'fp','{}',1,2,3)"):
            with self.assertRaises(sqlite3.IntegrityError):
                self.db.execute(sql)
        self.db.execute("""INSERT INTO access_memory_turns
            (id,conversation_id,sequence,mutation_id,request_digest,input_text,job_id,created_at)
            VALUES('turn','conv',1,'tm1','td1','Make a story','job',2)""")
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("""INSERT INTO access_memory_turns
                (id,conversation_id,sequence,mutation_id,request_digest,input_text,created_at)
                VALUES('turn2','conv',1,'tm2','td2','Again',3)""")
        self.db.execute("DELETE FROM access_memory_jobs WHERE id='job'")
        self.assertIsNone(self.db.execute(
            "SELECT job_id FROM access_memory_turns WHERE id='turn'").fetchone()[0])

    def test_downgrade_drops_only_new_tables_and_preserves_e6_rows(self):
        with Operations.context(MigrationContext.configure(self.connection)):
            migration.downgrade()
        names = {row[0] for row in self.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertFalse(NEW_TABLES & names)
        self.assertEqual(self._preserved(), self.before)
        self.assertEqual(self.db.execute('PRAGMA foreign_key_check').fetchall(), [])


if __name__ == '__main__':
    unittest.main()
