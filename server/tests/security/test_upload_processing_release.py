"""Synthetic security coverage for explicitly releasing deferred upload starters."""
from pathlib import Path
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'tests/security'))
import test_promotion as promotion_fixture
from app.access.provisioning import PlanRejected
from app.access.provisioning_apply import _identity
from app.access.promotion import promote_and_assign
from app.access.runtime import ExistingDatabase, RuntimeUnavailable
from app.access.upload_processing import release_deferred_upload_starters


class UploadProcessingReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        promotion_fixture.PromotionTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        promotion_fixture.PromotionTests.tearDownClass()

    def setUp(self):
        self.fixture = promotion_fixture.PromotionTests(
            'test_promotion_moves_the_file_and_makes_the_photo_visible')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        uploaded = self.fixture.upload()
        self.asset_id = int(uploaded['asset_id'])
        self.envelope = self.fixture.planned('promote', library_id='family-a',
            operator_account_id=self.fixture.owner_id, asset_ids=[self.asset_id])
        self.original_receipt = promote_and_assign(self.envelope,
            review=self.fixture.review(self.envelope), clock=lambda: promotion_fixture.NOW,
            release_starters=False)
        self.expected = [dict(row) for row in self.fixture.rows('''SELECT id,type,payload_json,state
            FROM tasks WHERE json_extract(payload_json,'$.asset_id')=? ORDER BY id''',
            (self.asset_id,))]

    def release(self, **overrides):
        args = {'database_factory': ExistingDatabase(self.fixture.path.resolve()),
            'database_identity': _identity(self.fixture.path.resolve()),
            'operator_account_id': self.fixture.owner_id, 'library_id': 'family-a',
            'asset_ids': [self.asset_id], 'expected_tasks': self.expected,
            'authority_reference': 'release-2026-01',
            'clock': lambda: promotion_fixture.NOW}
        args.update(overrides)
        return release_deferred_upload_starters(self.envelope, **args)

    def task_state(self):
        return [tuple(row) for row in self.fixture.rows(
            'SELECT id,type,state,payload_json,last_error FROM tasks ORDER BY id')]

    def test_releases_exact_deferred_starters_and_preserves_promotion_receipt(self):
        before = self.task_state()
        receipt = self.release()
        after = self.task_state()
        self.assertEqual(len(receipt['released_tasks']), 5)
        self.assertEqual(sum(row[2] == 'pending' for row in after), 5)
        self.assertEqual(sum(row[2] == 'awaiting_review' for row in after), 0)
        original = self.fixture.rows('''SELECT receipt FROM access_provisioning_receipts
            WHERE plan_id=?''', (self.envelope['plan']['plan_id'],))[0][0]
        self.assertEqual(json.loads(original), self.original_receipt)
        self.assertEqual(len(self.fixture.rows('SELECT 1 FROM access_provisioning_receipts')), 2)
        self.assertNotEqual(before, after)

    def test_changed_task_is_rejected_without_partial_release(self):
        self.fixture.mutate("UPDATE tasks SET payload_json='{}' WHERE id=?",
                            (self.expected[0]['id'],))
        before = self.task_state()
        with self.assertRaises(PlanRejected):
            self.release()
        self.assertEqual(self.task_state(), before)
        self.assertEqual(len(self.fixture.rows('SELECT 1 FROM access_provisioning_receipts')), 1)

    def test_non_embed_modality_is_rejected_without_partial_release(self):
        altered = [dict(row) for row in self.expected]
        altered[0]['payload_json'] = json.dumps({'asset_id': self.asset_id,
                                                 'modality': 'audio'}, sort_keys=True)
        before = self.task_state()
        with self.assertRaises(PlanRejected):
            self.release(expected_tasks=altered)
        self.assertEqual(self.task_state(), before)
        self.assertEqual(len(self.fixture.rows('SELECT 1 FROM access_provisioning_receipts')), 1)

    def test_cancellation_request_is_rejected_without_partial_release(self):
        self.fixture.mutate('UPDATE tasks SET cancel_requested=1 WHERE id=?',
                            (self.expected[0]['id'],))
        before = self.task_state()
        with self.assertRaises(PlanRejected):
            self.release()
        self.assertEqual(self.task_state(), before)
        self.assertEqual(len(self.fixture.rows('SELECT 1 FROM access_provisioning_receipts')), 1)

    def test_changed_assignment_is_rejected_without_partial_release(self):
        self.fixture.mutate("UPDATE access_asset_libraries SET library_id='family-b' WHERE asset_id=?",
                            (self.asset_id,))
        before = self.task_state()
        with self.assertRaises(PlanRejected):
            self.release()
        self.assertEqual(self.task_state(), before)
        self.assertEqual(len(self.fixture.rows('SELECT 1 FROM access_provisioning_receipts')), 1)

    def test_changed_uploader_membership_is_rejected_without_partial_release(self):
        self.fixture.mutate("UPDATE access_memberships SET status='revoked' WHERE account_id=? AND library_id='family-a'",
                            (self.fixture.member_id,))
        before = self.task_state()
        with self.assertRaises(PlanRejected):
            self.release()
        self.assertEqual(self.task_state(), before)
        self.assertEqual(len(self.fixture.rows('SELECT 1 FROM access_provisioning_receipts')), 1)

    def test_changed_owner_membership_is_rejected_without_partial_release(self):
        self.fixture.mutate("UPDATE access_memberships SET status='revoked' WHERE account_id=? AND library_id='family-a'",
                            (self.fixture.owner_id,))
        before = self.task_state()
        with self.assertRaises(PlanRejected):
            self.release()
        self.assertEqual(self.task_state(), before)
        self.assertEqual(len(self.fixture.rows('SELECT 1 FROM access_provisioning_receipts')), 1)

    def test_external_journal_guard_blocks_release(self):
        class StaleJournal:
            def assert_current(self, _db):
                raise RuntimeError('stale synthetic journal')

        before = self.task_state()
        with self.assertRaises(RuntimeUnavailable):
            self.release(database_factory=ExistingDatabase(self.fixture.path.resolve(),
                original_deletions=StaleJournal()))
        self.assertEqual(self.task_state(), before)
        self.assertEqual(len(self.fixture.rows('SELECT 1 FROM access_provisioning_receipts')), 1)

    def test_replay_cannot_reset_a_completed_starter(self):
        self.release()
        task_id = self.expected[0]['id']
        self.fixture.mutate("UPDATE tasks SET state='completed',last_error='result' WHERE id=?",
                            (task_id,))
        before = self.task_state()
        with self.assertRaises(PlanRejected):
            self.release()
        self.assertEqual(self.task_state(), before)
        self.assertEqual(len(self.fixture.rows('SELECT 1 FROM access_provisioning_receipts')), 2)


if __name__ == '__main__':
    unittest.main()
