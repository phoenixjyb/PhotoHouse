"""Atomic, opt-in story refinement queueing over protected synthetic data."""
import json
import unittest
import uuid
from unittest.mock import patch

import test_memory_stories as fixture
from app.access.memory_jobs import MemoryJobs
from app.access.memory_stories import MemoryStories
from app.access.service import AccessDenied, AccessService


class MemoryStoryAutoRefinementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.MemoryStoryTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        fixture.MemoryStoryTests.tearDownClass()

    def setUp(self):
        self.f = fixture.MemoryStoryTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.library = self.f.f

    def call(self, method, token, *args, **kwargs):
        with self.library.connection() as db:
            access = AccessService(db, clock=lambda: self.library.now)
            return getattr(MemoryStories(access), method)(token, 'family-a', *args, **kwargs)

    def save(self, body=None, ident=None, *, auto_refine=False, token=None):
        body = self.f.body() if body is None else body
        return self.call('save', token or self.library.owner_token, body, ident,
                         False, False, auto_refine)

    def counts(self):
        with self.library.connection() as db:
            return tuple(db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                         for table in ('access_memory_stories', 'access_memory_revisions',
                                       'access_memory_jobs'))

    def job_rows(self, story_id):
        with self.library.connection() as db:
            return db.execute('''SELECT id,actor_id,library_id,story_id,kind,state,
                mutation_id,base_revision,input_json FROM access_memory_jobs
                WHERE story_id=?''', (story_id,)).fetchall()

    def test_save_and_queue_are_atomic_and_default_off(self):
        body = self.f.body()
        before = self.counts()
        saved = self.save(body)
        self.assertNotIn('auto_refinement', saved)
        self.assertEqual(self.counts(), (before[0] + 1, before[1] + 1, before[2]))

        other = self.f.body()
        before = self.counts()
        with patch.object(MemoryJobs, '_queue', side_effect=RuntimeError('queue failed')):
            with self.assertRaises(RuntimeError):
                self.save(other, auto_refine=True)
        self.assertEqual(self.counts(), before)

    def test_confirmed_save_queues_conservative_review_only_job_once(self):
        body = self.f.body()
        saved = self.save(body, auto_refine=True)
        proposal = saved['auto_refinement']
        self.assertEqual((proposal['kind'], proposal['state'], proposal['base_revision']),
                         ('narrative', 'queued', '1'))
        self.assertTrue(proposal['needs_review'])
        self.assertIsNone(proposal['result'])
        row, = self.job_rows(saved['id'])
        controls = json.loads(row[8])
        self.assertEqual(controls, {'instructions':
            'Create a conservative proposed refinement of the existing chapter narration. '
            'Preserve its meaning, facts, names, dates, sequence, language, and family voice. '
            'Correct clear transcription and punctuation mistakes only when supported by the supplied context. '
            'If a name or fact is uncertain, keep the original wording and add a review question. '
            'Do not invent events, quotations, dialogue, emotions, or source details. '
            'Use only the currently authorized selected story and its existing narration. '
            'Return a proposal for family review. Never save or adopt it into the original story.'})
        self.assertEqual(row[3:5], (saved['id'], 'narrative'))
        self.assertEqual(row[7], 1)

        replay = self.save(body, auto_refine=True)
        self.assertEqual(replay['id'], saved['id'])
        self.assertEqual(replay['revision'], '1')
        self.assertEqual(replay['auto_refinement']['id'], proposal['id'])
        self.assertEqual(len(self.job_rows(saved['id'])), 1)

    def test_replay_returns_original_revision_job_after_later_edit(self):
        first_body = self.f.body()
        first = self.save(first_body, auto_refine=True)
        later_body = self.f.body()
        later_body.update(revision='1', mutation_id=str(uuid.uuid4()), title='Later edit')
        second = self.save(later_body, first['id'])
        self.assertEqual(second['revision'], '2')

        replay = self.save(first_body, auto_refine=True)
        self.assertEqual(replay['revision'], '1')
        self.assertEqual(replay['title'], first['title'])
        self.assertEqual(replay['auto_refinement']['id'], first['auto_refinement']['id'])
        self.assertEqual(replay['auto_refinement']['base_revision'], '1')
        self.assertEqual(replay['auto_refinement']['state'], 'stale')
        self.assertEqual(len(self.job_rows(first['id'])), 1)

    def test_ready_proposal_is_separate_original_is_preserved_and_scope_is_current(self):
        saved = self.save(self.f.body(), auto_refine=True)
        job_id = saved['auto_refinement']['id']
        proposed = {'version': 1, 'chapters': [{'id': 'chapter-1',
                    'title': 'Suggested title', 'narration': 'Suggested wording.',
                    'asset_ids': ['102', '101'], 'evidence_ids': []}]}
        with self.library.connection() as db:
            db.execute("""UPDATE access_memory_jobs SET state='ready',output_json=?,
                updated_at=? WHERE id=?""", (json.dumps(proposed), self.library.now, job_id))
            db.commit()

        current = self.call('get', self.library.owner_token, saved['id'], False, True)
        self.assertEqual(current['chapters'][0]['narration'],
                         '这段回忆由家人讲述。\n保留我们的语气。')
        self.assertEqual(current['auto_refinement']['result'], proposed)
        self.assertTrue(current['auto_refinement']['needs_review'])

        member = self.call('get', self.library.member_token, saved['id'], False, True)
        self.assertNotIn('auto_refinement', member)
        with self.library.connection() as db:
            access = AccessService(db, clock=lambda: self.library.now)
            with self.assertRaises(AccessDenied):
                MemoryStories(access).get(self.library.owner_token, 'family-b', saved['id'],
                                          False, True)

        # A later saved revision does not surface the prior revision's job as current.
        edited = self.f.body()
        edited.update(revision='1', mutation_id=str(uuid.uuid4()), title='New revision')
        self.save(edited, saved['id'])
        latest = self.call('get', self.library.owner_token, saved['id'], False, True)
        self.assertEqual(latest['revision'], '2')
        self.assertIsNone(latest['auto_refinement'])

    def test_http_refinement_requires_enabled_worker_and_current_authorized_story(self):
        saved = self.save()
        app = self.f.client.app
        url = '/memory-stories/' + saved['id'] + '/refinement?library=family-a'
        headers = {'Authorization': 'Bearer ' + self.library.owner_token}
        self.assertEqual(self.f.client.post(url, headers=headers,
                                           json={'revision': '1'}).status_code, 503)
        app.state.memory_auto_refinement_enabled = True
        app.state.memory_refinement_healthy = True
        first = self.f.client.post(url, headers=headers, json={'revision': '1'})
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.headers['cache-control'], 'no-store')
        replay = self.f.client.post(url, headers=headers, json={'revision': '1'})
        self.assertEqual(first.json()['id'], replay.json()['id'])
        self.assertEqual(self.f.client.post(url, json={'revision': '1'}).status_code, 401)
        self.assertEqual(self.f.client.post(url, headers=headers,
                                           json={'revision': '2'}).status_code, 409)
        self.assertEqual(self.f.client.post(url, headers=headers,
                                           json={'revision': '1', 'instructions': 'override'}).status_code, 400)
        app.state.memory_refinement_healthy = False
        self.assertEqual(self.f.client.post(url, headers=headers,
                                           json={'revision': '1'}).status_code, 503)

    def test_existing_story_refinement_preserves_revision_and_complete_narration(self):
        body = self.f.body()
        chapters = json.loads(body['chapters'])
        original = '这是完整的生日回忆。' * 100
        chapters[0]['narration'] = original
        body['chapters'] = json.dumps(chapters)
        saved = self.save(body)
        before = self.counts()
        job = self.call('refine', self.library.owner_token, saved['id'], '1')
        repeated = self.call('refine', self.library.owner_token, saved['id'], '1')
        self.assertEqual(job['id'], repeated['id'])
        self.assertEqual(self.counts(), (before[0], before[1], before[2] + 1))
        with self.library.connection() as db:
            from app.access.memory_processing import job_context
            access = AccessService(db, clock=lambda: self.library.now)
            row = access._one('SELECT * FROM access_memory_jobs WHERE id=?', (job['id'],))
            bundle = job_context(access, row)
        self.assertEqual(bundle['chapters'][0]['narration'], original)
        with self.assertRaises(AccessDenied):
            self.call('refine', self.library.member_token, saved['id'], '1')
        from app.access.transport import TransportError
        with self.assertRaises(TransportError):
            self.call('refine', self.library.owner_token, saved['id'], '2')

    def test_empty_narration_never_queues_photo_only_story(self):
        body = self.f.body()
        chapters = json.loads(body['chapters'])
        chapters[0]['narration'] = ''
        body['chapters'] = json.dumps(chapters)
        saved = self.save(body, auto_refine=True)
        self.assertIn('auto_refinement', saved)
        self.assertIsNone(saved['auto_refinement'])
        self.assertEqual(self.job_rows(saved['id']), [])


if __name__ == '__main__':
    unittest.main()
