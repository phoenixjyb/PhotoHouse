"""Protected story-title routes over migrated synthetic family storage."""
import json
import unittest

import test_library_reads as fixture
from app.main import create_app
from app.access.transport import COOKIE, csrf_token
from fastapi.testclient import TestClient


class StubSuggester:
    def __init__(self, result=None, callback=None):
        self.result = result
        self.callback = callback
        self.calls = []

    def suggest(self, bundle):
        self.calls.append(bundle)
        if self.callback is not None:
            self.callback(bundle)
        if callable(self.result):
            return self.result(bundle)
        if self.result is not None:
            return self.result
        return {
            'version': 1,
            'selection_revision': bundle['selection_revision'],
            'titles': [{'text': 'A family day', 'source_ids': [bundle['sources'][0]['id']]}],
            'needs_review': True,
        }


class StoryTitleRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.LibraryReadTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        fixture.LibraryReadTests.tearDownClass()

    def setUp(self):
        self.f = fixture.LibraryReadTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.suggester = None
        runtime = self.f.client.app.state.access_runtime
        self.client = TestClient(create_app(access_runtime=runtime),
                                  base_url='https://photohouse.test',
                                  client=('192.0.2.20', 23456))
        self.client.headers['Sec-Fetch-Site'] = 'same-origin'
        self.addCleanup(self.client.close)
        self.headers = {'Authorization': 'Bearer ' + self.f.member_token}

    def configure(self, suggester):
        runtime = self.client.app.state.access_runtime
        self.client.close()
        self.suggester = suggester
        self.client = TestClient(create_app(access_runtime=runtime,
                                            story_title_suggester=suggester),
                                 base_url='https://photohouse.test',
                                 client=('192.0.2.20', 23456))
        self.client.headers['Sec-Fetch-Site'] = 'same-origin'
        self.addCleanup(self.client.close)

    def preview(self, asset_ids='102,101', **changes):
        response = self.client.post('/story-workspace/preview?library=family-a',
            headers=self.headers,
            json={'asset_ids': asset_ids, 'theme': 'trip', 'language': 'zh',
                  'title': '', **changes})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def request_body(self, story=None, *, asset_ids='102,101', chapters=None, **changes):
        story = story or self.preview(asset_ids=asset_ids)
        if chapters is None:
            chapters = [{'id': chapter['id'], 'narration': 'User draft remains unchanged'}
                        for chapter in story['chapters']]
        return {
            'asset_ids': asset_ids,
            'theme': 'trip',
            'language': 'zh',
            'selection_revision': story['selection_revision'],
            'chapters': json.dumps(chapters, ensure_ascii=False, separators=(',', ':')),
            **changes,
        }

    def suggest(self, body=None, *, headers=None, library='family-a'):
        return self.client.post('/story-workspace/title-suggestions?library=' + library,
            headers=self.headers if headers is None else headers,
            json=body if body is not None else self.request_body())

    def test_capabilities_are_scoped_default_off_and_no_store(self):
        response = self.client.get('/story-workspace/title-capabilities?library=family-a',
                                   headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers['cache-control'], 'no-store')
        self.assertEqual(response.json(), {
            'version': 1, 'enabled': False, 'max_suggestions': 3, 'needs_review': True})
        self.assertEqual(self.client.get('/story-workspace/title-capabilities?library=family-b',
                                         headers=self.headers).status_code, 401)
        self.assertEqual(self.client.get('/story-workspace/title-capabilities?library=family-a').status_code, 401)
        disabled = self.suggest()
        self.assertEqual(disabled.status_code, 503)
        self.assertEqual(disabled.headers['cache-control'], 'no-store')

    def test_enabled_capability_and_suggestions_are_review_only(self):
        adapter = StubSuggester()
        self.configure(adapter)
        capability = self.client.get('/story-workspace/title-capabilities?library=family-a',
                                     headers=self.headers)
        self.assertEqual(capability.status_code, 200)
        self.assertTrue(capability.json()['enabled'])
        self.assertEqual(capability.headers['cache-control'], 'no-store')
        result = self.suggest()
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.headers['cache-control'], 'no-store')
        self.assertEqual(result.json()['needs_review'], True)
        self.assertEqual(result.json()['titles'][0]['text'], 'A family day')
        self.assertEqual(len(adapter.calls), 1)

    def test_permission_csrf_query_and_malformed_request_gates_precede_inference(self):
        adapter = StubSuggester()
        self.configure(adapter)
        body = self.request_body()
        self.assertEqual(self.suggest(body, library='family-b').status_code, 401)
        self.assertEqual(self.suggest(body, headers={}).status_code, 401)
        browser = { 'Cookie': COOKIE + '=' + self.f.member_token,
                    'Origin': 'https://photohouse.test', 'Sec-Fetch-Site': 'same-origin' }
        self.assertEqual(self.suggest(body, headers=browser).status_code, 403)
        browser['X-CSRF-Token'] = csrf_token(self.f.member_token)
        self.assertEqual(self.suggest(body, headers=browser).status_code, 200)
        self.assertEqual(self.suggest(body, headers=self.headers,
                                      library='family-a&library=family-b').status_code, 400)
        self.assertEqual(len(adapter.calls), 1)

        malformed = self.client.post('/story-workspace/title-suggestions?library=family-a',
            headers={**self.headers, 'Content-Type': 'application/json'},
            content='{"asset_ids":"101","asset_ids":"102"}')
        self.assertEqual(malformed.status_code, 400)
        unknown = dict(body, extra='not accepted')
        self.assertEqual(self.suggest(unknown).status_code, 400)
        wrong_type = dict(body, chapters=[])  # all wire fields must be strings
        self.assertEqual(self.suggest(wrong_type).status_code, 400)
        self.assertEqual(len(adapter.calls), 1)

    def test_chapters_must_match_current_outline_order_and_shape(self):
        adapter = StubSuggester()
        self.configure(adapter)
        story = self.preview()
        chapters = [{'id': chapter['id'], 'narration': 'draft'} for chapter in story['chapters']]
        wrong_order = list(reversed(chapters))
        if wrong_order == chapters:
            wrong_order = [{'id': 'chapter-99', 'narration': 'draft'}]
        self.assertEqual(self.suggest(self.request_body(story, chapters=wrong_order)).status_code, 400)
        wrong_shape = [{'id': chapters[0]['id'], 'narration': 'draft', 'extra': 'ignored'}]
        self.assertEqual(self.suggest(self.request_body(story, chapters=wrong_shape)).status_code, 400)
        wrong_count = chapters[:-1]
        self.assertEqual(self.suggest(self.request_body(story, chapters=wrong_count)).status_code, 400)
        too_long = [{'id': chapter['id'], 'narration': 'x' * 6001} for chapter in chapters]
        self.assertEqual(self.suggest(self.request_body(story, chapters=too_long)).status_code, 400)
        self.assertEqual(len(adapter.calls), 0)

    def test_context_contains_only_selected_evidence_and_labeled_untouched_drafts(self):
        self.f.mutate('''INSERT INTO access_stories
            (id,asset_id,library_id,author_id,revision,title,text,language,byline,created_at,updated_at,deleted)
            VALUES ('story-one',101,'family-a',?,1,'Family note title','Family original prose','zh','Family',1,1,0)''',
            (self.f.member_id,))
        adapter = StubSuggester()
        self.configure(adapter)
        story = self.preview(asset_ids='101')
        original_draft = 'Draft words from user. ' * 100
        body = self.request_body(story, asset_ids='101', chapters=[
            {'id': c['id'], 'narration': original_draft} for c in story['chapters']])
        response = self.suggest(body)
        self.assertEqual(response.status_code, 200, response.text)
        submitted = adapter.calls[0]
        self.assertEqual(set(submitted), {
            'version', 'language', 'theme', 'selection_revision', 'sources'})
        by_source = {entry['source']: entry for entry in submitted['sources']}
        self.assertEqual(by_source['family']['text'], 'Family original prose')
        self.assertEqual(by_source['ai']['text'], 'caption-101')
        self.assertEqual(by_source['draft']['text'], original_draft[:1800])
        self.assertEqual(by_source['draft']['id'], 'draft-chapter-1')
        ids = {entry['id'] for entry in submitted['sources']}
        self.assertNotIn('caption-102', ids)
        self.assertNotIn('draft-chapter-2', ids)
        with self.f.connection() as db:
            self.assertEqual(db.execute("SELECT text FROM access_stories WHERE id='story-one'").fetchone()[0],
                             'Family original prose')
            self.assertEqual(db.execute("SELECT COUNT(*) FROM access_stories WHERE id='story-one'").fetchone()[0], 1)

    def test_stale_revision_is_rejected_before_provider(self):
        adapter = StubSuggester()
        self.configure(adapter)
        body = self.request_body()
        body['selection_revision'] = '0' * 64
        response = self.suggest(body)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(len(adapter.calls), 0)

    def test_current_source_change_during_inference_returns_conflict(self):
        def change_source(_bundle):
            self.f.mutate("UPDATE captions SET text='changed caption' WHERE id=101")
        adapter = StubSuggester(callback=change_source)
        self.configure(adapter)
        response = self.suggest()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(len(adapter.calls), 1)

    def test_deletion_or_session_revocation_during_inference_returns_unauthorized(self):
        changes = [
            lambda: self.f.mutate("UPDATE assets SET status='deleted' WHERE id=101"),
            lambda: self.f.mutate('UPDATE access_sessions SET revoked=1'),
        ]
        for change in changes:
            adapter = StubSuggester(callback=lambda _bundle, change=change: change())
            self.configure(adapter)
            response = self.suggest()
            self.assertEqual(response.status_code, 401, response.text)
            self.assertEqual(len(adapter.calls), 1)
            # Restore the isolated synthetic fixture before the second scenario.
            self.f.mutate("UPDATE assets SET status='active' WHERE id=101")
            self.f.mutate('UPDATE access_sessions SET revoked=0')

    def test_invalid_adapter_output_is_sanitized_and_lock_is_released(self):
        adapter = StubSuggester(result={'version': 1, 'selection_revision': 'bad',
                                        'titles': [], 'needs_review': True})
        self.configure(adapter)
        before_notes = self.count("SELECT COUNT(*) FROM access_stories")
        self.f.trace.clear()
        rejected = self.suggest()
        self.assertEqual(rejected.status_code, 503)
        self.assertNotIn('bad', rejected.text)
        adapter.result = None
        recovered = self.suggest()
        self.assertEqual(recovered.status_code, 200, recovered.text)
        self.assertEqual(self.count("SELECT COUNT(*) FROM access_stories"), before_notes)
        self.assertFalse(any(sql.lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE'))
                             for sql in self.f.trace))

    def test_busy_lock_returns_503_without_calling_provider(self):
        adapter = StubSuggester()
        self.configure(adapter)
        lock = self.client.app.state.story_title_lock
        self.assertTrue(lock.acquire(blocking=False))
        try:
            response = self.suggest()
        finally:
            lock.release()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(len(adapter.calls), 0)

    def test_original_family_note_is_never_written_and_route_has_no_sql_writes(self):
        self.f.mutate('''INSERT INTO access_stories
            (id,asset_id,library_id,author_id,revision,title,text,language,byline,created_at,updated_at,deleted)
            VALUES ('story-immutable',101,'family-a',?,1,'Original title','Original note','zh','Family',1,1,0)''',
            (self.f.member_id,))
        adapter = StubSuggester()
        self.configure(adapter)
        before = self.count("SELECT COUNT(*) FROM access_stories")
        self.f.trace.clear()
        response = self.suggest()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.count("SELECT COUNT(*) FROM access_stories"), before)
        with self.f.connection() as db:
            self.assertEqual(db.execute("SELECT title,text FROM access_stories WHERE id='story-immutable'").fetchone(),
                             ('Original title', 'Original note'))
        self.assertFalse(any(sql.lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE'))
                             for sql in self.f.trace))

    def count(self, sql):
        with self.f.connection() as db:
            return db.execute(sql).fetchone()[0]


if __name__ == '__main__':
    unittest.main()
