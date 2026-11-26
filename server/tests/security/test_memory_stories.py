"""Saved story journey against real protected HTTP and migrated synthetic SQLite."""
import json
import unittest
import uuid

import test_library_reads as fixture
from app.access.transport import COOKIE, csrf_token


class MemoryStoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): fixture.LibraryReadTests.setUpClass()
    @classmethod
    def tearDownClass(cls): fixture.LibraryReadTests.tearDownClass()

    def setUp(self):
        self.f = fixture.LibraryReadTests(); self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.client = self.f.client
        self.headers = {'Authorization': 'Bearer '+self.f.owner_token}

    def preview(self):
        r = self.client.post('/story-workspace/preview?library=family-a', headers=self.headers,
            json={'asset_ids':'102,101','title':'湖边的一天','theme':'trip','language':'zh'})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def body(self):
        draft = self.preview()
        draft['chapters'][0]['narration'] = '这段回忆由家人讲述。\n保留我们的语气。'
        return {'title':draft['title'],'theme':draft['theme'],'language':'zh',
            'asset_ids':','.join(i['id'] for i in draft['items']), 'chapters':json.dumps(draft['chapters']),
            'selection_revision':draft['selection_revision'],'revision':'0','mutation_id':str(uuid.uuid4())}

    def save(self, body=None, ident=None, headers=None):
        url = '/memory-stories'+('/'+ident if ident else '')+'?library=family-a'
        return self.client.request('PUT' if ident else 'POST', url,
            headers=self.headers if headers is None else headers, json=body or self.body())

    def get(self, path='/memory-stories?library=family-a', headers=None):
        return self.client.get(path, headers=self.headers if headers is None else headers)

    def test_save_reopen_edit_and_same_mutation_retry(self):
        body = self.body(); response = self.save(body)
        self.assertEqual(response.status_code, 200, response.text)
        saved = response.json(); ident = saved['id']
        self.assertTrue(saved['saved']); self.assertEqual(saved['revision'], '1')
        self.assertEqual(response.headers['cache-control'], 'no-store')
        self.assertEqual(self.save(body).json()['id'], ident)
        self.assertEqual(self.get().json()['items'][0]['id'], ident)
        reopened = self.get('/memory-stories/'+ident+'?library=family-a').json()
        self.assertEqual(reopened['chapters'][0]['narration'], '这段回忆由家人讲述。\n保留我们的语气。')
        edit = {**body,'revision':'1','mutation_id':str(uuid.uuid4()),'title':'我们的故事'}
        edited = self.save(edit, ident)
        self.assertEqual(edited.status_code, 200, edited.text)
        self.assertEqual(edited.json()['revision'], '2')
        self.assertEqual(self.save(edit, ident).json()['revision'], '2')
        self.assertEqual(self.save({**edit,'title':'复用标识'}, ident).status_code, 409)

    def test_full_story_keeps_mixed_media_order_across_save_and_reopen(self):
        asset_ids = list(range(1001, 1049))
        order = asset_ids[1::2] + asset_ids[::2][::-1]
        with self.f.connection() as db:
            db.executemany("""INSERT INTO assets(id,path,hash_sha256,status,mime,width,height)
                VALUES(?,?,?,'active',?,400,300)""",
                [(ident, f'synthetic/{ident}', f'fixture-{ident}',
                  'video/mp4' if ident % 7 == 0 else 'image/jpeg') for ident in asset_ids])
            db.executemany('INSERT INTO access_asset_libraries VALUES (?,?)',
                           [(ident, 'family-a') for ident in asset_ids])
            db.commit()
        selection = {'asset_ids': ','.join(map(str, order)), 'theme': 'everyday',
                     'language': 'en', 'title': 'Synthetic family story'}
        preview = self.client.post('/story-workspace/preview?library=family-a',
                                   headers=self.headers, json=selection)
        self.assertEqual(preview.status_code, 200, preview.text)
        draft = preview.json()
        expected = list(map(str, order))
        expected_chapters = [expected[start:start + 4] for start in range(0, 48, 4)]
        self.assertEqual([chapter['asset_ids'] for chapter in draft['chapters']], expected_chapters)
        self.assertEqual({item['kind'] for item in draft['items']}, {'image', 'video'})

        saved = self.save({**selection, 'chapters': json.dumps(draft['chapters']),
                           'selection_revision': draft['selection_revision'], 'revision': '0',
                           'mutation_id': str(uuid.uuid4())})
        self.assertEqual(saved.status_code, 200, saved.text)
        story_id = saved.json()['id']
        reopened = self.get(f'/memory-stories/{story_id}?library=family-a')
        self.assertEqual(reopened.status_code, 200, reopened.text)
        result = reopened.json()
        self.assertEqual([item['id'] for item in result['items']], expected)
        self.assertEqual([chapter['id'] for chapter in result['chapters']],
                         [f'chapter-{ordinal}' for ordinal in range(1, 13)])
        self.assertEqual([chapter['asset_ids'] for chapter in result['chapters']], expected_chapters)

        self.f.mutate("UPDATE assets SET status='deleted' WHERE id=?", (order[-1],))
        self.assertEqual(self.get(f'/memory-stories/{story_id}?library=family-a').status_code, 401)

    def test_viewer_can_read_but_not_create_or_edit(self):
        saved = self.save().json()
        member = {'Authorization':'Bearer '+self.f.member_token}
        self.assertFalse(self.get(headers=member).json()['can_create'])
        read = self.get('/memory-stories/'+saved['id']+'?library=family-a', member)
        self.assertEqual(read.status_code, 200); self.assertFalse(read.json()['can_edit'])
        self.assertEqual(self.save(headers=member).status_code, 401)
        self.assertEqual(self.save({**self.body(),'revision':'1'}, saved['id'], member).status_code, 401)

    def test_contributor_owns_only_its_own_drafts(self):
        self.f.mutate("UPDATE access_memberships SET role='contributor' WHERE account_id=?", (self.f.member_id,))
        member = {'Authorization':'Bearer '+self.f.member_token}
        owner_story = self.save().json()
        self.assertEqual(self.save({**self.body(),'revision':'1'}, owner_story['id'], member).status_code, 401)
        body = self.body(); own = self.save(body, headers=member)
        self.assertEqual(own.status_code, 200, own.text)
        self.assertTrue(own.json()['can_edit'])
        self.assertEqual(self.save({**body,'revision':'1','mutation_id':str(uuid.uuid4())},own.json()['id'],member).status_code,200)

    def test_moved_deleted_and_foreign_assets_hide_entire_story(self):
        body = self.body(); saved = self.save(body).json(); ident = saved['id']
        for statement in ("UPDATE assets SET status='deleted' WHERE id=101",
                          "UPDATE access_asset_libraries SET library_id='family-b' WHERE asset_id=101"):
            self.f.mutate(statement)
            self.assertEqual(self.get().json()['items'], [])
            self.assertEqual(self.get('/memory-stories/'+ident+'?library=family-a').status_code,401)
            self.assertEqual(self.save(body).status_code,401)
            self.f.mutate("UPDATE assets SET status='active' WHERE id=101")
            self.f.mutate("UPDATE access_asset_libraries SET library_id='family-a' WHERE asset_id=101")
        self.assertEqual(self.get('/memory-stories/'+ident+'?library=family-b').status_code,401)
        self.assertEqual(self.get(headers={}).status_code,401)

    def test_conflicts_preserve_saved_text_and_immutable_revisions(self):
        body = self.body(); saved = self.save(body).json(); ident = saved['id']
        edit = {**body,'revision':'1','title':'新标题','mutation_id':str(uuid.uuid4())}
        self.assertEqual(self.save(edit, ident).status_code,200)
        self.assertEqual(self.save({**edit,'title':'过期编辑','mutation_id':str(uuid.uuid4())}, ident).status_code,409)
        self.f.mutate("UPDATE captions SET text='new source' WHERE id=101")
        self.assertEqual(self.save({**body,'mutation_id':str(uuid.uuid4())}).status_code,409)
        current = self.get('/memory-stories/'+ident+'?library=family-a').json()
        self.assertEqual(current['title'],'新标题')
        self.assertEqual(current['items'][1]['evidence'][0]['text'],'new source')
        self.assertNotIn('caption-101',current['chapters'][0]['evidence_ids'])

    def test_pagination_filters_unavailable_stories_before_page_boundaries(self):
        body = self.body()
        for _ in range(9):
            self.assertEqual(self.save(body | {'mutation_id':str(uuid.uuid4())}).status_code,200)
        first=self.get().json(); second=self.get('/memory-stories?library=family-a&page=2').json()
        self.assertEqual(len(first['items']),8); self.assertTrue(first['has_more'])
        self.assertEqual(len(second['items']),1); self.assertFalse(second['has_more'])
        self.f.mutate("DELETE FROM access_asset_libraries WHERE asset_id=101")
        hidden=self.get().json()
        self.assertEqual(hidden['items'],[]); self.assertFalse(hidden['has_more'])

    def test_legacy_c4_keeps_library_access_but_refuses_saved_story_storage(self):
        self.f.mutate('DROP TABLE access_memory_revisions')
        self.f.mutate('DROP TABLE access_memory_stories')
        self.assertEqual(self.get().status_code,503)
        self.assertEqual(self.get(headers={}).status_code,401)
        self.assertEqual(self.get('/assets?library=family-a').status_code,200)

    def test_theme_filter_applies_to_entire_authorized_shelf_before_pagination(self):
        body = self.body()
        trip_ids = set()
        for index in range(9):
            saved = self.save(body | {'title':f'Trip {index}', 'mutation_id':str(uuid.uuid4())})
            self.assertEqual(saved.status_code, 200, saved.text)
            trip_ids.add(saved.json()['id'])
        for index in range(3):
            self.assertEqual(self.save(body | {'theme':'everyday', 'title':f'Trip diary {index}',
                'mutation_id':str(uuid.uuid4())}).status_code, 200)
        first = self.get('/memory-stories?library=family-a&theme=trip').json()
        second = self.get('/memory-stories?library=family-a&theme=trip&page=2').json()
        self.assertEqual(len(first['items']), 8)
        self.assertTrue(first['has_more'])
        self.assertEqual(len(second['items']), 1)
        self.assertFalse(second['has_more'])
        self.assertEqual({r['id'] for r in first['items']+second['items']}, trip_ids)
        self.assertTrue(all(r['theme']=='trip' for r in first['items']+second['items']))
        days = self.get('/memory-stories?library=family-a&theme=everyday').json()
        self.assertEqual(len(days['items']), 3)
        self.assertFalse(days['has_more'])
        self.assertEqual(set(days), set(first), 'optional theme keeps the existing response contract')
        self.assertEqual(self.get('/memory-stories?library=family-a&theme=birthday').json()['items'], [])
        pages = [self.client.post('/memory-stories/search?library=family-a',
                    headers=self.headers, json={'theme':'trip','title_query':' tRiP ','page':str(page)})
                 for page in (1, 2)]
        self.assertTrue(all(response.status_code == 200 for response in pages))
        self.assertEqual([response.json() for response in pages], [first, second])
        viewer = self.get('/memory-stories?library=family-a&theme=trip',
            {'Authorization':'Bearer '+self.f.member_token}).json()
        self.assertFalse(viewer['can_create'])
        self.assertEqual({r['id'] for r in viewer['items']}, {r['id'] for r in first['items']})
        self.f.mutate("DELETE FROM access_asset_libraries WHERE asset_id=101")
        hidden = self.get('/memory-stories?library=family-a&theme=trip').json()
        self.assertEqual(hidden['items'], [])
        self.assertFalse(hidden['has_more'])

    def test_theme_query_is_closed_and_requires_current_library_authorization(self):
        for value in ('', 'unknown', 'Trip', "trip' OR 1=1 --"):
            self.assertEqual(self.get('/memory-stories?library=family-a&theme='+value).status_code,400)
        self.assertEqual(self.get('/memory-stories?library=family-a&theme=trip&theme=everyday').status_code,400)
        self.assertEqual(self.get('/memory-stories?library=family-a&theme=trip&extra=1').status_code,400)
        self.assertEqual(self.get('/memory-stories?library=family-a&theme=trip', {}).status_code,401)
        self.assertEqual(self.get('/memory-stories?library=family-b&theme=trip').status_code,401)
        self.assertEqual(self.get('/memory-stories?library=family-a&theme=trip',
            self.headers | {'Origin':'https://foreign.test'}).status_code,403)
        self.f.mutate("UPDATE access_memberships SET status='revoked' WHERE account_id=?",(self.f.member_id,))
        self.assertEqual(self.get('/memory-stories?library=family-a&theme=trip',
            {'Authorization':'Bearer '+self.f.member_token}).status_code,401)

    def test_title_search_uses_literal_titles_and_current_private_scope(self):
        saved = self.save(self.body() | {'title':'湖边晚餐 100%'}).json()
        capability = self.get(headers=self.headers | {'X-PhotoHouse-Story-Shelf-Version':'1'}).json()
        self.assertIs(capability['title_search'], True)
        self.assertNotIn('title_search', self.get().json())
        url = '/memory-stories/search?library=family-a'
        member = {'Cookie':COOKIE+'='+self.f.member_token, 'Origin':'https://photohouse.test'}
        body = {'title_query':'湖边晚餐', 'page':'1'}
        self.assertEqual(self.client.post(url, headers=member, json=body).status_code,403)
        member['X-CSRF-Token'] = csrf_token(self.f.member_token)
        for query in ('湖边晚餐', '100%', ' % '):
            result = self.client.post(url, headers=member, json=body | {'title_query':query})
            self.assertEqual(result.status_code,200)
            self.assertEqual(result.headers['cache-control'],'no-store')
            self.assertEqual([story['id'] for story in result.json()['items']], [saved['id']])
            self.assertFalse(result.json()['can_create'])
        for query in ('_', '家人讲述', 'absent'):
            result = self.client.post(url, headers=member, json=body | {'title_query':query})
            self.assertEqual(result.json()['items'], [])
        for query in ('', 'a\n', '字'*161, 9):
            self.assertEqual(self.client.post(url, headers=member,
                json=body | {'title_query':query}).status_code,400)
        self.assertEqual(self.client.post(url+'&title_query=only-in-body', headers=member, json=body).status_code,400)
        self.assertEqual(self.client.post(url.replace('family-a','family-b'), headers=member, json=body).status_code,401)
        self.f.mutate("DELETE FROM access_asset_libraries WHERE asset_id=101")
        self.assertEqual(self.client.post(url, headers=member, json=body).json()['items'], [])
        self.f.mutate("UPDATE access_memberships SET status='revoked' WHERE account_id=?",(self.f.member_id,))
        self.assertEqual(self.client.post(url, headers=member, json=body).status_code,401)

    def test_structure_sources_unicode_and_body_validation(self):
        body = self.body(); chapters = json.loads(body['chapters'])
        for change in ({'asset_ids':['101','102']},{'asset_ids':['102','201']},
                       {'evidence_ids':['caption-201']},{'narration':'字'*2001},
                       {'title':'x'*161},{'narration':'bad\u0000'}):
            altered = [chapters[0] | change]
            self.assertEqual(self.save(body | {'chapters':json.dumps(altered)}).status_code,422)
        self.assertEqual(self.save(body | {'chapters':'[{"id":"a","id":"b"}]'}).status_code,422)
        self.assertEqual(self.save(body | {'extra':'field'}).status_code,400)
        unicode_body = body | {'title':'😀'*160}
        self.assertEqual(self.save(unicode_body).status_code,200)

    def test_cookie_csrf_closed_routes_and_revocation(self):
        cookie = {'Cookie':COOKIE+'='+self.f.owner_token,'Origin':'https://photohouse.test'}
        body = self.body()
        self.assertEqual(self.save(body, headers=cookie).status_code,403)
        cookie['X-CSRF-Token'] = csrf_token(self.f.owner_token)
        saved = self.save(body, headers=cookie)
        self.assertEqual(saved.status_code,200,saved.text)
        self.assertEqual(self.client.delete('/memory-stories/'+saved.json()['id']+'?library=family-a',headers=cookie).status_code,403)
        self.assertEqual(self.get('/memory-stories?library=family-a&token=secret').status_code,400)
        self.f.mutate("UPDATE access_memberships SET status='revoked' WHERE account_id=?",(self.f.member_id,))
        self.assertEqual(self.get(headers={'Authorization':'Bearer '+self.f.member_token}).status_code,401)

    def test_current_sources_not_copied_into_saved_content(self):
        self.f.mutate("UPDATE captions SET text='private-source-words' WHERE id=101")
        saved = self.save().json(); ident=saved['id']
        self.f.mutate("UPDATE captions SET superseded=1 WHERE id=101")
        reopened = self.get('/memory-stories/'+ident+'?library=family-a')
        self.assertNotIn('private-source-words',reopened.text)
        self.assertNotIn('caption-101',reopened.json()['chapters'][0]['evidence_ids'])


if __name__ == '__main__': unittest.main()
