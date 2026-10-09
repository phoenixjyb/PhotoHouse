"""Offline e6-to-a0 application safety against disposable synthetic catalogs."""
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

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'backend'))
import apply_memory_sources_schema as migration

full = migration.full


class MemorySourcesSchemaApplicationTests(unittest.TestCase):
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
        folder = tempfile.TemporaryDirectory(prefix='photohouse-memory-sources-schema-')
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name).resolve()
        self.db, self.backup = self.root / 'catalog.sqlite', self.root / 'backup.sqlite'
        with closing(sqlite3.connect(self.db)) as db:
            db.execute('PRAGMA foreign_keys=ON')
            self.template.backup(db)
            db.execute("INSERT INTO access_accounts(id,phone_login,password_hash,state) "
                       "VALUES('owner','+12025550101','synthetic','active')")
            db.execute("INSERT INTO access_libraries(id,state,bootstrap_operator) "
                       "VALUES('family','active','owner')")
            story = {'version': 1, 'title': 'Synthetic saved story', 'theme': 'everyday',
                     'language': 'en', 'asset_ids': [], 'chapters': [
                         {'id': 'chapter-1', 'title': 'A day', 'narration': 'Synthetic narrative.'}]}
            content = json.dumps(story, ensure_ascii=False, separators=(',', ':'))
            db.execute('''INSERT INTO access_memory_stories
                (id,library_id,author_id,revision,content,created_at,updated_at)
                VALUES('story-1','family','owner',1,?,10,20)''', (content,))
            db.execute('''INSERT INTO access_memory_revisions
                (story_id,revision,editor_id,mutation_id,request_digest,content,occurred_at)
                VALUES('story-1',1,'owner','synthetic-mutation','synthetic-digest',?,20)''', (content,))
            db.commit()
        self.copy_database(self.db, self.backup)
        self.budget = lambda: full.Budget(128 * 1024**2, 120)
        with full.read_source(self.db, self.budget(), offline=True) as source:
            self.digest = full.fingerprint(source, full.schema(source), self.budget())[0]
            self.source_tables = {name: columns for name, columns in full.schema(source).items()
                                  if name != 'alembic_version'}
            self.source_fingerprint = full.fingerprint(source, self.source_tables, self.budget())[0]

    @staticmethod
    def copy_database(source, destination):
        with closing(sqlite3.connect(source)) as src, closing(sqlite3.connect(destination)) as dst:
            src.backup(dst)
            dst.execute('PRAGMA journal_mode=DELETE')
            dst.commit()

    def apply(self, **options):
        return migration.apply(self.db, self.backup, self.digest, self.budget(), **options)

    def test_default_review_is_read_only(self):
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

    def test_execute_applies_both_revisions_and_preserves_e6(self):
        saved = self.backup.read_bytes()
        result = self.apply(execute=True, all_writers_stopped=True)
        self.assertTrue(result['applied'])
        self.assertEqual(result['revision'], migration.TO_REVISION)
        self.assertEqual(result['new_tables_created'], 9)
        self.assertEqual(result['new_rows_created'], 0)
        self.assertFalse(result['http_activated'])
        with closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(db.execute('SELECT version_num FROM alembic_version').fetchone()[0],
                             migration.TO_REVISION)
            self.assertEqual(db.execute('SELECT revision,content FROM access_memory_stories').fetchone()[0], 1)
            for table in migration.NEW_TABLES:
                self.assertEqual(db.execute('SELECT count(*) FROM ' + table).fetchone()[0], 0)
            current = {name: columns for name, columns in full.schema(db).items()
                       if name in self.source_tables}
            self.assertEqual(full.fingerprint(db, current, self.budget())[0], self.source_fingerprint)
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchall(), [('ok',)])
        self.assertEqual(self.backup.read_bytes(), saved)

    def test_rejects_stale_backup_and_running_task(self):
        with closing(sqlite3.connect(self.backup)) as saved:
            saved.execute("UPDATE access_memory_stories SET updated_at=updated_at+1")
            saved.commit()
        with self.assertRaises(full.small.Refused):
            self.apply()
        self.copy_database(self.db, self.backup)
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("INSERT INTO tasks(type,state,priority,payload_json) "
                       "VALUES('caption','running',0,'{}')")
            db.commit()
        with self.assertRaises(full.small.Refused):
            self.apply(execute=True, all_writers_stopped=True)
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("DELETE FROM tasks WHERE state='running'")
            db.commit()
        self.copy_database(self.db, self.backup)
        Path(str(self.db) + '-wal').write_bytes(b'busy')
        with self.assertRaises(full.small.Refused):
            self.apply(execute=True, all_writers_stopped=True)

    def test_execution_requires_assertion_and_rejects_partial_or_wrong_revision(self):
        with self.assertRaises(full.small.Refused):
            self.apply(execute=True)
        with closing(sqlite3.connect(self.db)) as db:
            db.execute('CREATE TABLE access_memory_contribution_refs (story_id TEXT)')
            db.commit()
        self.copy_database(self.db, self.backup)
        with full.read_source(self.db, self.budget(), offline=True) as source:
            self.digest = full.fingerprint(source, full.schema(source), self.budget())[0]
        with self.assertRaises(full.small.Refused):
            self.apply()

    def test_postcondition_failure_rolls_back_ddl_revision_and_existing_rows(self):
        original = command.upgrade

        def corrupt_after_upgrade(config, target):
            original(config, target)
            config.attributes['connection'].exec_driver_sql(
                "UPDATE access_memory_stories SET updated_at=999")

        with patch.object(command, 'upgrade', side_effect=corrupt_after_upgrade):
            with self.assertRaises(full.small.Refused):
                self.apply(execute=True, all_writers_stopped=True)
        with closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(db.execute('SELECT version_num FROM alembic_version').fetchone()[0],
                             migration.FROM_REVISION)
            self.assertEqual(db.execute('SELECT updated_at FROM access_memory_stories').fetchone()[0], 20)
            self.assertFalse(set(migration.NEW_TABLES) & set(full.schema(db)))

    def test_backup_replacement_after_review_is_refused(self):
        original = migration.review

        def replace(*args):
            result = original(*args)
            displaced = self.root / 'displaced.sqlite'
            self.backup.rename(displaced)
            self.copy_database(self.db, self.backup)
            return result

        with patch.object(migration, 'review', side_effect=replace):
            with self.assertRaises(full.small.Refused):
                self.apply(execute=True, all_writers_stopped=True)
        with closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(db.execute('SELECT version_num FROM alembic_version').fetchone()[0],
                             migration.FROM_REVISION)
            self.assertFalse(set(migration.NEW_TABLES) & set(full.schema(db)))


if __name__ == '__main__':
    unittest.main()
