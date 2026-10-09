"""Startup retention gate and expired private-history purge, synthetic DB only."""
from contextlib import contextmanager
import sqlite3
import unittest
import uuid

from fastapi.testclient import TestClient

import test_memory_jobs as fixture
from app.access.memory_jobs import RETENTION
from app.access.transport import AccessRuntime
from app.main import create_app


class MemoryRetentionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): fixture.MemoryJobTests.setUpClass()
    @classmethod
    def tearDownClass(cls): fixture.MemoryJobTests.tearDownClass()

    def setUp(self):
        self.f=fixture.MemoryJobTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)

    def runtime(self):
        return AccessRuntime(self.f.library.connection,'https://photohouse.test',
                             clock=lambda:self.f.library.now)

    def test_startup_prunes_expired_private_history_and_preserves_saved_and_original_prose(self):
        conversation=self.f.start()
        chat=self.f.send(conversation['id'],'synthetic expired conversation words')
        narrative=self.f.narrative(instructions='synthetic expired job instructions')
        story_id=self.f.story_id
        original='synthetic original contribution prose must remain'
        contribution_id=str(uuid.uuid4())
        with self.f.library.connection() as db:
            story_content=db.execute('SELECT content FROM access_memory_stories WHERE id=?',(story_id,)).fetchone()[0]
            db.execute('''INSERT INTO access_memory_contributions
                (id,story_id,library_id,author_id,kind,original_text,original_audio,language,byline,
                 sha256,duration_ms,local_processing_consent,chapter_id,base_story_revision,state,
                 mutation_id,request_digest,created_at)
                VALUES(?,?, 'family-a',?,'text',?,NULL,'en','Synthetic author',?,NULL,0,NULL,1,
                       'pending',?,?,?)''',
                (contribution_id,story_id,self.f.library.member_id,original,'a'*64,
                 str(uuid.uuid4()),'synthetic-request-digest',self.f.library.now))
            db.execute('UPDATE access_memory_conversations SET created_at=?,expires_at=? WHERE id=?',
                       (self.f.library.now-RETENTION-1,self.f.library.now-1,conversation['id']))
            db.execute('UPDATE access_memory_jobs SET created_at=?,expires_at=? WHERE id IN (?,?)',
                       (self.f.library.now-RETENTION-1,self.f.library.now-1,chat['id'],narrative['id']))
            db.commit()

        observed_secure_delete=[]
        @contextmanager
        def checked_connection():
            with self.f.library.connection() as db:
                yield db
                observed_secure_delete.append(db.execute('PRAGMA secure_delete').fetchone()[0])

        runtime=AccessRuntime(checked_connection,'https://photohouse.test',clock=lambda:self.f.library.now)
        app=create_app(access_runtime=runtime,memory_collaboration_enabled=True)
        with TestClient(app,base_url='https://photohouse.test'):
            pass
        self.assertEqual(observed_secure_delete,[1])
        with self.f.library.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM access_memory_conversations WHERE id=?',
                                        (conversation['id'],)).fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM access_memory_jobs WHERE id IN (?,?)',
                                        (chat['id'],narrative['id'])).fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM access_memory_turns WHERE conversation_id=?',
                                        (conversation['id'],)).fetchone()[0],0)
            self.assertEqual(db.execute('SELECT content FROM access_memory_stories WHERE id=?',
                                        (story_id,)).fetchone()[0],story_content)
            self.assertEqual(db.execute('SELECT original_text FROM access_memory_contributions WHERE id=?',
                                        (contribution_id,)).fetchone()[0],original)

    def test_e6_database_without_f7_tables_fails_enabled_startup_closed(self):
        with self.f.library.connection() as db:
            db.execute("UPDATE alembic_version SET version_num='e6b2f8a1c903'")
            for table in ('access_memory_turns','access_memory_jobs','access_memory_conversations',
                          'access_memory_book_revisions','access_memory_books',
                          'access_memory_contribution_derivations','access_memory_contributions'):
                db.execute('DROP TABLE '+table)
            db.commit()
        app=create_app(access_runtime=self.runtime(),memory_collaboration_enabled=True)
        with self.assertRaises(Exception):
            with TestClient(app,base_url='https://photohouse.test'):
                pass

    def test_maintenance_scope_health_failure_blocks_requests_without_deleting_originals(self):
        app=create_app(access_runtime=self.runtime(),memory_collaboration_enabled=True,
                       memory_originals_enabled=True)
        with TestClient(app,base_url='https://photohouse.test') as client:
            # Starlette startup completed its maintenance pass. A later failed
            # pass must leave the private API closed until maintenance succeeds.
            self.f.library.mutate('''INSERT INTO access_memory_contributions
                (id,story_id,library_id,author_id,kind,original_text,original_audio,language,byline,
                 sha256,duration_ms,local_processing_consent,chapter_id,base_story_revision,state,
                 mutation_id,request_digest,created_at)
                VALUES(?,?,'family-a',?,'text','preserve original',NULL,'en','Synthetic author',?,NULL,0,NULL,1,
                       'pending',?,?,?)''',
                (str(uuid.uuid4()),self.f.story_id,self.f.library.member_id,'b'*64,
                 str(uuid.uuid4()),'synthetic-request-digest',self.f.library.now))
            app.state.memory_retention_healthy=False
            self.assertEqual(client.get('/memory-community/v1/books?library=family-a',
                headers={'Authorization':'Bearer '+self.f.owner}).status_code,503)
            with self.f.library.connection() as db:
                self.assertEqual(db.execute("SELECT original_text FROM access_memory_contributions").fetchone()[0],
                                 'preserve original')

    def test_contribution_table_rejects_oversized_text_and_audio_without_original_bytes(self):
        statement='''INSERT INTO access_memory_contributions
            (id,story_id,library_id,author_id,kind,original_text,original_audio,language,byline,
             sha256,duration_ms,local_processing_consent,chapter_id,base_story_revision,state,
             mutation_id,request_digest,created_at)
            VALUES(?,?,'family-a',?,?,?,?,?,'Synthetic author',?, ?,0,NULL,1,'pending',?,?,?)'''
        with self.f.library.connection() as db:
            oversized=('oversized',self.f.story_id,self.f.library.member_id,'text','x'*8193,None,
                       'en','a'*64,None,str(uuid.uuid4()),'digest',self.f.library.now)
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute(statement,oversized)
            missing_audio=('missing-audio',self.f.story_id,self.f.library.member_id,'audio',None,None,
                           'en','b'*64,100,str(uuid.uuid4()),'digest',self.f.library.now)
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute(statement,missing_audio)


if __name__=='__main__':unittest.main()
