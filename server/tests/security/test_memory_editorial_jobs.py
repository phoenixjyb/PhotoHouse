"""Synthetic lifecycle checks for optional memoir editorial job context."""
import json
import unittest
import uuid
from unittest.mock import patch

import test_memory_book_editorial_service as editorial_fixture
from app.access.memory_jobs import EDITORIAL_CONTEXT_PROFILE, MemoryJobs, RETENTION, context
from app.access.memory_narrative import validate_narrative
from app.access.memory_processing import process_job
from app.access.service import AccessService
from app.access.transport import TransportError


class MemoryEditorialJobTests(unittest.TestCase):
    """Exercise editorial context through jobs without importing fixture tests."""

    @classmethod
    def setUpClass(cls):
        editorial_fixture.book_fixture.MemoryBookTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        editorial_fixture.book_fixture.MemoryBookTests.tearDownClass()

    def setUp(self):
        self.fixture = editorial_fixture.MemoryBookEditorialServiceTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.base.doCleanups)
        self.f = self.fixture.f
        self.owner = self.fixture.owner
        self.book_id = self.fixture.book_id
        self.book_revision = self.fixture.book['revision']

    def call(self, method, *args, enabled=False, **kwargs):
        with self.f.connection() as db:
            access = AccessService(db, clock=lambda: self.f.now)
            return getattr(MemoryJobs(access, editorial_enabled=enabled), method)(
                self.owner, 'family-a', *args, **kwargs)

    def row(self, ident):
        with self.f.connection() as db:
            cursor = db.execute('SELECT * FROM access_memory_jobs WHERE id=?', (ident,))
            return dict(zip((column[0] for column in cursor.description), cursor.fetchone()))

    def scalar(self, sql, params=()):
        with self.f.connection() as db:
            return db.execute(sql, params).fetchone()[0]

    def save_editorial(self):
        saved = self.fixture._service('save', self.book_id, self.fixture._request(), enabled=True)
        self.book_revision = saved['revision']

    def narrative(self, *, enabled=False, editorial_context=False, mutation=None,
                  target_type='book', target_id=None):
        revision = self.book_revision if target_type == 'book' else '1'
        return self.call('narrative', target_type, target_id or self.book_id, revision,
                         mutation or str(uuid.uuid4()), 'Keep the saved family voices.',
                         editorial_context=editorial_context, enabled=enabled)

    def _valid_narrative(self, bundle):
        candidate = {
            'version': 1,
            'title': bundle['title'],
            'chapters': [
                {'id': chapter['id'], 'narration': 'A synthetic reviewed draft.',
                 'source_ids': chapter['evidence_ids']}
                for chapter in bundle['chapters']
            ],
            'questions': [],
            'needs_review': True,
        }
        return validate_narrative(candidate, bundle)

    def _valid_companion(self, bundle):
        source_ids = [source['id'] for source in bundle['sources']]
        return {'version': 1, 'kind': 'answer', 'reply': 'A synthetic grounded reply.',
                'source_ids': source_ids[:1], 'questions': [], 'proposal': None}

    def test_opt_out_preserves_legacy_context_and_job_profile_on_b1_a0_and_f7(self):
        # The false default leaves the legacy context builder and fingerprint intact.
        for revision in ('b1d7e4a9c230', 'a0c9d2e4f817', 'f7c3a9d2e614'):
            with self.subTest(revision=revision):
                self.f.mutate('UPDATE alembic_version SET version_num=?', (revision,))
                guard = patch('app.access.memory_book_editorial.MemoryBookEditorial._read_sidecar',
                              side_effect=AssertionError('default context must not read editorial sidecar'))
                with guard:
                    job = self.narrative()
                    with self.f.connection() as db:
                        access = AccessService(db, clock=lambda: self.f.now)
                        principal = access._require(self.owner, 'family-a', 'story.write')
                        default_bundle, fingerprint, _can_edit = context(
                            access, 'family-a', principal, 'book', self.book_id)
                        explicit_bundle, explicit_fingerprint, _ = context(
                            access, 'family-a', principal, 'book', self.book_id,
                            editorial_context=False)
                        saved = db.execute('SELECT input_json,source_fingerprint FROM access_memory_jobs '
                                           'WHERE id=?', (job['id'],)).fetchone()
                self.assertEqual(default_bundle, explicit_bundle)
                self.assertEqual(fingerprint, explicit_fingerprint)
                self.assertEqual(saved[1], fingerprint)
                self.assertEqual(json.loads(saved[0]), {'instructions': 'Keep the saved family voices.'})
                self.assertNotIn(EDITORIAL_CONTEXT_PROFILE, saved[0])
                self.f.mutate('DELETE FROM access_memory_jobs')
                self.f.mutate("UPDATE alembic_version SET version_num='b1d7e4a9c230'")

    def test_disabled_or_non_book_editorial_requests_fail_before_queue(self):
        with self.assertRaises(TransportError) as disabled:
            self.narrative(editorial_context=True)
        self.assertEqual(disabled.exception.status, 503)
        self.assertEqual(self.scalar('SELECT count(*) FROM access_memory_jobs'), 0)

        with self.assertRaises(TransportError) as story_only:
            self.narrative(enabled=True, editorial_context=True,
                           target_type='story', target_id=self.fixture.child_one)
        self.assertEqual(story_only.exception.status, 400)
        self.assertEqual(self.scalar('SELECT count(*) FROM access_memory_jobs'), 0)

    def test_profile_is_book_only_opaque_and_rehydrates_both_narrative_and_chat(self):
        self.save_editorial()
        narrative = self.narrative(enabled=True, editorial_context=True)
        with self.f.connection() as db:
            stored = db.execute('SELECT input_json,expires_at,created_at FROM access_memory_jobs '
                                'WHERE id=?', (narrative['id'],)).fetchone()
        controls = json.loads(stored[0])
        self.assertEqual(controls, {'instructions': 'Keep the saved family voices.',
                                    'context_profile': EDITORIAL_CONTEXT_PROFILE})
        self.assertNotIn('synthetic family contribution', stored[0])
        self.assertEqual(stored[1] - stored[2], RETENTION)

        conversation = self.call('start', 'book', self.book_id, str(uuid.uuid4()), enabled=True)
        sent = self.call('send', conversation['id'], self.book_revision, str(uuid.uuid4()),
                         'How do these memories connect?', editorial_context=True, enabled=True)
        with self.f.connection() as db:
            row = db.execute('SELECT input_json,expires_at FROM access_memory_jobs WHERE id=?',
                             (sent['id'],)).fetchone()
        chat_controls = json.loads(row[0])
        self.assertEqual(set(chat_controls), {'turn_id', 'context_profile'})
        self.assertEqual(chat_controls['context_profile'], EDITORIAL_CONTEXT_PROFILE)
        self.assertNotIn('synthetic family contribution', row[0])
        self.assertEqual(row[1], conversation['expires_at'])

        class FakeNarrator:
            def __init__(self):
                self.narrative_bundle = None
                self.chat_bundle = None

            def narrative(inner, bundle):
                inner.narrative_bundle = bundle
                return self._valid_narrative(bundle)

            def companion(inner, bundle):
                inner.chat_bundle = bundle
                return self._valid_companion(bundle)

        fake = FakeNarrator()
        for expected_kind in ('narrative', 'chat'):
            with self.f.connection() as db:
                result = process_job(db, narrator=fake, clock=lambda: self.f.now,
                                     editorial_enabled=True)
            self.assertEqual(result['state'], 'ready')
        for bundle in (fake.narrative_bundle, fake.chat_bundle):
            self.assertIsNotNone(bundle)
            editorial = bundle['book_editorial']
            self.assertEqual(len(editorial['children']), 2)
            self.assertEqual(editorial['introduction_source_ids'],
                             ['contribution-' + self.fixture.source_one])
            self.assertEqual(len(editorial['transitions']), 1)
            self.assertEqual(editorial['transitions'][0]['source_ids'],
                             ['contribution-' + self.fixture.source_two])
            self.assertIn('synthetic family contribution', json.dumps(bundle))

        ready = self.call('get', narrative['id'], enabled=True)
        self.assertEqual(ready['state'], 'ready')
        self.assertTrue(ready['result']['needs_review'])
        turns = self.call('turns', conversation['id'], 1, reply_context=True, enabled=True)
        self.assertEqual(turns['items'][0]['state'], 'ready')
        self.assertEqual(turns['items'][0]['reply_text'], 'A synthetic grounded reply.')

    def test_same_mutation_cannot_switch_context_profile(self):
        self.save_editorial()
        mutation = str(uuid.uuid4())
        legacy = self.call('start', 'book', self.book_id, str(uuid.uuid4()), enabled=True)
        first = self.call('send', legacy['id'], self.book_revision, mutation,
                          'Keep this message.', enabled=True)
        with self.assertRaises(TransportError) as changed:
            self.call('send', legacy['id'], self.book_revision, mutation, 'Keep this message.',
                      editorial_context=True, enabled=True)
        self.assertEqual(changed.exception.status, 409)
        self.assertEqual(self.scalar('SELECT count(*) FROM access_memory_jobs'), 1)
        self.assertEqual(self.scalar('SELECT count(*) FROM access_memory_turns'), 1)

        narrative_mutation = str(uuid.uuid4())
        self.narrative(enabled=True, mutation=narrative_mutation)
        with self.assertRaises(TransportError) as changed_narrative:
            self.narrative(enabled=True, editorial_context=True, mutation=narrative_mutation)
        self.assertEqual(changed_narrative.exception.status, 409)

    def test_revoked_consent_before_claim_stales_without_calling_provider(self):
        self.save_editorial()
        job = self.narrative(enabled=True, editorial_context=True)
        self.f.mutate('UPDATE access_memory_contributions SET local_processing_consent=0 WHERE id=?',
                      (self.fixture.source_two,))

        class NeverCalled:
            called = False
            def narrative(self, _bundle):
                self.called = True
                return {}

        fake = NeverCalled()
        with self.f.connection() as db:
            result = process_job(db, narrator=fake, clock=lambda: self.f.now,
                                 editorial_enabled=True)
        self.assertFalse(fake.called)
        self.assertEqual(result, {'id': job['id'], 'state': 'stale'})
        row = self.row(job['id'])
        self.assertEqual(row['state'], 'stale')
        self.assertIsNone(row['output_json'])

    def test_unknown_or_malformed_stored_profile_stales_without_provider_or_output(self):
        self.save_editorial()
        jobs = [self.narrative(enabled=True, editorial_context=True) for _ in range(3)]
        malformed_controls = (
            json.dumps({'instructions': '', 'context_profile': 'memoir_editorial_v2'}),
            json.dumps({'instructions': '', 'context_profile': None}),
            '{"instructions":"","context_profile":"memoir_editorial_v1",'
            '"context_profile":"memoir_editorial_v2"}',
        )
        for job, controls in zip(jobs, malformed_controls):
            self.f.mutate('UPDATE access_memory_jobs SET input_json=? WHERE id=?',
                          (controls, job['id']))

        class NeverCalled:
            called = False
            def narrative(self, _bundle):
                self.called = True
                return {}

        fake = NeverCalled()
        seen = set()
        for _job in jobs:
            with self.f.connection() as db:
                result = process_job(db, narrator=fake, clock=lambda: self.f.now,
                                     editorial_enabled=True)
            self.assertEqual(result['state'], 'stale')
            seen.add(result['id'])
            self.assertIsNone(self.row(result['id'])['output_json'])
        self.assertEqual(seen, {job['id'] for job in jobs})
        self.assertFalse(fake.called)

    def test_default_off_worker_and_reads_never_fall_back_from_v2(self):
        self.save_editorial()
        queued = self.narrative(enabled=True, editorial_context=True)

        class NeverCalled:
            called = False
            def narrative(self, _bundle):
                self.called = True
                return {}

        fake = NeverCalled()
        with self.f.connection() as db:
            result = process_job(db, narrator=fake, clock=lambda: self.f.now)
        self.assertEqual(result, {'id': queued['id'], 'state': 'stale'})
        self.assertFalse(fake.called)
        self.assertIsNone(self.row(queued['id'])['output_json'])

        ready_narrative = self.narrative(enabled=True, editorial_context=True)
        with self.f.connection() as db:
            access = AccessService(db, clock=lambda: self.f.now)
            principal = access._require(self.owner, 'family-a', 'story.write')
            bundle, _fingerprint, _can_edit = context(
                access, 'family-a', principal, 'book', self.book_id, editorial_context=True)
            valid_output = self._valid_narrative(bundle)
            db.execute("UPDATE access_memory_jobs SET state='ready',output_json=? WHERE id=?",
                       (json.dumps(valid_output), ready_narrative['id']))
            db.commit()
        self.assertEqual(self.call('get', ready_narrative['id'], enabled=True)['state'], 'ready')
        disabled_read = self.call('get', ready_narrative['id'])
        self.assertEqual(disabled_read['state'], 'stale')
        self.assertIsNone(disabled_read['result'])

        conversation = self.call('start', 'book', self.book_id, str(uuid.uuid4()), enabled=True)
        chat = self.call('send', conversation['id'], self.book_revision,
                         str(uuid.uuid4()), 'Keep this reply private to its source context.',
                         editorial_context=True, enabled=True)
        with self.f.connection() as db:
            output = self._valid_companion(bundle)
            db.execute("UPDATE access_memory_jobs SET state='ready',output_json=? WHERE id=?",
                       (json.dumps(output), chat['id']))
            db.execute("UPDATE access_memory_turns SET reply_text=?,reply_kind='answer' WHERE job_id=?",
                       (output['reply'], chat['id']))
            db.commit()
        enabled_turn = self.call('turns', conversation['id'], 1,
                                 reply_context=True, enabled=True)['items'][0]
        self.assertEqual(enabled_turn['state'], 'ready')
        self.assertEqual(enabled_turn['reply_text'], output['reply'])
        disabled_turn = self.call('turns', conversation['id'], 1,
                                  reply_context=True)['items'][0]
        self.assertEqual(disabled_turn['state'], 'stale')
        self.assertIsNone(disabled_turn['reply_text'])

    def test_child_revision_change_during_provider_discards_result(self):
        self.save_editorial()
        job = self.narrative(enabled=True, editorial_context=True)

        class MutatingNarrator:
            called = False
            def narrative(inner, bundle):
                inner.called = True
                self.assertIn('book_editorial', bundle)
                self.f.mutate('UPDATE access_memory_stories SET revision=revision+1 WHERE id=?',
                              (self.fixture.child_one,))
                return self._valid_narrative(bundle)

        fake = MutatingNarrator()
        with self.f.connection() as db:
            result = process_job(db, narrator=fake, clock=lambda: self.f.now,
                                 editorial_enabled=True)
        self.assertTrue(fake.called)
        self.assertEqual(result['state'], 'stale')
        row = self.row(job['id'])
        self.assertIsNone(row['output_json'])
        self.assertEqual(row['error_code'], 'source_changed')

    def test_sidecar_change_during_provider_discards_result(self):
        self.save_editorial()
        job = self.narrative(enabled=True, editorial_context=True)

        class MutatingNarrator:
            def narrative(inner, bundle):
                self.fixture._service('save', self.book_id,
                    self.fixture._request(revision=self.book_revision,
                        transition_text='Edited while drafting.'), enabled=True)
                return self._valid_narrative(bundle)

        with self.f.connection() as db:
            result = process_job(db, narrator=MutatingNarrator(), clock=lambda: self.f.now,
                                 editorial_enabled=True)
        self.assertEqual(result['state'], 'stale')
        self.assertIsNone(self.row(job['id'])['output_json'])


if __name__ == '__main__':
    unittest.main()
