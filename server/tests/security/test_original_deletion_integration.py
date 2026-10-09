"""Domain and HTTP gates use the same external original-deletion watermark."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
import uuid

from fastapi.testclient import TestClient
import test_memory_contributions as fixture
from app.access.memory_contributions import MemoryContributions
from app.access.original_deletions import OriginalDeletionJournal
from app.access.runtime import ExistingDatabase, RuntimeConfiguration, RuntimeUnavailable
from app.access.service import AccessService
from app.access.transport import AccessRuntime, TransportError
from app.main import create_app


class OriginalDeletionIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixture.MemoryContributionTests.setUpClass()
    @classmethod
    def tearDownClass(cls):fixture.MemoryContributionTests.tearDownClass()

    def setUp(self):
        self.base=fixture.MemoryContributionTests();self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.f=self.base.f
        self.tmp=tempfile.TemporaryDirectory(prefix='photohouse-journal-integration-')
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()
        self.path=self.root/'journal.sqlite';self.namespace=str(uuid.uuid4())
        self.journal=OriginalDeletionJournal.initialize(self.path,self.namespace)
        with self.f.connection() as db:self.journal.bind(db)
        self.database=ExistingDatabase(self.f.path.resolve(),original_deletions=self.journal)
        runtime=AccessRuntime(self.database,'https://photohouse.test',clock=lambda:self.f.now)
        self.client=TestClient(create_app(access_runtime=runtime,memory_collaboration_enabled=True,
            memory_originals_enabled=True,memory_generation_enabled=True),base_url='https://photohouse.test')
        self.addCleanup(self.client.close)

    def get(self,path):
        return self.client.get(path,headers={'Authorization':'Bearer '+self.f.owner_token})

    def row(self,db,ident):
        cursor=db.execute('SELECT * FROM access_memory_contributions WHERE id=?',(ident,))
        return dict(zip((column[0] for column in cursor.description),cursor.fetchone()))

    def test_owner_delete_writes_tombstone_and_viewer_cannot_delete(self):
        item=self.base.create()
        path=f'/memory-community/v1/stories/{self.base.story}/contributions/{item["id"]}?library=family-a'
        denied=self.client.delete(path,headers={'Authorization':'Bearer '+self.f.member_token})
        self.assertEqual(denied.status_code,401)
        self.assertEqual(self.journal.head()[1],0)
        response=self.client.delete(path,headers={'Authorization':'Bearer '+self.f.owner_token})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json(),{'deleted':True,'id':item['id']})
        self.assertEqual(self.journal.head()[1],1)
        with self.database() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM access_memory_contributions').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT applied_seq FROM access_original_deletion_state').fetchone()[0],1)

    def test_crash_before_primary_commit_closes_reads_until_offline_replay(self):
        item=self.base.create()
        with self.database() as db:
            db.execute('PRAGMA secure_delete=ON');db.execute('BEGIN IMMEDIATE')
            self.journal.append(db,'memory',self.row(db,item['id']),self.f.now)
            db.rollback()  # Simulates the primary writer stopping after journal commit.
        response=self.get('/assets?library=family-a')
        self.assertEqual(response.status_code,503)
        self.assertNotIn(str(self.f.path),response.text)
        with self.f.connection() as db:self.journal.replay(db)
        self.assertEqual(self.get('/assets?library=family-a').status_code,200)
        with self.f.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM access_memory_contributions').fetchone()[0],0)

    def test_preopened_connection_checks_watermark_at_transaction_entry(self):
        item=self.base.create()
        with self.database() as reader:
            service=AccessService(reader,clock=lambda:self.f.now)
            with self.f.connection() as writer:
                writer.execute('PRAGMA secure_delete=ON');writer.execute('BEGIN IMMEDIATE')
                self.journal.append(writer,'memory',self.row(writer,item['id']),self.f.now)
                writer.rollback()
            with self.assertRaises(TransportError) as refused:
                service.require(self.f.owner_token,'family-a','library.read')
            self.assertEqual(refused.exception.status,503)
            self.assertFalse(reader.in_transaction)

    def test_runtime_requires_explicit_paired_journal_before_originals_or_generation(self):
        settings=RuntimeConfiguration(self.f.path.resolve(),'https://photohouse.test',
            (self.root/'originals',),self.root/'derived')
        for flag in ('annotation_intake_enabled','memory_originals_enabled','memory_generation_enabled'):
            with self.subTest(flag=flag),self.assertRaises(ValueError):
                replace(settings,**{flag:True}).build_app()
        with self.assertRaises(ValueError):replace(settings,original_deletion_journal_path=self.path).build_app()
        missing=self.root/'missing.sqlite'
        with self.assertRaises(RuntimeError):
            replace(settings,original_deletion_journal_path=missing,original_deletion_namespace=self.namespace).build_app()
        self.assertFalse(missing.exists())

    def test_bound_primary_cannot_bypass_deletion_guard_by_omitting_configuration(self):
        with self.assertRaises(RuntimeUnavailable):
            with ExistingDatabase(self.f.path.resolve())():
                self.fail('Bound original store opened without external deletion history')
        settings=RuntimeConfiguration(self.f.path.resolve(),'https://photohouse.test',
            (self.root/'originals',),self.root/'derived')
        with TestClient(settings.build_app(clock=lambda:self.f.now),base_url='https://photohouse.test') as client:
            response=client.get('/assets?library=family-a',headers={'Authorization':'Bearer '+self.f.owner_token})
        self.assertEqual(response.status_code,503)
        self.assertNotIn(str(self.f.path),response.text)


if __name__=='__main__':unittest.main()
