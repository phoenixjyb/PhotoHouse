"""HTTP boundary tests for the opt-in memory collaboration API.

All records and audio in this module are synthetic and use the local SQLite
fixture. No external provider or live PhotoHouse service is contacted.
"""
import base64
import io
import json
import uuid
import wave
import unittest

import test_library_reads as fixture
from app.main import create_app
from app.access.transport import AccessRuntime, COOKIE, csrf_token


class MemoryTransportTests(unittest.TestCase):
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

    def enabled_client(self, *, originals=True, generation=True):
        runtime = AccessRuntime(self.f.connection, 'https://photohouse.test', clock=lambda: self.f.now)
        from fastapi.testclient import TestClient
        client = TestClient(create_app(access_runtime=runtime,
            memory_collaboration_enabled=True, memory_originals_enabled=originals,
            memory_generation_enabled=generation), base_url='https://photohouse.test',
            client=('192.0.2.21', 23457))
        client.headers['Sec-Fetch-Site'] = 'same-origin'
        self.addCleanup(client.close)
        return client

    def headers(self, token=None):
        return {'Authorization': 'Bearer ' + (token or self.f.owner_token)}

    def story(self, client=None):
        client = client or self.f.client
        response = client.post('/story-workspace/preview?library=family-a',
            headers=self.headers(), json={'asset_ids':'101,102','title':'家庭相册',
                'theme':'everyday','language':'zh'})
        self.assertEqual(response.status_code, 200, response.text)
        draft = response.json()
        chapter = draft['chapters'][0] | {'narration':'这一天我们一起散步。'}
        body = {'title':draft['title'],'theme':draft['theme'],'language':'zh',
            'asset_ids':'101,102','chapters':json.dumps([chapter],ensure_ascii=False),
            'selection_revision':draft['selection_revision'],'revision':'0',
            'mutation_id':str(uuid.uuid4())}
        response = client.post('/memory-stories?library=family-a',headers=self.headers(),json=body)
        self.assertEqual(response.status_code,200,response.text)
        return response.json()['id']

    def contribution_body(self, *, kind='text', **changes):
        return {'kind':kind,'text':'奶奶记得那天的阳光。' if kind=='text' else '',
            'language':'zh','byline':'家人','consent':'1',
            'chapter_id':'chapter-1' if kind=='text' else '', 'revision':'1',
            'mutation_id':str(uuid.uuid4())} | changes

    @staticmethod
    def wav(*, channels=1, rate=16000, width=2, frames=1600):
        out=io.BytesIO()
        with wave.open(out,'wb') as target:
            target.setnchannels(channels); target.setframerate(rate); target.setsampwidth(width)
            target.writeframes(b'\0' * frames * channels * width)
        return out.getvalue()

    def audio(self, client, story_id, token, body=None, payload=None, **headers):
        body = body or self.contribution_body(kind='audio')
        payload = self.wav() if payload is None else payload
        encoded = base64.b64encode(json.dumps(body,ensure_ascii=False).encode()).decode()
        request_headers = self.headers(token) | {'Content-Type':'audio/wav',
            'X-PhotoHouse-Memory-Metadata':encoded} | headers
        return client.post(f'/memory-community/v1/stories/{story_id}/contributions/audio?library=family-a',
                           headers=request_headers,content=payload)

    def test_auth_flags_csrf_origin_route_and_query_guards(self):
        path='/memory-community/v1/capabilities?library=family-a'
        self.assertEqual(self.f.client.get(path).status_code,401)
        self.assertEqual(self.f.client.get(path,headers={'Cookie':f'{COOKIE}={self.f.member_token}'}).status_code,200)
        self.assertEqual(self.f.client.get(path,headers=self.headers()).status_code,200)
        caps=self.f.client.get(path,headers=self.headers()).json()
        self.assertEqual((caps['enabled'],caps['contributions_enabled'],caps['generation_enabled']),(False,False,False))
        community='/memory-community/v1/books?library=family-a'
        self.assertEqual(self.f.client.get(community,headers=self.headers()).status_code,503)
        self.assertEqual(self.f.client.get('/memory-community/v1/books?library=family-a&library=family-b',headers=self.headers()).status_code,400)
        self.assertEqual(self.f.client.post(path,headers=self.headers()).status_code,403)
        self.assertEqual(self.f.client.get('/memory-community/v1/books/?library=family-a',headers=self.headers()).status_code,403)
        self.assertEqual(self.f.client.get(community,headers=self.headers()|{'Origin':'https://attacker.test'}).status_code,403)
        cookie_client=self.enabled_client()
        cookie_client.cookies.set(COOKIE,self.f.member_token)
        self.assertEqual(cookie_client.get('/memory-community/v1/capabilities?library=family-a').status_code,200)
        story=self.story(self.f.client)
        payload={'id':str(uuid.uuid4()),'target_type':'story','target_id':story}
        denied=cookie_client.post('/memory-community/v1/conversations?library=family-a',json=payload)
        self.assertEqual(denied.status_code,403)
        csrf=csrf_token(self.f.member_token)
        accepted=cookie_client.post('/memory-community/v1/conversations?library=family-a',
            headers={'Origin':'https://photohouse.test','X-CSRF-Token':csrf},
            json=payload)
        self.assertEqual(accepted.status_code,200,accepted.text)
        for method in ('put','delete','head','options'):
            self.assertEqual(getattr(cookie_client,method)(community,headers=self.headers()).status_code,403)

    def test_capabilities_distinguish_independent_flags_and_missing_schema_fails_closed(self):
        partial=self.enabled_client(originals=False,generation=False)
        caps=partial.get('/memory-community/v1/capabilities?library=family-a',headers=self.headers()).json()
        self.assertEqual((caps['enabled'],caps['contributions_enabled'],caps['generation_enabled']),(True,False,False))
        self.assertEqual(partial.get('/memory-community/v1/books?library=family-a',headers=self.headers()).status_code,200)
        story=self.story(partial)
        self.assertEqual(partial.get(f'/memory-community/v1/stories/{story}/contributions?library=family-a',headers=self.headers()).status_code,503)
        self.assertEqual(partial.post('/memory-community/v1/jobs?library=family-a',headers=self.headers(),json={}).status_code,503)
        self.assertEqual(partial.post('/memory-community/v1/conversations?library=family-a',headers=self.headers(),json={}).status_code,503)
        full=self.enabled_client()
        with self.f.connection() as db:
            tables=('access_memory_turns','access_memory_jobs','access_memory_conversations',
                    'access_memory_book_revisions','access_memory_books',
                    'access_memory_contribution_derivations','access_memory_contributions')
            present={row[0] for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertTrue(set(tables) <= present, set(tables) - present)
            db.execute('PRAGMA foreign_keys=OFF')
            try:
                for table in tables:
                    db.execute(f'DROP TABLE {table}')
            finally:
                db.execute('PRAGMA foreign_keys=ON')
            db.commit()
        response=full.get('/memory-community/v1/books?library=family-a',headers=self.headers())
        self.assertEqual(response.status_code,503,response.text)

    def test_text_audio_submission_visibility_review_delete_and_audio_guards(self):
        client=self.enabled_client()
        story=self.story(client)
        with self.f.connection() as db:
            from app.access.service import AccessService
            access=AccessService(db,clock=lambda:self.f.now)
            code=access.invite(self.f.owner_token,'family-a','+12025550104')
            other_member=access.register('+12025550104',fixture.PASSWORD,code,'Second Synthetic Reader')
        body=self.contribution_body()
        text=client.post(f'/memory-community/v1/stories/{story}/contributions/text?library=family-a',headers=self.headers(self.f.member_token),json=body)
        self.assertEqual(text.status_code,200,text.text)
        text_id=text.json()['id']
        self.assertEqual(client.get(f'/memory-community/v1/stories/{story}/contributions/{text_id}?library=family-a',headers=self.headers(self.f.other_token)).status_code,401)
        review=client.post(f'/memory-community/v1/stories/{story}/contributions/{text_id}/review?library=family-a',headers=self.headers(),json={'state':'accepted','revision':'1'})
        self.assertEqual(review.status_code,200,review.text)
        visible=client.get(f'/memory-community/v1/stories/{story}/contributions/{text_id}?library=family-a',headers=self.headers(self.f.member_token))
        self.assertEqual(visible.status_code,200,visible.text)
        self.assertEqual(visible.json()['text'],'奶奶记得那天的阳光。')

        audio=self.audio(client,story,self.f.member_token)
        self.assertEqual(audio.status_code,200,audio.text)
        audio_id=audio.json()['id']
        private=client.get(f'/memory-community/v1/stories/{story}/contributions/{audio_id}?library=family-a',headers=self.headers(self.f.other_token))
        self.assertEqual(private.status_code,401)
        self.assertEqual(client.get(f'/memory-community/v1/stories/{story}/contributions/{audio_id}/audio?library=family-a',headers=self.headers(self.f.other_token)).status_code,401)
        accepted=client.post(f'/memory-community/v1/stories/{story}/contributions/{audio_id}/review?library=family-a',headers=self.headers(),json={'state':'accepted','revision':'1'})
        self.assertEqual(accepted.status_code,200,accepted.text)
        retrieved=client.get(f'/memory-community/v1/stories/{story}/contributions/{audio_id}/audio?library=family-a',headers=self.headers(other_member))
        self.assertEqual((retrieved.status_code,retrieved.content),(200,self.wav()))
        self.assertEqual(client.post(f'/memory-community/v1/stories/{story}/contributions/{text_id}/review?library=family-a',headers=self.headers(),json={'state':'declined','revision':'1'}).status_code,409)
        deleted=client.delete(f'/memory-community/v1/stories/{story}/contributions/{text_id}?library=family-a',headers=self.headers())
        self.assertEqual(deleted.status_code,200,deleted.text)

        # The route must authorize the parent before consuming or validating the audio body.
        foreign=self.audio(client,story,self.f.other_token,payload=b'not a wav')
        self.assertEqual(foreign.status_code,401,foreign.text)
        invalids=[('@@',self.wav()),
            (base64.b64encode(b'\xff').decode(),self.wav()),
            (base64.b64encode(b'{"kind":"audio","kind":"audio"}').decode(),self.wav()),
            (base64.b64encode(json.dumps(self.contribution_body(kind='audio')|{'extra':'x'}).encode()).decode(),self.wav()),
            (base64.b64encode(json.dumps(self.contribution_body(kind='audio')).encode()).decode(),self.wav(channels=2))]
        for encoded,payload in invalids:
            response=client.post(f'/memory-community/v1/stories/{story}/contributions/audio?library=family-a',
                headers=self.headers(self.f.member_token)|{'Content-Type':'audio/wav','X-PhotoHouse-Memory-Metadata':encoded},content=payload)
            self.assertIn(response.status_code,(400,422),response.text)
        over=client.post(f'/memory-community/v1/stories/{story}/contributions/audio?library=family-a',
            headers=self.headers(self.f.member_token)|{'Content-Type':'audio/wav','Content-Length':str(2*1024*1024+1),'X-PhotoHouse-Memory-Metadata':base64.b64encode(json.dumps(self.contribution_body(kind='audio')).encode()).decode()},content=b'')
        self.assertEqual(over.status_code,413)
        payload=self.wav()
        incomplete=self.audio(client,story,self.f.member_token,payload=payload,
            **{'Content-Length':str(len(payload)+1)})
        self.assertEqual(incomplete.status_code,400,incomplete.text)

    def test_book_conversation_and_job_http_auth_cas_and_generation_flags(self):
        client=self.enabled_client()
        story=self.story(client)
        book_body={'title':'家庭记忆','language':'zh','introduction':'一起度过的一天。','story_ids':story,'revision':'0','mutation_id':str(uuid.uuid4())}
        created=client.post('/memory-community/v1/books?library=family-a',headers=self.headers(),json=book_body)
        self.assertEqual(created.status_code,200,created.text)
        book_id=created.json()['id']
        self.assertEqual(client.get('/memory-community/v1/books?library=family-a',headers=self.headers(self.f.member_token)).status_code,200)
        self.assertEqual(client.get(f'/memory-community/v1/books/{book_id}?library=family-a',headers=self.headers(self.f.member_token)).status_code,200)
        edit=book_body|{'title':'家庭记忆续篇','revision':'1','mutation_id':str(uuid.uuid4())}
        self.assertEqual(client.put(f'/memory-community/v1/books/{book_id}?library=family-a',headers=self.headers(),json=edit).status_code,200)
        self.assertEqual(client.put(f'/memory-community/v1/books/{book_id}?library=family-a',headers=self.headers(),json=edit|{'title':'stale'}).status_code,409)
        self.assertEqual(client.post('/memory-community/v1/books?library=family-a',headers=self.headers(),json=book_body|{'unknown':'no'}).status_code,400)

        member=self.f.member_token
        start={'id':str(uuid.uuid4()),'target_type':'story','target_id':story}
        conversation=client.post('/memory-community/v1/conversations?library=family-a',headers=self.headers(member),json=start)
        self.assertEqual(conversation.status_code,200,conversation.text)
        conversation_id=conversation.json()['id']
        turn={'revision':'1','mutation_id':str(uuid.uuid4()),'text':'我还记得那一天。'}
        sent=client.post(f'/memory-community/v1/conversations/{conversation_id}/turns?library=family-a',headers=self.headers(member),json=turn)
        self.assertEqual(sent.status_code,200,sent.text)
        history_path=f'/memory-community/v1/conversations/{conversation_id}/turns?library=family-a'
        legacy=client.get(history_path,headers=self.headers(member))
        self.assertEqual(legacy.status_code,200,legacy.text)
        self.assertEqual(set(legacy.json()['items'][0]),
            {'id','sequence','input_text','reply_text','reply_kind','job_id','state'})
        enriched=client.get(history_path+'&reply_context=1',headers=self.headers(member))
        self.assertEqual(enriched.status_code,200,enriched.text)
        self.assertEqual(enriched.json()['items'][0]['reply_source_ids'],[])
        self.assertEqual(enriched.json()['items'][0]['reply_questions'],[])
        for flag in ('0','true','', '1&reply_context=1'):
            self.assertEqual(client.get(history_path+'&reply_context='+flag,
                headers=self.headers(member)).status_code,400)
        recent=client.get(history_path+'&order=recent&reply_context=1',headers=self.headers(member))
        self.assertEqual(recent.status_code,200,recent.text)
        self.assertEqual(recent.json()['items'],enriched.json()['items'])
        for order in ('oldest','desc','', 'recent&order=recent'):
            self.assertEqual(client.get(history_path+'&order='+order,
                headers=self.headers(member)).status_code,400)
        self.assertEqual(client.get(f'/memory-community/v1/conversations/{conversation_id}/turns?library=family-a',headers=self.headers()).status_code,401)
        narrative=client.post('/memory-community/v1/jobs?library=family-a',headers=self.headers(member),json={'target_type':'story','target_id':story,'revision':'1','mutation_id':str(uuid.uuid4()),'instructions':''})
        self.assertEqual(narrative.status_code,401,narrative.text)
        owner_job=client.post('/memory-community/v1/jobs?library=family-a',headers=self.headers(),json={'target_type':'story','target_id':story,'revision':'1','mutation_id':str(uuid.uuid4()),'instructions':''})
        self.assertEqual(owner_job.status_code,200,owner_job.text)
        job_id=owner_job.json()['id']
        self.assertEqual(client.get(f'/memory-community/v1/jobs/{job_id}?library=family-a',headers=self.headers(member)).status_code,401)
        cancelled=client.delete(f'/memory-community/v1/jobs/{job_id}?library=family-a',headers=self.headers())
        self.assertEqual(cancelled.status_code,200,cancelled.text)
        self.assertEqual(cancelled.json()['state'],'cancelled')
        self.f.mutate("UPDATE access_memberships SET status='revoked' WHERE account_id=?",(fixture.LibraryReadTests.member_id,))
        self.assertEqual(client.get(f'/memory-community/v1/jobs/{job_id}?library=family-a',headers=self.headers(member)).status_code,401)

    def test_memoir_plan_read_auth_query_origin_no_job_and_generation_off(self):
        client = self.enabled_client(generation=False)
        story = self.story(client)
        body = {'title': 'Private memoir', 'language': 'zh', 'introduction': 'Our opening',
                'story_ids': story, 'revision': '0', 'mutation_id': str(uuid.uuid4())}
        created = client.post('/memory-community/v1/books?library=family-a',
                              headers=self.headers(), json=body)
        self.assertEqual(created.status_code, 200, created.text)
        path = f"/memory-community/v1/books/{created.json()['id']}/plan?library=family-a"
        response = client.get(path, headers=self.headers(self.f.member_token))
        self.assertEqual(response.status_code, 200, response.text)
        plan = response.json()
        self.assertFalse(plan['can_edit'])
        self.assertFalse(plan['whole']['can_draft'])
        self.assertEqual(plan['sections'][0]['id'], story)
        self.assertFalse(plan['queued'])
        self.assertFalse(plan['generated'])
        self.assertNotIn('这一天我们一起散步', response.text)
        with self.f.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM access_memory_jobs').fetchone()[0], 0)
        self.assertEqual(self.f.client.get(path, headers=self.headers()).status_code, 503)
        self.assertEqual(client.get(path).status_code, 401)
        self.assertEqual(client.get(path, headers=self.headers(self.f.other_token)).status_code, 401)
        self.assertEqual(client.get(path+'&page=1', headers=self.headers()).status_code, 400)
        self.assertEqual(client.get(path+'&library=family-b', headers=self.headers()).status_code, 400)
        self.assertEqual(client.get(path, headers=self.headers()|{'Origin': 'https://attacker.test'}).status_code, 403)
        self.assertEqual(client.post(path, headers=self.headers()).status_code, 403)
        self.f.mutate("UPDATE assets SET status='deleted' WHERE id=101")
        self.assertEqual(client.get(path, headers=self.headers()).status_code, 401)

    def test_conversation_history_lists_are_actor_scoped_parent_checked_and_readable_without_generation(self):
        client=self.enabled_client()
        story=self.story(client)
        member=self.f.member_token
        started=client.post('/memory-community/v1/conversations?library=family-a',headers=self.headers(member),
            json={'id':str(uuid.uuid4()),'target_type':'story','target_id':story})
        self.assertEqual(started.status_code,200,started.text)
        query=f'?library=family-a&target_type=story&target_id={story}'
        member_history=client.get('/memory-community/v1/conversations'+query,headers=self.headers(member))
        self.assertEqual(member_history.status_code,200,member_history.text)
        self.assertEqual([row['id'] for row in member_history.json()['items']],[started.json()['id']])
        self.assertEqual(set(member_history.json()['items'][0]),{'id','created_at','expires_at'})
        preview_history=client.get('/memory-community/v1/conversations'+query+'&preview=1',headers=self.headers(member))
        self.assertEqual(preview_history.status_code,200,preview_history.text)
        self.assertEqual(preview_history.json()['items'][0]['first_message_preview'],'')
        self.assertEqual(client.get('/memory-community/v1/conversations'+query+'&preview=0',headers=self.headers(member)).status_code,400)
        self.assertEqual(client.get('/memory-community/v1/conversations'+query+'&preview=1&preview=1',headers=self.headers(member)).status_code,400)
        self.assertEqual(client.get('/memory-community/v1/conversations'+query,headers=self.headers()).json()['items'],[])
        for invalid in ('?library=family-a','?library=family-a&target_type=story',
                        query+'&extra=unexpected',query+f'&target_id={story}'):
            self.assertEqual(client.get('/memory-community/v1/conversations'+invalid,headers=self.headers(member)).status_code,400)

        generation_off=self.enabled_client(generation=False)
        historical=generation_off.get('/memory-community/v1/conversations'+query,headers=self.headers(member))
        self.assertEqual(historical.status_code,200,historical.text)
        self.assertEqual(historical.json()['items'][0]['id'],started.json()['id'])
        self.assertEqual(set(historical.json()['items'][0]),{'id','created_at','expires_at'})
        self.assertEqual(generation_off.post('/memory-community/v1/conversations?library=family-a',
            headers=self.headers(member),json={'id':str(uuid.uuid4()),'target_type':'story','target_id':story}).status_code,503)
        self.f.mutate("UPDATE access_asset_libraries SET library_id='family-b' WHERE asset_id=101")
        self.assertEqual(generation_off.get('/memory-community/v1/conversations'+query,headers=self.headers(member)).status_code,401)

    def test_retention_unhealthy_fails_http_scope_closed_without_touching_originals(self):
        client=self.enabled_client()
        story=self.story(client)
        submitted=client.post(f'/memory-community/v1/stories/{story}/contributions/text?library=family-a',
            headers=self.headers(self.f.member_token),json=self.contribution_body())
        self.assertEqual(submitted.status_code,200,submitted.text)
        ident=submitted.json()['id']
        client.app.state.memory_retention_healthy=False
        denied=client.get(f'/memory-community/v1/stories/{story}/contributions/{ident}?library=family-a',headers=self.headers())
        self.assertEqual(denied.status_code,503,denied.text)
        with self.f.connection() as db:
            self.assertEqual(db.execute('SELECT original_text FROM access_memory_contributions WHERE id=?',(ident,)).fetchone()[0],
                             '奶奶记得那天的阳光。')


if __name__ == '__main__': unittest.main()
