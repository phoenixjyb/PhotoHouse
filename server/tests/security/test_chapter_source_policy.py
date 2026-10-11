"""Explicit chapter source choices over generated protected storage."""
import json
import sqlite3
import threading
import unittest
import uuid

import test_shared_memory_evidence as fixture
from app.access.memory_jobs import context
from app.access.memory_stories import SOURCE_POLICY
from app.access.service import AccessService
from app.access.story_workspace import title_suggestions
from app.access.transport import COOKIE, csrf_token, TransportError


class ChapterSourcePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): fixture.SharedMemoryEvidenceTests.setUpClass()
    @classmethod
    def tearDownClass(cls): fixture.SharedMemoryEvidenceTests.tearDownClass()

    def setUp(self):
        self.f = fixture.SharedMemoryEvidenceTests(); self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.client, self.headers = self.f.client, self.f.headers

    def body(self, assets='102,101', refs=None):
        draft = self.f.preview(assets).json()
        for chapter in draft['chapters']:
            chapter['narration'] = ''
        if refs is not None:
            draft['chapters'][0]['evidence_ids'] = refs
        return {key: draft[key] for key in ('title', 'theme', 'language', 'selection_revision')} | {
            'asset_ids': assets, 'chapters': json.dumps(draft['chapters']),
            'mutation_id': str(uuid.uuid4()), 'revision': '0', 'source_policy': SOURCE_POLICY}

    def save(self, body, ident=None, review=True, headers=None, extra=''):
        url = '/memory-stories' + ('/' + ident if ident else '') + '?library=family-a'
        if review: url += '&source_review=1'
        return self.client.request('PUT' if ident else 'POST', url + extra,
            headers=self.headers if headers is None else headers, json=body)

    def get(self, ident, review=True):
        return self.client.get('/memory-stories/' + ident + '?library=family-a' +
            ('&source_review=1' if review else ''), headers=self.headers)

    def bundle(self, saved): return self.f.bundle(saved)[0]

    def test_capability_is_authorized_exact_closed_and_has_no_store(self):
        path = '/story-workspace/source-capabilities?library=family-a'
        result = self.client.get(path, headers=self.headers)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json(), {'version': 1, 'source_policy': SOURCE_POLICY,
            'max_sources_per_chapter': 12, 'needs_review': True})
        self.assertEqual(result.headers['cache-control'], 'no-store')
        self.assertEqual(self.client.get(path).status_code, 401)
        self.assertEqual(self.client.get(path.replace('family-a', 'family-b'), headers=self.headers).status_code, 401)
        self.assertEqual(self.client.get(path + '&extra=1', headers=self.headers).status_code, 400)
        self.assertEqual(self.client.post(path, headers=self.headers, json={}).status_code, 403)
        self.assertEqual(self.client.get(path.replace('source-capabilities', 'source-capabilities/extra'), headers=self.headers).status_code, 403)

    def test_subset_and_empty_are_saved_without_source_text_and_honored_by_context(self):
        for refs in ([self.f.source_id], []):
            with self.subTest(refs=refs):
                body = self.body(refs=refs); response = self.save(body)
                self.assertEqual(response.status_code, 200, response.text)
                saved = response.json()
                self.assertEqual(saved['source_policy'], SOURCE_POLICY)
                self.assertEqual(saved['chapters'][0]['evidence_ids'], refs)
                self.assertEqual(self.get(saved['id']).json()['chapters'][0]['evidence_ids'], refs)
                bundle = self.bundle(saved)
                self.assertEqual([s['id'] for s in bundle['sources']], refs)
                self.assertEqual(bundle['chapters'][0]['evidence_ids'], refs)
                with self.f.f.connection() as db:
                    raw = db.execute('SELECT content FROM access_memory_stories WHERE id=?', (saved['id'],)).fetchone()[0]
                self.assertNotIn(self.f.note['text'], raw)
                self.assertNotIn('A parent', raw)
                self.assertEqual(self.save(body).json()['id'], saved['id'])

    def test_legacy_wire_and_prompt_behavior_remain_compatible(self):
        body = self.body(refs=[]); body.pop('source_policy')
        result = self.save(body, review=False)
        self.assertEqual(result.status_code, 200, result.text)
        saved = result.json()
        self.assertNotIn('source_policy', saved)
        self.assertIsNone(self.get(saved['id']).json()['source_policy'])
        self.assertNotIn('source_policy', self.get(saved['id'], review=False).json())
        self.assertIn(self.f.source_id, [s['id'] for s in self.bundle(saved)['sources']])

    def test_legacy_edit_preserves_policy_but_cannot_reinclude_sources(self):
        body = self.body(refs=[]); saved = self.save(body).json()
        edit = body | {'revision': '1', 'mutation_id': str(uuid.uuid4()), 'title': 'Edited narration'}
        edit.pop('source_policy')
        result = self.save(edit, saved['id'], review=False)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertNotIn('source_policy', result.json())
        self.assertEqual(self.get(saved['id']).json()['source_policy'], SOURCE_POLICY)
        self.assertEqual(self.bundle(saved)['sources'], [])
        chapters = json.loads(edit['chapters']); chapters[0]['evidence_ids'] = [self.f.source_id]
        changed = edit | {'revision': '2', 'mutation_id': str(uuid.uuid4()), 'chapters': json.dumps(chapters)}
        self.assertEqual(self.save(changed, saved['id'], review=False).status_code, 409)
        self.assertEqual(self.get(saved['id']).json()['chapters'][0]['evidence_ids'], [])
        reviewed = changed | {'source_policy': SOURCE_POLICY}
        self.assertEqual(self.save(reviewed, saved['id']).status_code, 200)
        self.assertEqual([s['id'] for s in self.bundle(saved)['sources']], [self.f.source_id])

    def test_changed_note_is_not_silently_reselected_and_new_edit_needs_current_revision(self):
        body = self.body(refs=[self.f.source_id]); saved = self.save(body).json()
        self.f.base.edit_note(self.f.note, revision=1, title='Changed', text='Replacement words')
        current = self.get(saved['id']).json()
        self.assertEqual(current['chapters'][0]['evidence_ids'], [])
        self.assertNotIn(self.f.source_id, [s['id'] for s in self.bundle(saved)['sources']])
        self.assertEqual(self.save(body | {'revision': '1', 'mutation_id': str(uuid.uuid4())}, saved['id']).status_code, 409)

    def test_profile_shape_query_ids_csrf_and_revocation_are_closed(self):
        body = self.body()
        self.assertEqual(self.save(body, review=False).status_code, 400)
        missing = dict(body); missing.pop('source_policy')
        self.assertEqual(self.save(missing).status_code, 400)
        for policy in ('', 'all', 'chapter_sources_v2'):
            self.assertEqual(self.save(body | {'source_policy': policy}).status_code, 400)
        for extra in ('&source_review=0', '&source_review=1', '&extra=1'):
            self.assertEqual(self.save(body, extra=extra).status_code, 400)
        for refs in (['caption-201'], [self.f.source_id, self.f.source_id], ['unknown']):
            self.assertEqual(self.save(self.body(refs=refs)).status_code, 422)
        cookie = {'Cookie': COOKIE + '=' + self.f.owner, 'Origin': 'https://photohouse.test'}
        self.assertEqual(self.save(body, headers=cookie).status_code, 403)
        cookie['X-CSRF-Token'] = csrf_token(self.f.owner)
        saved = self.save(body, headers=cookie)
        self.assertEqual(saved.status_code, 200, saved.text)
        self.f.f.mutate('UPDATE access_sessions SET revoked=1')
        self.assertEqual(self.get(saved.json()['id']).status_code, 401)

    def test_unknown_stored_policy_cannot_revert_to_all_evidence(self):
        saved = self.save(self.body(refs=[])).json()
        with self.f.f.connection() as db:
            raw = json.loads(db.execute('SELECT content FROM access_memory_stories WHERE id=?', (saved['id'],)).fetchone()[0])
            raw['source_policy'] = 'unknown'
            db.execute('UPDATE access_memory_stories SET content=? WHERE id=?', (json.dumps(raw), saved['id'])); db.commit()
        self.assertEqual(self.get(saved['id']).status_code, 503)
        with self.assertRaises(TransportError): self.bundle(saved)

    def test_sources_do_not_cross_chapters_or_memoir_children(self):
        from app.access.memory_books import MemoryBooks
        with self.f.f.connection() as db:
            db.execute("UPDATE assets SET status='active' WHERE id=103")
            for ident in (104, 105):
                db.execute('''INSERT INTO assets(id,path,hash_sha256,status,mime,width,height)
                    VALUES (?,?,?,'active','image/jpeg',640,480)''',
                    (ident, f'synthetic/{ident}.jpg', f'synthetic-hash-{ident}'))
                db.execute("INSERT INTO access_asset_libraries VALUES (?,'family-a')", (ident,))
                db.execute("INSERT INTO captions(id,asset_id,text,model,user_edited,superseded) VALUES (?,?,?,'synthetic',0,0)",
                           (ident, ident, 'Caption ' + str(ident)))
            db.commit()
        body = self.body('101,102,103,104,105')
        chapters = json.loads(body['chapters'])
        chapters[0]['evidence_ids'] = []
        chapters[1]['evidence_ids'] = ['caption-105']
        body['chapters'] = json.dumps(chapters)
        response = self.save(body)
        self.assertEqual(response.status_code, 200, response.text)
        saved = response.json(); bundle = self.bundle(saved)
        self.assertEqual([s['id'] for s in bundle['sources']], ['caption-105'])
        self.assertEqual([c['evidence_ids'] for c in bundle['chapters']], [[], ['caption-105']])
        chapters[0]['evidence_ids'] = ['caption-105']
        self.assertEqual(self.save(body | {'chapters': json.dumps(chapters), 'mutation_id': str(uuid.uuid4())}).status_code, 422)
        shared = self.save(self.body('102', refs=[self.f.source_id])).json()
        with self.f.f.connection() as db:
            access = AccessService(db, clock=lambda: self.f.f.now, memory_groups_enabled=True)
            book = MemoryBooks(access).save(self.f.owner, 'family-a', {
                'title': 'Two stories', 'language': 'en', 'introduction': '',
                'story_ids': saved['id'] + ',' + shared['id'], 'revision': '0', 'mutation_id': str(uuid.uuid4())})
        combined = self.f.bundle(book, 'book')[0]
        self.assertEqual(combined['chapters'][0]['evidence_ids'], [])
        self.assertEqual(combined['chapters'][-1]['evidence_ids'], [self.f.source_id])

    def test_editorial_words_are_separate_from_item_source_choices(self):
        body = self.body(refs=[]); chapters = json.loads(body['chapters'])
        chapters[0]['narration'] = 'Our own editorial wording.'
        response = self.save(body | {'chapters': json.dumps(chapters)})
        self.assertEqual(response.status_code, 200, response.text)
        bundle = self.bundle(response.json())
        self.assertEqual([(s['kind'], s['text']) for s in bundle['sources']],
                         [('editorial', 'Our own editorial wording.')])

    def title(self, refs, *, review=True, callback=None):
        draft = self.f.preview().json(); calls = []
        class Adapter:
            def suggest(self, bundle):
                calls.append(bundle)
                if callback: callback()
                return {'version': 1, 'selection_revision': bundle['selection_revision'],
                        'titles': [], 'needs_review': True}
        chapter = {'id': draft['chapters'][0]['id'], 'narration': ''}
        if review: chapter['evidence_ids'] = refs
        body = {key: draft[key] for key in ('theme', 'language', 'selection_revision')} | {
            'asset_ids': '102,101', 'chapters': json.dumps([chapter])}
        if review: body['source_policy'] = SOURCE_POLICY
        result = title_suggestions(self.f.runtime, self.f.owner, 'family-a', body, Adapter(), threading.Lock(), review)
        return result, calls

    def test_title_context_honors_subset_empty_and_legacy_while_shared_source_is_once(self):
        for refs in ([self.f.source_id], []):
            _, calls = self.title(refs)
            self.assertEqual([s['id'] for s in calls[0]['sources']], refs)
        _, legacy = self.title([], review=False)
        self.assertIn(self.f.source_id, [s['id'] for s in legacy[0]['sources']])
        self.assertEqual([s['id'] for s in legacy[0]['sources']].count(self.f.source_id), 1)
        with self.assertRaises(TransportError) as invalid: self.title(['caption-201'])
        self.assertEqual(invalid.exception.status, 400)

    def test_title_changed_reference_recheck_refuses_result(self):
        with self.assertRaises(TransportError) as stale:
            self.title([self.f.source_id], callback=lambda: self.f.base.edit_note(
                self.f.note, revision=1, title='Changed', text='Changed during provider'))
        self.assertEqual(stale.exception.status, 409)

    def test_http_title_profile_is_closed_and_authorized_before_provider(self):
        from test_story_title_routes import StubSuggester
        adapter = StubSuggester(result=lambda bundle: {
            'version': 1, 'selection_revision': bundle['selection_revision'],
            'titles': [], 'needs_review': True})
        self.client.app.state.story_title_suggester = adapter
        body = self.body(refs=[])
        chapters = [{'id': c['id'], 'narration': c['narration'], 'evidence_ids': c['evidence_ids']}
                    for c in json.loads(body['chapters'])]
        body = {key: body[key] for key in ('asset_ids', 'theme', 'language', 'selection_revision', 'source_policy')} | {
            'chapters': json.dumps(chapters)}
        path = '/story-workspace/title-suggestions?library=family-a&source_review=1'
        response = self.client.post(path, headers=self.headers, json=body)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(adapter.calls[0]['sources'], [])
        self.assertEqual(self.client.post(path, json=body).status_code, 401)
        self.assertEqual(self.client.post(path.replace('family-a', 'family-b'), headers=self.headers, json=body).status_code, 401)
        self.assertEqual(self.client.post(path + '&source_review=1', headers=self.headers, json=body).status_code, 400)
        self.assertEqual(self.client.post(path.replace('&source_review=1', ''), headers=self.headers, json=body).status_code, 400)
        self.assertEqual(self.client.post(path, headers=self.headers, json=body | {'source_policy': 'unknown'}).status_code, 400)
        self.assertEqual(len(adapter.calls), 1)

    def test_running_job_discards_output_after_source_choice_edit(self):
        from app.access.memory_jobs import MemoryJobs
        from app.access.memory_processing import process_job
        body = self.body(refs=[self.f.source_id]); saved = self.save(body).json()
        with self.f.f.connection() as db:
            db.row_factory = sqlite3.Row
            access = AccessService(db, clock=lambda: self.f.f.now, memory_groups_enabled=True)
            queued = MemoryJobs(access).narrative(self.f.owner, 'family-a', 'story', saved['id'],
                '1', str(uuid.uuid4()), '')
        class Narrator:
            def narrative(inner, bundle):
                self.assertEqual([s['id'] for s in bundle['sources']], [self.f.source_id])
                edit = self.body(refs=[]) | {'revision': '1', 'mutation_id': str(uuid.uuid4())}
                changed = self.save(edit, saved['id'])
                self.assertEqual(changed.status_code, 200, changed.text)
                return {'version': 1, 'title': 'Discard this old proposal',
                    'chapters': [{'id': bundle['chapters'][0]['id'], 'narration': 'Older words',
                                  'source_ids': [self.f.source_id]}],
                    'questions': [], 'needs_review': True}
        with self.f.f.connection() as db:
            db.row_factory = sqlite3.Row
            result = process_job(db, narrator=Narrator(), clock=lambda: self.f.f.now,
                                 memory_groups_enabled=True)
            row = db.execute('SELECT state,output_json FROM access_memory_jobs WHERE id=?', (queued['id'],)).fetchone()
        self.assertEqual(result['state'], 'stale')
        self.assertEqual((row['state'], row['output_json']), ('stale', None))


if __name__ == '__main__': unittest.main()
