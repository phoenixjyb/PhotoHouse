"""Shared family notes in reviewed stories, with generated libraries only."""
import json
import sqlite3
import threading
import unittest
import uuid
from dataclasses import replace

from fastapi.testclient import TestClient
import test_memory_groups as fixture
from app.main import create_app
from app.access.memory_books import MemoryBooks
from app.access.memory_book_editions import MemoryBookEditions
from app.access.memory_book_edition_sources import MemoryBookEditionSources
from app.access.memory_jobs import MemoryJobs, context
from app.access.memory_processing import process_job
from app.access.service import AccessService
from app.access.story_workspace import title_suggestions


class SharedMemoryEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): fixture.MemoryGroupTests.setUpClass()

    @classmethod
    def tearDownClass(cls): fixture.MemoryGroupTests.tearDownClass()

    def setUp(self):
        self.base = fixture.MemoryGroupTests()
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.f = self.base.f
        self.runtime = self.f.client.app.state.access_runtime
        self.client = TestClient(create_app(access_runtime=self.runtime,
            memory_groups_enabled=True), base_url='https://photohouse.test',
            client=('192.0.2.20', 23456))
        self.addCleanup(self.client.close)
        self.runtime = replace(self.client.app.state.access_runtime, memory_groups_enabled=True)
        self.owner = self.base.owner
        self.headers = {'Authorization': 'Bearer ' + self.owner}
        self.note = self.base.note(title='One afternoon', text='Original shared family wording.')
        self.group = self.base.save(self.owner, self.base.body(sources=self.note['id']))
        self.source_id = 'family-' + self.note['id']

    def preview(self, assets='102,101', *, client=None):
        return (client or self.client).post('/story-workspace/preview?library=family-a',
            headers=self.headers, json={'asset_ids': assets, 'theme': 'everyday',
                                        'language': 'en', 'title': 'Our afternoon'})

    def save(self, assets='102,101'):
        preview = self.preview(assets)
        self.assertEqual(preview.status_code, 200, preview.text)
        draft = preview.json()
        body = {key: draft[key] for key in ('title', 'theme', 'language', 'selection_revision')}
        body.update(asset_ids=assets, chapters=json.dumps(draft['chapters']),
                    revision='0', mutation_id=str(uuid.uuid4()))
        saved = self.client.post('/memory-stories?library=family-a',
                                 headers=self.headers, json=body)
        self.assertEqual(saved.status_code, 200, saved.text)
        return saved.json()

    def bundle(self, story, target='story'):
        with self.f.connection() as db:
            access = AccessService(db, clock=lambda: self.f.now, memory_groups_enabled=True)
            with access._transaction():
                member = access._require(self.owner, 'family-a', 'library.read')
                return context(access, 'family-a', member, target, story['id'])[:2]

    def test_preview_canonical_origin_byline_and_chapter_dedup_without_writes(self):
        self.f.trace.clear()
        response = self.preview()
        self.assertEqual(response.status_code, 200, response.text)
        draft = response.json()
        occurrences = [e for item in draft['items'] for e in item['evidence']
                       if e['id'] == self.source_id]
        self.assertEqual(len(occurrences), 2)
        self.assertEqual(occurrences[0], occurrences[1])
        self.assertEqual(occurrences[0]['origin_asset_id'], '101')
        self.assertEqual(occurrences[0]['byline'], 'A parent')
        self.assertEqual(draft['chapters'][0]['evidence_ids'].count(self.source_id), 1)
        self.assertNotIn(self.note['author_id'], response.text)
        self.assertEqual(response.headers['cache-control'], 'no-store')
        self.assertFalse(any(sql.lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE'))
                             for sql in self.f.trace))

    def test_default_off_ignores_group_notes_and_keeps_legacy_shape(self):
        response = self.preview('102', client=self.f.client)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn(self.source_id, response.text)
        own = self.preview('101', client=self.f.client).json()['items'][0]['evidence'][0]
        self.assertNotIn('origin_asset_id', own)
        self.assertNotIn('byline', own)

    def test_saved_draft_keeps_ids_and_digests_not_original_words_or_labels(self):
        saved = self.save('102')
        with self.f.connection() as db:
            rows = db.execute('SELECT content FROM access_memory_revisions WHERE story_id=?',
                              (saved['id'],)).fetchall()
        self.assertIn(self.source_id, rows[0][0])
        self.assertNotIn(self.note['text'], rows[0][0])
        self.assertNotIn('A parent', rows[0][0])
        bundle, _ = self.bundle(saved)
        source = next(s for s in bundle['sources'] if s['id'] == self.source_id)
        self.assertEqual((source['asset_id'], source['author'], source['text']),
                         ('101', 'A parent', self.note['text']))
        self.assertEqual(bundle['chapters'][0]['asset_ids'], ['102'])
        self.assertIn(self.source_id, bundle['chapters'][0]['evidence_ids'])

    def test_note_edits_refresh_words_and_invalidate_reviewed_reference(self):
        saved = self.save('102')
        _, fingerprint = self.bundle(saved)
        self.base.edit_note(self.note, revision=1, title='Edited', text='Current edited memory.')
        current = self.client.get('/memory-stories/' + saved['id'] + '?library=family-a',
                                  headers=self.headers).json()
        self.assertEqual(current['items'][0]['evidence'][0]['text'], 'Current edited memory.')
        self.assertNotIn(self.source_id, current['chapters'][0]['evidence_ids'])
        _, changed = self.bundle(saved)
        self.assertNotEqual(changed, fingerprint)

    def test_exclusion_removes_shared_source_and_old_reviewed_reference(self):
        saved = self.save('102')
        _, fingerprint = self.bundle(saved)
        self.base.save(self.owner, self.base.body(assets='101', excluded='102',
            sources=self.note['id'], revision=self.group['revision']), self.group['id'])
        current, changed = self.bundle(saved)
        self.assertNotEqual(changed, fingerprint)
        self.assertNotIn(self.source_id, [s['id'] for s in current['sources']])

    def test_group_revision_changes_snapshot_even_when_note_wording_is_unchanged(self):
        saved = self.save('102')
        _, fingerprint = self.bundle(saved)
        before = self.preview('102').json()
        self.base.save(self.owner, self.base.body(sources=self.note['id'], theme='trip',
            revision=self.group['revision']), self.group['id'])
        after = self.preview('102').json()
        self.assertEqual(before['items'], after['items'])
        self.assertNotEqual(before['selection_revision'], after['selection_revision'])
        self.assertNotEqual(self.bundle(saved)[1], fingerprint)

    def test_whole_group_invalid_after_any_member_withdrawal_or_library_move(self):
        for sql in ("UPDATE assets SET status='deleted' WHERE id=101",
                    "UPDATE access_asset_libraries SET library_id='family-b' WHERE asset_id=101"):
            with self.subTest(sql=sql):
                self.f.mutate(sql)
                response = self.preview('102')
                self.assertEqual(response.status_code, 200, response.text)
                self.assertNotIn(self.source_id, response.text)
                self.f.mutate("UPDATE assets SET status='active' WHERE id=101")
                self.f.mutate("UPDATE access_asset_libraries SET library_id='family-a' WHERE asset_id=101")

    def test_note_deletion_omits_source_and_revocation_denies_whole_request(self):
        self.base.edit_note(self.note, revision=1, title='', text='', delete=True)
        self.assertNotIn(self.source_id, self.preview('102').text)
        self.f.mutate('UPDATE access_sessions SET revoked=1')
        self.assertEqual(self.preview('102').status_code, 401)

    def test_memoir_consumes_one_original_across_two_child_stories(self):
        first, second = self.save('102'), self.save('101')
        with self.f.connection() as db:
            access = AccessService(db, clock=lambda: self.f.now, memory_groups_enabled=True)
            book = MemoryBooks(access).save(self.owner, 'family-a',
                self.base.base.body([first['id'], second['id']]))
        bundle, _ = self.bundle(book, 'book')
        self.assertEqual([s['id'] for s in bundle['sources']].count(self.source_id), 1)
        self.assertEqual(sum(self.source_id in c['evidence_ids'] for c in bundle['chapters']), 2)

    def test_reviewed_memoir_can_reopen_original_outside_selected_media(self):
        story = self.save('102')
        with self.f.connection() as db:
            db.row_factory = sqlite3.Row
            access = AccessService(db, clock=lambda: self.f.now, memory_groups_enabled=True)
            book = MemoryBooks(access).save(self.owner, 'family-a',
                self.base.base.body([story['id']]))
            job = MemoryJobs(access).narrative(self.owner, 'family-a', 'book', book['id'],
                                               '1', str(uuid.uuid4()), '')
            class Narrator:
                def narrative(_self, bundle):
                    return {'version': 1, 'title': 'Reviewed afternoon',
                        'chapters': [{'id': c['id'], 'narration': 'A family recollection.',
                                      'source_ids': [self.source_id]} for c in bundle['chapters']],
                        'questions': [], 'needs_review': True}
            self.assertEqual(process_job(db, narrator=Narrator(), clock=lambda: self.f.now,
                memory_groups_enabled=True)['state'], 'ready')
            db.row_factory = None
            editions = MemoryBookEditions(access, enabled=True)
            proposal = editions.proposal(self.owner, 'family-a', book['id'], job['id'])
            raw = json.dumps({key: proposal[key] for key in ('version', 'revision', 'job_id',
                'job_result_sha256', 'source_fingerprint', 'children', 'manuscript')} |
                {'mutation_id': str(uuid.uuid4()), 'reviewed': True}).encode()
            receipt = editions.save(self.owner, 'family-a', book['id'], raw)
            sources = MemoryBookEditionSources(editions, originals_enabled=True)
            original = sources.detail(self.owner, 'family-a', book['id'], receipt['id'], self.source_id)
            self.assertEqual(original['state'], 'current')
            self.assertEqual(original['source']['original_text'], self.note['text'])
            self.assertEqual(original['source']['byline'], 'A parent')
            self.assertEqual(original['source']['asset_id'], '101')
            self.base.save(self.owner, self.base.body(assets='101', excluded='102',
                sources=self.note['id'], revision=self.group['revision']), self.group['id'])
            stale = sources.detail(self.owner, 'family-a', book['id'], receipt['id'], self.source_id)
            self.assertEqual(stale['state'], 'source_changed')
            self.assertIsNone(stale['source'])

    def test_title_inference_receives_a_deduplicated_current_source_list(self):
        draft = self.preview().json()
        seen = []
        class Adapter:
            def suggest(_self, bundle):
                seen.extend(s['id'] for s in bundle['sources'])
                return {'version': 1, 'selection_revision': bundle['selection_revision'],
                        'titles': [{'text': 'Our afternoon', 'source_ids': [self.source_id]}],
                        'needs_review': True}
        result = title_suggestions(self.runtime, self.owner, 'family-a', {
                'asset_ids': '102,101', 'theme': 'everyday', 'language': 'en',
                'selection_revision': draft['selection_revision'],
                'chapters': json.dumps([{'id': c['id'], 'narration': ''} for c in draft['chapters']]),
            }, Adapter(), threading.Lock())
        self.assertEqual(result['titles'][0]['source_ids'], [self.source_id])
        self.assertEqual(seen.count(self.source_id), 1)
        self.assertEqual(len(set(seen)), len(seen))

    def add_asset(self, ident):
        self.f.mutate('''INSERT INTO assets(id,path,hash_sha256,status,mime)
            VALUES (?,? ,?,'active','image/jpeg')''',
            (ident, 'generated/' + str(ident), 'generated-hash-' + str(ident)))
        self.f.mutate('INSERT INTO access_asset_libraries VALUES (?,?)', (ident, 'family-a'))

    def test_overlapping_groups_dedup_identity_but_not_two_authored_notes(self):
        self.base.save(self.owner, self.base.body(sources=self.note['id']))
        second = self.base.note(title=self.note['title'], text=self.note['text'])
        self.base.save(self.owner, self.base.body(sources=second['id']))
        draft = self.preview('102').json()
        ids = [e['id'] for e in draft['items'][0]['evidence']]
        self.assertEqual(ids.count(self.source_id), 1)
        self.assertIn('family-' + second['id'], ids)
        self.assertEqual(len(set(ids)), len(ids))

    def test_source_can_support_two_chapters_and_manual_video_without_date_inference(self):
        for ident in (104, 105, 106): self.add_asset(ident)
        self.f.mutate("UPDATE assets SET mime='video/mp4',taken_at=NULL WHERE id=102")
        self.base.save(self.owner, self.base.body(assets='101,102,104,105,106',
            sources=self.note['id'], revision=self.group['revision']), self.group['id'])
        saved = self.save('102,104,105,106,101')
        bundle, _ = self.bundle(saved)
        self.assertEqual(len(bundle['chapters']), 2)
        self.assertTrue(all(self.source_id in c['evidence_ids'] for c in bundle['chapters']))
        self.assertEqual([s['id'] for s in bundle['sources']].count(self.source_id), 1)
        self.assertIsNone(saved['items'][0]['taken_at'])

    def test_excess_chapter_sources_refuse_instead_of_silently_dropping_memories(self):
        for ident in (104, 105): self.add_asset(ident)
        notes = [self.base.note(asset=101)['id'] for _ in range(8)]
        self.base.save(self.owner, self.base.body(assets='101,102,104,105',
            sources=','.join(notes), revision=self.group['revision']), self.group['id'])
        # Eight shared notes plus each asset's direct notes and captions remain
        # bounded until four additional, distinct original notes make >12 refs.
        for ident in (104, 105):
            for _ in range(2): self.base.note(asset=ident)
        response = self.preview('101,102,104,105')
        self.assertEqual(response.status_code, 422, response.text)
        self.assertNotIn('Original shared family wording.', response.text)

    def test_corrupt_optional_schema_refuses_enabled_collection(self):
        self.f.mutate('ALTER TABLE access_memory_groups ADD COLUMN unexpected TEXT')
        response = self.preview('102')
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(self.source_id, response.text)

    def test_group_change_during_provider_call_discards_output(self):
        saved = self.save('102')
        with self.f.connection() as db:
            db.row_factory = sqlite3.Row
            access = AccessService(db, clock=lambda: self.f.now, memory_groups_enabled=True)
            job = MemoryJobs(access).narrative(self.owner, 'family-a', 'story', saved['id'],
                                                '1', str(uuid.uuid4()), '')
            class Narrator:
                def narrative(_self, bundle):
                    self.assertFalse(db.in_transaction)
                    self.base.save(self.owner, self.base.body(assets='101', excluded='102',
                        sources=self.note['id'], revision=self.group['revision']), self.group['id'])
                    return {'version': 1, 'title': 'Must discard',
                        'chapters': [{'id': c['id'], 'narration': 'A proposal.',
                                      'source_ids': [self.source_id]} for c in bundle['chapters']],
                        'questions': [], 'needs_review': True}
            result = process_job(db, narrator=Narrator(), clock=lambda: self.f.now,
                                 memory_groups_enabled=True)
            self.assertEqual(result, {'id': job['id'], 'state': 'stale'})
            self.assertEqual(tuple(db.execute('SELECT output_json,error_code FROM access_memory_jobs WHERE id=?',
                                             (job['id'],)).fetchone()), (None, 'source_changed'))


if __name__ == '__main__': unittest.main()
