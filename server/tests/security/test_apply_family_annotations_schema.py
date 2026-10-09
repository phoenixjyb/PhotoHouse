"""Offline a8-to-c4 application against disposable synthetic catalogs only."""
from contextlib import closing, redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import apply_family_annotations_schema as migration

full = migration.full


class FamilySchemaApplicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from alembic import command
        from sqlalchemy import create_engine
        cls.template = sqlite3.connect(':memory:')
        engine = create_engine('sqlite://')
        with engine.connect() as connection:
            config = full.small.migration_config()
            config.attributes['connection'] = connection
            command.upgrade(config, migration.FROM_REVISION)
            connection.connection.driver_connection.backup(cls.template)
        engine.dispose()

    @classmethod
    def tearDownClass(cls):
        cls.template.close()

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
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
            db.execute("INSERT INTO access_uploads(id,asset_id,account_id,incoming_label,batch,"
                       "original_name,sha256,bytes,state,created_at) "
                       "VALUES(1,1,'owner','owner','batch','a.jpg','synthetic-hash',10,'incoming',1)")
            db.execute("INSERT INTO access_upload_transfers(id,account_id,request_id,batch,filename,"
                       "bytes,sha256,kind,offset,state,asset_id,created_at) "
                       "VALUES('transfer','owner','request','batch','a.jpg',10,'synthetic-hash',"
                       "'image',0,'uploading',NULL,1)")
            db.commit()
        self.digest = full.snapshot(self.db, self.backup, self.budget())['snapshot_digest']

    @staticmethod
    def budget():
        return full.Budget(128 * 1024**2, 120)

    def apply(self, **options):
        return migration.apply(self.db, self.backup, self.digest, self.budget(), **options)

    def test_default_review_is_read_only(self):
        before = self.db.read_bytes(), self.backup.read_bytes()
        result = self.apply()
        self.assertEqual((result['source_revision'], result['target_revision']),
                         (migration.FROM_REVISION, migration.TO_REVISION))
        self.assertFalse(result['applied'])
        self.assertEqual(before, (self.db.read_bytes(), self.backup.read_bytes()))

    def test_execute_preserves_existing_rows_and_creates_no_grants_or_notes(self):
        saved = self.backup.read_bytes()
        with patch.dict('os.environ', {'DATABASE_URL': 'sqlite:////never-use-this.sqlite'}):
            result = self.apply(execute=True, all_writers_stopped=True)
        self.assertTrue(result['applied'])
        self.assertEqual(result['policies_enabled'], 0)
        with closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(db.execute('SELECT version_num FROM alembic_version').fetchone()[0],
                             migration.TO_REVISION)
            self.assertEqual(db.execute('SELECT path FROM assets').fetchone()[0], 'synthetic/a.jpg')
            self.assertEqual(db.execute('SELECT incoming_label,batch FROM access_uploads').fetchone(),
                             ('owner', 'batch'))
            self.assertEqual(db.execute('SELECT destination_library_id,approval_mode FROM access_uploads').fetchone(),
                             (None, None))
            self.assertEqual(db.execute('SELECT destination_library_id FROM access_upload_transfers').fetchone(),
                             (None,))
            for name in migration.NEW_TABLES:
                self.assertEqual(db.execute('SELECT count(*) FROM ' + name).fetchone()[0], 0)
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
            self.assertIsNotNone(db.execute('SELECT name FROM sqlite_master WHERE type=? AND name=?',
                                            ('trigger', migration.IMMUTABLE_TRIGGER)).fetchone())
        self.assertEqual(self.backup.read_bytes(), saved)

    def test_execution_requires_stopped_writer_assertion(self):
        with self.assertRaises(full.small.Refused):
            self.apply(execute=True)

    def test_running_task_is_refused(self):
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("INSERT INTO tasks(type,state,priority,payload_json) "
                       "VALUES('caption','running',0,'{}')")
            db.commit()
        with self.assertRaises(full.small.Refused):
            self.apply(execute=True, all_writers_stopped=True)

    def test_stale_backup_and_repeat_are_refused(self):
        with closing(sqlite3.connect(self.backup)) as saved:
            saved.execute("UPDATE assets SET path='changed.jpg'")
            saved.commit()
        with self.assertRaises(full.small.Refused):
            self.apply(execute=True, all_writers_stopped=True)
        with closing(sqlite3.connect(self.backup)) as saved:
            saved.execute("UPDATE assets SET path='synthetic/a.jpg'")
            saved.commit()
        self.apply(execute=True, all_writers_stopped=True)
        with self.assertRaises(full.small.Refused):
            self.apply(execute=True, all_writers_stopped=True)

    def test_partial_schema_or_wal_is_refused(self):
        with closing(sqlite3.connect(self.db)) as db:
            db.execute('ALTER TABLE access_uploads ADD COLUMN destination_library_id TEXT')
            db.commit()
        with self.assertRaises(full.small.Refused):
            self.apply()
        with closing(sqlite3.connect(self.db)) as db:
            db.execute('PRAGMA journal_mode=WAL')
        with self.assertRaises(full.small.Refused):
            self.apply()

    def test_ddl_or_preservation_failure_rolls_back(self):
        from alembic import command
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
            self.assertEqual(db.execute('SELECT path FROM assets').fetchone()[0], 'synthetic/a.jpg')
        self.assertFalse(self.apply()['applied'])

    def test_change_between_review_and_exclusive_lock_is_refused(self):
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
        from alembic import command
        original = command.upgrade

        def checked(config, target):
            with closing(sqlite3.connect(self.db, timeout=0)) as other:
                with self.assertRaises(sqlite3.OperationalError):
                    other.execute("UPDATE assets SET path='race.jpg'")
            original(config, target)

        with patch.object(command, 'upgrade', side_effect=checked):
            self.assertTrue(self.apply(execute=True, all_writers_stopped=True)['applied'])

    def test_budget_expiry_after_ddl_rolls_back(self):
        from alembic import command
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
