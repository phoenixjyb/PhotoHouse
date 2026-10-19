"""Real owner routes over migrated fictional data; confirmations admit no faces."""
import unittest
from unittest.mock import Mock

import test_people_management as base
from app.access import discovery as d
from app.access.discovery_provider import MemoryIndexProvider, RefreshingPeopleIndex, ReviewedPerson, ReviewedFace
from app.access.discovery_transport import DiscoveryRuntime
from app.access.transport import COOKIE, csrf_token


class VisualPeopleReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): base.PeopleTests.setUpClass()

    @classmethod
    def tearDownClass(cls): base.PeopleTests.tearDownClass()

    def setUp(self):
        self.fixture = base.PeopleTests('runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.f = self.fixture.f
        self.client, self.owner = self.f.client, self.f.owner_token
        with self.f.connection() as db:
            owner_id = db.execute("SELECT bootstrap_operator FROM access_libraries WHERE id='family-a'").fetchone()[0]
            db.execute("INSERT INTO access_person_libraries VALUES(1,'family-a',?,1)", (owner_id,))
            db.execute("UPDATE face_detections SET label_source='manual' WHERE id=11")
            for face, source in [(12, 'manual'), (13, 'manual'), (14, 'dnn')]:
                db.execute('''INSERT INTO face_detections(id,asset_id,person_id,bbox_x,bbox_y,bbox_w,bbox_h,
                    label_source,embedding_path) VALUES(?,102,1,0,0,1,1,?,'private-vector')''', (face, source))
            catalog = d.reviewed_people_source('family-a', (ReviewedPerson('family-a','1','Alice'),),
                                               lambda sql, args: db.execute(sql, args).fetchall())
            db.commit()
        self.index = RefreshingPeopleIndex('family-a', '1', ('101','102'), ('101','102'), '0'*64,
            people=(ReviewedPerson('family-a','1','Alice'),), assignments=(ReviewedFace('11','101','1'),),
            enabled=('people','date','locations','media'), catalog_digest=d.reviewed_catalog_digest(catalog))
        self.install(self.index)

    def install(self, index=None, provider=None):
        app = self.client.app
        self.provider = provider or MemoryIndexProvider((index or self.index,))
        app.state.discovery_runtime = DiscoveryRuntime(app.state.access_runtime, self.provider, d.ReadBudget())

    def get(self, path='/admin/people/1/review?library=family-a', token=None):
        return self.client.get(path, headers={'Authorization': 'Bearer ' + (token or self.owner)})

    def queue(self):
        response = self.get()
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def confirm(self, item, token=None, **changes):
        body = {k:item[k] for k in ('person_id','revision','person_revision','review_revision')}
        body.update(changes)
        return self.client.post(f"/admin/faces/{item['id']}/review?library=family-a",
            headers={'Authorization':'Bearer ' + (token or self.owner)}, json=body)

    def mutate(self, sql, args=()):
        with self.f.connection() as db:
            db.execute(sql, args)
            db.commit()

    def marker_count(self):
        with self.f.connection() as db:
            return db.execute("SELECT count(*) FROM access_audit WHERE action LIKE 'face.review.%'").fetchone()[0]

    def test_queue_only_manual_unadmitted_faces_no_media_or_biometrics(self):
        result = self.queue()
        self.assertEqual([i['id'] for i in result['items']], ['13','12'])
        self.assertIsNone(result['next_before'])
        self.assertEqual(result['status'], 'requires_explicit_review')
        for item in result['items']:
            self.assertFalse(item['identity_confirmed'])
            self.assertFalse(item['search_eligible'])
        text = self.get().text
        for secret in ('bbox', 'embedding', 'private-vector', 'Foreign', 'Unmapped', 'creator', 'phone'):
            self.assertNotIn(secret, text)
        self.assertEqual(self.get().headers['cache-control'], 'no-store')
        self.assertEqual(self.marker_count(), 0)

    def test_explicit_subset_is_recorded_once_without_identity_or_search_changes(self):
        item = self.queue()['items'][0]
        with self.f.connection() as db:
            before = db.execute('SELECT * FROM face_detections ORDER BY id').fetchall()
            events = db.execute('SELECT count(*) FROM face_assignment_events').fetchone()[0]
        saved = self.confirm(item)
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertTrue(saved.json()['identity_confirmed'])
        self.assertFalse(saved.json()['search_activated'])
        self.assertEqual(self.confirm(item).status_code, 200)
        self.assertEqual(self.marker_count(), 1)
        self.assertEqual([i['id'] for i in self.queue()['items']], ['12'])
        receipt = self.get('/admin/faces/13/review?library=family-a').json()
        self.assertTrue(receipt['identity_confirmed'])
        self.assertEqual(receipt['review_revision'], item['review_revision'])
        with self.f.connection() as db:
            self.assertEqual(db.execute('SELECT * FROM face_detections ORDER BY id').fetchall(), before)
            self.assertEqual(db.execute('SELECT count(*) FROM face_assignment_events').fetchone()[0], events)
            # The serving artifact/provider remains exactly the frozen approved input.
            self.assertEqual(self.provider.get('family-a').assignments, (ReviewedFace('11','101','1'),))

    def test_revoked_or_non_owner_cannot_touch_provider_or_receipts(self):
        item = self.queue()['items'][0]
        provider = Mock()
        provider.get.side_effect = AssertionError('must authorize first')
        self.install(provider=provider)
        for token in ('invalid', self.f.member_token):
            self.assertIn(self.get(token=token).status_code, (401,403))
            self.assertIn(self.confirm(item, token=token).status_code, (401,403))
        self.mutate("UPDATE access_memberships SET status='revoked',revision=revision+1 WHERE library_id='family-a'")
        self.assertIn(self.get().status_code, (401,403))
        self.assertIn(self.confirm(item).status_code, (401,403))
        provider.get.assert_not_called()
        self.assertEqual(self.marker_count(), 0)

    def test_changed_candidate_revision_or_person_cannot_confirm(self):
        for change in ('bbox', 'person', 'source'):
            with self.subTest(change=change):
                item = self.queue()['items'][0]
                if change == 'bbox': self.mutate('UPDATE face_detections SET bbox_x=0.1 WHERE id=13')
                elif change == 'person': self.mutate('UPDATE face_detections SET person_id=5 WHERE id=13')
                else: self.mutate("UPDATE face_detections SET label_source='dnn' WHERE id=13")
                self.assertEqual(self.confirm(item).status_code, 409)
                self.assertEqual(self.marker_count(), 0)
                self.mutate("UPDATE face_detections SET person_id=1,label_source='manual',bbox_x=0 WHERE id=13")

    def test_renamed_identity_or_withdrawn_active_review_refuses_batch(self):
        item = self.queue()['items'][0]
        self.mutate("UPDATE persons SET display_name='Changed' WHERE id=1")
        self.assertEqual(self.get().status_code, 409)
        self.assertEqual(self.confirm(item).status_code, 409)
        self.mutate("UPDATE persons SET display_name='Alice' WHERE id=1")
        self.mutate("UPDATE assets SET status='suppressed' WHERE id=101")
        self.assertEqual(self.get().status_code, 409)
        self.assertEqual(self.confirm(item).status_code, 409)

    def test_confirmation_proof_is_owner_and_membership_revision_bound(self):
        item = self.queue()['items'][0]
        self.assertEqual(self.confirm(item).status_code, 200)
        self.mutate("UPDATE access_memberships SET revision=revision+1 WHERE library_id='family-a'")
        self.assertEqual(self.confirm(item).status_code, 409)
        current = self.get('/admin/faces/13/review?library=family-a')
        self.assertFalse(current.json()['identity_confirmed'])
        self.assertNotEqual(current.json()['review_revision'], item['review_revision'])

    def test_face_job_prevents_confirmation_and_invalid_post_has_no_writes(self):
        item = self.queue()['items'][0]
        self.mutate("INSERT INTO tasks(type,payload_json,state) VALUES('face',?, 'pending')", ('{"asset_id":102}',))
        self.assertEqual(self.confirm(item).status_code, 409)
        self.assertEqual(self.confirm(item, review_revision='invalid').status_code, 400)
        self.assertEqual(self.confirm(item, unexpected='no').status_code, 400)
        self.assertEqual(self.marker_count(), 0)

    def test_current_receipt_disappears_after_face_mutation(self):
        item = self.queue()['items'][0]
        self.assertEqual(self.confirm(item).status_code, 200)
        self.mutate('UPDATE face_detections SET bbox_y=0.2 WHERE id=13')
        self.assertFalse(self.get('/admin/faces/13/review?library=family-a').json()['identity_confirmed'])
        self.assertEqual([i['id'] for i in self.queue()['items']], ['13','12'])

    def test_bounded_cursor_keeps_all_remaining_candidates_and_never_counts_foreign_faces(self):
        with self.f.connection() as db:
            for face in range(100, 130):
                db.execute('''INSERT INTO face_detections(id,asset_id,person_id,bbox_x,bbox_y,bbox_w,bbox_h,
                    label_source) VALUES(?,102,1,0,0,1,1,'manual')''', (face,))
            db.commit()
        seen, before = [], None
        for _ in range(5):
            path = '/admin/people/1/review?library=family-a' + ('&before='+before if before else '')
            page = self.get(path).json()
            self.assertLessEqual(len(page['items']), 12)
            seen.extend(i['id'] for i in page['items'])
            before = page['next_before']
            if before is None: break
        self.assertEqual(seen, [str(i) for i in reversed(range(100,130))] + ['13','12'])

    def test_cookie_confirmation_requires_csrf_and_foreign_faces_are_hidden(self):
        item = self.queue()['items'][0]
        self.client.cookies.set(COOKIE, self.owner)
        path = '/admin/faces/13/review?library=family-a'
        body = {k:item[k] for k in ('person_id','revision','person_revision','review_revision')}
        self.assertEqual(self.client.post(path, json=body).status_code, 403)
        response = self.client.post(path, json=body,
            headers={'Origin':'https://photohouse.test','X-CSRF-Token':csrf_token(self.owner)})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn(self.get('/admin/faces/21/review?library=family-a').status_code,(401,403))


if __name__ == '__main__': unittest.main()
