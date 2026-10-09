"""Atomic saved-story references to accepted synthetic family contributions."""
import json
import unittest
import uuid

from alembic import command
from sqlalchemy import create_engine

import test_library_reads as fixture
import test_orm_migrations as migrations
from app.access.memory_contributions import MemoryContributions
from app.access.memory_source_refs import parse_groups
from app.access.memory_jobs import context, MemoryJobs
from app.access.memory_books import MemoryBooks
from app.access.memory_processing import process_job
from app.access.original_deletions import erase_memory_original
from app.access.service import AccessService
from app.access.transport import TransportError


class MemoryContributionRefTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): fixture.LibraryReadTests.setUpClass()
    @classmethod
    def tearDownClass(cls): fixture.LibraryReadTests.tearDownClass()

    def setUp(self):
        self.f = fixture.LibraryReadTests(); self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.headers = {'Authorization': 'Bearer ' + self.f.owner_token}
        preview = self.f.client.post('/story-workspace/preview?library=family-a',
            headers=self.headers, json={'asset_ids':'101,102','title':'湖边的一天',
                'theme':'everyday','language':'zh'}).json()
        chapter = preview['chapters'][0] | {'narration':'家人共同记得湖边的风。'}
        self.story_body = {'title':preview['title'],'theme':preview['theme'],'language':'zh',
            'asset_ids':'101,102','chapters':json.dumps([chapter]),
            'selection_revision':preview['selection_revision'],'revision':'0',
            'mutation_id':str(uuid.uuid4())}
        response = self.save(self.story_body)
        self.assertEqual(response.status_code, 200, response.text)
        self.story = response.json()['id']

    def save(self, body, ident=None, *, opt_in=False):
        suffix = f'/{ident}' if ident else ''
        query = '?library=family-a' + ('&contribution_refs=1' if opt_in else '')
        return self.f.client.request('PUT' if ident else 'POST',
            '/memory-stories' + suffix + query, headers=self.headers, json=body)

    def contribution(self, *, story=None, chapter_id='chapter-1', consent='1'):
        story_id = story or self.story
        with self.f.connection() as db:
            access = AccessService(db, clock=lambda: self.f.now)
            service = MemoryContributions(access)
            body = {'kind':'text','text':'那天大家都笑了。','language':'zh','byline':'synthetic',
                'consent':consent,'chapter_id':chapter_id,'revision':'1',
                'mutation_id':str(uuid.uuid4())}
            created = service.create(self.f.member_token, 'family-a', story_id, body)
            accepted = service.review(self.f.owner_token, 'family-a', story_id,
                                      created['id'], 'accepted', 1)
            return accepted['id']

    def read_refs(self, revision=1, story=None, library='family-a', token=None):
        ident = story or self.story
        auth = {'Authorization':'Bearer ' + (token or self.f.owner_token)}
        return self.f.client.get(f'/memory-stories/{ident}/contribution-refs?library={library}&revision={revision}',
                                 headers=auth)

    def test_opt_in_atomic_write_latest_read_and_legacy_carry_or_change(self):
        ref = self.contribution()
        encoded = json.dumps([{'chapter_id':'chapter-1','contribution_ids':[ref]}])
        edit = self.story_body | {'revision':'1','mutation_id':str(uuid.uuid4()),
            'contribution_refs':encoded}
        saved = self.save(edit, self.story, opt_in=True)
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertNotIn('contribution_refs', saved.json())
        # A byte-identical retry is idempotent for both the revision and refs.
        with self.f.connection() as db:
            before_revisions = db.execute('SELECT count(*) FROM access_memory_revisions WHERE story_id=?',(self.story,)).fetchone()[0]
            before_refs = db.execute('SELECT count(*) FROM access_memory_contribution_refs WHERE story_id=?',(self.story,)).fetchone()[0]
        retry = self.save(edit,self.story,opt_in=True)
        self.assertEqual(retry.status_code,200,retry.text)
        self.assertEqual(retry.json()['revision'],'2')
        with self.f.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM access_memory_revisions WHERE story_id=?',(self.story,)).fetchone()[0],before_revisions)
            self.assertEqual(db.execute('SELECT count(*) FROM access_memory_contribution_refs WHERE story_id=?',(self.story,)).fetchone()[0],before_refs)
        self.assertEqual(self.read_refs(2).json(), {'version':1,'id':self.story,
            'library_id':'family-a','revision':'2','chapters':[
                {'id':'chapter-1','contribution_ids':[ref]}]})
        self.assertEqual(self.read_refs(1).status_code, 409)
        # Legacy v1 edit carries references only when that chapter's text and
        # ordered asset selection are unchanged.
        legacy = self.story_body | {'revision':'2','mutation_id':str(uuid.uuid4()),
            'title':'标题变了'}
        self.assertEqual(self.save(legacy,self.story).status_code, 200)
        self.assertEqual(self.read_refs(3).json()['chapters'][0]['contribution_ids'],[ref])
        changed = self.story_body | {'revision':'3','mutation_id':str(uuid.uuid4())}
        chapters = json.loads(changed['chapters']); chapters[0]['narration'] += '新句子。'
        changed['chapters'] = json.dumps(chapters)
        self.assertEqual(self.save(changed,self.story).status_code, 200)
        self.assertEqual(self.read_refs(4).json()['chapters'][0]['contribution_ids'],[])
        # Explicit empty refs are the clear operation and also produce a new revision.
        clear = self.story_body | {'revision':'4','mutation_id':str(uuid.uuid4()),
            'contribution_refs':'[]'}
        self.assertEqual(self.save(clear,self.story,opt_in=True).status_code, 200)
        self.assertEqual(self.read_refs(5).json()['chapters'][0]['contribution_ids'],[])

    def test_invalid_pending_unconsented_wrong_parent_and_duplicate_refs_rejected(self):
        pending = None
        with self.f.connection() as db:
            access = AccessService(db, clock=lambda: self.f.now)
            pending = MemoryContributions(access).create(self.f.member_token,'family-a',self.story,
                {'kind':'text','text':'pending','language':'zh','byline':'synthetic','consent':'1',
                 'chapter_id':'chapter-1','revision':'1','mutation_id':str(uuid.uuid4())})['id']
        no_consent = self.contribution(consent='0')
        accepted = self.contribution()
        cases = [
            json.dumps([{'chapter_id':'chapter-1','contribution_ids':[pending]}]),
            json.dumps([{'chapter_id':'chapter-1','contribution_ids':[no_consent]}]),
            json.dumps([{'chapter_id':'chapter-1','contribution_ids':[accepted,accepted]}]),
            json.dumps([{'chapter_id':'chapter-2','contribution_ids':[accepted]}]),
            '[{"chapter_id":"chapter-1","contribution_ids":[]},{"chapter_id":"chapter-1","contribution_ids":[]}]',
        ]
        for raw in cases:
            with self.subTest(raw=raw):
                body = self.story_body | {'revision':'1','mutation_id':str(uuid.uuid4()),
                                          'contribution_refs':raw}
                self.assertIn(self.save(body,self.story,opt_in=True).status_code,(422,))
        # A valid submitted group reused under the same mutation is a conflict.
        body = self.story_body | {'revision':'1','mutation_id':str(uuid.uuid4()),
            'contribution_refs':json.dumps([{'chapter_id':'chapter-1','contribution_ids':[accepted]}])}
        self.assertEqual(self.save(body,self.story,opt_in=True).status_code,200)
        changed = body | {'contribution_refs':'[]'}
        self.assertEqual(self.save(changed,self.story,opt_in=True).status_code,409)

    def test_wrong_story_library_and_malformed_groups_are_rejected(self):
        other = self.story_body | {'mutation_id':str(uuid.uuid4()),'title':'同库另一段故事'}
        other_story = self.save(other).json()['id']
        other_story_ref = self.contribution(story=other_story)
        wrong_story = self.story_body | {'revision':'1','mutation_id':str(uuid.uuid4()),
            'contribution_refs':json.dumps([{'chapter_id':'chapter-1','contribution_ids':[other_story_ref]}])}
        self.assertEqual(self.save(wrong_story,self.story,opt_in=True).status_code,422)

        # Synthetic cross-library row tests the validator independently of the
        # normal contribution API, which correctly cannot create this mismatch.
        foreign_id = str(uuid.uuid4())
        with self.f.connection() as db:
            actor = AccessService(db,clock=lambda:self.f.now).profile(self.f.other_token)['account_id']
            db.execute('''INSERT INTO access_memory_contributions
                (id,story_id,library_id,author_id,kind,original_text,language,byline,sha256,
                 local_processing_consent,chapter_id,base_story_revision,state,mutation_id,
                 request_digest,created_at,reviewed_by_id,reviewed_at)
                VALUES(?,?, 'family-b',?,'text','foreign synthetic','en','synthetic',?,1,
                       'chapter-1',1,'accepted',?,?,?, ?,?)''',
                (foreign_id,self.story,actor,'0'*64,str(uuid.uuid4()),'digest',self.f.now,actor,self.f.now))
            db.commit()
        wrong_library = self.story_body | {'revision':'1','mutation_id':str(uuid.uuid4()),
            'contribution_refs':json.dumps([{'chapter_id':'chapter-1','contribution_ids':[foreign_id]}])}
        self.assertEqual(self.save(wrong_library,self.story,opt_in=True).status_code,422)

        for raw in (
            '[{"chapter_id":"chapter-1","chapter_id":"chapter-1","contribution_ids":[]}]',
            '[{"chapter_id":"chapter-1","contribution_ids":[],"extra":true}]',
            '[{"chapter_id":"chapter-1","contribution_ids":["not-a-canonical-uuid"]}]',
        ):
            body = self.story_body | {'revision':'1','mutation_id':str(uuid.uuid4()),'contribution_refs':raw}
            self.assertEqual(self.save(body,self.story,opt_in=True).status_code,422)
        with self.assertRaises(TransportError):
            parse_groups(json.dumps([{'chapter_id':f'chapter-{i}','contribution_ids':[]}
                                     for i in range(1,8)]),[f'chapter-{i}' for i in range(1,8)])
        with self.assertRaises(TransportError):
            parse_groups(json.dumps([{'chapter_id':'chapter-1','contribution_ids':[
                str(uuid.uuid4()) for _ in range(13)]}]),['chapter-1'])
        no_query_optin = self.story_body | {'contribution_refs':'[]'}
        self.assertEqual(self.save(no_query_optin).status_code,400)
        missing_body_field = self.story_body | {'revision':'1','mutation_id':str(uuid.uuid4())}
        self.assertEqual(self.save(missing_body_field,self.story,opt_in=True).status_code,400)

    def test_reference_insert_failure_rolls_back_entire_story_mutation(self):
        ref = self.contribution()
        self.f.mutate('''CREATE TRIGGER reject_source_ref BEFORE INSERT ON access_memory_contribution_refs
            BEGIN SELECT RAISE(ABORT,'synthetic reference insert failure'); END''')
        body = self.story_body | {'revision':'1','mutation_id':str(uuid.uuid4()),
            'title':'Must roll back','contribution_refs':json.dumps([
                {'chapter_id':'chapter-1','contribution_ids':[ref]}])}
        failed = self.save(body,self.story,opt_in=True)
        self.assertEqual(failed.status_code,503)
        detail = self.f.client.get('/memory-stories/'+self.story+'?library=family-a',headers=self.headers).json()
        self.assertEqual((detail['revision'],detail['title']),('1','湖边的一天'))
        with self.f.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM access_memory_revisions WHERE story_id=?',(self.story,)).fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM access_memory_revisions WHERE mutation_id=?',(body['mutation_id'],)).fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM access_memory_contribution_refs WHERE story_id=?',(self.story,)).fetchone()[0],0)
            self.assertEqual(db.execute("SELECT count(*) FROM access_audit WHERE action='memory.edit'").fetchone()[0],0)

    def test_creation_requires_empty_refs_and_chapter_binding_is_enforced(self):
        accepted = self.contribution()
        create_with_ref = self.story_body | {'mutation_id':str(uuid.uuid4()),
            'contribution_refs':json.dumps([{'chapter_id':'chapter-1','contribution_ids':[accepted]}])}
        self.assertEqual(self.save(create_with_ref,opt_in=True).status_code,422)
        create_empty = self.story_body | {'mutation_id':str(uuid.uuid4()),
                                          'contribution_refs':'[]'}
        self.assertEqual(self.save(create_empty,opt_in=True).status_code,200)

        # Construct a two-chapter saved story using the same authorized media
        # snapshot. A chapter-bound source cannot be assigned to its sibling.
        original = json.loads(self.story_body['chapters'])[0]
        chapters = [
            original | {'id':'chapter-1','asset_ids':['101'],'evidence_ids':[]},
            original | {'id':'chapter-2','asset_ids':['102'],'evidence_ids':[]},
        ]
        split_body = self.story_body | {'chapters':json.dumps(chapters),
            'mutation_id':str(uuid.uuid4())}
        split = self.save(split_body)
        self.assertEqual(split.status_code,200,split.text)
        split_id = split.json()['id']
        bound = self.contribution(story=split_id,chapter_id='chapter-1')
        bad = split_body | {'revision':'1','mutation_id':str(uuid.uuid4()),
            'contribution_refs':json.dumps([{'chapter_id':'chapter-2','contribution_ids':[bound]}])}
        self.assertEqual(self.save(bad,split_id,opt_in=True).status_code,422)
        global_ref = self.contribution(story=split_id,chapter_id='')
        good = split_body | {'revision':'1','mutation_id':str(uuid.uuid4()),
            'contribution_refs':json.dumps([{'chapter_id':'chapter-2','contribution_ids':[global_ref]}])}
        self.assertEqual(self.save(good,split_id,opt_in=True).status_code,200)

    def test_parent_media_authorization_and_missing_additive_table(self):
        ref = self.contribution()
        body = self.story_body | {'revision':'1','mutation_id':str(uuid.uuid4()),
            'contribution_refs':json.dumps([{'chapter_id':'chapter-1','contribution_ids':[ref]}])}
        self.assertEqual(self.save(body,self.story,opt_in=True).status_code,200)
        self.assertIn(self.read_refs(2,library='family-b').status_code,(401,403))
        member = {'Authorization':'Bearer '+self.f.member_token}
        self.assertEqual(self.read_refs(2,token=self.f.member_token).status_code,200)
        self.f.mutate("UPDATE access_memberships SET status='revoked' WHERE account_id=?",
                      (fixture.LibraryReadTests.member_id,))
        self.assertEqual(self.read_refs(2,token=self.f.member_token).status_code,401)
        self.f.mutate("UPDATE access_asset_libraries SET library_id='family-b' WHERE asset_id=101")
        self.assertEqual(self.read_refs(2).status_code,401)
        self.f.mutate("UPDATE access_asset_libraries SET library_id='family-a' WHERE asset_id=101")
        self.f.mutate('DROP TABLE access_memory_contribution_refs')
        self.f.mutate("UPDATE alembic_version SET version_num='f7c3a9d2e614'")
        self.assertEqual(self.read_refs(2).status_code,503)
        self.assertEqual(self.read_refs().status_code,503)
        # Legacy v1 reads/saves stay available on the actual f7 schema.
        self.assertEqual(self.f.client.get('/memory-stories/'+self.story+'?library=family-a',headers=self.headers).status_code,200)
        legacy = self.story_body | {'revision':'2','mutation_id':str(uuid.uuid4())}
        self.assertEqual(self.save(legacy,self.story).status_code,200)
        refs_required = self.story_body | {'revision':'3','mutation_id':str(uuid.uuid4()),'contribution_refs':'[]'}
        self.assertEqual(self.save(refs_required,self.story,opt_in=True).status_code,503)

    def test_unavailable_contribution_is_filtered_and_not_carried_to_new_revision(self):
        ref = self.contribution()
        body = self.story_body | {'revision':'1','mutation_id':str(uuid.uuid4()),
            'contribution_refs':json.dumps([{'chapter_id':'chapter-1','contribution_ids':[ref]}])}
        self.assertEqual(self.save(body,self.story,opt_in=True).status_code,200)
        self.f.mutate("UPDATE access_memory_contributions SET state='declined' WHERE id=?",(ref,))
        self.assertEqual(self.read_refs(2).json()['chapters'][0]['contribution_ids'],[])
        legacy = self.story_body | {'revision':'2','mutation_id':str(uuid.uuid4())}
        self.assertEqual(self.save(legacy,self.story).status_code,200)
        self.assertEqual(self.read_refs(3).json()['chapters'][0]['contribution_ids'],[])
        with self.f.connection() as db:
            # The earlier immutable revision remains a record until original deletion.
            self.assertEqual(db.execute('''SELECT count(*) FROM access_memory_contribution_refs
                WHERE story_id=? AND revision=2 AND contribution_id=?''',(self.story,ref)).fetchone()[0],1)

    def test_a0_revision_with_tampered_multiple_heads_disables_reference_operation(self):
        with self.f.connection() as db:
            db.execute('DROP TABLE alembic_version')
            db.execute('CREATE TABLE alembic_version(version_num VARCHAR(32) NOT NULL)')
            db.executemany('INSERT INTO alembic_version VALUES(?)',
                           [('a0c9d2e4f817',),('f7c3a9d2e614',)])
            db.commit()
        body = self.story_body | {'revision':'1','mutation_id':str(uuid.uuid4()),'contribution_refs':'[]'}
        self.assertEqual(self.save(body,self.story,opt_in=True).status_code,503)

    def test_schema_downgrade_refuses_to_drop_persisted_references(self):
        ref = self.contribution()
        body = self.story_body | {'revision':'1','mutation_id':str(uuid.uuid4()),
            'contribution_refs':json.dumps([{'chapter_id':'chapter-1','contribution_ids':[ref]}])}
        self.assertEqual(self.save(body,self.story,opt_in=True).status_code,200)
        engine = create_engine('sqlite:///'+str(self.f.path))
        self.addCleanup(engine.dispose)
        schema_sql = "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
        with engine.connect() as connection:
            starting_revision = connection.exec_driver_sql('SELECT version_num FROM alembic_version').scalar_one()
            starting_schema = connection.exec_driver_sql(schema_sql).all()
            starting_refs = connection.exec_driver_sql('SELECT * FROM access_memory_contribution_refs').all()
        def downgrade():
            with engine.begin() as connection:
                cfg = migrations.config(); cfg.attributes['connection'] = connection
                command.downgrade(cfg,'f7c3a9d2e614')
        with self.assertRaisesRegex(RuntimeError,'reviewed offline backup restoration'):
            downgrade()
        with engine.begin() as connection:
            self.assertEqual(connection.exec_driver_sql('SELECT version_num FROM alembic_version').scalar_one(),starting_revision)
            self.assertEqual(connection.exec_driver_sql(schema_sql).all(),starting_schema)
            self.assertEqual(connection.exec_driver_sql('SELECT * FROM access_memory_contribution_refs').all(),starting_refs)
            self.assertEqual(connection.exec_driver_sql('SELECT count(*) FROM access_memory_contribution_refs').scalar_one(),1)
            connection.exec_driver_sql('DELETE FROM access_memory_contribution_refs')
        downgrade()
        with engine.connect() as connection:
            self.assertEqual(connection.exec_driver_sql('SELECT version_num FROM alembic_version').scalar_one(),'f7c3a9d2e614')

    def test_original_erasure_explicitly_removes_refs_across_revisions(self):
        ref = self.contribution()
        groups = json.dumps([{'chapter_id':'chapter-1','contribution_ids':[ref]}])
        body = self.story_body | {'revision':'1','mutation_id':str(uuid.uuid4()),
                                  'contribution_refs':groups}
        self.assertEqual(self.save(body,self.story,opt_in=True).status_code,200)
        with self.f.connection() as db:
            db.execute('''INSERT INTO access_memory_contribution_refs
                (story_id,revision,chapter_id,ordinal,contribution_id)
                VALUES(?,1,'chapter-1',0,?)''',(self.story,ref))
            db.commit()
            db.execute('PRAGMA foreign_keys=OFF')
            db.execute('PRAGMA secure_delete=ON')
            db.execute('BEGIN IMMEDIATE')
            erase_memory_original(db,ref,self.story,'family-a',self.f.now)
            db.commit()
            self.assertEqual(db.execute('SELECT count(*) FROM access_memory_contribution_refs WHERE contribution_id=?',(ref,)).fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM access_memory_contributions WHERE id=?',(ref,)).fetchone()[0],0)


    def linked_save(self, refs):
        body = self.story_body | {'revision':'1','mutation_id':str(uuid.uuid4()),
            'contribution_refs':json.dumps([{'chapter_id':'chapter-1','contribution_ids':refs}])}
        response = self.save(body,self.story,opt_in=True)
        self.assertEqual(response.status_code,200,response.text)

    def bundle(self, *, book=None):
        with self.f.connection() as db:
            access = AccessService(db,clock=lambda:self.f.now)
            member = access._require(self.f.member_token,'family-a','library.read')
            return context(access,'family-a',member,'book' if book else 'story',book or self.story)

    def test_current_links_keep_old_chapter_sources_in_story_and_memoir_context(self):
        linked = self.contribution()
        omitted = self.contribution()
        self.linked_save([linked])
        bundle, _, _ = self.bundle()
        sources = {item['id']:item for item in bundle['sources']}
        source_id = 'contribution-'+linked
        self.assertEqual(sources[source_id]['kind'],'family')
        self.assertEqual(sources[source_id]['text'],'那天大家都笑了。')
        self.assertNotIn('contribution-'+omitted,sources)
        self.assertIn(source_id,bundle['chapters'][0]['evidence_ids'])
        with self.f.connection() as db:
            access = AccessService(db,clock=lambda:self.f.now)
            book = MemoryBooks(access).save(self.f.owner_token,'family-a',{
                'title':'共同回忆','language':'zh','introduction':'','story_ids':self.story,
                'revision':'0','mutation_id':str(uuid.uuid4())})
        memoir, _, _ = self.bundle(book=book['id'])
        self.assertIn(source_id,memoir['chapters'][0]['evidence_ids'])
        self.assertEqual(memoir['sources'],bundle['sources'])
        # Historical references remain stored but never opt a removed source
        # into the latest chapter's context.
        clear = self.story_body | {'revision':'2','mutation_id':str(uuid.uuid4()),
                                  'contribution_refs':'[]'}
        self.assertEqual(self.save(clear,self.story,opt_in=True).status_code,200)
        current, _, _ = self.bundle()
        self.assertNotIn(source_id,{item['id'] for item in current['sources']})
        with self.f.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM access_memory_contribution_refs WHERE revision=2').fetchone()[0],1)

    def test_linked_sources_still_require_acceptance_consent_and_same_parent(self):
        linked = self.contribution()
        self.linked_save([linked])
        before, fingerprint, _ = self.bundle()
        self.assertIn('contribution-'+linked,{s['id'] for s in before['sources']})
        for statement in (
            "UPDATE access_memory_contributions SET local_processing_consent=0 WHERE id=?",
            "UPDATE access_memory_contributions SET local_processing_consent=1,state='declined' WHERE id=?",
            "UPDATE access_memory_contributions SET state='accepted',library_id='family-b' WHERE id=?",
        ):
            self.f.mutate(statement,(linked,))
            after, changed, _ = self.bundle()
            self.assertNotIn('contribution-'+linked,{s['id'] for s in after['sources']})
            self.assertNotEqual(changed,fingerprint)

    def test_linked_audio_uses_only_ready_transcript_and_never_raw_or_polished_text(self):
        linked = self.contribution()
        self.linked_save([linked])
        self.f.mutate("UPDATE access_memory_contributions SET kind='audio',original_text=NULL,original_audio=?,duration_ms=1000 WHERE id=?",(b'synthetic-not-decoded',linked))
        self.f.mutate("UPDATE access_memory_contribution_derivations SET state='waiting',transcript='not-ready',polished_text='editorial-polish' WHERE contribution_id=?",(linked,))
        waiting, _, _ = self.bundle()
        self.assertNotIn('contribution-'+linked,{s['id'] for s in waiting['sources']})
        self.f.mutate("UPDATE access_memory_contribution_derivations SET state='ready',transcript='AI 转写原话' WHERE contribution_id=?",(linked,))
        ready, _, _ = self.bundle()
        source = next(s for s in ready['sources'] if s['id']=='contribution-'+linked)
        self.assertEqual((source['kind'],source['text'],source['author']),('transcript','AI 转写原话','synthetic'))
        self.assertNotIn('editorial-polish',json.dumps(ready))
        self.assertNotIn('synthetic-not-decoded',json.dumps(ready))

    def test_link_removal_during_narration_discards_output_without_editing_story(self):
        linked = self.contribution()
        self.linked_save([linked])
        with self.f.connection() as db:
            queued = MemoryJobs(AccessService(db,clock=lambda:self.f.now)).narrative(
                self.f.owner_token,'family-a','story',self.story,'2',str(uuid.uuid4()),'')
        outer = self
        class Narrator:
            def narrative(self,bundle):
                outer.assertIn('contribution-'+linked,bundle['chapters'][0]['evidence_ids'])
                outer.f.mutate('DELETE FROM access_memory_contribution_refs WHERE story_id=? AND revision=2',(outer.story,))
                return {'version':1,'title':'必须丢弃的草稿','chapters':[{
                    'id':'chapter-1','narration':'来源已移除','source_ids':['contribution-'+linked]}],
                    'questions':[],'needs_review':True}
        with self.f.connection() as db:
            result = process_job(db,narrator=Narrator(),clock=lambda:self.f.now)
            job = db.execute('SELECT state,output_json,error_code FROM access_memory_jobs WHERE id=?',(queued['id'],)).fetchone()
            raw = db.execute('SELECT revision,content FROM access_memory_stories WHERE id=?',(self.story,)).fetchone()
            controls = db.execute('SELECT input_json FROM access_memory_jobs WHERE id=?',(queued['id'],)).fetchone()[0]
        self.assertEqual(result,{'id':queued['id'],'state':'stale'})
        self.assertEqual(tuple(job),('stale',None,'source_changed'))
        self.assertEqual(raw[0],2)
        self.assertNotIn('来源已移除',raw[1])
        self.assertNotIn('那天大家都笑了',controls)

    def test_f7_context_never_reads_unexpected_source_ref_table(self):
        linked = self.contribution()
        self.linked_save([linked])
        self.f.mutate("UPDATE alembic_version SET version_num='f7c3a9d2e614'")
        with self.f.connection() as db:
            # If the feature queried the table on f7, this deliberately renamed
            # column would fail. The explicit schema ledger keeps it disabled.
            db.execute('ALTER TABLE access_memory_contribution_refs RENAME COLUMN contribution_id TO ignored_on_f7')
            db.commit()
        bundle, _, _ = self.bundle()
        self.assertNotIn('contribution-'+linked,{s['id'] for s in bundle['sources']})


if __name__ == '__main__': unittest.main()
