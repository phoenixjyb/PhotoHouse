"""Guarded photo-stack schema application on private synthetic databases only."""
from contextlib import closing
import hashlib
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))

import apply_library_photo_stack_schema as migration
import qualify_library_photo_stacks as fixture
from alembic import command
from app.access.original_deletions import OriginalDeletionJournal


class LibraryPhotoStackSchemaApplicationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='photo-stack-schema-apply-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        if os.name != 'nt':
            self.root.chmod(0o700)
        self.primary = self.root / 'primary.sqlite'
        self.backup = self.root / 'primary-backup.sqlite'
        self.journal_path = self.root / 'journal.sqlite'
        self.journal_backup = self.root / 'journal-backup.sqlite'
        self.origin = migration.A0_REVISION
        self.namespace = None
        self._seed()

    @staticmethod
    def budget():
        return migration.full.Budget(128 * 1024**2, 180)

    def _seed(self, origin=None, journal_version=1, with_originals=True):
        origin = origin or self.origin
        for path in (self.primary, self.backup, self.journal_path, self.journal_backup):
            if path.exists():
                path.unlink()
        note = fixture.fixture._seed(self.primary, revision=migration.A0_REVISION)
        self.namespace = 'e08d0f8b-c4ec-4f7b-9e2b-a3cf26da6e03'
        journal = OriginalDeletionJournal.initialize(
            self.journal_path, self.namespace, format_version=journal_version)
        if with_originals:
            fixture._seed_originals(self.primary, journal)
        else:
            with fixture._connection(self.primary) as db:
                journal.bind(db)
        if origin != migration.A0_REVISION:
            fixture._migrate(self.primary, origin)
        if origin == migration.E7_REVISION:
            from app.access.memory_groups import MemoryGroups
            from app.access.service import AccessService
            with fixture._connection(self.primary, journal) as db:
                MemoryGroups(AccessService(db, clock=lambda: fixture.fixture.NOW)).save(
                    fixture.fixture.TOKEN, fixture.fixture.LIBRARY, fixture.fixture._body(note))
        fixture.fixture._backup(self.primary, self.backup)
        shutil.copyfile(self.journal_path, self.journal_backup)
        if os.name != 'nt':
            self.journal_backup.chmod(0o600)
        self.origin = origin
        self.journal = OriginalDeletionJournal(self.journal_path, self.namespace)
        self.head = self.journal.head()
        self.digest = self._primary_digest(self.primary)
        self.journal_hash = hashlib.sha256(self.journal_path.read_bytes()).hexdigest()
        self.before = fixture.fixture._snapshot(self.primary)
        self.backup_bytes = self.backup.read_bytes()
        self.journal_bytes = self.journal_path.read_bytes()
        self.journal_backup_bytes = self.journal_backup.read_bytes()

    def _primary_digest(self, path):
        budget = self.budget()
        with migration.full.read_source(path, budget, offline=True) as db:
            return migration.full.fingerprint(db, migration.full.schema(db), budget)[0]

    def apply(self, **options):
        options.setdefault('from_revision', self.origin)
        return migration.apply(self.primary, self.backup, self.journal_path,
            self.journal_backup, self.digest, self.namespace, self.head[1],
            self.head[2], self.journal_hash, self.budget(), **options)

    def _refresh_backup_and_digest(self):
        self.backup.unlink()
        fixture.fixture._backup(self.primary, self.backup)
        self.digest = self._primary_digest(self.primary)
        self.backup_bytes = self.backup.read_bytes()

    def _refresh_journal_backup(self):
        self.journal_backup.write_bytes(self.journal_path.read_bytes())
        if os.name != 'nt':
            self.journal_backup.chmod(0o600)
        self.head = self.journal.head()
        self.journal_hash = hashlib.sha256(self.journal_path.read_bytes()).hexdigest()
        self.journal_bytes = self.journal_path.read_bytes()
        self.journal_backup_bytes = self.journal_backup.read_bytes()

    def _assert_preserved(self, before):
        old_objects, old_rows = before
        current_objects, current_rows = fixture.fixture._snapshot(self.primary)
        self.assertTrue(all(item in current_objects for item in old_objects))
        self.assertTrue(all(current_rows.get(name) == rows for name, rows in old_rows.items()))

    def test_a0_full_chain_preserves_originals_and_v1_history(self):
        report = self.apply(execute=True, all_writers_stopped=True)
        self.assertTrue(report['applied'])
        self.assertEqual(report['source_revision'], migration.A0_REVISION)
        self.assertEqual(report['revision'], migration.TO_REVISION)
        self.assertEqual(report['new_tables_created'], 13)
        self.assertTrue(report['journal_unchanged'])
        self.assertEqual(report['journal_format_version'], 1)
        self.assertFalse(report['journal_format_upgrade_required'])
        self.assertTrue(report['photo_stack_history_ready'])
        self.assertFalse(report['family_note_erasure_format_ready'])
        self._assert_preserved(self.before)
        self.assertEqual(self.backup.read_bytes(), self.backup_bytes)
        self.assertEqual(self.journal_path.read_bytes(), self.journal_bytes)
        self.assertEqual(self.journal_backup.read_bytes(), self.journal_backup_bytes)
        self.assertEqual(self.journal.head(), self.head)
        with closing(fixture.fixture._db(self.primary)) as db:
            self.assertTrue(migration.stack_available(db))
            for table in migration._additions(migration.A0_REVISION):
                self.assertEqual(db.execute('SELECT count(*) FROM ' + migration.full.quoted(table)).fetchone(), (0,))

    def test_e7_adds_only_stack_tables_and_preserves_v2_format(self):
        self._seed(migration.E7_REVISION, journal_version=2, with_originals=False)
        before = fixture.fixture._snapshot(self.primary)
        report = self.apply(execute=True, all_writers_stopped=True)
        self.assertEqual(report['new_tables_created'], 4)
        self.assertEqual(report['journal_format_version'], 2)
        self.assertFalse(report['journal_format_upgrade_required'])
        self._assert_preserved(before)
        self.assertEqual(self.journal_path.read_bytes(), self.journal_bytes)

    def test_review_is_read_only_and_execution_requires_explicit_shutdown(self):
        before = (self.primary.read_bytes(), self.backup.read_bytes(),
                  self.journal_path.read_bytes(), self.journal_backup.read_bytes())
        report = self.apply()
        self.assertFalse(report['applied'])
        self.assertFalse(report['operational_quiescence_verified'])
        self.assertEqual(report['new_tables_planned'], 13)
        with self.assertRaises(migration.full.small.Refused):
            self.apply(execute=True)
        with self.assertRaises(migration.full.small.Refused):
            self.apply(execute=1, all_writers_stopped=True)
        self.assertEqual(before, (self.primary.read_bytes(), self.backup.read_bytes(),
                                  self.journal_path.read_bytes(), self.journal_backup.read_bytes()))

    def test_mismatched_primary_backup_journal_backup_head_and_hash_refuse(self):
        with closing(fixture.fixture._db(self.backup)) as db:
            db.execute("UPDATE access_stories SET text='stale backup'")
            db.commit()
        with self.assertRaises(migration.full.small.Refused):
            self.apply()

        self._seed()
        self.journal_backup.write_bytes(self.journal_backup.read_bytes() + b'x')
        with self.assertRaises(migration.full.small.Refused):
            self.apply()

        self._seed()
        with self.assertRaises(migration.full.small.Refused):
            migration.apply(self.primary, self.backup, self.journal_path, self.journal_backup,
                self.digest, self.namespace, self.head[1], '0'*64,
                self.journal_hash, self.budget())

        with self.assertRaises(migration.full.small.Refused):
            migration.apply(self.primary, self.backup, self.journal_path, self.journal_backup,
                self.digest, self.namespace, self.head[1] + 1, self.head[2],
                self.journal_hash, self.budget())

    def test_stale_primary_marker_and_partial_f2_schema_refuse(self):
        # A logically matching backup with an old but valid marker must not be
        # admitted against a journal whose head has advanced past that marker.
        with closing(fixture.fixture._db(self.primary)) as db:
            db.execute('UPDATE access_original_deletion_state SET applied_seq=0,applied_digest=? WHERE id=1',
                       (self.journal.history_digest(0),))
            db.commit()
        self._refresh_backup_and_digest()
        with self.assertRaises(migration.full.small.Refused):
            self.apply()

        self._seed()
        with closing(fixture.fixture._db(self.primary)) as db:
            db.execute('CREATE TABLE access_photo_stack_indexes(id TEXT)')
            db.commit()
        self.digest = self._primary_digest(self.primary)
        self._refresh_backup_and_digest()
        with self.assertRaises(migration.full.small.Refused):
            self.apply()

    def test_interrupted_migration_rolls_back_primary_and_leaves_journal_unchanged(self):
        before = self.primary.read_bytes(), self.backup.read_bytes(), self.journal_path.read_bytes()
        actual = command.upgrade

        def interrupt(config, revision):
            connection = config.attributes['connection']
            from sqlalchemy import event

            def fail(_conn, _cursor, statement, *_rest):
                if statement.lstrip().startswith('CREATE TABLE ' + migration.STACK_TABLES[2]):
                    raise RuntimeError('synthetic photo-stack interruption')
            event.listen(connection, 'before_cursor_execute', fail)
            try:
                return actual(config, revision)
            finally:
                event.remove(connection, 'before_cursor_execute', fail)

        with patch.object(command, 'upgrade', side_effect=interrupt):
            with self.assertRaisesRegex(RuntimeError, 'synthetic photo-stack interruption'):
                self.apply(execute=True, all_writers_stopped=True)
        self.assertEqual(fixture.fixture._snapshot(self.primary), self.before)
        self.assertEqual((self.primary.read_bytes(), self.backup.read_bytes(), self.journal_path.read_bytes()), before)

    def test_unexpected_object_backfill_and_existing_row_mutation_roll_back(self):
        actual = command.upgrade
        changes = (
            'CREATE TABLE unexpected_photo_stack_object(id INTEGER)',
            "INSERT INTO access_photo_stack_indexes VALUES('" + fixture.fixture.LIBRARY + "',"
            "'00000000-0000-4000-8000-000000000001','" + 'a'*64 + "',0,1)",
            "UPDATE captions SET text='mutated existing caption'",
        )
        for sql in changes:
            with self.subTest(change=sql):
                self._seed()
                def corrupt(config, revision):
                    actual(config, revision)
                    config.attributes['connection'].exec_driver_sql(sql)
                with patch.object(command, 'upgrade', side_effect=corrupt):
                    with self.assertRaises(migration.full.small.Refused):
                        self.apply(execute=True, all_writers_stopped=True)
                self.assertEqual(fixture.fixture._snapshot(self.primary), self.before)
                self.assertEqual(self.journal_path.read_bytes(), self.journal_bytes)

    def test_replaced_input_is_rejected_before_migration(self):
        actual = migration._expected_addition

        def replace_after_review(revision):
            value = actual(revision)
            replacement = self.root / 'replacement.sqlite'
            shutil.copyfile(self.backup, replacement)
            if os.name != 'nt':
                replacement.chmod(0o600)
            os.replace(replacement, self.primary)
            return value

        with patch.object(migration, '_expected_addition', side_effect=replace_after_review):
            with self.assertRaises(migration.full.small.Refused):
                self.apply(execute=True, all_writers_stopped=True)
        self.assertEqual(self.journal_path.read_bytes(), self.journal_bytes)

    def test_same_file_sidecar_or_changed_journal_hash_refuse(self):
        with self.assertRaises(migration.full.small.Refused):
            migration.apply(self.primary, self.primary, self.journal_path,
                self.journal_backup, self.digest, self.namespace, self.head[1],
                self.head[2], self.journal_hash, self.budget())
        sidecar = Path(str(self.primary) + '-wal')
        sidecar.write_bytes(b'synthetic sidecar')
        with self.assertRaises(migration.full.small.Refused):
            self.apply()
        sidecar.unlink()
        with self.assertRaises(migration.full.small.Refused):
            migration.apply(self.primary, self.backup, self.journal_path, self.journal_backup,
                self.digest, self.namespace, self.head[1], self.head[2], '0'*64, self.budget())

    def test_running_writer_and_unprivate_input_refuse(self):
        with closing(fixture.fixture._db(self.primary)) as db:
            db.execute("UPDATE tasks SET state='running'")
            db.commit()
        self.digest = self._primary_digest(self.primary)
        self._refresh_backup_and_digest()
        with self.assertRaises(migration.full.small.Refused):
            self.apply(execute=True, all_writers_stopped=True)

        self._seed()
        if os.name != 'nt':
            self.journal_backup.chmod(0o644)
            with self.assertRaises(migration.full.small.Refused):
                self.apply()

    def test_only_explicit_a0_or_e7_source_revision_is_supported(self):
        with self.assertRaises(migration.full.small.Refused):
            self.apply(from_revision='d1f6a8c3e920')

    def test_existing_v2_v3_v4_histories_keep_their_format_and_original_records(self):
        for version in (2,3,4):
            with self.subTest(version=version):
                self._seed(migration.A0_REVISION,journal_version=version)
                report = self.apply(execute=True,all_writers_stopped=True)
                self.assertEqual(report['journal_format_version'],version)
                self.assertFalse(report['journal_upgrade_performed'])
                self.assertEqual(self.journal_path.read_bytes(),self.journal_bytes)
                self.assertEqual(self.journal.head(),self.head)
                self._assert_preserved(self.before)

    def test_reviewed_journal_handles_cannot_write(self):
        guard = migration._ReadOnlyJournal(self.journal_path,self.namespace,self.budget())
        with closing(guard._connect()) as db:
            self.assertEqual(db.execute('PRAGMA query_only').fetchone()[0],1)
            with self.assertRaises(sqlite3.OperationalError):
                db.execute('UPDATE journal_meta SET head_seq=99')
        self.assertEqual(self.journal_path.read_bytes(),self.journal_bytes)

    def test_backup_drift_during_migration_rolls_back_without_restoring_that_backup(self):
        actual = command.upgrade
        def corrupt(config,revision):
            actual(config,revision)
            with self.journal_backup.open('ab') as stream:
                stream.write(b'generated external drift')
        with patch.object(command,'upgrade',side_effect=corrupt):
            with self.assertRaises(migration.full.small.Refused):
                self.apply(execute=True,all_writers_stopped=True)
        self.assertEqual(fixture.fixture._snapshot(self.primary),self.before)
        self.assertEqual(self.journal_path.read_bytes(),self.journal_bytes)
        self.assertNotEqual(self.journal_backup.read_bytes(),self.journal_backup_bytes)


if __name__ == '__main__':
    unittest.main()
