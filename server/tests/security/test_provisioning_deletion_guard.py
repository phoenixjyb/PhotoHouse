"""A bound ownership repair must retain its external deletion-history guard."""
from contextlib import closing
import hashlib
import os
from pathlib import Path
import shutil
import sqlite3
import unittest
from unittest.mock import patch
import uuid

import test_suppressed_ownership_repair as repair_fixtures
from app.access.original_deletions import OriginalDeletionJournal
from app.access.provisioning import PlanRejected, ProvisioningPlanner
from app.access.provisioning_apply import (
    apply_reviewed, assert_deletion_history, capture_deletion_history,
    guarded_database, plan_digest, review_backup,
)
from app.access.runtime import ExistingDatabase, RuntimeUnavailable


class ProvisioningDeletionGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        repair_fixtures.SuppressedOwnershipRepairTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        repair_fixtures.SuppressedOwnershipRepairTests.tearDownClass()

    def setUp(self):
        self.fixture = repair_fixtures.SuppressedOwnershipRepairTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.path, self.backup = self.fixture.path, self.fixture.backup
        self.ledger = self.path.parent / 'deletions.sqlite'
        self.namespace = str(uuid.uuid4())
        self.journal = OriginalDeletionJournal.initialize(self.ledger, self.namespace)
        with ExistingDatabase(self.path)() as db:
            self.journal.bind(db)
        self.context = capture_deletion_history(self.ledger, self.namespace)

    def plan(self):
        with guarded_database(self.path, read_only=True, deletion_history=self.context)() as db:
            return ProvisioningPlanner(db, clock=lambda: self.fixture.now).repair_person(
                library_id='family-a', operator_account_id=self.fixture.owner, person_id=301,
                asset_ids=[1003], quiescence_reference='synthetic-stopped',
                provenance_reference='synthetic-provenance')

    def review(self, plan, **kwargs):
        with guarded_database(self.path, read_only=True, deletion_history=self.context)() as source:
            with closing(sqlite3.connect(self.backup)) as target:
                source.backup(target)
        values = dict(database=self.path, backup=self.backup, envelope=plan,
            reviewed_plan_digest=plan_digest(plan), authority_reference='synthetic-authority',
            restore_reference='synthetic-restore', clock=lambda: self.fixture.now,
            restore_out=self.path.parent / 'restored.sqlite', deletion_history=self.context)
        values.update(kwargs)
        return review_backup(**values)

    def apply(self, plan, review, **kwargs):
        return apply_reviewed(plan, review=review, clock=lambda: self.fixture.now,
                              all_writers_stopped=True, **kwargs)

    def rows(self, query):
        # Independent assertion only: raw SQLite cannot bypass the product guard.
        with closing(sqlite3.connect(self.path)) as db:
            return db.execute(query).fetchall()

    def assert_unapplied(self):
        for query in ('SELECT * FROM access_asset_libraries WHERE asset_id=1003',
                      'SELECT * FROM access_person_libraries WHERE person_id=301',
                      'SELECT * FROM access_provisioning_receipts'):
            self.assertEqual(self.rows(query), [])

    def advance_ledger_on_copy(self):
        """A different primary legitimately advances the shared external ledger."""
        twin = self.path.parent / 'other-primary.sqlite'
        with closing(sqlite3.connect(self.path)) as source, closing(sqlite3.connect(twin)) as db:
            source.backup(db)
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA foreign_keys=ON')
            ident, batch, mutation = str(uuid.uuid4()), uuid.uuid4().hex, str(uuid.uuid4())
            digest = hashlib.sha256(b'synthetic').hexdigest()
            db.execute('''INSERT INTO access_upload_annotations
                (id,author_id,library_id,batch,asset_id,kind,original_text,original_audio,
                 mime,duration_ms,sha256,language,consent,mutation_id,request_digest,created_at)
                VALUES (?,?,'family-a',?,101,'text','synthetic',NULL,NULL,NULL,?,'en',1,?,?,?)''',
                (ident, self.fixture.owner, batch, digest, mutation, digest, self.fixture.now))
            db.commit()
            db.execute('PRAGMA secure_delete=ON')
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM access_upload_annotations WHERE id=?', (ident,)).fetchone()
            self.journal.append(db, 'upload', row, self.fixture.now)
            db.execute('DELETE FROM access_upload_annotations WHERE id=?', (ident,))
            db.commit()

    def test_bound_repair_preserves_ledger_and_all_protected_state(self):
        ledger_bytes = self.ledger.read_bytes()
        before = {table: self.rows('SELECT * FROM ' + table) for table in
                  ('assets', 'persons', 'face_detections', 'tasks', 'access_memberships',
                   'access_original_deletion_state')}
        plan = self.plan()
        review = self.review(plan)
        self.assertEqual(review.deletion_history, self.context)
        result = self.apply(plan, review)
        self.assertEqual(result['operation'], 'repair_suppressed_person_ownership')
        self.assertEqual(self.rows('SELECT asset_id,library_id FROM access_asset_libraries WHERE asset_id=1003'),
                         [(1003, 'family-a')])
        self.assertEqual(self.rows('SELECT person_id FROM access_person_libraries'), [(301,)])
        for table, expected in before.items():
            self.assertEqual(self.rows('SELECT * FROM ' + table), expected)
        assert_deletion_history(self.context)
        self.assertEqual(self.ledger.read_bytes(), ledger_bytes)
        with guarded_database(self.path, read_only=True, deletion_history=self.context)() as db:
            assert_deletion_history(self.context, db)

    def test_missing_guard_and_partial_selection_are_refused(self):
        self.assertIsNone(capture_deletion_history())
        for args in ((self.ledger, None), (None, self.namespace), (str(self.ledger), self.namespace),
                     (self.ledger, str(uuid.uuid4()))):
            with self.assertRaises(PlanRejected):
                capture_deletion_history(*args)
        with self.assertRaises(RuntimeUnavailable):
            with ExistingDatabase(self.path, read_only=True)():
                pass
        self.assert_unapplied()

    def test_guard_does_not_create_or_modify_a_ledger(self):
        absent = self.path.parent / 'missing.sqlite'
        with self.assertRaises(PlanRejected):
            capture_deletion_history(absent, self.namespace)
        self.assertFalse(absent.exists())
        from app.access.provisioning_apply import _reviewed_journal
        with closing(_reviewed_journal(self.context)._connect()) as db:
            self.assertEqual(db.execute('PRAGMA query_only').fetchone()[0], 1)
            with self.assertRaisesRegex(sqlite3.OperationalError, 'readonly'):
                db.execute('DELETE FROM deletions')

    def test_guarded_review_requires_disk_restore_and_repair_operation(self):
        plan = self.plan()
        with self.assertRaisesRegex(PlanRejected, 'fresh disk restore'):
            self.review(plan, restore_out=None)
        for invalid in (None, [], {'plan': []}, {'plan': {'operation': 'bootstrap_owner'}}):
            with self.assertRaises(PlanRejected):
                review_backup(database=self.path, backup=self.backup, envelope=invalid,
                    reviewed_plan_digest='bad', authority_reference='synthetic-authority',
                    restore_reference='synthetic-restore', deletion_history=self.context)
        self.assert_unapplied()

    def test_marker_mismatch_in_primary_or_backup_is_refused(self):
        plan = self.plan()
        self.review(plan)
        with closing(sqlite3.connect(self.backup)) as db:
            db.execute("UPDATE access_original_deletion_state SET applied_digest=?", ('f' * 64,))
            db.commit()
        with self.assertRaises(RuntimeUnavailable):
            review_backup(database=self.path, backup=self.backup, envelope=plan,
                reviewed_plan_digest=plan_digest(plan), authority_reference='synthetic-authority',
                restore_reference='synthetic-restore', deletion_history=self.context,
                restore_out=self.path.parent / 'second-restore.sqlite', clock=lambda: self.fixture.now)
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("UPDATE access_original_deletion_state SET namespace=?", (str(uuid.uuid4()),))
            db.commit()
        with self.assertRaises(RuntimeUnavailable):
            self.plan()
        self.assert_unapplied()

    def test_replaced_ledger_after_review_is_refused(self):
        plan = self.plan()
        review = self.review(plan)
        replacement = self.path.parent / 'replacement.sqlite'
        shutil.copyfile(self.ledger, replacement)
        os.replace(replacement, self.ledger)
        with self.assertRaises(PlanRejected):
            self.apply(plan, review)
        self.assert_unapplied()

    def test_advanced_ledger_after_review_is_refused(self):
        plan = self.plan()
        review = self.review(plan)
        self.advance_ledger_on_copy()
        with self.assertRaises(PlanRejected):
            self.apply(plan, review)
        self.assert_unapplied()

    def test_ledger_replaced_during_apply_rolls_back_mapping_audit_and_receipt(self):
        plan = self.plan()
        review = self.review(plan)
        before = self.rows('SELECT * FROM access_audit')
        from app.access.ownership_repair import apply_repair
        def change_after_inserts(state, target):
            apply_repair(state, target)
            replacement = self.path.parent / 'replacement.sqlite'
            shutil.copyfile(self.ledger, replacement)
            os.replace(replacement, self.ledger)
        with patch('app.access.ownership_repair.apply_repair', side_effect=change_after_inserts):
            with self.assertRaises(PlanRejected):
                self.apply(plan, review)
        self.assert_unapplied()
        self.assertEqual(self.rows('SELECT * FROM access_audit'), before)


if __name__ == '__main__':
    unittest.main()
