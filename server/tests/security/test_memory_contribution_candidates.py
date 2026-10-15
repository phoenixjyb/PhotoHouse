"""Metadata-only, current-revision chapter source choices on synthetic SQLite."""
import json
import unittest
import uuid

import test_memory_transport as fixture


class ContributionCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): fixture.MemoryTransportTests.setUpClass()
    @classmethod
    def tearDownClass(cls): fixture.MemoryTransportTests.tearDownClass()

    def setUp(self):
        self.helper = fixture.MemoryTransportTests()
        self.helper.setUp()
        self.addCleanup(self.helper.doCleanups)
        self.f = self.helper.f
        self.client = self.helper.enabled_client(originals=True, generation=False)
        self.story = self.helper.story(self.client)
        self.headers = self.helper.headers()

    def choices(self, *, token=None, story=None, library='family-a', revision='1', chapter='chapter-1', page='1', extra=''):
        return self.client.get(f'/memory-community/v1/stories/{story or self.story}/contribution-candidates'
            f'?library={library}&revision={revision}&chapter_id={chapter}&page={page}{extra}',
            headers=self.helper.headers(token))

    def contribute(self, *, state='accepted', consent='1', chapter='chapter-1', story=None, kind='text', byline='家人'):
        story = story or self.story
        body = self.helper.contribution_body(kind=kind, chapter_id=chapter, consent=consent,
                                              byline=byline, text='PRIVATE-ORIGINAL-CONTENT' if kind == 'text' else '')
        if kind == 'audio':
            response = self.helper.audio(self.client, story, self.f.member_token, body=body)
        else:
            response = self.client.post(f'/memory-community/v1/stories/{story}/contributions/text?library=family-a',
                headers=self.helper.headers(self.f.member_token), json=body)
        self.assertEqual(response.status_code, 200, response.text)
        ident = response.json()['id']
        if state != 'pending':
            reviewed = self.client.post(f'/memory-community/v1/stories/{story}/contributions/{ident}/review?library=family-a',
                headers=self.headers, json={'state':state, 'revision':'1'})
            self.assertEqual(reviewed.status_code, 200, reviewed.text)
        return ident

    def edit_body(self, ids):
        detail = self.client.get(f'/memory-stories/{self.story}?library=family-a', headers=self.headers).json()
        return {key:detail[key] for key in ('title','theme','language','selection_revision','revision')} | {
            'asset_ids':','.join(item['id'] for item in detail['items']),
            'chapters':json.dumps(detail['chapters']), 'mutation_id':str(uuid.uuid4()),
            'contribution_refs':json.dumps([{'chapter_id':'chapter-1','contribution_ids':ids}])}

    def test_only_eligible_metadata_is_returned_without_original_or_derived_content(self):
        text = self.contribute(byline='<b>Literal family name</b>')
        audio = self.contribute(kind='audio', chapter='')
        self.contribute(state='pending')
        self.contribute(state='declined')
        self.contribute(consent='0')
        other_chapter = self.contribute()
        self.f.mutate('UPDATE access_memory_contributions SET chapter_id=? WHERE id=?', ('chapter-2', other_chapter))
        other_story = self.helper.story(self.client)
        self.contribute(story=other_story)
        response = self.choices()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers['cache-control'], 'no-store')
        self.assertEqual(response.headers['cross-origin-resource-policy'], 'same-origin')
        value = response.json()
        self.assertEqual(set(value), {'version','story_id','library_id','revision','chapter_id','page','page_size','has_more','items'})
        self.assertEqual((value['story_id'],value['library_id'],value['revision'],value['chapter_id']),
                         (self.story,'family-a','1','chapter-1'))
        self.assertEqual({row['id'] for row in value['items']}, {text,audio})
        for row in value['items']:
            self.assertEqual(set(row), {'id','kind','byline','language','chapter_id','created_at','duration_ms'})
        self.assertEqual(next(row['byline'] for row in value['items'] if row['id']==text), '<b>Literal family name</b>')
        self.assertNotIn('PRIVATE-ORIGINAL-CONTENT', response.text)
        self.assertTrue(all(word not in response.text for word in ('original_text','original_audio','transcript','polished_text','author_id','sha256')))
        with self.f.connection() as db:
            columns_read = []
            def authorize(action, column_table, column, database, trigger):
                import sqlite3
                if action == sqlite3.SQLITE_READ and column_table in {'access_memory_contributions','access_memory_contribution_derivations'}:
                    columns_read.append((column_table,column))
                return sqlite3.SQLITE_OK
            db.set_authorizer(authorize)
            from app.access.memory_contributions import MemoryContributions
            from app.access.service import AccessService
            MemoryContributions(AccessService(db, clock=lambda:self.f.now)).candidates(
                self.f.owner_token,'family-a',self.story,1,'chapter-1',1)
            self.assertFalse(any(column in {'original_text','original_audio','transcript','polished_text'} for _,column in columns_read))

    def test_filtering_precedes_pagination_and_order_is_stable(self):
        accepted = {self.contribute() for _ in range(17)}
        for _ in range(3): self.contribute(state='pending')
        first = self.choices().json(); second = self.choices(page='2').json()
        self.assertEqual((len(first['items']),first['has_more'],first['page_size']), (16,True,16))
        self.assertEqual((len(second['items']),second['has_more']), (1,False))
        self.assertEqual({row['id'] for row in first['items']+second['items']}, accepted)
        self.assertEqual(first['items'], self.choices().json()['items'])

    def test_current_membership_full_parent_and_editor_permission_are_required(self):
        self.contribute()
        for token,library,story in ((self.f.member_token,'family-a',self.story),
                                   (self.f.other_token,'family-a',self.story),
                                   (self.f.owner_token,'family-b',self.story),
                                   (self.f.owner_token,'family-a',str(uuid.uuid4()))):
            with self.subTest(token=token==self.f.owner_token,library=library):
                response=self.choices(token=token,library=library,story=story)
                self.assertIn(response.status_code, (401,403), response.text)
        self.f.mutate('UPDATE assets SET status=? WHERE id=?', ('deleted',101))
        response=self.choices()
        self.assertIn(response.status_code,(401,403,404),response.text)
        self.assertNotIn('items',response.json())

    def test_contributor_can_choose_for_own_story_until_membership_is_revoked(self):
        self.f.mutate("UPDATE access_memberships SET role='contributor' WHERE account_id=? AND library_id='family-a'",
                      (self.f.member_id,))
        body=self.edit_body([])
        body.pop('contribution_refs');body['revision']='0'
        created=self.client.post('/memory-stories?library=family-a',
            headers=self.helper.headers(self.f.member_token),json=body)
        self.assertEqual(created.status_code,200,created.text)
        owned=created.json()['id']
        self.assertEqual(self.choices(token=self.f.member_token,story=owned).status_code,200)
        self.assertIn(self.choices(token=self.f.member_token).status_code,(401,403))
        self.f.mutate("UPDATE access_memberships SET status='revoked' WHERE account_id=? AND library_id='family-a'",
                      (self.f.member_id,))
        self.assertIn(self.choices(token=self.f.member_token,story=owned).status_code,(401,403))

    def test_flags_retention_schema_and_strict_queries_fail_closed(self):
        path=f'/memory-community/v1/stories/{self.story}/contribution-candidates?library=family-a&revision=1&chapter_id=chapter-1'
        self.assertEqual(self.client.get(path).status_code,401)
        for method in ('POST','PUT','DELETE','HEAD','OPTIONS'):
            with self.subTest(method=method):
                self.assertEqual(self.client.request(method,path,headers=self.headers).status_code,403)
        for name in ('memory_collaboration_enabled','memory_originals_enabled','memory_retention_healthy'):
            with self.subTest(flag=name):
                prior=getattr(self.client.app.state,name)
                setattr(self.client.app.state,name,False)
                self.assertEqual(self.choices().status_code,503)
                setattr(self.client.app.state,name,prior)
        for change in ({'revision':'01'},{'revision':'0'},{'revision':'2'}, {'chapter':'chapter-2'},
                       {'chapter':'chapter-01'}, {'page':'0'}, {'extra':'&page=2'}, {'extra':'&text=yes'}):
            with self.subTest(change=change):
                response=self.choices(**change)
                self.assertIn(response.status_code,(400,409,422),response.text)
                self.assertNotIn('items',response.json())
        self.f.mutate('UPDATE alembic_version SET version_num=?', ('not-admitted',))
        self.assertEqual(self.choices().status_code,503)

    def test_explicit_choice_saves_as_reference_and_revoked_choice_does_not_partially_save(self):
        ident=self.contribute()
        body=self.edit_body([ident])
        self.assertEqual(self.choices().status_code,200)
        path=f'/memory-stories/{self.story}?library=family-a&contribution_refs=1'
        saved=self.client.put(path,headers=self.headers,json=body)
        self.assertEqual(saved.status_code,200,saved.text)
        self.assertEqual(saved.json()['revision'],'2')
        refs=self.client.get(f'/memory-stories/{self.story}/contribution-refs?library=family-a&revision=2',headers=self.headers)
        self.assertEqual(refs.json()['chapters'][0]['contribution_ids'],[ident])
        self.assertEqual(self.choices().status_code,409,'old chooser revision is stale after save')
        fresh=self.choices(revision='2');self.assertEqual(fresh.status_code,200,fresh.text)
        body=self.edit_body([ident]);body['title']='must not be saved'
        self.f.mutate('UPDATE access_memory_contributions SET local_processing_consent=0 WHERE id=?',(ident,))
        self.assertEqual(self.choices(revision='2').json()['items'],[])
        denied=self.client.put(path,headers=self.headers,json=body)
        self.assertEqual(denied.status_code,422,denied.text)
        reread=self.client.get(f'/memory-stories/{self.story}?library=family-a',headers=self.headers).json()
        self.assertEqual(reread['revision'],'2');self.assertNotEqual(reread['title'],'must not be saved')
