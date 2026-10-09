"""Actual protected story workspace HTTP on fully migrated synthetic storage."""
import json
import unittest
import uuid

import test_library_reads as fixture
from app.access.transport import COOKIE, csrf_token


class StoryWorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): fixture.LibraryReadTests.setUpClass()
    @classmethod
    def tearDownClass(cls): fixture.LibraryReadTests.tearDownClass()

    def setUp(self):
        self.f = fixture.LibraryReadTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.client = self.f.client
        self.headers = {'Authorization': 'Bearer ' + self.f.member_token}

    def preview(self, headers=None, library='family-a', **changes):
        return self.client.post('/story-workspace/preview?library=' + library,
            headers=self.headers if headers is None else headers,
            json={'asset_ids': '102,101', 'theme': 'trip', 'language': 'zh',
                  'title': '我们的片段', **changes})

    def test_order_sources_and_read_only_draft(self):
        story = str(uuid.uuid4())
        self.f.mutate('''INSERT INTO access_stories
            (id,asset_id,library_id,author_id,revision,title,text,language,byline,created_at,updated_at,deleted)
            VALUES (?,101,'family-a',?,1,'家人的话','这天我们一起散步。','zh','家人',1,1,0)''',
            (story, self.f.member_id))
        self.f.trace.clear()
        response = self.preview()
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(response.headers['cache-control'], 'no-store')
        self.assertEqual([i['id'] for i in result['items']], ['102', '101'])
        self.assertEqual(result['chapters'][0]['asset_ids'], ['102', '101'])
        self.assertFalse(result['saved'])
        self.assertTrue(result['needs_review'])
        sources = result['items'][1]['evidence']
        self.assertEqual(sources[0]['source'], 'family')
        self.assertEqual(sources[0]['text'], '这天我们一起散步。')
        self.assertEqual(sources[1]['source'], 'ai')
        self.assertNotIn('private-', response.text)
        self.assertNotIn('old-hidden', response.text)
        self.assertNotIn('一起散步', result['chapters'][0]['narration'])
        self.assertFalse(any(s.lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE'))
                             for s in self.f.trace))

    def test_whole_selection_denied_when_any_item_is_foreign_deleted_or_unmapped(self):
        for ident in ('201', '103', '999', '777'):
            r = self.preview(asset_ids='101,' + ident)
            self.assertEqual(r.status_code, 401)
            self.assertNotIn('caption-101', r.text)
        self.assertEqual(self.preview(library='family-b').status_code, 401)
        self.assertEqual(self.preview(headers={}).status_code, 401)
        self.f.mutate('UPDATE access_sessions SET revoked=1 WHERE digest IN (SELECT digest FROM access_sessions)')
        self.assertEqual(self.preview().status_code, 401)

    def test_browser_csrf_and_closed_routes(self):
        headers = {'Cookie': COOKIE + '=' + self.f.member_token, 'Origin': 'https://photohouse.test'}
        self.assertEqual(self.preview(headers=headers).status_code, 403)
        headers['X-CSRF-Token'] = csrf_token(self.f.member_token)
        self.assertEqual(self.preview(headers=headers).status_code, 200)
        self.assertEqual(self.client.get('/story-workspace/preview?library=family-a', headers=self.headers).status_code, 403)
        self.assertEqual(self.client.post('/story-workspace/preview/extra', headers=self.headers).status_code, 403)

    def test_validation_bounds_and_literal_text(self):
        for changes in ({'asset_ids': ''}, {'asset_ids': '101,101'}, {'asset_ids': '101,0101'},
                        {'asset_ids': ','.join(str(i) for i in range(1, 26))},
                        {'theme': 'unknown'}, {'language': 'mixed'}, {'title': 'x'*161}):
            self.assertEqual(self.preview(**changes).status_code, 400)
        r = self.preview(title='<img src=x onerror=alert(1)>')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['title'], '<img src=x onerror=alert(1)>')
        self.assertEqual(self.preview(title='😀'*160).status_code, 200)
        raw = '{"asset_ids":"101","theme":"trip","language":"zh","title":"a","title":"b"}'
        self.assertEqual(self.client.post('/story-workspace/preview?library=family-a',
            content=raw, headers={**self.headers, 'Content-Type':'application/json'}).status_code, 400)

    def test_video_and_date_provenance_remain_visible(self):
        self.f.mutate("UPDATE assets SET mime='video/mp4',taken_at=NULL,path='mmexport1758585600000.mp4' WHERE id=102")
        item = self.preview().json()['items'][0]
        self.assertEqual(item['kind'], 'video')
        self.assertIsNone(item['taken_at'])
        self.assertEqual(item['date_hint']['source'], 'filename')


if __name__ == '__main__': unittest.main()
