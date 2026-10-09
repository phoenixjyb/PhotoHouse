"""Edition-bound original source reads never trust caller supplied citations."""
import unittest
import uuid
import io
import wave

import test_memory_book_editions as edition_fixture
from app.access.memory_book_edition_sources import MemoryBookEditionSources
from app.access.memory_book_editions import MemoryBookEditions
from app.access.memory_book_edition_deletions import invalidate_editions_for_contribution
from app.access.memory_contributions import MemoryContributions
from app.access.service import AccessDenied, AccessService
from app.access.stories import Stories
from app.access.transport import TransportError


class MemoryBookEditionSourcesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        edition_fixture.MemoryBookEditionsTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        edition_fixture.MemoryBookEditionsTests.tearDownClass()

    def setUp(self):
        self.seed = edition_fixture.MemoryBookEditionsTests()
        self.seed.setUp()
        self.addCleanup(self.seed.doCleanups)
        self.f = self.seed.f
        self.book_id = self.seed.book_id

    def _saved(self):
        proposal, _raw, receipt, job = self.seed._saved()
        self.saved_proposal = proposal
        self.saved_job = job
        return receipt['id']

    def _read(self, action, edition_id, *args, token=None, originals=True):
        with self.f.connection() as db:
            access = AccessService(db, clock=lambda: self.f.now)
            editions = MemoryBookEditions(access, enabled=True)
            source_reader = MemoryBookEditionSources(
                editions, originals_enabled=originals)
            return getattr(source_reader, action)(token or self.seed.owner, 'family-a',
                self.book_id, edition_id, *args)

    def test_list_uses_full_fresh_closure_and_detail_requires_membership(self):
        edition_id = self._saved()
        result = self._read('list', edition_id)
        self.assertEqual(result['state'], 'current')
        self.assertLessEqual(len(result['items']), 96)
        self.assertTrue(result['items'])
        self.assertTrue(all(set(item) == {'source_id', 'origin', 'kind', 'asset_id'}
                            for item in result['items']))
        self.assertTrue(any(item['source_id'].startswith('contribution-')
                            for item in result['items']))
        cited = {source_id for chapter in self.saved_proposal['manuscript']['chapters']
                 for source_id in chapter['source_ids']}
        self.assertTrue(any(item['source_id'] not in cited for item in result['items']))
        for item in result['items']:
            detail_item = self._read('detail', edition_id, item['source_id'])
            self.assertEqual(detail_item['state'], 'current', item['source_id'])
            self.assertEqual(detail_item['source']['origin'], item['origin'])
            self.assertEqual(detail_item['source']['prompt_excerpt'] is not None, True)
        source_id = next(item['source_id'] for item in result['items']
                         if item['source_id'].startswith('contribution-'))
        detail = self._read('detail', edition_id, source_id,
                            token=self.f.member_token)
        self.assertEqual(detail['state'], 'current')
        self.assertEqual(detail['source_id'], source_id)
        self.assertEqual(detail['source']['origin'], 'contribution_text')
        self.assertTrue(detail['source']['original_text'])
        self.assertNotIn('polished_text', detail['source'])
        self.assertNotIn('account_id', detail['source'])
        self.f.mutate('DELETE FROM access_memory_jobs WHERE id=?', (self.saved_job,))
        self.assertEqual(self._read('detail', edition_id, source_id)['state'], 'current')

    def test_asset_note_keeps_voluntary_byline_without_account_identity(self):
        with self.f.connection() as db:
            note = Stories(AccessService(db, clock=lambda: self.f.now)).save(
                self.seed.owner, 'family-a', {
                    'title': 'A family note', 'text': 'We planted flowers together.',
                    'language': 'en', 'byline': '奶奶', 'mutation_id': str(uuid.uuid4()),
                }, asset_id=102)
        edition_id = self._saved()
        source_id = 'family-' + note['id']
        result = self._read('detail', edition_id, source_id,
                            token=self.f.member_token)
        self.assertEqual(result['source']['origin'], 'asset_note')
        self.assertEqual(result['source']['byline'], '奶奶')
        self.assertEqual(result['source']['original_text'], 'We planted flowers together.')
        self.assertNotIn('author_id', result['source'])
        self.assertNotIn('account_id', result['source'])
        self.assertFalse(result['source']['audio_available'])
        # Attribution is a source dependency even if an out-of-band change did
        # not advance the ordinary note revision.
        self.f.mutate('UPDATE access_stories SET byline=? WHERE id=?', ('姥姥', note['id']))
        changed_label = self._read('detail', edition_id, source_id)
        self.assertEqual(changed_label['state'], 'source_changed')
        self.assertIsNone(changed_label['source'])
        # Re-reading never falls back to retained revision words or attribution.
        self.f.mutate('UPDATE access_stories SET deleted=1 WHERE id=?', (note['id'],))
        changed = self._read('detail', edition_id, source_id)
        self.assertEqual(changed['state'], 'source_changed')
        self.assertIsNone(changed['source'])

    def test_arbitrary_citation_and_originals_gate_fail_closed(self):
        edition_id = self._saved()
        with self.assertRaises(AccessDenied):
            self._read('detail', edition_id, 'contribution-' + str(uuid.uuid4()))
        with self.assertRaises(TransportError) as off:
            self._read('list', edition_id, originals=False)
        self.assertEqual(off.exception.status, 503)

    def test_changed_and_invalidated_editions_never_return_source_text(self):
        edition_id = self._saved()
        self.seed.base.base.save(self.seed.owner, self.seed.base.base.body(
            [self.seed.child_one, self.seed.child_two], title='Revised memoir', revision='1'),
            self.book_id)
        changed = self._read('detail', edition_id, 'contribution-' + str(uuid.uuid4()))
        self.assertEqual(changed['state'], 'source_changed')
        self.assertIsNone(changed['source'])

    def test_invalidated_edition_returns_null_without_resolving_selector(self):
        edition_id = self._saved()
        with self.f.connection() as db:
            db.execute('PRAGMA secure_delete=ON')
            db.execute('BEGIN IMMEDIATE')
            invalidate_editions_for_contribution(db, self.seed.base.source_one,
                self.seed.child_one, 'family-a')
            db.commit()
        invalidated = self._read('detail', edition_id, 'unknown-citation')
        self.assertEqual(invalidated['state'], 'source_invalidated')
        self.assertIsNone(invalidated['source'])

    def test_audio_source_is_an_explicit_bounded_read_and_rejects_bad_hash(self):
        raw = io.BytesIO()
        with wave.open(raw, 'wb') as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
            wav.writeframes(b'\0' * 320)
        payload = raw.getvalue()
        with self.f.connection() as db:
            access = AccessService(db, clock=lambda: self.f.now)
            contributions = MemoryContributions(access)
            item = contributions.create(self.f.member_token, 'family-a', self.seed.child_one, {
                'kind': 'audio', 'text': '', 'language': 'en', 'byline': 'Family',
                'consent': '1', 'chapter_id': '', 'revision': '1',
                'mutation_id': str(uuid.uuid4()),
            }, payload)
            contributions.review(self.seed.owner, 'family-a', self.seed.child_one,
                                 item['id'], 'accepted', 1)
            with access._transaction(write=True):
                db.execute('''UPDATE access_memory_contribution_derivations
                    SET state='ready',transcript='The family remembers this moment.'
                    WHERE contribution_id=?''', (item['id'],))
        edition_id = self._saved()
        listed = self._read('list', edition_id)
        audio_source = next(item['source_id'] for item in listed['items']
                            if item['origin'] == 'contribution_audio')
        detail = self._read('detail', edition_id, audio_source)
        self.assertEqual(detail['source']['original_text'], None)
        self.assertEqual(detail['source']['transcript'], 'The family remembers this moment.')
        self.assertTrue(detail['source']['audio_available'])
        self.assertEqual(self._read('audio', edition_id, audio_source)['audio'], payload)
        with self.f.connection() as db:
            triggers = [row[0] for row in db.execute('''SELECT name FROM sqlite_master
                WHERE type='trigger' AND tbl_name='access_memory_contributions' ''')]
            for name in triggers:
                db.execute('DROP TRIGGER "' + name.replace('"', '""') + '"')
            db.execute('''UPDATE access_memory_contributions SET original_audio=? WHERE id=?''',
                       (b'X' + payload[1:], item['id']))
            db.commit()
        with self.assertRaises(TransportError) as invalid:
            self._read('audio', edition_id, audio_source)
        self.assertEqual(invalid.exception.status, 503)
        with self.f.connection() as db:
            db.execute('''UPDATE access_memory_contributions SET original_audio=? WHERE id=?''',
                       (payload, item['id']))
            db.commit()
            access = AccessService(db, clock=lambda: self.f.now)
            editions = MemoryBookEditions(access, enabled=True)
            with access._transaction():
                member, book, children = editions._book(
                    self.seed.owner, 'family-a', self.book_id)
                row = access._one('SELECT * FROM access_memory_book_editions WHERE id=?',
                                  (edition_id,))
                _, state, bundle, verified = editions._verified_read(
                    row, 'family-a', member, book, children)
                self.assertEqual(state, 'current')
                provenance, _manuscript = verified
        with self.f.connection() as db:
            triggers = [row[0] for row in db.execute('''SELECT name FROM sqlite_master
                WHERE type='trigger' AND tbl_name='access_memory_contribution_derivations' ''')]
            for name in triggers:
                db.execute('DROP TRIGGER "' + name.replace('"', '""') + '"')
            db.execute('PRAGMA ignore_check_constraints=ON')
            db.execute('''UPDATE access_memory_contribution_derivations
                SET transcript=? WHERE contribution_id=?''', ('T' * 10000, item['id']))
            db.commit()
            access = AccessService(db, clock=lambda: self.f.now)
            sources = MemoryBookEditionSources(MemoryBookEditions(access, enabled=True),
                                               originals_enabled=True)
            with access._transaction():
                bounded, _ = sources._resolve('family-a', book, audio_source,
                    bundle, provenance)
                self.assertEqual(len(bounded['transcript'].encode('utf-8')), 8192)
                self.assertTrue(bounded['transcript_truncated'])
            db.execute('''UPDATE access_memory_contributions SET original_audio=? WHERE id=?''',
                       (b'X' * (2 * 1024 * 1024 + 1), item['id']))
            db.commit()
            with access._transaction():
                with self.assertRaises(TransportError) as oversized:
                    sources._resolve('family-a', book, audio_source, bundle,
                                     provenance, audio=True)
                self.assertEqual(oversized.exception.status, 503)
