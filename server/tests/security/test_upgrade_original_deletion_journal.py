"""Synthetic offline qualification and V1-to-V2 journal upgrade checks."""
from contextlib import closing, redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
import uuid
from unittest.mock import patch

import test_family_note_deletions as family_fixture
from scripts import upgrade_original_deletion_journal as upgrade
from app.access.original_deletions import OriginalDeletionError, OriginalDeletionJournal
from scripts import rehearse_fullsize_database as full


class UpgradeOriginalDeletionJournalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        family_fixture.FamilyNoteDeletionTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        family_fixture.FamilyNoteDeletionTests.tearDownClass()

    def setUp(self):
        self.fixture = family_fixture.FamilyNoteDeletionTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.temp = tempfile.TemporaryDirectory(prefix='upgrade-original-journal-', dir='/private/tmp')
        self.addCleanup(self.temp.cleanup)
        os.chmod(self.temp.name, 0o700)
        self.root = Path(self.temp.name)
        self.primary = self.root / 'qualification-primary.sqlite'
        self.backup = self.root / 'qualification-primary-backup.sqlite'
        self.original_id = str(uuid.uuid4())
        with closing(sqlite3.connect(self.fixture.f.path)) as source, closing(
                sqlite3.connect(self.primary)) as target:
            source.backup(target)
        os.chmod(self.primary, 0o600)
        raw = b'synthetic populated original'
        with closing(sqlite3.connect(self.primary)) as db:
            author = db.execute('SELECT id FROM access_accounts LIMIT 1').fetchone()[0]
            db.execute('''INSERT INTO access_upload_annotations
                (id,author_id,library_id,batch,asset_id,kind,original_text,original_audio,
                 mime,duration_ms,sha256,language,consent,mutation_id,request_digest,created_at)
                VALUES (?,?,? ,?,101,'text',?,NULL,NULL,NULL,?,'en',1,?,?,1)''',
                (self.original_id, author, 'family-a', uuid.uuid4().hex, raw.decode(),
                 hashlib.sha256(raw).hexdigest(), str(uuid.uuid4()), hashlib.sha256(b'mutation').hexdigest()))
            db.commit()
        with closing(sqlite3.connect(self.primary)) as source, closing(
                sqlite3.connect(self.backup)) as target:
            source.backup(target)
        os.chmod(self.backup, 0o600)
        self.journal = self.root / 'qualification-journal.sqlite'
        shutil.copyfile(self.fixture.journal_path, self.journal)
        os.chmod(self.journal, 0o600)
        self.journal_backup = self.root / 'qualification-journal-backup.sqlite'
        shutil.copyfile(self.journal, self.journal_backup)
        os.chmod(self.journal_backup, 0o600)
        self.head = self.fixture.journal.head()
        self.budget = full.Budget(64 * 1024 * 1024, 60)

    @staticmethod
    def _sha(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    def _qualify(self, *, execute=False, stopped=False, state=None):
        return upgrade.qualify(self.primary, self.backup, self.journal,
            self.journal_backup, self.head[0], self.head[1], self.head[2],
            full.Budget(64 * 1024 * 1024, 60), execute=execute,
            all_writers_stopped=stopped, state=state)

    def _cli(self, *extra):
        args = ['--database', str(self.primary), '--backup', str(self.backup),
                '--journal', str(self.journal), '--journal-backup', str(self.journal_backup),
                '--namespace', self.head[0], '--expected-sequence', str(self.head[1]),
                '--expected-digest', self.head[2], '--max-bytes', str(64 * 1024 * 1024),
                '--timeout-seconds', '60', *extra]
        output = io.StringIO()
        with redirect_stdout(output):
            code = upgrade.main(args)
        return code, json.loads(output.getvalue())

    def _install_guard_action(self, action):
        primitive = OriginalDeletionJournal.upgrade_family_format

        def wrapped(journal, primary_db, *, expected_head, precommit_guard=None):
            def guard(db):
                action(journal)
                precommit_guard(db)
            return primitive(journal, primary_db, expected_head=expected_head,
                             precommit_guard=guard)

        return patch.object(OriginalDeletionJournal, 'upgrade_family_format', wrapped)

    def test_review_is_read_only_and_accepts_populated_originals(self):
        before = (self._sha(self.primary), self._sha(self.backup),
                  self._sha(self.journal), self._sha(self.journal_backup))
        result = self._qualify()
        after = (self._sha(self.primary), self._sha(self.backup),
                 self._sha(self.journal), self._sha(self.journal_backup))
        self.assertEqual(result['status'], 'reviewed')
        self.assertEqual(result['mode'], 'read-only-review')
        self.assertGreater(result['original_rows'], 0)
        self.assertEqual(result['pending_records'], 0)
        self.assertEqual(before, after)

    def test_execute_requires_writer_attestation(self):
        code, report = self._cli('--execute')
        self.assertEqual(code, 2)
        self.assertEqual(report, {'status': 'refused'})
        self.assertEqual(upgrade._format(OriginalDeletionJournal(self.journal, self.head[0])),
                         'photohouse-original-deletion-journal-v1')

    def test_execute_upgrades_journal_and_preserves_primary_and_backup(self):
        before = upgrade._state(self.primary, self.budget)['fingerprint']
        backup_hash = self._sha(self.journal_backup)
        result = self._qualify(execute=True, stopped=True)
        self.assertEqual(result['status'], 'upgraded')
        self.assertTrue(result['primary_unchanged'])
        self.assertTrue(result['journal_backup_unchanged'])
        self.assertEqual(OriginalDeletionJournal(self.journal, self.head[0]).head(), self.head)
        self.assertEqual(upgrade._format(OriginalDeletionJournal(self.journal, self.head[0])),
                         'photohouse-original-deletion-journal-v2')
        self.assertEqual(self._sha(self.journal_backup), backup_hash)
        self.assertEqual(upgrade._state(self.primary, self.budget)['fingerprint'], before)

    def test_refuses_mismatched_journal_backup(self):
        with self.journal_backup.open('ab') as stream:
            stream.write(b'x')
        with self.assertRaises(full.small.Refused):
            self._qualify()

    def test_refuses_v2_input_without_retry_or_downgrade(self):
        db = sqlite3.connect(self.primary)
        try:
            db.execute('BEGIN IMMEDIATE')
            OriginalDeletionJournal(self.journal, self.head[0]).upgrade_family_format(
                db, expected_head=self.head)
            db.commit()
        finally:
            db.close()
        shutil.copyfile(self.journal, self.journal_backup)
        os.chmod(self.journal_backup, 0o600)
        code, report = self._cli('--execute', '--all-writers-stopped')
        self.assertEqual(code, 2)
        self.assertEqual(report, {'status': 'refused'})

    def test_locked_guard_detects_replaced_input(self):
        def replace_journal_backup(_journal):
            changed = self.root / 'replaced-journal-backup.sqlite'
            shutil.copyfile(self.journal_backup, changed)
            os.chmod(changed, 0o600)
            os.replace(changed, self.journal_backup)

        with self._install_guard_action(replace_journal_backup):
            with self.assertRaises(full.small.Refused):
                self._qualify(execute=True, stopped=True)
        self.assertEqual(upgrade._format(OriginalDeletionJournal(self.journal, self.head[0])),
                         'photohouse-original-deletion-journal-v1')

    def test_locked_guard_detects_primary_backup_mutation(self):
        def mutate_backup(_journal):
            with self.backup.open('ab') as stream:
                stream.write(b'changed')

        with self._install_guard_action(mutate_backup):
            with self.assertRaises(full.small.Refused):
                self._qualify(execute=True, stopped=True)
        self.assertEqual(upgrade._format(OriginalDeletionJournal(self.journal, self.head[0])),
                         'photohouse-original-deletion-journal-v1')

    def test_locked_guard_detects_journal_backup_mutation(self):
        def mutate_backup(_journal):
            with self.journal_backup.open('ab') as stream:
                stream.write(b'changed')

        with self._install_guard_action(mutate_backup):
            with self.assertRaises(full.small.Refused):
                self._qualify(execute=True, stopped=True)
        self.assertEqual(upgrade._format(OriginalDeletionJournal(self.journal, self.head[0])),
                         'photohouse-original-deletion-journal-v1')

    def test_primitive_holds_ledger_write_lock_before_guard_and_before_ddl(self):
        primitive = OriginalDeletionJournal.upgrade_family_format
        observed = []

        def wrapped(journal, primary_db, *, expected_head, precommit_guard=None):
            def guard(db):
                probe = sqlite3.connect(journal.path, timeout=0, isolation_level=None)
                try:
                    with self.assertRaises(sqlite3.OperationalError):
                        probe.execute('BEGIN IMMEDIATE')
                    columns = {row[1] for row in probe.execute('PRAGMA table_info(deletions)')}
                    observed.append(('family_binding_json' not in columns, db.in_transaction))
                finally:
                    if probe.in_transaction:
                        probe.rollback()
                    probe.close()
                precommit_guard(db)
            return primitive(journal, primary_db, expected_head=expected_head,
                             precommit_guard=guard)

        with patch.object(OriginalDeletionJournal, 'upgrade_family_format', wrapped):
            result = self._qualify(execute=True, stopped=True)
        self.assertEqual(result['status'], 'upgraded')
        self.assertEqual(observed, [(True, True)])

    def test_refuses_wrong_identity_schema(self):
        with closing(sqlite3.connect(self.primary)) as db:
            db.execute('DROP TRIGGER trg_family_note_no_reuse')
            db.commit()
        with closing(sqlite3.connect(self.primary)) as source, closing(
                sqlite3.connect(self.backup)) as target:
            source.backup(target)
        os.chmod(self.backup, 0o600)
        with self.assertRaises(full.small.Refused):
            self._qualify()

    def test_refuses_primary_marker_outside_journal_history(self):
        with closing(sqlite3.connect(self.primary)) as db:
            db.execute("UPDATE access_original_deletion_state SET applied_digest=? WHERE id=1",
                       ('a' * 64,))
            db.commit()
        with closing(sqlite3.connect(self.primary)) as source, closing(
                sqlite3.connect(self.backup)) as target:
            source.backup(target)
        os.chmod(self.backup, 0o600)
        with self.assertRaises(OriginalDeletionError):
            self._qualify()

    def test_refuses_pending_journal_record(self):
        journal = OriginalDeletionJournal(self.journal, self.head[0])
        with closing(sqlite3.connect(self.primary, isolation_level=None)) as db:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('PRAGMA secure_delete=ON')
            db.execute('BEGIN IMMEDIATE')
            cursor = db.execute('SELECT * FROM access_upload_annotations WHERE id=?',
                                (self.original_id,))
            row = dict(zip((column[0] for column in cursor.description), cursor.fetchone()))
            journal.append(db, 'upload', row, 2)
            db.rollback()
        self.head = journal.head()
        shutil.copyfile(self.journal, self.journal_backup)
        os.chmod(self.journal_backup, 0o600)
        with self.assertRaises(full.small.Refused):
            self._qualify()

    def test_refuses_corrupt_journal_chain(self):
        with closing(sqlite3.connect(self.journal)) as db:
            db.execute("UPDATE journal_meta SET head_digest=? WHERE id=1", ('f' * 64,))
            db.commit()
        shutil.copyfile(self.journal, self.journal_backup)
        os.chmod(self.journal_backup, 0o600)
        with self.assertRaises(OriginalDeletionError):
            self._qualify()

    def test_cli_refusal_has_no_private_details(self):
        with closing(sqlite3.connect(self.primary)) as db:
            db.execute("UPDATE access_original_deletion_state SET applied_digest=? WHERE id=1",
                       ('b' * 64,))
            db.commit()
        with closing(sqlite3.connect(self.primary)) as source, closing(
                sqlite3.connect(self.backup)) as target:
            source.backup(target)
        os.chmod(self.backup, 0o600)
        code, report = self._cli()
        self.assertEqual(code, 2)
        self.assertEqual(report, {'status': 'refused'})

    def test_oversized_journal_is_rejected_before_journal_parse(self):
        with self.journal_backup.open('ab') as stream:
            stream.write(b'x' * (1024 * 1024 + 1))
        budget = full.Budget(1024 * 1024, 10)
        with patch.object(upgrade._BoundedJournal, '_connect',
                          side_effect=AssertionError('journal parsing began')):
            with self.assertRaises(full.small.Refused):
                upgrade._regular_private(self.journal_backup, 'Journal backup', budget)

    def test_post_upgrade_verification_failure_reports_incomplete(self):
        original = upgrade._review_primary
        calls = 0

        def fail_second(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError('synthetic readback failure')
            return original(*args, **kwargs)

        with patch.object(upgrade, '_review_primary', fail_second):
            code, report = self._cli('--execute', '--all-writers-stopped')
        self.assertEqual(code, 2)
        self.assertEqual(report['status'], 'upgraded_verification_incomplete')
        self.assertEqual(OriginalDeletionJournal(self.journal, self.head[0]).head(), self.head)

    def test_primary_commit_exception_after_ledger_commit_reports_incomplete(self):
        open_primary = upgrade._open_primary

        class PrimaryCommitFailure:
            def __init__(self, connection):
                self.connection = connection

            def __getattr__(self, name):
                return getattr(self.connection, name)

            def commit(self):
                raise sqlite3.OperationalError('synthetic primary commit failure')

        def fail_primary_commit(*args, **kwargs):
            connection = open_primary(*args, **kwargs)
            return PrimaryCommitFailure(connection) if kwargs.get('writable') else connection

        with patch.object(upgrade, '_open_primary', fail_primary_commit):
            code, report = self._cli('--execute', '--all-writers-stopped')
        self.assertEqual(code, 2)
        self.assertEqual(report['status'], 'upgraded_verification_incomplete')
        upgraded = upgrade._BoundedJournal(self.journal, self.head[0],
                                           full.Budget(64 * 1024 * 1024, 10))
        self.assertEqual(upgraded.head(), self.head)
        self.assertEqual(upgrade._format(upgraded), 'photohouse-original-deletion-journal-v2')

    def test_expired_budget_during_post_commit_readback_reports_incomplete(self):
        original = upgrade._review_primary
        calls = 0

        def expire_second_review(path, journal, budget, expected_head):
            nonlocal calls
            calls += 1
            if calls == 2:
                budget.deadline = 0
            return original(path, journal, budget, expected_head)

        with patch.object(upgrade, '_review_primary', expire_second_review):
            code, report = self._cli('--execute', '--all-writers-stopped')
        self.assertEqual(code, 2)
        self.assertEqual(report['status'], 'upgraded_verification_incomplete')
        upgraded = upgrade._BoundedJournal(self.journal, self.head[0],
                                           full.Budget(64 * 1024 * 1024, 10))
        self.assertEqual(upgraded.head(), self.head)
        self.assertEqual(upgrade._format(upgraded), 'photohouse-original-deletion-journal-v2')


if __name__ == '__main__':
    unittest.main()
