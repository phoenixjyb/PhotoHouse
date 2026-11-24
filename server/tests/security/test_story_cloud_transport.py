"""Protected HTTP path with an in-process fake cloud; no external requests."""
import hashlib
import json
import unittest
from unittest.mock import patch
from test_memory_stories import MemoryStoryTests as Fixture
from app.access.story_cloud_proofreading import CloudProofreading


class FakeProvider:
    provider_name = 'DeepSeek'
    model = 'synthetic-local-test'
    def __init__(self): self.sent = []
    def send(self, body):
        self.sent.append(body)
        data = json.loads(json.loads(body)['messages'][1]['content'])
        return {'paragraphs': [c['narration'] + (' 这是一份待核对建议。' if c['narration'].strip() else '') for c in data['chapters']]}


class StoryCloudTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): Fixture.setUpClass()
    @classmethod
    def tearDownClass(cls): Fixture.tearDownClass()
    def setUp(self):
        self.base = Fixture(); self.base.setUp(); self.addCleanup(self.base.doCleanups)
        self.client = self.base.client
        self.provider = FakeProvider()
        self.client.app.state.story_cloud_proofreading = CloudProofreading(enabled=True, provider=self.provider)
        body = self.base.body(); chapters = json.loads(body['chapters'])
        for c in chapters: c['narration'] = 'Jamie带着相册，讲起旅行。'
        self.story = self.base.save({**body, 'chapters': json.dumps(chapters)}).json()
        self.path = '/memory-stories/' + self.story['id'] + '/proofreading/'
    def preview(self, headers=None):
        return self.client.post(self.path+'preview?library=family-a',headers=headers or self.base.headers,
                                json={'revision':self.story['revision']})
    def confirm(self, p, **updates):
        return self.client.post(self.path+'confirm?library=family-a',headers=self.base.headers,
            json={'revision':self.story['revision'],'preview_id':p['preview_id'],
                  'request_sha256':p['request_sha256'],'confirmed':'yes',**updates})
    def test_exact_preview_confirm_review_only_and_no_resend(self):
        with patch('app.access.story_cloud_transport.refinement_resolver',return_value=lambda *a,**kw:([{'name':'嘉宁','aliases':['Jamie']}],'synthetic-reviewed')):
            response=self.preview(); self.assertEqual(200,response.status_code,response.text); p=response.json()
            self.assertNotIn('Jamie',p['request_body']); self.assertNotIn('嘉宁',p['request_body'])
            self.assertNotIn(self.story['id'],p['request_body']); self.assertEqual([],self.provider.sent)
            self.assertEqual(p['request_sha256'],hashlib.sha256(p['request_body'].encode()).hexdigest())
            sent=self.confirm(p); self.assertEqual(200,sent.status_code,sent.text); result=sent.json()
            self.assertTrue(result['needs_review']); self.assertFalse(result['saved'])
            self.assertIn('嘉宁',result['chapters'][0]['narration'])
            self.assertEqual([p['request_body'].encode()],self.provider.sent)
            self.assertEqual(409,self.confirm(p).status_code)
        current=self.base.get('/memory-stories/'+self.story['id']+'?library=family-a').json()
        self.assertEqual(self.story['chapters'],current['chapters'])
    def test_default_off_and_missing_confirmation_do_not_send(self):
        self.client.app.state.story_cloud_proofreading=CloudProofreading(provider=self.provider)
        p=self.preview().json(); self.assertFalse(p['enabled']); self.assertTrue(p['configured'])
        self.assertEqual(503,self.confirm(p).status_code); self.assertEqual(422,self.confirm(p,confirmed='no').status_code)
        self.assertEqual([],self.provider.sent)
    def test_stale_revision_refuses_before_egress(self):
        p=self.preview().json()
        self.base.f.mutate('UPDATE access_memory_stories SET revision=revision+1 WHERE id=?',(self.story['id'],))
        self.assertEqual(409,self.confirm(p).status_code); self.assertEqual([],self.provider.sent)
    def test_reader_and_even_owner_cannot_send_another_authors_story(self):
        self.assertEqual(401,self.preview({'Authorization':'Bearer '+self.base.f.member_token}).status_code)
        self.base.f.mutate('UPDATE access_memory_stories SET author_id=? WHERE id=?',(self.base.f.member_id,self.story['id']))
        self.assertEqual(401,self.preview().status_code); self.assertEqual([],self.provider.sent)
    def test_deleted_selection_blocks_preview_and_confirm(self):
        p=self.preview().json(); self.base.f.mutate("UPDATE assets SET status='deleted' WHERE id=101")
        self.assertEqual(401,self.preview().status_code); self.assertEqual(401,self.confirm(p).status_code)
        self.assertEqual([],self.provider.sent)


if __name__=='__main__': unittest.main()
