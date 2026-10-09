"""Synthetic HTTP coverage for owner-selected upload auto approval."""
import hashlib
import sys
import unittest

from fastapi.testclient import TestClient

from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'tests/security'))
import test_promotion as promotion_fixture
from app.access.upload_review import UploadReviewRuntime


class UploadAutoApprovalTests(unittest.TestCase):
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
        self.review = UploadReviewRuntime(upload=self.fixture.uploads)
        from app.main import create_app
        self.client = TestClient(create_app(
            access_runtime=self.fixture.access,
            upload_runtime=self.fixture.uploads,
            upload_review_runtime=self.review),
            base_url='https://photohouse.test', client=('192.0.2.43', 23459))
        self.addCleanup(self.client.close)

    def headers(self, token):
        return {'Authorization': 'Bearer ' + token}

    def set_policy(self, owner, library, mode='on', member=None):
        member = member or self.fixture.member_id
        return self.client.put(
            f'/admin/upload-auto-approval/{member}?library={library}',
            headers=self.headers(owner), json={'mode': mode})

    def upload(self, data, *, library='family-a', batch='a' * 32, token=None):
        headers = {
            **self.headers(token or self.fixture.member_token),
            'Content-Type': 'application/octet-stream',
            'X-Upload-Filename': 'photo.png',
            'X-Upload-Batch': batch,
            'X-Upload-Destination-Library': library,
        }
        return self.client.post('/uploads', headers=headers, content=data)

    def rows(self, sql, args=()):
        return self.fixture.rows(sql, args)

    def grant_member_family_b(self):
        self.fixture.mutate('''INSERT INTO access_memberships
            (account_id,library_id,status,role,revision,expires_at,originals,approved_by)
            VALUES (?,'family-b','approved','contributor',1,NULL,0,?)''',
            (self.fixture.member_id, self.fixture.other_id))

    def test_owner_selects_member_and_library_and_foreign_or_nonowner_is_denied(self):
        listing = self.client.get('/admin/upload-auto-approval?library=family-a',
                                  headers=self.headers(self.fixture.owner_token))
        self.assertEqual(200, listing.status_code, listing.text)
        self.assertEqual({'library_id': 'family-a', 'items': []}, listing.json())

        enabled = self.set_policy(self.fixture.owner_token, 'family-a')
        self.assertEqual(200, enabled.status_code, enabled.text)
        self.assertEqual({'library_id': 'family-a', 'member_id': self.fixture.member_id,
                          'enabled': True, 'revision': 1}, enabled.json())
        listing = self.client.get('/admin/upload-auto-approval?library=family-a',
                                  headers=self.headers(self.fixture.owner_token))
        self.assertEqual([{'member_id': self.fixture.member_id, 'enabled': True, 'revision': 1}],
                         listing.json()['items'])

        # A contributor cannot select itself, and the family-b owner cannot select an account
        # that is not currently a member of that library.
        self.assertIn(self.set_policy(self.fixture.member_token, 'family-a').status_code,
                      (401, 403))
        self.assertIn(self.set_policy(self.fixture.other_token, 'family-b').status_code,
                      (401, 403))
        denied_destination = self.upload(promotion_fixture.png(701, 480), library='family-b')
        self.assertIn(denied_destination.status_code, (401, 403, 404))
        self.assertEqual([], self.rows('SELECT * FROM access_uploads'))

    def test_no_policy_keeps_explicit_destination_in_owner_review(self):
        data = promotion_fixture.png(640, 481)
        response = self.upload(data, batch='b' * 32)
        self.assertEqual(201, response.status_code, response.text)
        body = response.json()
        self.assertEqual('family-a', body['destination_library_id'])
        self.assertEqual('awaiting_review', body['approval_state'])
        asset_id = int(body['asset_id'])
        row = self.rows('SELECT destination_library_id,state,approval_mode FROM access_uploads '
                        'WHERE asset_id=?', (asset_id,))[0]
        self.assertEqual(('family-a', 'incoming', None), tuple(row))
        self.assertEqual([], self.rows('SELECT * FROM access_asset_libraries WHERE asset_id=?',
                                       (asset_id,)))
        self.assertEqual(5, len(self.rows("SELECT * FROM tasks WHERE state='awaiting_review'")))

        # Enabling a policy later never sweeps already received items into the library.
        self.assertEqual(200, self.set_policy(self.fixture.owner_token, 'family-a').status_code)
        self.assertEqual(('incoming', None), tuple(self.rows(
            'SELECT state,approval_mode FROM access_uploads WHERE asset_id=?', (asset_id,))[0]))
        self.assertEqual([], self.rows('SELECT * FROM access_asset_libraries WHERE asset_id=?',
                                       (asset_id,)))

    def test_identical_bytes_can_target_two_libraries_with_distinct_batches(self):
        self.grant_member_family_b()
        data = promotion_fixture.png(640, 482)
        first = self.upload(data, library='family-a', batch='c' * 32)
        second = self.upload(data, library='family-b', batch='d' * 32)
        self.assertEqual(201, first.status_code, first.text)
        self.assertEqual(201, second.status_code, second.text)
        first_id, second_id = int(first.json()['asset_id']), int(second.json()['asset_id'])
        self.assertNotEqual(first_id, second_id)
        records = self.rows('SELECT asset_id,destination_library_id,batch FROM access_uploads '
                            'WHERE asset_id IN (?,?) ORDER BY asset_id', (first_id, second_id))
        self.assertEqual([(first_id, 'family-a', 'c' * 32),
                          (second_id, 'family-b', 'd' * 32)], [tuple(row) for row in records])

        # A batch has one destination decision for its lifetime.
        conflict = self.upload(promotion_fixture.png(641, 482), library='family-b', batch='c' * 32)
        self.assertEqual(409, conflict.status_code, conflict.text)

    def test_explicit_destination_cannot_be_manually_reviewed_into_another_library(self):
        self.grant_member_family_b()
        response = self.upload(promotion_fixture.png(642, 482), library='family-a', batch='8' * 32)
        self.assertEqual(201, response.status_code, response.text)
        asset_id = response.json()['asset_id']
        wrong = self.client.post(
            f'/admin/uploads/{asset_id}/review?library=family-b',
            headers=self.headers(self.fixture.other_token), json={})
        self.assertIn(wrong.status_code, (401, 403, 404))
        self.assertEqual([], self.rows('SELECT * FROM access_asset_libraries WHERE asset_id=?',
                                       (int(asset_id),)))

    def test_selected_policy_promotes_upload_and_releases_staged_tasks(self):
        self.assertEqual(200, self.set_policy(self.fixture.owner_token, 'family-a').status_code)
        data = promotion_fixture.png(640, 483)
        response = self.upload(data, batch='e' * 32)
        self.assertEqual(201, response.status_code, response.text)
        body = response.json()
        self.assertEqual('automatic', body['approval_state'])
        self.assertEqual('family-a', body['library_id'])
        asset_id = int(body['asset_id'])

        provenance = self.rows('SELECT state,approval_mode,destination_library_id FROM access_uploads '
                               'WHERE asset_id=?', (asset_id,))[0]
        self.assertEqual(('assigned', 'automatic', 'family-a'), tuple(provenance))
        self.assertEqual([('family-a',)], [tuple(row) for row in self.rows(
            'SELECT library_id FROM access_asset_libraries WHERE asset_id=?', (asset_id,))])
        stored = Path(self.rows('SELECT path FROM assets WHERE id=?', (asset_id,))[0][0])
        self.assertTrue(stored.is_relative_to(self.fixture.originals.resolve()))
        self.assertTrue(stored.is_file())
        self.assertEqual([], self.rows("SELECT * FROM tasks WHERE state='awaiting_review'"))
        self.assertEqual(5, len(self.rows("SELECT * FROM tasks WHERE state='pending'")))
        self.assertEqual(1, len(self.rows('SELECT * FROM access_provisioning_receipts')))

        retry = self.upload(data, batch='e' * 32)
        self.assertEqual(201, retry.status_code, retry.text)
        self.assertEqual(asset_id, int(retry.json()['asset_id']))
        self.assertEqual('automatic', retry.json()['approval_state'])
        self.assertEqual('family-a', retry.json()['library_id'])
        self.assertEqual(0, retry.json()['tasks_enqueued'])
        self.assertEqual(1, len(self.rows('SELECT * FROM access_uploads')))
        self.assertEqual(1, len(self.rows('SELECT * FROM access_provisioning_receipts')))

    def test_lost_resumable_completion_reply_is_idempotent_after_auto_approval(self):
        self.assertEqual(200, self.set_policy(self.fixture.owner_token, 'family-a').status_code)
        data = promotion_fixture.png(640, 484)
        digest = hashlib.sha256(data).hexdigest()
        headers = self.headers(self.fixture.member_token)
        created = self.client.post('/upload-sessions', headers=headers, json={
            'request_id': '1' * 32, 'batch': 'f' * 32, 'filename': 'photo.png',
            'bytes': len(data), 'sha256': digest, 'kind': 'image',
            'destination_library_id': 'family-a'})
        self.assertEqual(201, created.status_code, created.text)
        transfer = created.json()
        appended = self.client.put(
            '/upload-sessions/' + transfer['upload_id'],
            headers={**headers, 'Content-Type': 'application/octet-stream',
                     'Upload-Offset': '0', 'X-Chunk-SHA256': digest}, content=data)
        self.assertEqual(200, appended.status_code, appended.text)

        first = self.client.post('/upload-sessions/' + transfer['upload_id'] + '/complete',
                                 headers=headers, json={})
        self.assertEqual(200, first.status_code, first.text)
        retry = self.client.post('/upload-sessions/' + transfer['upload_id'] + '/complete',
                                 headers=headers, json={})
        self.assertEqual(200, retry.status_code, retry.text)
        self.assertEqual(first.json(), retry.json())
        self.assertEqual('automatic', first.json()['approval_state'])
        self.assertEqual('family-a', first.json()['library_id'])
        asset_id = int(first.json()['asset_id'])
        self.assertEqual(1, len(self.rows('SELECT * FROM access_uploads WHERE asset_id=?', (asset_id,))))
        self.assertEqual(('assigned', 'automatic'), tuple(self.rows(
            'SELECT state,approval_mode FROM access_uploads WHERE asset_id=?', (asset_id,))[0]))
        self.assertEqual(1, len(self.rows('SELECT * FROM access_asset_libraries WHERE asset_id=?',
                                         (asset_id,))))
        self.assertEqual(1, len(self.rows('SELECT * FROM access_provisioning_receipts')))

    def test_policy_revoked_before_completion_leaves_upload_pending(self):
        self.assertEqual(200, self.set_policy(self.fixture.owner_token, 'family-a').status_code)
        data = promotion_fixture.png(640, 485)
        digest = hashlib.sha256(data).hexdigest()
        headers = self.headers(self.fixture.member_token)
        created = self.client.post('/upload-sessions', headers=headers, json={
            'request_id': '2' * 32, 'batch': '9' * 32, 'filename': 'photo.png',
            'bytes': len(data), 'sha256': digest, 'kind': 'image',
            'destination_library_id': 'family-a'})
        self.assertEqual(201, created.status_code, created.text)
        transfer = created.json()
        appended = self.client.put(
            '/upload-sessions/' + transfer['upload_id'],
            headers={**headers, 'Content-Type': 'application/octet-stream',
                     'Upload-Offset': '0', 'X-Chunk-SHA256': digest}, content=data)
        self.assertEqual(200, appended.status_code, appended.text)

        revoked = self.set_policy(self.fixture.owner_token, 'family-a', mode='off')
        self.assertEqual(200, revoked.status_code, revoked.text)
        self.assertEqual(2, revoked.json()['revision'])
        completed = self.client.post('/upload-sessions/' + transfer['upload_id'] + '/complete',
                                     headers=headers, json={})
        self.assertEqual(200, completed.status_code, completed.text)
        self.assertEqual('awaiting_review', completed.json()['approval_state'])
        asset_id = int(completed.json()['asset_id'])
        self.assertEqual(('incoming', None), tuple(self.rows(
            'SELECT state,approval_mode FROM access_uploads WHERE asset_id=?', (asset_id,))[0]))
        self.assertEqual([], self.rows('SELECT * FROM access_asset_libraries WHERE asset_id=?',
                                       (asset_id,)))
        self.assertEqual(5, len(self.rows("SELECT * FROM tasks WHERE state='awaiting_review'")))
        self.assertEqual([], self.rows('SELECT * FROM access_provisioning_receipts'))


if __name__ == '__main__':
    unittest.main()
