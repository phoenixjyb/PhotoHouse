"""Offline e6-to-f7 application safety against disposable synthetic catalogs."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

from alembic import command
from sqlalchemy import create_engine

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
sys.path.insert(0,str(ROOT/'backend'))
import apply_memory_collaboration_schema as migration

full=migration.full


class MemoryCollaborationSchemaApplicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template=sqlite3.connect(':memory:')
        engine=create_engine('sqlite://')
        try:
            with engine.connect() as connection:
                config=full.small.migration_config(); config.attributes['connection']=connection
                command.upgrade(config,migration.FROM_REVISION)
                connection.connection.driver_connection.backup(cls.template)
        finally:
            engine.dispose()

    @classmethod
    def tearDownClass(cls): cls.template.close()

    def setUp(self):
        folder=tempfile.TemporaryDirectory(prefix='photohouse-memory-collaboration-schema-')
        self.addCleanup(folder.cleanup)
        self.root=Path(folder.name).resolve()
        self.db=self.root/'catalog.sqlite'; self.backup=self.root/'backup.sqlite'
        with closing(sqlite3.connect(self.db)) as db:
            db.execute('PRAGMA foreign_keys=ON')
            self.template.backup(db)
            db.execute("INSERT INTO access_accounts(id,phone_login,password_hash,state) VALUES('owner','+12025550101','synthetic','active')")
            db.execute("INSERT INTO access_libraries(id,state,bootstrap_operator) VALUES('family','active','owner')")
            story={'version':1,'title':'Synthetic saved story','theme':'everyday','language':'en',
                   'asset_ids':[],'chapters':[{'id':'chapter-1','title':'A day','narration':'Synthetic narrative.'}]}
            content=json.dumps(story,ensure_ascii=False,separators=(',',':'))
            db.execute('''INSERT INTO access_memory_stories
                (id,library_id,author_id,revision,content,created_at,updated_at)
                VALUES('story-1','family','owner',1,?,10,20)''',(content,))
            db.execute('''INSERT INTO access_memory_revisions
                (story_id,revision,editor_id,mutation_id,request_digest,content,occurred_at)
                VALUES('story-1',1,'owner','synthetic-mutation','synthetic-digest',?,20)''',(content,))
            db.commit()
        self.copy_database(self.db,self.backup)
        self.budget=lambda:full.Budget(128*1024**2,120)
        with full.read_source(self.db,self.budget(),offline=True) as source:
            self.digest=full.fingerprint(source,full.schema(source),self.budget())[0]
            self.source_tables={name:columns for name,columns in full.schema(source).items() if name!='alembic_version'}
            self.source_fingerprint=full.fingerprint(source,self.source_tables,self.budget())[0]

    @staticmethod
    def copy_database(source,destination):
        with closing(sqlite3.connect(source)) as src, closing(sqlite3.connect(destination)) as dst:
            src.backup(dst)
            dst.execute('PRAGMA journal_mode=DELETE')
            dst.commit()

    def apply(self,**options):
        digest=options.pop('digest',self.digest)
        return migration.apply(self.db,self.backup,digest,self.budget(),**options)

    def test_review_is_read_only_and_target_does_not_activate_http(self):
        before=(self.db.read_bytes(),self.backup.read_bytes())
        reviewed=self.apply()
        self.assertEqual((reviewed['source_revision'],reviewed['target_revision']),
                         (migration.FROM_REVISION,migration.TO_REVISION))
        self.assertFalse(reviewed['applied'])
        self.assertEqual(before,(self.db.read_bytes(),self.backup.read_bytes()))
        missing=self.root/'missing.sqlite'
        with self.assertRaises(Exception):migration.apply(missing,self.backup,self.digest,self.budget())
        self.assertFalse(missing.exists())

    def test_execute_preserves_full_e6_rows_and_creates_only_empty_collaboration_tables(self):
        backup_bytes=self.backup.read_bytes()
        result=self.apply(execute=True,all_writers_stopped=True)
        self.assertTrue(result['applied'])
        self.assertEqual(result['revision'],migration.TO_REVISION)
        self.assertEqual(result['collaboration_tables_created'],8)
        self.assertEqual(result['new_rows_created'],0)
        self.assertFalse(result['http_activated']); self.assertFalse(result['feature_flags_enabled'])
        with closing(sqlite3.connect(self.db)) as db:
            db.execute('PRAGMA foreign_keys=ON')
            self.assertEqual(db.execute('SELECT version_num FROM alembic_version').fetchone()[0],migration.TO_REVISION)
            self.assertEqual(db.execute('SELECT content,revision FROM access_memory_stories').fetchone()[1],1)
            self.assertEqual(db.execute('SELECT content,revision FROM access_memory_revisions').fetchone()[1],1)
            for table in migration.NEW_TABLES:
                self.assertEqual(db.execute('SELECT count(*) FROM '+table).fetchone()[0],0)
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchall(),[('ok',)])
            current={name:columns for name,columns in full.schema(db).items() if name in self.source_tables}
            self.assertEqual(full.fingerprint(db,current,self.budget())[0],self.source_fingerprint)
        self.assertEqual(self.backup.read_bytes(),backup_bytes)
        # Application wiring remains default-off even after this isolated DB tool run.
        from app.main import create_app
        from app.access.transport import AccessRuntime
        runtime=AccessRuntime(lambda:sqlite3.connect(self.db),'https://photohouse.test')
        app=create_app(access_runtime=runtime)
        self.assertFalse(app.state.memory_collaboration_enabled)
        self.assertFalse(app.state.memory_originals_enabled)
        self.assertFalse(app.state.memory_generation_enabled)

    def test_replay_wrong_digest_wrong_revision_and_missing_tables_are_refused(self):
        with self.assertRaises(full.small.Refused):self.apply(digest='0'*64)
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("UPDATE alembic_version SET version_num='d4a7e3c9b821'"); db.commit()
        with self.assertRaises(full.small.Refused):self.apply()

    def test_mismatched_backup_dirty_writer_and_sidecar_are_refused(self):
        with closing(sqlite3.connect(self.backup)) as saved:
            saved.execute("UPDATE access_memory_stories SET updated_at=updated_at+1"); saved.commit()
        with self.assertRaises(full.small.Refused):self.apply()
        self.copy_database(self.db,self.backup)
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("INSERT INTO tasks(type,state,priority,payload_json) VALUES('caption','running',0,'{}')")
            db.commit()
        with self.assertRaises(full.small.Refused):self.apply(execute=True,all_writers_stopped=True)
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("DELETE FROM tasks WHERE state='running'"); db.commit()
        Path(str(self.db)+'-wal').write_bytes(b'busy')
        with self.assertRaises(full.small.Refused):self.apply()

    def test_execution_needs_explicit_writer_assertion_and_separate_backup(self):
        with self.assertRaises(full.small.Refused):self.apply(execute=True)
        with self.assertRaises(full.small.Refused):migration.apply(self.db,self.db,self.digest,self.budget())

    def test_backup_replacement_after_review_is_refused(self):
        original=migration.review
        def replace(*args):
            result=original(*args)
            displaced=self.root/'displaced.sqlite'
            self.backup.rename(displaced)
            self.copy_database(self.db,self.backup)
            return result
        with patch.object(migration,'review',side_effect=replace):
            with self.assertRaises(full.small.Refused):self.apply(execute=True,all_writers_stopped=True)
        with closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(db.execute('SELECT version_num FROM alembic_version').fetchone()[0],migration.FROM_REVISION)
            self.assertFalse(set(migration.NEW_TABLES)&set(full.schema(db)))

    def test_transaction_rolls_back_data_or_metadata_failure(self):
        original=command.upgrade
        def corrupt_data(config,target):
            original(config,target)
            config.attributes['connection'].exec_driver_sql("UPDATE access_memory_stories SET updated_at=999")
        with patch.object(command,'upgrade',side_effect=corrupt_data):
            with self.assertRaises(full.small.Refused):self.apply(execute=True,all_writers_stopped=True)
        with closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(db.execute('SELECT version_num FROM alembic_version').fetchone()[0],migration.FROM_REVISION)
            self.assertEqual(db.execute('SELECT updated_at FROM access_memory_stories').fetchone()[0],20)
            self.assertFalse(set(migration.NEW_TABLES)&set(full.schema(db)))

        def bad_metadata(config,target):
            original(config,target)
            config.attributes['connection'].exec_driver_sql('DROP INDEX ix_memory_job_queue')
        with patch.object(command,'upgrade',side_effect=bad_metadata):
            with self.assertRaises(full.small.Refused):self.apply(execute=True,all_writers_stopped=True)
        with closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(db.execute('SELECT version_num FROM alembic_version').fetchone()[0],migration.FROM_REVISION)
            self.assertFalse(set(migration.NEW_TABLES)&set(full.schema(db)))

    def test_target_cannot_be_replayed_after_success(self):
        self.apply(execute=True,all_writers_stopped=True)
        with self.assertRaises(full.small.Refused):self.apply(execute=True,all_writers_stopped=True)

    def test_missing_e6_saved_story_table_is_refused(self):
        with closing(sqlite3.connect(self.db)) as db:
            db.execute('DROP TABLE access_memory_revisions')
            db.execute('DROP TABLE access_memory_stories')
            db.commit()
        with self.assertRaises(full.small.Refused):self.apply()


if __name__=='__main__':unittest.main()
