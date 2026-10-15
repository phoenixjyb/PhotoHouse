"""Reviewed offline e7 application on generated databases; no live target."""
from contextlib import closing, redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import apply_memory_group_schema as migration
import qualify_memory_groups as fixture

from alembic import command


class MemoryGroupSchemaApplicationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='memory-group-apply-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        if os.name != 'nt':
            self.root.chmod(0o700)
        self.database = self.root/'primary.sqlite'
        self.backup = self.root/'backup.sqlite'
        fixture._seed(self.database)
        fixture._backup(self.database, self.backup)
        self.digest = self.fingerprint(self.database)
        self.before = fixture._snapshot(self.database)
        self.backup_bytes = self.backup.read_bytes()

    @staticmethod
    def budget():
        return migration.full.Budget(128*1024**2,120)

    def fingerprint(self, path):
        budget = self.budget()
        with migration.full.read_source(path, budget, offline=True) as db:
            return migration.full.fingerprint(db, migration.full.schema(db), budget)[0]

    def apply(self, **options):
        return migration.apply(self.database, self.backup, self.digest, self.budget(), **options)

    def test_review_is_read_only_and_execute_needs_explicit_shutdown(self):
        before=self.database.read_bytes(),self.backup.read_bytes()
        report=self.apply()
        self.assertFalse(report['applied'])
        self.assertFalse(report['operational_quiescence_verified'])
        self.assertEqual((report['source_revision'],report['target_revision']),
                         (migration.FROM_REVISION,migration.TO_REVISION))
        with self.assertRaises(migration.full.small.Refused):
            self.apply(execute=True)
        with self.assertRaises(migration.full.small.Refused):
            self.apply(execute=1,all_writers_stopped=True)
        self.assertEqual((self.database.read_bytes(),self.backup.read_bytes()),before)

    def test_exact_addition_preserves_all_rows_schema_and_backup(self):
        with patch.dict(os.environ, {'DATABASE_URL':'sqlite:////never-open-live.sqlite'}), \
                patch('socket.socket.connect',side_effect=AssertionError('network forbidden')), \
                patch('socket.socket.bind',side_effect=AssertionError('listener forbidden')), \
                patch('subprocess.Popen',side_effect=AssertionError('child forbidden')):
            report=self.apply(execute=True,all_writers_stopped=True)
        self.assertTrue(report['applied']);self.assertFalse(report['http_activated'])
        self.assertFalse(report['backup_restored'])
        self.assertEqual(report['new_tables_created'],2)
        self.assertEqual(report['new_rows_created'],0)
        self.assertEqual(fixture._snapshot(self.database,exclude_groups=True),self.before)
        self.assertEqual(self.backup.read_bytes(),self.backup_bytes)
        self.assertEqual(fixture._revision(self.database),[(migration.TO_REVISION,)])
        with closing(fixture._db(self.database)) as db:
            for table in migration.NEW_TABLES:
                self.assertEqual(db.execute('SELECT count(*) FROM '+table).fetchone(),(0,))
            self.assertTrue(migration.verify_memory_group_schema(db))
        with self.assertRaises(migration.full.small.Refused):
            self.apply(execute=True,all_writers_stopped=True)

    def test_stale_or_separate_changed_backup_and_same_inode_refuse(self):
        with closing(fixture._db(self.backup)) as db:
            db.execute("UPDATE access_stories SET text='changed backup'");db.commit()
        with self.assertRaises(migration.full.small.Refused):
            self.apply(execute=True,all_writers_stopped=True)
        self.assertEqual(fixture._snapshot(self.database),self.before)
        with self.assertRaises(migration.full.small.Refused):
            migration.apply(self.database,self.database,self.digest,self.budget())
        alias=self.root/'alias.sqlite'
        os.link(self.database,alias)
        with self.assertRaises(ValueError):
            migration.apply(self.database,alias,self.digest,self.budget())

    def test_matching_stale_digest_wrong_revision_running_task_and_partial_schema_refuse(self):
        for change in ("UPDATE access_stories SET text='changed source'",
                       "UPDATE alembic_version SET version_num='c2e6b8a1d490'",
                       "UPDATE tasks SET state='running'",
                       'CREATE TABLE access_memory_groups(id TEXT)'):
            with self.subTest(change=change):
                with closing(fixture._db(self.database)) as db:
                    db.execute(change);db.commit()
                with self.assertRaises(migration.full.small.Refused):
                    self.apply(execute=True,all_writers_stopped=True)
                # Restore only this test-owned generated file between cases.
                self.database.unlink()
                fixture._backup(self.backup,self.database)

    def test_sidecar_and_unprivate_file_refuse_before_write(self):
        sidecar=Path(str(self.database)+'-wal');sidecar.write_bytes(b'synthetic sidecar')
        with self.assertRaises(migration.full.small.Refused):
            self.apply(execute=True,all_writers_stopped=True)
        sidecar.unlink()
        if os.name!='nt':
            self.backup.chmod(0o644)
            with self.assertRaises(ValueError):
                self.apply(execute=True,all_writers_stopped=True)
        self.assertEqual(fixture._snapshot(self.database),self.before)

    def test_injected_second_table_failure_rolls_back_ddl_and_version(self):
        actual=command.upgrade
        def incomplete(config,target):
            connection=config.attributes['connection']
            from sqlalchemy import event
            def fail(_conn,_cursor,statement,*rest):
                if statement.lstrip().startswith('CREATE TABLE '+migration.REVISION_TABLE):
                    raise RuntimeError('synthetic interruption')
            event.listen(connection,'before_cursor_execute',fail)
            try:actual(config,target)
            finally:event.remove(connection,'before_cursor_execute',fail)
        with patch.object(command,'upgrade',side_effect=incomplete):
            with self.assertRaisesRegex(RuntimeError,'synthetic interruption'):
                self.apply(execute=True,all_writers_stopped=True)
        self.assertEqual(fixture._snapshot(self.database),self.before)
        self.assertEqual(fixture._revision(self.database),[(migration.FROM_REVISION,)])
        self.assertEqual(self.backup.read_bytes(),self.backup_bytes)

    def test_row_change_extra_object_and_group_backfill_each_roll_back(self):
        actual=command.upgrade
        changes=("UPDATE access_stories SET text='wrongly rewritten'",
                 'CREATE TABLE unexpected_table(id INTEGER)',
                 "INSERT INTO access_memory_groups(id,library_id,author_id,revision,theme,asset_ids_json,excluded_asset_ids_json,source_story_ids_json,created_at,updated_at) VALUES('synthetic-group','synthetic-group-library','synthetic-owner',1,'everyday','[101]','[]','[]',1,1)")
        for sql in changes:
            with self.subTest(change=sql):
                def corrupt(config,target):
                    actual(config,target)
                    config.attributes['connection'].exec_driver_sql(sql)
                with patch.object(command,'upgrade',side_effect=corrupt):
                    with self.assertRaises(migration.full.small.Refused):
                        self.apply(execute=True,all_writers_stopped=True)
                self.assertEqual(fixture._snapshot(self.database),self.before)
                self.assertEqual(fixture._revision(self.database),[(migration.FROM_REVISION,)])

    def test_target_change_after_review_is_rechecked_under_exclusive_lock(self):
        actual=migration.review
        def change_after_review(*args):
            result=actual(*args)
            with closing(fixture._db(self.database)) as db:
                db.execute("UPDATE access_stories SET text='late change'");db.commit()
            return result
        with patch.object(migration,'review',side_effect=change_after_review):
            with self.assertRaisesRegex(migration.full.small.Refused,'Target changed after review'):
                self.apply(execute=True,all_writers_stopped=True)
        self.assertEqual(fixture._revision(self.database),[(migration.FROM_REVISION,)])

    def test_every_explicit_supported_source_preserves_rows_and_exact_objects(self):
        for origin in migration.SOURCE_REVISIONS:
            with self.subTest(origin=origin):
                source=self.root/(origin+'.sqlite')
                saved=self.root/(origin+'-backup.sqlite')
                fixture._seed(source,revision=origin)
                fixture._backup(source,saved)
                digest=self.fingerprint(source)
                saved_bytes=saved.read_bytes()
                with migration.full.read_source(source,self.budget(),offline=True) as db:
                    tables=migration.full.schema(db)
                    objects=migration._objects(db)
                    preserved={name:columns for name,columns in tables.items()
                               if name!='alembic_version'}
                    rows=migration.full.fingerprint(db,preserved,self.budget())[0]
                if origin!=migration.FROM_REVISION:
                    with self.assertRaises(migration.full.small.Refused):
                        migration.apply(source,saved,digest,self.budget(),execute=True,
                                        all_writers_stopped=True)
                result=migration.apply(source,saved,digest,self.budget(),execute=True,
                                       all_writers_stopped=True,from_revision=origin)
                self.assertEqual(result['new_tables_created'],len(migration._additions(origin)))
                self.assertEqual(result['new_rows_created'],0)
                with migration.full.read_source(source,self.budget(),offline=True) as db:
                    self.assertEqual(migration._objects(db),objects|migration._expected_addition(origin))
                    self.assertEqual(migration.full.fingerprint(db,preserved,self.budget())[0],rows)
                self.assertEqual(saved.read_bytes(),saved_bytes)

    def test_generated_a0_full_chain_interruption_and_apply(self):
        report=migration.qualify_generated(self.root/'guarded-chain')
        self.assertEqual(report,{'source_revision':'a0c9d2e4f817',
            'revision':migration.TO_REVISION,'new_tables_created':9,'new_rows_created':0,
            'interruption_rollback_verified':True,'backup_unchanged':True,
            'existing_rows_preserved':True})
        with self.assertRaises(ValueError):
            migration.qualify_generated(self.root/'guarded-chain')

    def test_unknown_source_choice_refused_before_database_access(self):
        with patch.object(migration,'require_private_file',side_effect=AssertionError('opened')):
            for value in ('head',migration.TO_REVISION,None,True):
                with self.subTest(value=value),self.assertRaises(migration.full.small.Refused):
                    self.apply(from_revision=value)

    def test_cli_review_and_failure_do_not_emit_private_paths_or_note_text(self):
        arguments=['--database',str(self.database),'--backup',str(self.backup),
                   '--reviewed-backup-digest',self.digest,'--max-bytes',str(128*1024**2),
                   '--timeout-seconds','120']
        output=io.StringIO()
        with redirect_stdout(output):self.assertEqual(migration.main(arguments),0)
        self.assertFalse(json.loads(output.getvalue())['applied'])
        error=io.StringIO()
        with redirect_stderr(error):self.assertEqual(migration.main(arguments+['--execute']),2)
        self.assertNotIn(str(self.database),output.getvalue()+error.getvalue())
        self.assertNotIn('我们',output.getvalue()+error.getvalue())


if __name__=='__main__':
    unittest.main()
