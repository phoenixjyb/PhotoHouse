"""Offline c4-to-e6 application against disposable synthetic catalogs only."""
from contextlib import closing, redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

from alembic import command
from sqlalchemy import create_engine

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'backend'))
import apply_memory_stories_schema as migration

full = migration.full


class MemoryStoriesSchemaApplicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = sqlite3.connect(':memory:')
        engine = create_engine('sqlite://')
        try:
            with engine.connect() as connection:
                config = full.small.migration_config()
                config.attributes['connection'] = connection
                command.upgrade(config, migration.FROM_REVISION)
                connection.connection.driver_connection.backup(cls.template)
        finally:
            engine.dispose()

    @classmethod
    def tearDownClass(cls):
        cls.template.close()

    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix='photohouse-memory-schema-')
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name).resolve()
        self.db, self.backup = self.root / 'catalog.sqlite', self.root / 'backup.sqlite'
        with closing(sqlite3.connect(self.db)) as db:
            self.template.backup(db)
            db.execute("INSERT INTO access_accounts(id,phone_login,password_hash,state) "
                       "VALUES('owner','+12025550101','synthetic','active')")
            db.execute("INSERT INTO access_libraries(id,state,bootstrap_operator) "
                       "VALUES('family','active','owner')")
            db.execute("INSERT INTO assets(id,path,hash_sha256,status) "
                       "VALUES(1,'synthetic/a.jpg','synthetic-hash','active')")
            db.execute("INSERT INTO access_asset_libraries(asset_id,library_id) VALUES(1,'family')")
            db.execute("INSERT INTO access_uploads(id,asset_id,account_id,incoming_label,batch,"
                       "original_name,sha256,bytes,state,created_at) "
                       "VALUES(1,1,'owner','owner','batch','a.jpg','synthetic-hash',10,'assigned',1)")
            db.execute("INSERT INTO access_stories "
                       "(id,asset_id,library_id,author_id,revision,title,text,language,byline,created_at,updated_at,deleted) "
                       "VALUES('story-1',1,'family','owner',1,'First day','A family note','en','',1,2,0)")
            db.execute("INSERT INTO access_story_revisions "
                       "(story_id,revision,editor_id,mutation_id,request_digest,title,text,language,byline,occurred_at,deleted) "
                       "VALUES('story-1',1,'owner','mutation','digest','First day','A family note','en','',2,0)")
            db.commit()
        self.budget = lambda: full.Budget(128 * 1024**2, 120)
        self.digest = full.snapshot(self.db, self.backup, self.budget())['snapshot_digest']
        with full.read_source(self.db, self.budget(), offline=True) as source:
            self.source_tables = {name: columns for name, columns in full.schema(source).items()
                                  if name != 'alembic_version'}
            self.source_fingerprint = full.fingerprint(source, self.source_tables, self.budget())[0]

    def apply(self, **options):
        return migration.apply(self.db, self.backup, self.digest, self.budget(), **options)

    def test_default_review_is_read_only_and_never_creates_missing_database(self):
        before = self.db.read_bytes(), self.backup.read_bytes()
        result = self.apply()
        self.assertEqual((result['source_revision'], result['target_revision']),
                         (migration.FROM_REVISION, migration.TO_REVISION))
        self.assertFalse(result['applied'])
        self.assertEqual(before, (self.db.read_bytes(), self.backup.read_bytes()))
        missing = self.root / 'missing.sqlite'
        with self.assertRaises(Exception):
            migration.apply(missing, self.backup, self.digest, self.budget())
        self.assertFalse(missing.exists())

    def test_execute_preserves_c4_rows_and_creates_only_empty_memory_tables(self):
        saved = self.backup.read_bytes()
        result = self.apply(execute=True, all_writers_stopped=True)
        self.assertTrue(result['applied'])
        self.assertEqual(result['saved_stories_created'], 0)
        with closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(db.execute('SELECT version_num FROM alembic_version').fetchone()[0],
                             migration.TO_REVISION)
            self.assertEqual(db.execute('SELECT path FROM assets').fetchone(), ('synthetic/a.jpg',))
            self.assertEqual(db.execute('SELECT title,text,revision FROM access_stories').fetchone(),
                             ('First day', 'A family note', 1))
            self.assertEqual(db.execute('SELECT text,revision FROM access_story_revisions').fetchone(),
                             ('A family note', 1))
            for table in migration.NEW_TABLES:
                self.assertEqual(db.execute('SELECT count(*) FROM ' + table).fetchone()[0], 0)
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
            after_tables = full.schema(db)
            preserved = {name: columns for name, columns in after_tables.items()
                         if name in self.source_tables}
            self.assertEqual(full.fingerprint(db, preserved, self.budget())[0], self.source_fingerprint)
        self.assertEqual(self.backup.read_bytes(), saved)

    def test_successful_application_cannot_be_replayed(self):
        self.apply(execute=True, all_writers_stopped=True)
        with self.assertRaises(full.small.Refused):
            self.apply(execute=True, all_writers_stopped=True)

    def test_execution_requires_explicit_all_writers_stopped_assertion(self):
        with self.assertRaises(full.small.Refused):
            self.apply(execute=True)

    def test_running_task_is_refused(self):
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("INSERT INTO tasks(type,state,priority,payload_json) "
                       "VALUES('caption','running',0,'{}')")
            db.commit()
        with self.assertRaises(full.small.Refused):
            self.apply(execute=True, all_writers_stopped=True)

    def test_stale_backup_and_partial_schema_are_refused(self):
        with closing(sqlite3.connect(self.backup)) as saved:
            saved.execute("UPDATE assets SET path='changed.jpg'")
            saved.commit()
        with self.assertRaises(full.small.Refused):
            self.apply(execute=True, all_writers_stopped=True)
        with closing(sqlite3.connect(self.backup)) as saved:
            saved.execute("UPDATE assets SET path='synthetic/a.jpg'")
            saved.commit()
        with closing(sqlite3.connect(self.db)) as db:
            db.execute('CREATE TABLE access_memory_stories (id TEXT)')
            db.commit()
        with self.assertRaises(full.small.Refused):
            self.apply()

    def test_wal_and_wrong_revision_are_refused(self):
        with closing(sqlite3.connect(self.db)) as db:
            db.execute('PRAGMA journal_mode=WAL')
        with self.assertRaises(full.small.Refused):
            self.apply()
        with closing(sqlite3.connect(self.db)) as db:
            db.execute('PRAGMA journal_mode=DELETE')
            db.execute("UPDATE alembic_version SET version_num='a8d4c2e6f901'")
            db.commit()
        with self.assertRaises(full.small.Refused):
            self.apply()

    def test_ddl_or_preservation_failure_rolls_back(self):
        original = command.upgrade

        def corrupt(config, target):
            original(config, target)
            config.attributes['connection'].exec_driver_sql(
                "UPDATE assets SET path='corrupted.jpg'")

        with patch.object(command, 'upgrade', side_effect=corrupt):
            with self.assertRaises(full.small.Refused):
                self.apply(execute=True, all_writers_stopped=True)
        with closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(db.execute('SELECT version_num FROM alembic_version').fetchone()[0],
                             migration.FROM_REVISION)
            self.assertEqual(db.execute('SELECT path FROM assets').fetchone(), ('synthetic/a.jpg',))
            self.assertFalse(set(migration.NEW_TABLES) & set(full.schema(db)))
        self.assertFalse(self.apply()['applied'])

    def test_change_after_review_is_refused(self):
        original = migration.review

        def changed(*args):
            result = original(*args)
            with closing(sqlite3.connect(self.db)) as db:
                db.execute("UPDATE assets SET path='concurrent.jpg'")
                db.commit()
            return result

        with patch.object(migration, 'review', side_effect=changed):
            with self.assertRaises(full.small.Refused):
                self.apply(execute=True, all_writers_stopped=True)
        with closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(db.execute('SELECT version_num FROM alembic_version').fetchone()[0],
                             migration.FROM_REVISION)

    def test_exclusive_transaction_blocks_competing_writer(self):
        original = command.upgrade

        def checked(config, target):
            with closing(sqlite3.connect(self.db, timeout=0)) as other:
                with self.assertRaises(sqlite3.OperationalError):
                    other.execute("UPDATE assets SET path='race.jpg'")
            original(config, target)

        with patch.object(command, 'upgrade', side_effect=checked):
            self.assertTrue(self.apply(execute=True, all_writers_stopped=True)['applied'])

    def test_expired_budget_after_ddl_rolls_back(self):
        original = command.upgrade
        budget = self.budget()

        def expire(config, target):
            original(config, target)
            budget.deadline = 0

        with patch.object(command, 'upgrade', side_effect=expire):
            with self.assertRaises(full.small.Refused):
                migration.apply(self.db, self.backup, self.digest, budget,
                                execute=True, all_writers_stopped=True)
        self.assertFalse(self.apply()['applied'])

    def test_cli_refusal_does_not_echo_unexpected_argument(self):
        args = ['--database', str(self.db), '--backup', str(self.backup),
                '--reviewed-backup-digest', self.digest,
                '--max-bytes', str(128 * 1024**2), '--timeout-seconds', '120']
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(migration.main(args), 0)
        self.assertFalse(json.loads(out.getvalue())['applied'])
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(migration.main(args + ['--unexpected-secret', 'do-not-echo']), 2)
        self.assertNotIn('do-not-echo', out.getvalue() + err.getvalue())


if __name__ == '__main__':
    unittest.main()
