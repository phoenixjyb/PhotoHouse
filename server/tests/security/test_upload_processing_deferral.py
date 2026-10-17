"""Synthetic coverage for approving uploads while keeping their starter jobs held."""
from pathlib import Path
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'tests/security'))
import test_promotion as promotion_fixture
from app.access.promotion import promote_and_assign
from app.access.provisioning import PlanRejected


class UploadProcessingDeferralTests(unittest.TestCase):
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

    def plan_for(self, asset_id):
        return self.fixture.planned(
            'promote', library_id='family-a',
            operator_account_id=self.fixture.owner_id, asset_ids=[asset_id])

    def test_deferred_approval_promotes_and_maps_without_releasing_any_tasks(self):
        uploaded = self.fixture.upload()
        asset_id = int(uploaded['asset_id'])
        self.fixture.mutate('''INSERT INTO tasks(type,payload_json,state,priority,last_error)
            VALUES ('caption', ?, 'completed', 110, 'completed-result'),
                   ('thumb', ?, 'failed', 80, 'failed-result'),
                   ('caption', ?, 'awaiting_review', 110, 'unrelated')''',
            (f'{{"asset_id":{asset_id}}}', f'{{"asset_id":{asset_id}}}',
             '{"asset_id":900}'))
        before = self.fixture.rows('''SELECT id,type,state,payload_json,last_error FROM tasks
            ORDER BY id''')
        envelope = self.plan_for(asset_id)

        receipt = promote_and_assign(
            envelope, review=self.fixture.review(envelope), clock=lambda: promotion_fixture.NOW,
            release_starters=False)

        stored_path = Path(self.fixture.rows(
            'SELECT path FROM assets WHERE id=?', (asset_id,))[0][0])
        self.assertTrue(stored_path.is_relative_to(self.fixture.originals.resolve()))
        self.assertTrue(stored_path.is_file())
        self.assertEqual(self.fixture.rows(
            'SELECT state FROM access_uploads WHERE asset_id=?', (asset_id,))[0][0], 'assigned')
        self.assertEqual(self.fixture.rows(
            'SELECT library_id FROM access_asset_libraries WHERE asset_id=?', (asset_id,))[0][0],
            'family-a')

        after = self.fixture.rows('''SELECT id,type,state,payload_json,last_error FROM tasks
            ORDER BY id''')
        self.assertEqual([tuple(row) for row in after], [tuple(row) for row in before])
        self.assertEqual(sum(row['state'] == 'awaiting_review' for row in after), 6)
        self.assertTrue(receipt['processing_deferred'])
        persisted = self.fixture.rows('SELECT receipt FROM access_provisioning_receipts')[0][0]
        self.assertTrue(json.loads(persisted)['processing_deferred'])
        # An idempotent approval retry with the ordinary default must not start jobs.
        replay = promote_and_assign(envelope, review=self.fixture.review(envelope),
            clock=lambda: promotion_fixture.NOW, allow_replay=True,
            authorize=lambda access, plan: None)
        self.assertTrue(replay['processing_deferred'])
        self.assertEqual([tuple(row) for row in self.fixture.rows(
            'SELECT id,type,state,payload_json,last_error FROM tasks ORDER BY id')],
            [tuple(row) for row in before])

    def test_non_boolean_option_is_rejected_before_promotion_effects(self):
        uploaded = self.fixture.upload()
        asset_id = int(uploaded['asset_id'])
        envelope = self.plan_for(asset_id)
        original_path = self.fixture.rows(
            'SELECT path FROM assets WHERE id=?', (asset_id,))[0][0]
        initial_tasks = [tuple(row) for row in self.fixture.rows(
            'SELECT id,type,state,payload_json FROM tasks ORDER BY id')]

        with self.assertRaises(PlanRejected):
            promote_and_assign(envelope, review=self.fixture.review(envelope),
                               clock=lambda: promotion_fixture.NOW, release_starters=1)

        self.assertEqual(self.fixture.rows(
            'SELECT path FROM assets WHERE id=?', (asset_id,))[0][0], original_path)
        self.assertTrue(Path(original_path).is_file())
        self.assertEqual(self.fixture.rows(
            'SELECT state FROM access_uploads WHERE asset_id=?', (asset_id,))[0][0], 'incoming')
        self.assertEqual(self.fixture.rows(
            'SELECT 1 FROM access_asset_libraries WHERE asset_id=?', (asset_id,)), [])
        self.assertEqual(self.fixture.rows('SELECT 1 FROM access_provisioning_receipts'), [])
        self.assertEqual([tuple(row) for row in self.fixture.rows(
            'SELECT id,type,state,payload_json FROM tasks ORDER BY id')], initial_tasks)


if __name__ == '__main__':
    unittest.main()
