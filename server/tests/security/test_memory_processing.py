"""Synthetic one-item workers: no provider or live library I/O."""

import json
import io
import sqlite3
import unittest
import uuid
import wave
from contextlib import contextmanager

import test_memory_books as book_fixture
from app.access.memory_contributions import MemoryContributions
from app.access.memory_jobs import MemoryJobs
from app.access.memory_processing import process_contribution, process_job, recover_contribution
from app.access.service import AccessService
from app.access.stories import Stories


class MemoryProcessingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        book_fixture.MemoryBookTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        book_fixture.MemoryBookTests.tearDownClass()

    def setUp(self):
        self.f = book_fixture.MemoryBookTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.library = self.f.library_fixture
        self.story_id = self.f.story('Worker target')

    @contextmanager
    def connection(self):
        with self.library.connection() as db:
            db.row_factory = sqlite3.Row
            yield db

    def queue_narrative(self):
        with self.connection() as db:
            access = AccessService(db, clock=lambda: self.library.now)
            return MemoryJobs(access).narrative(
                self.f.owner, 'family-a', 'story', self.story_id, '1',
                str(uuid.uuid4()), 'Use cautious wording.')

    def queue_chat(self, message='First thought'):
        with self.connection() as db:
            access = AccessService(db, clock=lambda: self.library.now)
            jobs = MemoryJobs(access)
            conversation = jobs.start(self.f.member, 'family-a', 'story', self.story_id,
                                      str(uuid.uuid4()))
            job = jobs.send(self.f.member, 'family-a', conversation['id'], '1',
                            str(uuid.uuid4()), message)
            return conversation['id'], job['id']

    def send_chat(self, conversation_id, message):
        with self.connection() as db:
            access = AccessService(db, clock=lambda: self.library.now)
            return MemoryJobs(access).send(self.f.member, 'family-a', conversation_id,
                                           '1', str(uuid.uuid4()), message)

    def make_contribution(self, *, consent='1', review=True):
        body = {'kind': 'text', 'text': 'Synthetic family recollection.',
                'language': 'en', 'byline': 'Synthetic member', 'consent': consent,
                'chapter_id': 'chapter-1', 'revision': '1', 'mutation_id': str(uuid.uuid4())}
        with self.connection() as db:
            access = AccessService(db, clock=lambda: self.library.now)
            item = MemoryContributions(access).create(
                self.f.member, 'family-a', self.story_id, body)
            if review:
                MemoryContributions(access).review(
                    self.f.owner, 'family-a', self.story_id, item['id'], 'accepted', 1)
            return item

    def test_narrative_runs_outside_transaction_rechecks_sources_and_never_edits_story(self):
        queued = self.queue_narrative()
        seen = {}

        class Narrator:
            def narrative(inner, bundle):
                self.assertFalse(db.in_transaction)
                seen['bundle'] = bundle
                chapter = bundle['chapters'][0]
                seen['story_revision'] = bundle['target']['revision']
                refs = chapter['evidence_ids']
                return {'version': 1, 'title': 'Draft only',
                        'chapters': [{'id': chapter['id'], 'narration': 'Reviewed draft.',
                                      'source_ids': refs[:1]}],
                        'questions': [], 'needs_review': True}

        with self.connection() as db:
            result = process_job(db, narrator=Narrator(), clock=lambda: self.library.now)
            self.assertEqual(result, {'id': queued['id'], 'state': 'ready'})
            saved = db.execute('SELECT state,output_json,error_code FROM access_memory_jobs WHERE id=?',
                               (queued['id'],)).fetchone()
            story = db.execute('SELECT revision,content FROM access_memory_stories WHERE id=?',
                               (self.story_id,)).fetchone()
        self.assertEqual(saved['state'], 'ready')
        self.assertIsNone(saved['error_code'])
        output = json.loads(saved['output_json'])
        self.assertEqual(output['chapters'][0]['id'], seen['bundle']['chapters'][0]['id'])
        self.assertEqual(story['revision'], seen['story_revision'])
        self.assertNotIn('Reviewed draft.', story['content'])

        # A new job is discarded if its source changes while the provider is running.
        queued = self.queue_narrative()

        class EditingNarrator:
            def narrative(inner, bundle):
                self.assertFalse(db.in_transaction)
                self.library.mutate("UPDATE captions SET text='new current source' WHERE id=101")
                chapter = bundle['chapters'][0]
                return {'version': 1, 'title': 'Must be discarded',
                        'chapters': [{'id': chapter['id'], 'narration': 'Stale output.',
                                      'source_ids': chapter['evidence_ids'][:1]}],
                        'questions': [], 'needs_review': True}

        with self.connection() as db:
            result = process_job(db, narrator=EditingNarrator(), clock=lambda: self.library.now)
            saved = db.execute('SELECT state,output_json,error_code FROM access_memory_jobs WHERE id=?',
                               (queued['id'],)).fetchone()
        self.assertEqual(result['state'], 'stale')
        self.assertEqual(tuple(saved), ('stale', None, 'source_changed'))

    def test_worker_preserves_each_note_voice_and_discards_changed_attribution(self):
        with self.connection() as db:
            access = AccessService(db, clock=lambda: self.library.now)
            notes = []
            for asset_id, byline in ((102, '奶奶'), (101, '爷爷')):
                notes.append(Stories(access).save(self.f.owner, 'family-a', {
                    'title': 'A shared memory', 'text': 'I remember planting flowers.',
                    'language': 'en', 'byline': byline, 'mutation_id': str(uuid.uuid4()),
                }, asset_id=asset_id))
        expected = {'family-' + note['id']: note['byline'] for note in notes}
        seen = []
        edit_during_inference = False

        class Narrator:
            def narrative(inner, bundle):
                self.assertFalse(db.in_transaction)
                actual = {source['id']: source['author'] for source in bundle['sources']
                          if source['id'] in expected}
                self.assertEqual(actual, expected)
                self.assertTrue(all(source['author'] is None for source in bundle['sources']
                                    if source['kind'] in {'ai', 'editorial'}))
                seen.append(actual)
                if edit_during_inference:
                    self.library.mutate('UPDATE access_stories SET byline=? WHERE id=?',
                                        ('Revised speaker label', notes[0]['id']))
                chapter = bundle['chapters'][0]
                return {'version': 1, 'title': 'For family review',
                        'chapters': [{'id': chapter['id'], 'narration': 'A synthetic draft.',
                                      'source_ids': chapter['evidence_ids'][:1]}],
                        'questions': [], 'needs_review': True}

        queued = self.queue_narrative()
        with self.connection() as db:
            controls = db.execute('SELECT input_json FROM access_memory_jobs WHERE id=?',
                                  (queued['id'],)).fetchone()[0]
            readable_controls = json.dumps(json.loads(controls), ensure_ascii=False)
            self.assertNotIn('奶奶', readable_controls)
            self.assertNotIn('爷爷', readable_controls)
            self.assertNotIn('I remember planting flowers.', readable_controls)
            result = process_job(db, narrator=Narrator(), clock=lambda: self.library.now)
            self.assertEqual(result['state'], 'ready')
        queued = self.queue_narrative()
        edit_during_inference = True
        with self.connection() as db:
            result = process_job(db, narrator=Narrator(), clock=lambda: self.library.now)
            saved = db.execute('SELECT state,output_json,error_code FROM access_memory_jobs WHERE id=?',
                               (queued['id'],)).fetchone()
        self.assertEqual(len(seen), 2)
        self.assertEqual(result['state'], 'stale')
        self.assertEqual(tuple(saved), ('stale', None, 'source_changed'))

    def test_memoir_opening_note_edit_during_provider_discards_unadopted_output(self):
        book = self.f.save(self.f.owner, self.f.body([self.story_id],
                           introduction='An opening about our summer.'))
        with self.connection() as db:
            queued = MemoryJobs(AccessService(db, clock=lambda: self.library.now)).narrative(
                self.f.owner, 'family-a', 'book', book['id'], '1', str(uuid.uuid4()), '')

        class EditingNarrator:
            def narrative(inner, bundle):
                self.assertFalse(db.in_transaction)
                opening = next(source for source in bundle['sources']
                               if source['id'] == 'editorial-book-' + book['id'])
                self.assertEqual(opening['kind'], 'editorial')
                self.assertEqual(opening['text'], 'An opening about our summer.')
                self.f.save(self.f.owner, self.f.body([self.story_id], revision='1',
                            introduction='The family changed the opening.'), book['id'])
                return {'version': 1, 'title': 'Needs review',
                        'chapters': [{'id': chapter['id'], 'narration': 'A draft from the old opening.',
                                      'source_ids': chapter['evidence_ids'][:1]}
                                     for chapter in bundle['chapters']],
                        'questions': [], 'needs_review': True}

        with self.connection() as db:
            result = process_job(db, narrator=EditingNarrator(), clock=lambda: self.library.now)
            saved = db.execute('SELECT state,output_json,error_code FROM access_memory_jobs WHERE id=?',
                               (queued['id'],)).fetchone()
        self.assertEqual(result['state'], 'stale')
        self.assertEqual(tuple(saved), ('stale', None, 'source_changed'))

    def test_cancellation_during_provider_discards_result_and_expiry_is_deleted(self):
        queued = self.queue_narrative()

        class CancellingNarrator:
            def narrative(inner, bundle):
                self.assertFalse(db.in_transaction)
                self.library.mutate("""UPDATE access_memory_jobs SET state='cancelled',output_json=NULL,
                    lease_id=NULL,lease_until=NULL WHERE id=?""", (queued['id'],))
                chapter = bundle['chapters'][0]
                return {'version': 1, 'title': 'Cancelled',
                        'chapters': [{'id': chapter['id'], 'narration': '', 'source_ids': []}],
                        'questions': [], 'needs_review': True}

        with self.connection() as db:
            result = process_job(db, narrator=CancellingNarrator(), clock=lambda: self.library.now)
        self.assertEqual(result, {'id': queued['id'], 'state': 'cancelled'})

        queued = self.queue_narrative()

        class ExpiringNarrator:
            def narrative(inner, bundle):
                self.library.now += 31 * 86400
                chapter = bundle['chapters'][0]
                return {'version': 1, 'title': 'Expired',
                        'chapters': [{'id': chapter['id'], 'narration': '', 'source_ids': []}],
                        'questions': [], 'needs_review': True}

        with self.connection() as db:
            result = process_job(db, narrator=ExpiringNarrator(), clock=lambda: self.library.now)
            self.assertIsNone(db.execute('SELECT 1 FROM access_memory_jobs WHERE id=?',
                                         (queued['id'],)).fetchone())
        self.assertEqual(result['state'], 'expired')

    def test_chat_turn_stales_if_prior_ready_reply_is_cancelled_during_provider(self):
        conversation_id, prior_id = self.queue_chat()
        self.library.mutate("UPDATE access_memory_jobs SET state='ready',output_json='{}' WHERE id=?",
                            (prior_id,))
        self.library.mutate("UPDATE access_memory_turns SET reply_text='prior private reply',reply_kind='answer' WHERE job_id=?",
                            (prior_id,))
        current = self.send_chat(conversation_id, 'Second thought')
        seen = {}

        class CancellingPriorReply:
            def companion(inner, bundle):
                self.assertEqual('prior private reply', bundle['recent_turns'][0]['assistant'])
                self.library.mutate("UPDATE access_memory_jobs SET state='cancelled',output_json=NULL WHERE id=?",
                                    (prior_id,))
                self.library.mutate("UPDATE access_memory_turns SET reply_text=NULL,reply_kind=NULL WHERE job_id=?",
                                    (prior_id,))
                seen['called'] = True
                return {'version': 1, 'kind': 'answer', 'reply': 'Must be discarded.',
                        'source_ids': [], 'questions': [], 'proposal': None}

        with self.connection() as db:
            result = process_job(db, narrator=CancellingPriorReply(), clock=lambda: self.library.now)
            job = db.execute('SELECT state,output_json,error_code FROM access_memory_jobs WHERE id=?',
                             (current['id'],)).fetchone()
            turn = db.execute('SELECT reply_text,reply_kind FROM access_memory_turns WHERE job_id=?',
                              (current['id'],)).fetchone()
        self.assertTrue(seen.get('called'))
        self.assertEqual(result['state'], 'stale')
        self.assertEqual(tuple(job), ('stale', None, 'source_changed'))
        self.assertEqual(tuple(turn), (None, None))

    def test_chat_never_sends_already_stale_prior_reply_to_provider(self):
        conversation_id, prior_id = self.queue_chat()
        self.library.mutate("UPDATE access_memory_jobs SET state='stale',output_json=NULL WHERE id=?",
                            (prior_id,))
        # A stale reply field may survive a legacy/out-of-band write; it is not trusted context.
        self.library.mutate("UPDATE access_memory_turns SET reply_text='stale private reply',reply_kind='answer' WHERE job_id=?",
                            (prior_id,))
        current = self.send_chat(conversation_id, 'Second thought')
        seen = {}

        class InspectContext:
            def companion(inner, bundle):
                seen['recent'] = bundle['recent_turns']
                return {'version': 1, 'kind': 'answer', 'reply': 'Current reply.',
                        'source_ids': [], 'questions': [], 'proposal': None}

        with self.connection() as db:
            result = process_job(db, narrator=InspectContext(), clock=lambda: self.library.now)
            row = db.execute('SELECT state,output_json FROM access_memory_jobs WHERE id=?',
                             (current['id'],)).fetchone()
        self.assertEqual(seen['recent'][0]['assistant'], '')
        self.assertEqual(result['state'], 'ready')
        self.assertEqual(row['state'], 'ready')
        self.assertIn('Current reply.', row['output_json'])

    def test_expired_contribution_recovery_is_exact_and_never_requeues(self):
        item = self.make_contribution()
        self.library.mutate("""UPDATE access_memory_contribution_derivations SET state='running',
            transcript='private transcript',polished_text='private draft',tags='[\"tag\"]',
            provider='private-provider',model='private-model',lease_id='lease',lease_until=?,updated_at=?
            WHERE contribution_id=? AND revision=1""",
            (self.library.now + 30, self.library.now, item['id']))
        with self.connection() as db:
            with self.assertRaises(ValueError):
                recover_contribution(db, item['id'], 1, clock=lambda: self.library.now)
            with self.assertRaises(ValueError):
                recover_contribution(db, item['id'], 2, clock=lambda: self.library.now)
        self.library.mutate("UPDATE access_memory_contribution_derivations SET lease_until=? WHERE contribution_id=?",
                            (self.library.now - 1, item['id']))
        with self.connection() as db:
            result = recover_contribution(db, item['id'], 1, clock=lambda: self.library.now)
            derivation = db.execute('''SELECT state,transcript,polished_text,tags,provider,model,
                error_code,lease_id,lease_until FROM access_memory_contribution_derivations
                WHERE contribution_id=? AND revision=1''', (item['id'],)).fetchone()
            self.assertIsNone(process_contribution(db, transcribe=lambda *_: self.fail('no automatic retry'),
                polish=lambda *_: self.fail('no automatic retry'), clock=lambda: self.library.now))
        self.assertEqual(result, {'id': item['id'], 'revision': 1, 'state': 'failed'})
        self.assertEqual(tuple(derivation), ('failed', None, None, '[]', None, None,
                                             'interrupted', None, None))

    def test_provider_failure_is_sanitized_and_not_automatically_retried(self):
        queued = self.queue_narrative()

        class BrokenNarrator:
            def narrative(inner, _bundle):
                raise RuntimeError('secret prompt and source text')

        with self.connection() as db:
            result = process_job(db, narrator=BrokenNarrator(), clock=lambda: self.library.now)
            row = db.execute('SELECT state,error_code,output_json,input_json FROM access_memory_jobs WHERE id=?',
                             (queued['id'],)).fetchone()
        self.assertEqual(result['state'], 'failed')
        self.assertEqual(tuple(row[:3]), ('failed', 'local_processing_failed', None))
        self.assertNotIn('secret prompt', row['input_json'])
        with self.connection() as db:
            self.assertIsNone(process_job(db, narrator=BrokenNarrator(), clock=lambda: self.library.now))

    def test_contribution_writes_separate_derivation_and_rechecks_consent_membership_and_source(self):
        item = self.make_contribution()
        original = item['text']
        calls = []

        def transcribe(_audio, _language):
            self.fail('text contribution must not invoke ASR')

        def polish(text, language):
            self.assertFalse(db.in_transaction)
            calls.append((text, language))
            return {'text': 'Separate polished derivation.', 'tags': ['family'],
                    'provider': 'synthetic', 'model': 'fake'}

        with self.connection() as db:
            result = process_contribution(db, transcribe=transcribe, polish=polish,
                                          clock=lambda: self.library.now)
            saved = db.execute('''SELECT d.state,d.transcript,d.polished_text,d.tags,c.original_text
                FROM access_memory_contribution_derivations d JOIN access_memory_contributions c
                ON c.id=d.contribution_id WHERE c.id=?''', (item['id'],)).fetchone()
            story = db.execute('SELECT revision,content FROM access_memory_stories WHERE id=?',
                               (self.story_id,)).fetchone()
        self.assertEqual(result['state'], 'ready')
        self.assertEqual(calls, [(original, 'en')])
        self.assertEqual((saved['state'], saved['transcript'], saved['polished_text'], saved['original_text']),
                         ('ready', None, 'Separate polished derivation.', original))
        self.assertNotIn('Separate polished derivation.', story['content'])

        # Declining during provider work revokes eligibility before derivation commit.
        declined = self.make_contribution()

        def decline_during_polish(text, language):
            self.assertFalse(db.in_transaction)
            self.library.mutate("UPDATE access_memory_contributions SET state='declined' WHERE id=?",
                                (declined['id'],))
            return {'text': 'Must be discarded.', 'tags': [], 'provider': 'synthetic', 'model': 'fake'}

        with self.connection() as db:
            result = process_contribution(db, transcribe=transcribe, polish=decline_during_polish,
                                          clock=lambda: self.library.now)
            saved = db.execute('''SELECT state,transcript,polished_text,error_code FROM
                access_memory_contribution_derivations WHERE contribution_id=?''',
                               (declined['id'],)).fetchone()
        self.assertEqual(result['state'], 'cancelled')
        self.assertEqual(tuple(saved), ('cancelled', None, None, 'source_changed'))

    def test_contribution_requires_acceptance_and_explicit_consent_and_rechecks_moved_media(self):
        pending = self.make_contribution(consent='1', review=False)
        no_consent = self.make_contribution(consent='0')
        self.assertEqual(pending['state'], 'pending')
        calls = []

        def unused(*args):
            calls.append(args)
            return {'text': 'unexpected', 'tags': [], 'provider': 'fake', 'model': 'fake'}

        with self.connection() as db:
            self.assertIsNone(process_contribution(db, transcribe=unused, polish=unused,
                                                   clock=lambda: self.library.now))
        self.assertEqual(calls, [])
        # An accepted contribution without local processing consent creates no job.
        with self.connection() as db:
            self.assertIsNone(process_contribution(db, transcribe=unused, polish=unused,
                                                   clock=lambda: self.library.now))
        self.assertEqual(calls, [])

        accepted = self.make_contribution()

        def move_during_polish(_text, _language):
            self.assertFalse(db.in_transaction)
            self.library.mutate("UPDATE access_asset_libraries SET library_id='family-b' WHERE asset_id=101")
            return {'text': 'Must not be retained.', 'tags': [], 'provider': 'fake', 'model': 'fake'}

        with self.connection() as db:
            result = process_contribution(db, transcribe=unused, polish=move_during_polish,
                                          clock=lambda: self.library.now)
            saved = db.execute('''SELECT state,transcript,polished_text FROM
                access_memory_contribution_derivations WHERE contribution_id=?''',
                               (accepted['id'],)).fetchone()
        self.assertEqual(result['state'], 'cancelled')
        self.assertEqual(tuple(saved), ('cancelled', None, None))

    def test_corrupt_text_original_is_cancelled_before_any_provider_call(self):
        item = self.make_contribution()
        self.library.mutate("UPDATE access_memory_contributions SET original_text=? WHERE id=?",
                            ('Corrupted but still bounded.', item['id']))
        calls = []

        def unexpected(*args):
            calls.append(args)
            self.fail('corrupt original must not reach a provider')

        with self.connection() as db:
            result = process_contribution(db, transcribe=unexpected, polish=unexpected,
                                          clock=lambda: self.library.now)
            derivation = db.execute('''SELECT state,transcript,polished_text,tags,provider,model,
                error_code FROM access_memory_contribution_derivations
                WHERE contribution_id=? AND revision=1''', (item['id'],)).fetchone()
        self.assertEqual(result, {'id': item['id'], 'state': 'cancelled'})
        self.assertEqual(calls, [])
        self.assertEqual(tuple(derivation), ('cancelled', None, None, '[]', None, None,
                                             'source_changed'))

    def test_corrupt_audio_original_during_provider_discards_all_derived_words(self):
        wav = io.BytesIO()
        with wave.open(wav, 'wb') as target:
            target.setnchannels(1)
            target.setsampwidth(2)
            target.setframerate(16000)
            target.writeframes(b'\x00\x00' * 16000)
        original = wav.getvalue()
        body = {'kind': 'audio', 'text': '', 'language': 'en', 'byline': 'Synthetic member',
                'consent': '1', 'chapter_id': 'chapter-1', 'revision': '1',
                'mutation_id': str(uuid.uuid4())}
        with self.connection() as db:
            access = AccessService(db, clock=lambda: self.library.now)
            item = MemoryContributions(access).create(self.f.member, 'family-a', self.story_id,
                                                       body, original)
            MemoryContributions(access).review(self.f.owner, 'family-a', self.story_id,
                                               item['id'], 'accepted', 1)

        changed = original[:-1] + bytes([original[-1] ^ 1])
        calls = []

        def transcribe(audio, _language):
            self.assertEqual(audio, original)
            calls.append('transcribe')
            # Simulate an out-of-band source replacement while inference is running.
            self.library.mutate("UPDATE access_memory_contributions SET original_audio=? WHERE id=?",
                                (changed, item['id']))
            return {'text': 'Transcript must not be retained.', 'provider': 'fake-asr',
                    'model': 'fake-asr'}

        def polish(transcript, _language):
            calls.append('polish')
            self.assertEqual(transcript, 'Transcript must not be retained.')
            return {'text': 'Polish must not be retained.', 'tags': ['private-tag'],
                    'provider': 'fake-polish', 'model': 'fake-polish'}

        with self.connection() as db:
            result = process_contribution(db, transcribe=transcribe, polish=polish,
                                          clock=lambda: self.library.now)
            derivation = db.execute('''SELECT state,transcript,polished_text,tags,provider,model,
                error_code FROM access_memory_contribution_derivations
                WHERE contribution_id=? AND revision=1''', (item['id'],)).fetchone()
        self.assertEqual(result, {'id': item['id'], 'state': 'cancelled'})
        self.assertEqual(calls, ['transcribe', 'polish'])
        self.assertEqual(tuple(derivation), ('cancelled', None, None, '[]', None, None,
                                             'source_changed'))

    def test_contribution_revocation_and_delete_during_provider_drop_derived_data(self):
        item = self.make_contribution()

        def revoke_during_polish(_text, _language):
            self.assertFalse(db.in_transaction)
            self.library.mutate("UPDATE access_memberships SET status='revoked' WHERE account_id=?",
                                (self.library.member_id,))
            return {'text': 'Revoked result.', 'tags': [], 'provider': 'fake', 'model': 'fake'}

        with self.connection() as db:
            result = process_contribution(db, transcribe=lambda *_: None,
                                          polish=revoke_during_polish,
                                          clock=lambda: self.library.now)
            saved = db.execute('''SELECT state,transcript,polished_text FROM
                access_memory_contribution_derivations WHERE contribution_id=?''',
                               (item['id'],)).fetchone()
        self.assertEqual(result['state'], 'cancelled')
        self.assertEqual(tuple(saved), ('cancelled', None, None))

        # Fresh fixture membership and a second accepted item; deletion invalidates the lease.
        self.library.mutate("UPDATE access_memberships SET status='approved' WHERE account_id=?",
                            (self.library.member_id,))
        deleted = self.make_contribution()

        def delete_during_polish(_text, _language):
            self.assertFalse(db.in_transaction)
            with self.connection() as other_db:
                access = AccessService(other_db, clock=lambda: self.library.now)
                MemoryContributions(access).delete(self.f.owner, 'family-a', self.story_id,
                                                   deleted['id'])
            return {'text': 'Deleted result.', 'tags': [], 'provider': 'fake', 'model': 'fake'}

        with self.connection() as db:
            result = process_contribution(db, transcribe=lambda *_: None,
                                          polish=delete_during_polish,
                                          clock=lambda: self.library.now)
            exists = db.execute('SELECT 1 FROM access_memory_contributions WHERE id=?',
                                (deleted['id'],)).fetchone()
        self.assertEqual(result['state'], 'cancelled')
        self.assertIsNone(exists)

    def test_audio_transcript_and_polish_are_separate_from_immutable_original_wav(self):
        wav = io.BytesIO()
        with wave.open(wav, 'wb') as target:
            target.setnchannels(1)
            target.setsampwidth(2)
            target.setframerate(16000)
            target.writeframes(b'\x00\x00' * 16000)
        original = wav.getvalue()
        body = {'kind': 'audio', 'text': '', 'language': 'en', 'byline': 'Synthetic member',
                'consent': '1', 'chapter_id': 'chapter-1', 'revision': '1',
                'mutation_id': str(uuid.uuid4())}
        with self.connection() as db:
            access = AccessService(db, clock=lambda: self.library.now)
            item = MemoryContributions(access).create(self.f.member, 'family-a', self.story_id,
                                                       body, original)
            MemoryContributions(access).review(self.f.owner, 'family-a', self.story_id,
                                               item['id'], 'accepted', 1)

        def transcribe(audio, language):
            self.assertFalse(db.in_transaction)
            self.assertEqual(audio, original)
            self.assertEqual(language, 'en')
            return {'text': 'Transcript from audio.', 'provider': 'fake-asr', 'model': 'fake-asr'}

        def polish(text, language):
            self.assertFalse(db.in_transaction)
            self.assertEqual(text, 'Transcript from audio.')
            self.assertEqual(language, 'en')
            return {'text': 'Polished from transcript.', 'tags': [],
                    'provider': 'fake-polish', 'model': 'fake-polish'}

        with self.connection() as db:
            result = process_contribution(db, transcribe=transcribe, polish=polish,
                                          clock=lambda: self.library.now)
            saved = db.execute('''SELECT d.state,d.transcript,d.polished_text,c.original_audio
                FROM access_memory_contribution_derivations d JOIN access_memory_contributions c
                ON c.id=d.contribution_id WHERE c.id=?''', (item['id'],)).fetchone()
        self.assertEqual(result['state'], 'ready')
        self.assertEqual((saved['state'], saved['transcript'], saved['polished_text'],
                          saved['original_audio']),
                         ('ready', 'Transcript from audio.', 'Polished from transcript.', original))

    def test_story_author_contributor_can_accept_before_worker_processing(self):
        self.library.mutate("UPDATE access_memberships SET role='contributor' WHERE account_id=?",
                            (self.library.member_id,))
        story_id = self.f.story('Contributor-owned target', token=self.f.member)
        body = {'kind': 'text', 'text': 'Approved contributor context.', 'language': 'en',
                'byline': 'Synthetic owner', 'consent': '1', 'chapter_id': 'chapter-1',
                'revision': '1', 'mutation_id': str(uuid.uuid4())}
        with self.connection() as db:
            access = AccessService(db, clock=lambda: self.library.now)
            contributions = MemoryContributions(access)
            item = contributions.create(self.f.owner, 'family-a', story_id, body)
            reviewed = contributions.review(self.f.member, 'family-a', story_id,
                                            item['id'], 'accepted', 1)
        self.assertEqual(reviewed['state'], 'accepted')

        def polish(text, language):
            self.assertFalse(db.in_transaction)
            self.assertEqual((text, language), ('Approved contributor context.', 'en'))
            return {'text': 'Separated reviewed derivation.', 'tags': [],
                    'provider': 'synthetic', 'model': 'fake'}

        with self.connection() as db:
            result = process_contribution(db, transcribe=lambda *_: None, polish=polish,
                                          clock=lambda: self.library.now)
        self.assertEqual(result['state'], 'ready')


if __name__ == '__main__':
    unittest.main()
