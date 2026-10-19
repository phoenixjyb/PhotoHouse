"""Bound original-deletion context must survive upload approval boundaries."""
from dataclasses import replace
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
import uuid

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'tests/security'))
import test_promotion as promotion_fixture
from app.access.original_deletions import OriginalDeletionJournal
from app.access.asset_tombstones import prepare_asset_tombstone
from app.access.promotion import PromotionPlanner, PromotionReview, promote_and_assign
from app.access.provisioning_apply import _identity, plan_digest
from app.access.runtime import ExistingDatabase, RuntimeUnavailable
from app.access.upload import UploadRuntime
from app.access.upload_review import UploadReviewRuntime
from app.main import create_app


class UploadOriginalDeletionJournalTests(unittest.TestCase):
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
        self.tmp = tempfile.TemporaryDirectory(prefix='upload-journal-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()

        # Match a policy enabled before the original store was bound to its journal.
        pre_app = create_app(access_runtime=self.fixture.access,
            upload_runtime=self.fixture.uploads,
            upload_review_runtime=UploadReviewRuntime(self.fixture.uploads))
        self.pre_client = TestClient(pre_app, base_url='https://photohouse.test')
        self.addCleanup(self.pre_client.close)
        owner_headers = {'Authorization': 'Bearer ' + self.fixture.owner_token}
        enabled = self.pre_client.put(
            f'/admin/upload-auto-approval/{self.fixture.member_id}?library=family-a',
            headers=owner_headers, json={'mode': 'on'})
        self.assertEqual(200, enabled.status_code, enabled.text)

        self.journal = OriginalDeletionJournal.initialize(self.root / 'journal.sqlite', str(uuid.uuid4()),
                                                          format_version=3)
        with self.fixture.connection() as db:
            self.journal.bind(db)
        factory = ExistingDatabase(self.fixture.path.resolve(), timeout=1.25,
                                   original_deletions=self.journal)
        self.fixture.access = replace(self.fixture.access, connection_factory=factory)
        self.fixture.uploads = UploadRuntime(self.fixture.access, self.fixture.incoming,
                                             (self.fixture.originals,))
        app = create_app(access_runtime=self.fixture.access, upload_runtime=self.fixture.uploads,
            upload_review_runtime=UploadReviewRuntime(self.fixture.uploads))
        self.assertEqual(factory.timeout,
            app.state.upload_review_runtime._database(read_only=True).timeout)
        self.client = TestClient(app, base_url='https://photohouse.test')
        self.addCleanup(self.client.close)
        self.headers = {'Authorization': 'Bearer ' + self.fixture.member_token}

    def _complete(self, request_id='1', batch='2'):
        data = promotion_fixture.png(640, 480)
        digest = hashlib.sha256(data).hexdigest()
        created = self.client.post('/upload-sessions', headers=self.headers, json={
            'request_id': request_id * 32, 'batch': batch * 32, 'filename': 'photo.png',
            'bytes': len(data), 'sha256': digest, 'kind': 'image',
            'destination_library_id': 'family-a'})
        self.assertEqual(201, created.status_code, created.text)
        transfer = created.json()
        appended = self.client.put('/upload-sessions/' + transfer['upload_id'], headers={
            **self.headers, 'Content-Type': 'application/octet-stream', 'Upload-Offset': '0',
            'X-Chunk-SHA256': digest}, content=data)
        self.assertEqual(200, appended.status_code, appended.text)
        completed = self.client.post('/upload-sessions/' + transfer['upload_id'] + '/complete',
                                     headers=self.headers, json={})
        return transfer, completed

    def test_resumable_auto_approval_carries_journal_through_read_and_apply(self):
        transfer, completed = self._complete()
        self.assertEqual(200, completed.status_code, completed.text)
        self.assertEqual('automatic', completed.json()['approval_state'])
        asset = int(completed.json()['asset_id'])
        self.assertEqual(('complete', asset), tuple(self.fixture.rows(
            'SELECT state,asset_id FROM access_upload_transfers WHERE id=?',
            (transfer['upload_id'],))[0]))
        self.assertEqual(('assigned', 'automatic'), tuple(self.fixture.rows(
            'SELECT state,approval_mode FROM access_uploads WHERE asset_id=?', (asset,))[0]))
        self.assertEqual(1, len(self.fixture.rows('SELECT 1 FROM access_provisioning_receipts')))
        factory = self.fixture.access.connection_factory
        with replace(factory, read_only=True)() as db:
            self.journal.assert_current(db)

        # A journal head that advances while the primary transaction rolls back
        # must make this same-namespace primary unavailable until replay.
        with factory() as db:
            db.execute('PRAGMA secure_delete=ON')
            db.execute('BEGIN IMMEDIATE')
            binding = prepare_asset_tombstone(db, asset, 'family-a', promotion_fixture.NOW)
            self.journal.append(db, 'asset', {'id': asset, 'library_id': 'family-a',
                'asset_binding_json': binding['asset_binding_json']}, promotion_fixture.NOW)
            db.rollback()
        with self.assertRaises(RuntimeUnavailable):
            with factory():
                self.fail('A primary with a stale same-namespace watermark opened')

    def test_missing_apply_context_and_mismatched_journal_fail_closed(self):
        uploaded = self.fixture.uploads.store(self.fixture.member_token,
            promotion_fixture.png(641, 480), 'photo.png', '3' * 32, 'family-a')
        asset = int(uploaded['asset_id'])
        with replace(self.fixture.access.connection_factory, read_only=True)() as db:
            envelope = PromotionPlanner(db, clock=lambda: promotion_fixture.NOW).promote(
                library_id='family-a', operator_account_id=self.fixture.owner_id,
                asset_ids=[asset])

        # Offline/default callers do not inherit or discover a journal implicitly.
        review = PromotionReview(database=self.fixture.path.resolve(),
            database_identity=_identity(self.fixture.path.resolve()), plan_digest=plan_digest(envelope),
            authority_reference='synthetic-missing-journal', incoming_root=self.fixture.incoming,
            originals_root=self.fixture.originals)
        before_asset = tuple(self.fixture.rows(
            'SELECT path,file_size,status FROM assets WHERE id=?', (asset,))[0])
        before_upload = tuple(self.fixture.rows(
            'SELECT state,approval_mode FROM access_uploads WHERE asset_id=?', (asset,))[0])
        before_mapping = self.fixture.rows(
            'SELECT library_id FROM access_asset_libraries WHERE asset_id=?', (asset,))
        payloads = ('{"asset_id": %d}' % asset,
                    '{"asset_id": %d, "modality": "image"}' % asset)
        before_tasks = self.fixture.rows(
            'SELECT type,state,payload_json FROM tasks WHERE payload_json IN (?,?) ORDER BY type', payloads)
        before_receipts = self.fixture.rows(
            'SELECT plan_id,plan_digest,receipt FROM access_provisioning_receipts')
        before_bytes = Path(before_asset[0]).read_bytes()
        with self.assertRaises(RuntimeUnavailable):
            promote_and_assign(envelope, review=review, clock=lambda: promotion_fixture.NOW)
        self.assertEqual(before_asset, tuple(self.fixture.rows(
            'SELECT path,file_size,status FROM assets WHERE id=?', (asset,))[0]))
        self.assertEqual(before_upload, tuple(self.fixture.rows(
            'SELECT state,approval_mode FROM access_uploads WHERE asset_id=?', (asset,))[0]))
        self.assertEqual(before_mapping, self.fixture.rows(
            'SELECT library_id FROM access_asset_libraries WHERE asset_id=?', (asset,)))
        self.assertEqual(before_tasks, self.fixture.rows(
            'SELECT type,state,payload_json FROM tasks WHERE payload_json IN (?,?) ORDER BY type', payloads))
        self.assertEqual(before_receipts, self.fixture.rows(
            'SELECT plan_id,plan_digest,receipt FROM access_provisioning_receipts'))
        self.assertEqual(before_bytes, Path(before_asset[0]).read_bytes())

        stale = OriginalDeletionJournal.initialize(self.root / 'stale.sqlite', str(uuid.uuid4()))
        with self.assertRaises(RuntimeUnavailable):
            with ExistingDatabase(self.fixture.path.resolve(), read_only=True,
                                  original_deletions=stale)():
                self.fail('A mismatched journal opened a bound primary')

    def test_manual_upload_approval_and_library_move_keep_bound_context(self):
        owner_headers = {'Authorization': 'Bearer ' + self.fixture.owner_token}
        disabled = self.client.put(
            f'/admin/upload-auto-approval/{self.fixture.member_id}?library=family-a',
            headers=owner_headers, json={'mode': 'off'})
        self.assertEqual(200, disabled.status_code, disabled.text)

        data = promotion_fixture.png(642, 480)
        uploaded = self.client.post('/uploads', headers={
            **self.headers, 'Content-Type': 'application/octet-stream',
            'X-Upload-Filename': 'manual.png', 'X-Upload-Batch': '4' * 32,
            'X-Upload-Destination-Library': 'family-a'}, content=data)
        self.assertEqual(201, uploaded.status_code, uploaded.text)
        asset = uploaded.json()['asset_id']
        self.assertEqual('awaiting_review', uploaded.json()['approval_state'])

        reviewed = self.client.post(f'/admin/uploads/{asset}/review?library=family-a',
                                    headers=owner_headers, json={})
        self.assertEqual(200, reviewed.status_code, reviewed.text)
        approved = self.client.post(f'/admin/uploads/{asset}/approve?library=family-a',
            headers=owner_headers, json={'plan': reviewed.json()['plan']})
        self.assertEqual(200, approved.status_code, approved.text)

        # Add a second destination owned by the same synthetic operator and exercise
        # the separate library-move review/apply path with the same bound journal.
        self.fixture.mutate("INSERT INTO access_libraries(id,state,bootstrap_operator) "
                            "VALUES ('documents','active',?)", (self.fixture.owner_id,))
        self.fixture.mutate('''INSERT INTO access_memberships
            (account_id,library_id,status,role,revision,expires_at,originals,approved_by)
            VALUES (?,'documents','approved','owner',1,NULL,0,?)''',
            (self.fixture.owner_id, self.fixture.owner_id))
        moved_review = self.client.post('/admin/library-transfers/review?library=family-a',
            headers=owner_headers, json={'asset_ids': str(asset), 'destination': 'documents'})
        self.assertEqual(200, moved_review.status_code, moved_review.text)
        moved = self.client.post('/admin/library-transfers/confirm?library=family-a',
            headers=owner_headers, json={'plan': moved_review.json()['plan']})
        self.assertEqual(200, moved.status_code, moved.text)
        self.assertEqual(('documents',), tuple(self.fixture.rows(
            'SELECT library_id FROM access_asset_libraries WHERE asset_id=?', (int(asset),))[0]))
        with replace(self.fixture.access.connection_factory, read_only=True)() as db:
            self.journal.assert_current(db)


if __name__ == '__main__':
    unittest.main()
