"""Offline a0-to-b1 operator checks against synthetic saved-memory data."""
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
import apply_memory_editorial_schema as migration

full = migration.full


class MemoryEditorialSchemaApplicationTests(unittest.TestCase):
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
        folder = tempfile.TemporaryDirectory(prefix='photohouse-memory-editorial-schema-')
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name).resolve()
        self.db, self.backup = self.root / 'catalog.sqlite', self.root / 'backup.sqlite'
        with closing(sqlite3.connect(self.db)) as db:
            db.execute('PRAGMA foreign_keys=ON')
            self.template.backup(db)
            db.execute("INSERT INTO access_accounts(id,phone_login,password_hash) "
                       "VALUES('owner','+12025550101','synthetic')")
            db.execute("INSERT INTO access_operators(account_id) VALUES('owner')")
            db.execute("INSERT INTO access_libraries(id,bootstrap_operator) VALUES('family','owner')")
            db.execute("INSERT INTO access_memberships(account_id,library_id,status,role,revision,approved_by) "
                       "VALUES('owner','family','approved','owner',1,'owner')")
            content = json.dumps({'title': 'Synthetic story', 'chapters': []}, separators=(',', ':'))
            db.execute('''INSERT INTO access_memory_stories
                (id,library_id,author_id,revision,content,created_at,updated_at)
                VALUES('story-1','family','owner',1,?,10,11)''', (content,))
            db.execute('''INSERT INTO access_memory_revisions
                (story_id,revision,editor_id,mutation_id,request_digest,content,occurred_at)
                VALUES('story-1',1,'owner','story-mutation','story-digest',?,11)''', (content,))
            book = json.dumps({'title': 'Synthetic saved memoir', 'story_ids': ['story-1']},
                              separators=(',', ':'))
            db.execute('''INSERT INTO access_memory_books
                (id,library_id,author_id,revision,content,created_at,updated_at)
                VALUES('book-1','family','owner',1,?,20,21)''', (book,))
            db.execute('''INSERT INTO access_memory_book_revisions
                (book_id,revision,editor_id,mutation_id,request_digest,content,occurred_at)
                VALUES('book-1',1,'owner','book-mutation','book-digest',?,21)''', (book,))
            db.execute('''INSERT INTO access_memory_contributions
                (id,story_id,library_id,author_id,kind,original_text,original_audio,
                 language,byline,sha256,duration_ms,local_processing_consent,chapter_id,
                 base_story_revision,state,mutation_id,request_digest,created_at,
                 reviewed_by_id,reviewed_at)
                VALUES('contribution-1','story-1','family','owner','text','Synthetic original',NULL,
                       'en','Synthetic author',?,NULL,1,'chapter-1',1,'accepted',
                       'contribution-mutation','contribution-digest',30,'owner',30)''', ('a' * 64,))
            db.execute('''INSERT INTO access_memory_contribution_refs
                (story_id,revision,chapter_id,ordinal,contribution_id)
                VALUES('story-1',1,'chapter-1',0,'contribution-1')''')
            db.commit()
        self.copy_database(self.db, self.backup)
        self.budget = lambda: full.Budget(128 * 1024**2, 120)
        with full.read_source(self.db, self.budget(), offline=True) as source:
            self.digest = full.fingerprint(source, full.schema(source), self.budget())[0]
            self.source_tables = {name: columns for name, columns in full.schema(source).items()
                                  if name != 'alembic_version'}
            self.source_fingerprint = full.fingerprint(source, self.source_tables, self.budget())[0]
            self.source_objects = migration._schema_objects(source)

    @staticmethod
    def copy_database(source, destination):
        with closing(sqlite3.connect(source)) as src, closing(sqlite3.connect(destination)) as dst:
            src.backup(dst)
            dst.execute('PRAGMA journal_mode=DELETE')
            dst.commit()

    def apply(self, **options):
        return migration.apply(self.db, self.backup, self.digest, self.budget(), **options)

    def test_default_review_is_read_only_and_execute_requires_quiescence(self):
        before = self.db.read_bytes(), self.backup.read_bytes()
        result = self.apply()
        self.assertEqual((result['source_revision'], result['target_revision']),
                         (migration.FROM_REVISION, migration.TO_REVISION))
        self.assertFalse(result['applied'])
        self.assertEqual(before, (self.db.read_bytes(), self.backup.read_bytes()))
        with self.assertRaises(full.small.Refused):
            self.apply(execute=True)
        self.assertEqual(before, (self.db.read_bytes(), self.backup.read_bytes()))

    def test_execution_preserves_historical_rows_and_adds_empty_editorial_tables(self):
        backup_bytes = self.backup.read_bytes()
        result = self.apply(execute=True, all_writers_stopped=True)
        self.assertTrue(result['applied'])
        self.assertEqual(result['revision'], migration.TO_REVISION)
        self.assertEqual(result['new_tables_created'], 2)
        self.assertEqual(result['new_rows_created'], 0)
        with closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(db.execute('SELECT version_num FROM alembic_version').fetchone()[0],
                             migration.TO_REVISION)
            current = {name: columns for name, columns in full.schema(db).items()
                       if name in self.source_tables}
            self.assertEqual(full.fingerprint(db, current, self.budget())[0], self.source_fingerprint)
            self.assertEqual(migration._schema_objects(db),
                             self.source_objects | migration.EDITORIAL_OBJECTS)
            for table in migration.NEW_TABLES:
                self.assertEqual(db.execute('SELECT count(*) FROM ' + table).fetchone()[0], 0)
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchall(), [('ok',)])
        self.assertEqual(self.backup.read_bytes(), backup_bytes)

    def test_wrong_revision_and_partial_b1_source_are_refused(self):
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("UPDATE alembic_version SET version_num='e6b2f8a1c903'")
            db.commit()
        self.copy_database(self.db, self.backup)
        with full.read_source(self.db, self.budget(), offline=True) as source:
            self.digest = full.fingerprint(source, full.schema(source), self.budget())[0]
        with self.assertRaises(full.small.Refused):
            self.apply()

        # Restore a fresh a0 source, then introduce one partial editorial table.
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("UPDATE alembic_version SET version_num=?", (migration.FROM_REVISION,))
            db.execute('CREATE TABLE access_memory_book_editorial (book_id TEXT)')
            db.commit()
        self.copy_database(self.db, self.backup)
        with full.read_source(self.db, self.budget(), offline=True) as source:
            self.digest = full.fingerprint(source, full.schema(source), self.budget())[0]
        with self.assertRaises(full.small.Refused):
            self.apply()

    def test_backup_row_and_schema_mismatches_are_refused(self):
        with closing(sqlite3.connect(self.backup)) as db:
            db.execute("UPDATE access_memory_books SET updated_at=updated_at+1")
            db.commit()
        with self.assertRaises(full.small.Refused):
            self.apply()
        self.copy_database(self.db, self.backup)
        with closing(sqlite3.connect(self.backup)) as db:
            db.execute('CREATE INDEX synthetic_extra ON access_memory_books(id)')
            db.commit()
        with self.assertRaises(full.small.Refused):
            self.apply()

    def test_identically_tampered_prerequisite_ddl_is_refused_with_matching_digest(self):
        with closing(sqlite3.connect(self.db)) as db:
            version = db.execute('PRAGMA schema_version').fetchone()[0]
            db.execute('PRAGMA writable_schema=ON')
            db.execute("UPDATE sqlite_master SET sql=replace(sql,'revision > 0','revision >= 0') "
                       "WHERE type='table' AND name='access_memory_contribution_refs'")
            db.execute('PRAGMA schema_version=' + str(version + 1))
            db.commit()
        self.copy_database(self.db, self.backup)
        with full.read_source(self.db, self.budget(), offline=True) as source:
            self.digest = full.fingerprint(source, full.schema(source), self.budget())[0]
        with full.read_source(self.backup, self.budget(), offline=True) as saved:
            self.assertEqual(full.fingerprint(saved, full.schema(saved), self.budget())[0], self.digest)
        with self.assertRaises(full.small.Refused):
            self.apply()

    def test_identically_tampered_prerequisite_check_literal_is_refused(self):
        with closing(sqlite3.connect(self.db)) as db:
            version = db.execute('PRAGMA schema_version').fetchone()[0]
            db.execute('PRAGMA writable_schema=ON')
            db.execute("UPDATE sqlite_master SET sql=replace(sql,?,?) "
                       "WHERE type='table' AND name='access_memory_contribution_refs'",
                       ("'chapter-1'", "'Chapter-1'"))
            db.execute('PRAGMA schema_version=' + str(version + 1))
            db.commit()
        self.copy_database(self.db, self.backup)
        with full.read_source(self.db, self.budget(), offline=True) as source:
            self.digest = full.fingerprint(source, full.schema(source), self.budget())[0]
        with full.read_source(self.backup, self.budget(), offline=True) as saved:
            self.assertEqual(full.fingerprint(saved, full.schema(saved), self.budget())[0], self.digest)
        with self.assertRaises(full.small.Refused):
            self.apply()

    def test_sql_normalization_preserves_escaped_literal_whitespace(self):
        first = ('CREATE TABLE "sample" ( "value" TEXT CHECK '
                 "( \"value\" = 'a  ''quoted'' value' ) )")
        formatted = ("create table sample ( value text check "
                     "( value = 'a  ''quoted'' value' ) )")
        changed_literal = ("create table sample ( value text check "
                           "( value = 'a ''quoted'' value' ) )")
        self.assertEqual(migration._normalize_sql(first), migration._normalize_sql(formatted))
        self.assertNotEqual(migration._normalize_sql(formatted),
                            migration._normalize_sql(changed_literal))

    def test_identically_tampered_prerequisite_index_is_refused_with_matching_digest(self):
        with closing(sqlite3.connect(self.db)) as db:
            db.execute('DROP INDEX ix_memory_contribution_refs_source')
            db.execute('CREATE INDEX synthetic_source_ref_index '
                       'ON access_memory_contribution_refs(contribution_id)')
            db.commit()
        self.copy_database(self.db, self.backup)
        with full.read_source(self.db, self.budget(), offline=True) as source:
            self.digest = full.fingerprint(source, full.schema(source), self.budget())[0]
        with full.read_source(self.backup, self.budget(), offline=True) as saved:
            self.assertEqual(full.fingerprint(saved, full.schema(saved), self.budget())[0], self.digest)
        with self.assertRaises(full.small.Refused):
            self.apply()

    def test_backup_identity_replacement_after_review_is_refused(self):
        original = migration.review

        def replace_backup_after_review(*args):
            identities = original(*args)
            displaced = self.root / 'displaced-backup.sqlite'
            self.backup.rename(displaced)
            self.copy_database(self.db, self.backup)
            return identities

        with patch.object(migration, 'review', side_effect=replace_backup_after_review):
            with self.assertRaises(full.small.Refused):
                self.apply(execute=True, all_writers_stopped=True)

    def test_running_task_is_refused_even_with_matching_backup_and_digest(self):
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("INSERT INTO tasks(type,state,priority,payload_json) "
                       "VALUES('caption','running',0,'{}')")
            db.commit()
        self.copy_database(self.db, self.backup)
        with full.read_source(self.db, self.budget(), offline=True) as source:
            self.digest = full.fingerprint(source, full.schema(source), self.budget())[0]
        with full.read_source(self.backup, self.budget(), offline=True) as saved:
            self.assertEqual(full.fingerprint(saved, full.schema(saved), self.budget())[0], self.digest)
        with self.assertRaises(full.small.Refused):
            self.apply()

    def test_source_change_after_review_is_refused_before_migration(self):
        original = migration.review

        def change_after_review(*args):
            identities = original(*args)
            with closing(sqlite3.connect(self.db)) as db:
                db.execute("UPDATE access_memory_books SET updated_at=updated_at+1")
                db.commit()
            return identities

        with patch.object(migration, 'review', side_effect=change_after_review):
            with self.assertRaises(full.small.Refused):
                self.apply(execute=True, all_writers_stopped=True)
        with closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(db.execute('SELECT version_num FROM alembic_version').fetchone()[0],
                             migration.FROM_REVISION)
            self.assertFalse(set(migration.NEW_TABLES) & set(full.schema(db)))

    def test_sidecars_are_refused(self):
        sidecar = Path(str(self.db) + '-wal')
        sidecar.write_bytes(b'synthetic active WAL')
        self.addCleanup(lambda: sidecar.unlink(missing_ok=True))
        with self.assertRaises(full.small.Refused):
            self.apply(execute=True, all_writers_stopped=True)

    def test_interrupted_ddl_rolls_back_revision_and_new_objects(self):
        def interrupt(config, _target):
            connection = config.attributes['connection']
            connection.exec_driver_sql('CREATE TABLE synthetic_partial (id TEXT)')
            raise RuntimeError('synthetic interrupted DDL')

        with patch.object(command, 'upgrade', side_effect=interrupt):
            with self.assertRaises(RuntimeError):
                self.apply(execute=True, all_writers_stopped=True)
        with closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(db.execute('SELECT version_num FROM alembic_version').fetchone()[0],
                             migration.FROM_REVISION)
            self.assertEqual(migration._schema_objects(db), self.source_objects)
            self.assertEqual(full.fingerprint(db, self.source_tables, self.budget())[0],
                             self.source_fingerprint)

    def test_preexisting_data_or_schema_mutation_is_refused_and_rolled_back(self):
        original = command.upgrade

        def mutate_data(config, target):
            original(config, target)
            config.attributes['connection'].exec_driver_sql(
                "UPDATE access_memory_books SET updated_at=999")

        with patch.object(command, 'upgrade', side_effect=mutate_data):
            with self.assertRaises(full.small.Refused):
                self.apply(execute=True, all_writers_stopped=True)
        with closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(db.execute('SELECT version_num FROM alembic_version').fetchone()[0],
                             migration.FROM_REVISION)
            self.assertEqual(full.fingerprint(db, self.source_tables, self.budget())[0],
                             self.source_fingerprint)

        def mutate_schema(config, target):
            original(config, target)
            config.attributes['connection'].exec_driver_sql(
                'CREATE TRIGGER synthetic_unexpected AFTER UPDATE ON access_memory_books '
                'BEGIN SELECT 1; END')

        with patch.object(command, 'upgrade', side_effect=mutate_schema):
            with self.assertRaises(full.small.Refused):
                self.apply(execute=True, all_writers_stopped=True)
        with closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(db.execute('SELECT version_num FROM alembic_version').fetchone()[0],
                             migration.FROM_REVISION)
            self.assertEqual(migration._schema_objects(db), self.source_objects)


if __name__ == '__main__':
    unittest.main()
