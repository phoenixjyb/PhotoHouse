"""CLI coverage for explicit deletion-journal guarded person ownership repair."""
from contextlib import closing, redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(ROOT / 'scripts'))
import test_library_reads as fixtures
from app.access.original_deletions import OriginalDeletionJournal
from app.access.provisioning_apply import guarded_database
from app.access.runtime import REQUIRED_REVISION
import provision_access as cli
from test_access_foundation import NOW


JOURNAL_ARGS = ('--original-deletion-journal', '--original-deletion-namespace')


class OperatorDeletionGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Use the repair operation's explicitly supported schema, produced by
        # the real migration chain rather than relabeling a newer fixture.
        fixtures.LibraryReadTests.setUpClass(migration_target=REQUIRED_REVISION)

    @classmethod
    def tearDownClass(cls):
        fixtures.LibraryReadTests.tearDownClass()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='photohouse-deletion-guard-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.database = self.root / 'metadata.sqlite'
        self.backup = self.root / 'backup.sqlite'
        self.request = self.root / 'repair-request.json'
        self.plan = self.root / 'repair-plan.json'
        self.review_restore = self.root / 'review-restore.sqlite'
        self.apply_restore = self.root / 'apply-restore.sqlite'
        self.journal_path = self.root / 'external-deletions.sqlite'
        self.namespace = str(uuid.uuid4())
        with closing(sqlite3.connect(self.database)) as db:
            fixtures.LibraryReadTests.template.backup(db)
            self.owner = db.execute(
                "SELECT account_id FROM access_memberships WHERE library_id='family-a' AND role='owner'"
            ).fetchone()[0]
            db.executemany('INSERT INTO assets(id,path,hash_sha256,status) VALUES (?,?,?,?)', [
                (1003, 'synthetic/suppressed-target.jpg', 'synthetic-hash-1003', 'suppressed'),
                (1004, 'synthetic/active-collateral.jpg', 'synthetic-hash-1004', 'active'),
            ])
            db.executemany('INSERT INTO persons(id,display_name,face_count) VALUES (?,?,?)', [
                (301, 'Synthetic Target', 2), (302, 'Synthetic Collateral', 2),
            ])
            db.executemany(
                'INSERT INTO face_detections(id,asset_id,bbox_x,bbox_y,bbox_w,bbox_h,person_id,label_source) '
                'VALUES (?,?,?,?,?,?,?,?)', [
                    (3011, 101, 0, 0, 1, 1, 301, 'manual'),
                    (3012, 1003, 0, 0, 1, 1, 301, 'manual'),
                    (3021, 1003, 0, 0, 1, 1, 302, 'manual'),
                    (3022, 1004, 0, 0, 1, 1, 302, 'manual'),
                ])
            db.commit()
        self.journal = OriginalDeletionJournal.initialize(self.journal_path, self.namespace)
        with closing(sqlite3.connect(self.database)) as db:
            db.execute('PRAGMA foreign_keys=ON')
            self.journal.bind(db)
        self.now = NOW
        for target in ('socket.socket.bind', 'socket.socket.connect', 'subprocess.Popen', 'os.system'):
            guard = patch(target, side_effect=AssertionError('External I/O forbidden'))
            guard.start()
            self.addCleanup(guard.stop)

    def journal_options(self, *, path=None, namespace=None):
        return ['--original-deletion-journal', str(path or self.journal_path),
                '--original-deletion-namespace', namespace or self.namespace]

    def call(self, command, *args):
        output, error = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            code = cli.main([command, '--database', str(self.database), *map(str, args)],
                            clock=lambda: self.now)
        text = output.getvalue() + error.getvalue()
        for private in (str(self.journal_path), self.namespace, 'Synthetic Target', 'Synthetic Collateral',
                        'synthetic-hash-1003', 'journal_meta', 'deletions'):
            self.assertNotIn(private, text)
        return code, json.loads(output.getvalue()) if output.getvalue() else None, error.getvalue()

    def make_plan(self, *, with_guard=True):
        self.request.write_text(json.dumps({
            'library_id': 'family-a', 'operator_account_id': self.owner,
            'person_id': 301, 'asset_ids': [1003],
            'quiescence_reference': 'synthetic-stopped',
            'provenance_reference': 'synthetic-provenance',
        }))
        guard = self.journal_options() if with_guard else []
        code, result, error = self.call('plan-person-repair', '--request', self.request,
                                        '--out', self.plan, *guard)
        self.assertEqual((code, error), (0, ''))
        self.plan_digest = result['plan_digest']
        self.plan_id = result['plan_id']
        return result

    def copy_backup(self):
        with guarded_database(self.database, read_only=True,
                              deletion_history=cli_context(self.journal_path, self.namespace))() as source, \
                closing(sqlite3.connect(self.backup)) as target:
            source.backup(target)

    def review_args(self, *, restore_out=None, with_guard=True):
        self.copy_backup()
        args = ['--plan', self.plan, '--backup', self.backup,
                '--reviewed-plan-digest', self.plan_digest,
                '--authority-reference', 'synthetic-authority',
                '--restore-reference', 'synthetic-restore']
        if restore_out is not False:
            args.extend(['--restore-out', restore_out or self.review_restore])
        if with_guard:
            args.extend(self.journal_options())
        return args

    def apply_args(self, review_digest):
        return ['--plan', self.plan, '--backup', self.backup,
                '--reviewed-plan-digest', self.plan_digest,
                '--authority-reference', 'synthetic-authority',
                '--restore-reference', 'synthetic-restore',
                '--restore-out', self.apply_restore, '--review-digest', review_digest,
                '--all-writers-stopped', *self.journal_options()]

    def query(self, sql, args=()):
        with guarded_database(self.database, read_only=True,
                              deletion_history=cli_context(self.journal_path, self.namespace))() as db:
            return db.execute(sql, args).fetchall()

    def test_bound_repair_plan_validate_review_apply_receipt(self):
        planned = self.make_plan()
        self.assertEqual(planned['operation'], 'repair_suppressed_person_ownership')
        code, validated, error = self.call('validate', '--plan', self.plan, *self.journal_options())
        self.assertEqual((code, error), (0, ''))
        self.assertTrue(validated['valid'])

        review_args = self.review_args()
        code, reviewed, error = self.call('review', *review_args)
        self.assertEqual((code, error), (0, ''))
        self.assertTrue(self.review_restore.is_file())
        self.assertNotIn(str(self.journal_path), json.dumps(reviewed))
        self.assertNotIn(self.namespace, json.dumps(reviewed))

        code, applied, error = self.call('apply', *self.apply_args(reviewed['review_digest']))
        self.assertEqual((code, error), (0, ''))
        self.assertTrue(self.apply_restore.is_file())
        self.assertTrue(applied['applied'])
        self.assertEqual(self.query('SELECT status FROM assets WHERE id=1003'), [('suppressed',)])
        self.assertEqual(self.query('SELECT person_id,library_id FROM access_person_libraries WHERE person_id=301'),
                         [(301, 'family-a')])
        self.assertEqual(self.query('SELECT person_id,label_source FROM face_detections ORDER BY id'),
                         [(301, 'manual'), (301, 'manual'), (302, 'manual'), (302, 'manual')])

        code, receipt, error = self.call('receipt', '--plan-id', self.plan_id,
            '--reviewed-plan-digest', self.plan_digest, *self.journal_options())
        self.assertEqual((code, error), (0, ''))
        self.assertTrue(receipt['receipt_found'])
        self.assertEqual(receipt['operation'], 'repair_suppressed_person_ownership')

    def test_missing_or_mismatched_options_refuse_without_leaking_values(self):
        self.request.write_text(json.dumps({
            'library_id': 'family-a', 'operator_account_id': self.owner,
            'person_id': 301, 'asset_ids': [1003],
            'quiescence_reference': 'synthetic-stopped',
            'provenance_reference': 'synthetic-provenance',
        }))
        code, _, _ = self.call('plan-person-repair', '--request', self.request,
                               '--out', self.plan)
        self.assertEqual(code, 2)
        code, _, _ = self.call('plan-person-repair', '--request', self.request,
            '--out', self.plan, '--original-deletion-journal', self.journal_path)
        self.assertEqual(code, 2)
        code, _, _ = self.call('plan-person-repair', '--request', self.request,
            '--out', self.plan, *self.journal_options(namespace=str(uuid.uuid4())))
        self.assertEqual(code, 2)

    def test_journal_flags_are_not_available_to_other_command_families(self):
        with self.assertRaises(cli.OperatorError):
            cli.parser().parse_args(['plan-management', '--database', str(self.database),
                '--request', str(self.request), '--out', str(self.plan), *self.journal_options()])
        for malformed in ({}, {'plan': None}, {'plan': []}, {'plan': 'invalid'},
                          {'plan': {'operation': 'bootstrap_owner'}}):
            self.plan.write_text(json.dumps(malformed))
            code, _, _ = self.call('validate', '--plan', self.plan, *self.journal_options())
            self.assertEqual(code, 2)

    def test_receipt_with_journal_context_refuses_nonrepair_operation(self):
        plan_id, digest = str(uuid.uuid4()), 'a' * 64
        with closing(sqlite3.connect(self.database)) as db:
            db.execute('INSERT INTO access_provisioning_receipts(plan_id,plan_digest,receipt) VALUES (?,?,?)',
                (plan_id, digest, json.dumps({'operation': 'import_management_ownership'})))
            db.commit()
        code, _, _ = self.call('receipt', '--plan-id', plan_id,
            '--reviewed-plan-digest', digest, *self.journal_options())
        self.assertEqual(code, 2)

    def test_guarded_review_requires_restore_file_and_apply_rejects_changed_journal_identity(self):
        self.make_plan()
        args = self.review_args(restore_out=False)
        code, _, _ = self.call('review', *args)
        self.assertEqual(code, 2)
        args = self.review_args()
        code, reviewed, error = self.call('review', *args)
        self.assertEqual((code, error), (0, ''))

        replacement = self.root / 'replacement-ledger.sqlite'
        shutil.copy2(self.journal_path, replacement)
        os.replace(replacement, self.journal_path)
        before = self.database.read_bytes()
        code, _, _ = self.call('apply', *self.apply_args(reviewed['review_digest']))
        self.assertEqual(code, 2)
        self.assertEqual(self.database.read_bytes(), before)

    def test_changed_or_invalid_journal_head_refuses_read_only_plan(self):
        self.journal_path.chmod(0o600)
        with closing(sqlite3.connect(self.journal_path)) as db:
            db.execute("UPDATE journal_meta SET head_digest=? WHERE id=1", ('0' * 64,))
            db.commit()
        before = self.database.read_bytes()
        self.request.write_text(json.dumps({
            'library_id': 'family-a', 'operator_account_id': self.owner,
            'person_id': 301, 'asset_ids': [1003],
            'quiescence_reference': 'synthetic-stopped',
            'provenance_reference': 'synthetic-provenance',
        }))
        code, _, _ = self.call('plan-person-repair', '--request', self.request,
            '--out', self.plan, *self.journal_options())
        self.assertEqual(code, 2)
        self.assertEqual(self.database.read_bytes(), before)


def cli_context(journal_path, namespace):
    from app.access.provisioning_apply import capture_deletion_history
    return capture_deletion_history(journal_path, namespace)


if __name__ == '__main__':
    unittest.main()
