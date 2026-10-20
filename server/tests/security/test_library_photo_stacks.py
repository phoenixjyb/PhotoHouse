"""Actual indexed gallery and private choices against fully migrated fixtures."""
from contextlib import closing
import json
import re
import sqlite3
import unittest
from unittest.mock import patch
import test_library_reads as fixture
from app.access.library_photo_stacks import LibraryPhotoStacks, rebuild_photo_stack_index
from app.access.service import AccessService, Conflict


class LibraryPhotoStacksTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture=fixture.LibraryReadTests;cls.fixture.setUpClass()
    @classmethod
    def tearDownClass(cls):cls.fixture.tearDownClass()
    def setUp(self):
        self.f=self.fixture();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.token=self.f.member_token
        with self.f.connection() as db:
            db.execute("UPDATE assets SET taken_at='2026-04-05 12:00:00',perceptual_hash=? WHERE id IN(101,102)",('0'*16,));db.commit()
        self.build()
    def build(self,expected=None):
        with self.f.connection() as db:
            self.built=rebuild_photo_stack_index(db,'family-a',expected_generation=expected)
        return self.built
    def headers(self,token):return {"Authorization":"Bearer "+token}
    def get(self,token=None,**query):
        return self.f.client.get('/photo-stacks/gallery',params={'library':'family-a',**query},headers=self.headers(token or self.token))
    def body(self,**values):
        page=self.get().json();e=page['photo_stacks']
        return {'index_revision':e['index_revision'],'revision':str(e['preference_revision']),
                'group_id':'101','cover_asset_id':'','separate_asset_id':'','reset':'0',**values}
    def post(self,body,token=None):
        return self.f.client.post('/photo-stacks/preferences?library=family-a',json=body,headers=self.headers(token or self.token))

    def test_complete_group_one_position_and_unchanged_old_gallery(self):
        value=self.get().json();self.assertEqual((value['page_size'],value['total']), (12,1))
        self.assertEqual({a['id'] for a in value['items']},{'101','102'})
        self.assertEqual(value['photo_stacks']['groups'][0]['count'],2)
        normal=self.f.client.get('/assets?library=family-a&page_size=1&photo_stacks=1',headers=self.headers(self.token)).json()
        self.assertEqual(normal['total'],2);self.assertEqual(normal['photo_stacks']['scope'],'page')
        for secret in ['perceptual_hash','private-provider-error','private-synthetic','account_id','batch','source_digest']:
            self.assertNotIn(secret,json.dumps(value))

    def test_cross_page_group_is_not_split_or_duplicated(self):
        with self.f.connection() as db:
            for ident in range(1000,1013):
                db.execute("INSERT INTO assets(id,path,hash_sha256,status,mime,taken_at) VALUES(?,?,?,'active','image/jpeg',?)",(ident,f'x/{ident}',f'h{ident}',f'2026-05-{ident-999:02} 12:00:00'))
                db.execute('INSERT INTO access_asset_libraries VALUES (?,?)',(ident,'family-a'))
            db.commit()
        self.build(self.built['index_revision'])
        first=self.get(page='1').json();second=self.get(page='2').json()
        self.assertEqual((first['total'],second['total']), (14,14))
        self.assertEqual(first['photo_stacks']['groups'],[])
        self.assertEqual(second['photo_stacks']['groups'][0]['asset_ids'],['102','101'])
        allids=[a['id'] for p in [first,second] for a in p['items']]
        self.assertEqual(len(allids),15);self.assertEqual(len(set(allids)),15)

    def test_private_cover_survives_refresh_and_unchanged_rebuild(self):
        result=self.post(self.body(cover_asset_id='101'));self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(self.get().json()['photo_stacks']['groups'][0]['cover_asset_id'],'101')
        self.assertEqual(self.get(token=self.f.owner_token).json()['photo_stacks']['groups'][0]['cover_asset_id'],'102')
        same=self.build(self.built['index_revision']);self.assertFalse(same['changed'])
        self.assertEqual(self.get().json()['photo_stacks']['groups'][0]['cover_asset_id'],'101')

    def test_saved_cover_survives_new_similar_member_when_still_eligible(self):
        self.post(self.body(cover_asset_id='101'))
        with self.f.connection() as db:
            db.execute("INSERT INTO assets(id,path,hash_sha256,status,mime,taken_at,perceptual_hash) VALUES(104,'x/104','h104','active','image/jpeg','2026-04-05 12:00:00',?)",('0'*16,))
            db.execute("INSERT INTO access_asset_libraries VALUES(104,'family-a')");db.commit()
        self.build(self.built['index_revision'])
        group=self.get().json()['photo_stacks']['groups'][0]
        self.assertEqual(group['count'],3);self.assertEqual(group['cover_asset_id'],'101')

    def test_separate_and_reset_do_not_change_another_member_or_originals(self):
        self.assertEqual(self.post(self.body(separate_asset_id='101')).status_code,200)
        page=self.get().json();self.assertEqual(page['total'],2);self.assertEqual(page['photo_stacks']['groups'],[])
        self.assertEqual(self.get(token=self.f.owner_token).json()['total'],1)
        self.assertEqual(self.post(self.body(group_id='',reset='1')).status_code,200)
        self.assertEqual(self.get().json()['total'],1)
        with self.f.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM assets WHERE id IN(101,102)').fetchone()[0],2)

    def test_separating_original_anchor_keeps_remaining_group_stable(self):
        with self.f.connection() as db:
            db.execute("INSERT INTO assets(id,path,hash_sha256,status,mime,taken_at,perceptual_hash) VALUES(104,'x/104','h104','active','image/jpeg','2026-04-05 12:00:00',?)",('0'*16,))
            db.execute("INSERT INTO access_asset_libraries VALUES(104,'family-a')");db.commit()
        self.build(self.built['index_revision'])
        self.post(self.body(separate_asset_id='101'))
        group=self.get().json()['photo_stacks']['groups'][0]
        self.assertEqual(group['id'],'101');self.assertEqual(set(group['asset_ids']),{'102','104'})

    def test_preference_revision_and_index_revision_reject_stale_writes(self):
        body=self.body(cover_asset_id='101')
        self.assertEqual(self.post(body).status_code,200)
        self.assertEqual(self.post(body).status_code,409)
        body=self.body(cover_asset_id='102')
        with self.f.connection() as db:db.execute("UPDATE assets SET width=800 WHERE id=101");db.commit()
        self.build(self.built['index_revision'])
        self.assertEqual(self.post(body).status_code,409)

    def test_stale_similarity_dissolves_group_and_refuses_old_choice(self):
        for column,value in [('perceptual_hash','f'*16),('taken_at','2026-04-07 12:00:00'),('mime','video/mp4')]:
            with self.subTest(column=column),self.f.connection() as db:
                old=db.execute('SELECT '+column+' FROM assets WHERE id=101').fetchone()[0]
                db.execute('UPDATE assets SET '+column+'=? WHERE id=101',(value,));db.commit()
                self.assertEqual(self.get().json()['photo_stacks']['groups'],[])
                self.assertEqual(self.post(self.body(cover_asset_id='102')).status_code,409)
                db.execute('UPDATE assets SET '+column+'=? WHERE id=101',(old,));db.commit()

    def test_moved_or_suppressed_member_never_leaks_or_hides_remaining(self):
        with self.f.connection() as db:
            db.execute("UPDATE access_asset_libraries SET library_id='family-b' WHERE asset_id=101");db.commit()
        page=self.get().json();self.assertEqual([a['id'] for a in page['items']],['102']);self.assertEqual(page['total'],1)
        self.assertEqual(page['photo_stacks']['groups'],[])
        with self.f.connection() as db:db.execute("UPDATE assets SET status='suppressed' WHERE id=102");db.commit()
        self.assertEqual(self.get().json()['items'],[])

    def test_new_unindexed_assets_stay_visible(self):
        with self.f.connection() as db:
            db.execute("INSERT INTO assets(id,path,hash_sha256,status,mime,taken_at) VALUES(104,'x/104','h104','active','image/jpeg','2026-06-01')")
            db.execute("INSERT INTO access_asset_libraries VALUES(104,'family-a')");db.commit()
        page=self.get().json();self.assertEqual(page['total'],2);self.assertEqual(len(page['items']),3)

    def test_access_rechecked_before_optional_schema_and_each_write(self):
        self.assertEqual(self.f.client.get('/photo-stacks/gallery?library=family-b',headers=self.headers(self.token)).status_code,401)
        body=self.body(cover_asset_id='101')
        with self.f.connection() as db:
            db.execute("UPDATE access_memberships SET status='revoked' WHERE account_id=? AND library_id='family-a'",(self.f.member_id,));db.commit()
        self.assertEqual(self.get().status_code,401);self.assertEqual(self.post(body).status_code,401)

    def test_optional_index_missing_and_invalid_input(self):
        with self.f.connection() as db:db.execute("DELETE FROM access_photo_stack_indexes WHERE library_id='family-a'");db.commit()
        self.assertEqual(self.get().status_code,404)
        self.assertEqual(self.get(page='0').status_code,400)
        self.assertEqual(self.get(page_size='12').status_code,400)
        self.assertEqual(self.get(media='video').status_code,400)

    def test_read_only_get_never_rebuilds_or_persists_preferences(self):
        self.f.trace.clear()
        self.assertEqual(self.get().status_code,200)
        self.assertFalse(any(re.match(r'\s*(INSERT|UPDATE|DELETE|CREATE)',q,re.I) for q in self.f.trace if 'photo_stack' in q))

    def test_worker_refreshes_new_media_and_preserves_saved_choices(self):
        from app.access.photo_stack_worker import PhotoStackRefreshWorker
        worker=PhotoStackRefreshWorker(self.f.connection,('family-a',))
        self.assertEqual(worker.run_once()[0]['status'],'unchanged')
        self.post(self.body(cover_asset_id='101'))
        with self.f.connection() as db:
            db.execute("INSERT INTO assets(id,path,hash_sha256,status,mime,taken_at,perceptual_hash) VALUES(104,'x/104','h104','active','image/jpeg','2026-04-05 12:00:00',?)",('0'*16,))
            db.execute("INSERT INTO access_asset_libraries VALUES(104,'family-a')");db.commit()
        self.assertEqual(worker.run_once()[0]['status'],'updated')
        self.assertEqual(self.get().json()['photo_stacks']['groups'][0]['cover_asset_id'],'101')
        self.assertEqual(worker.run_once()[0]['status'],'unchanged')
        self.assertEqual(PhotoStackRefreshWorker(self.f.connection,('family-a',),stopped=lambda:True).run_once(),[])

    def test_worker_waits_only_for_runnable_scoped_hash_tasks_and_retains_failures(self):
        from app.access.photo_stack_worker import PhotoStackRefreshWorker
        worker=PhotoStackRefreshWorker(self.f.connection,('family-a',))
        with self.f.connection() as db:
            db.execute("INSERT INTO tasks(type,payload_json,state,cancel_requested) VALUES('phash',?,'pending',0)",
                       (json.dumps({'asset_id':101}),));db.commit()
        self.assertEqual(worker.run_once()[0]['status'],'waiting')
        with self.f.connection() as db:
            db.execute("UPDATE tasks SET state='failed',retry_count=3,last_error='retained failure' WHERE type='phash'");db.commit()
        self.assertEqual(worker.run_once()[0]['status'],'unchanged')
        with self.f.connection() as db:
            self.assertEqual(db.execute("SELECT state,retry_count,last_error FROM tasks WHERE type='phash'").fetchone(),
                             ('failed',3,'retained failure'))
            db.execute("UPDATE tasks SET state='pending',scheduled_at='2999-01-01 00:00:00'");db.commit()
        self.assertEqual(worker.run_once()[0]['status'],'unchanged')
        with self.f.connection() as db:
            db.execute("UPDATE tasks SET state='running',payload_json=?",(json.dumps({'asset_id':201}),));db.commit()
        self.assertEqual(worker.run_once()[0]['status'],'unchanged')

    def test_cookie_preference_write_requires_origin_and_csrf(self):
        from app.access.transport import COOKIE,csrf_token
        body=self.body(cover_asset_id='101')
        self.f.client.cookies.set(COOKIE,self.token)
        for headers in ({},{'Origin':'https://photohouse.test'},
                        {'Origin':'https://evil.test','X-CSRF-Token':csrf_token(self.token)}):
            self.assertEqual(self.f.client.post('/photo-stacks/preferences?library=family-a',json=body,headers=headers).status_code,403)
        response=self.f.client.post('/photo-stacks/preferences?library=family-a',json=body,
            headers={'Origin':'https://photohouse.test','X-CSRF-Token':csrf_token(self.token)})
        self.assertEqual(response.status_code,200,response.text)

    def test_invalid_choices_never_write_and_corrupt_saved_choices_fail_closed(self):
        body=self.body(cover_asset_id='101')
        for changes in ({'revision':0},{'reset':'1'},{'cover_asset_id':'201'},
                        {'separate_asset_id':'102'},{'unexpected':'value'}):
            with self.subTest(changes=changes):
                self.assertIn(self.post({**body,**changes}).status_code,(400,409))
        with self.f.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM access_photo_stack_preferences').fetchone()[0],0)
            db.execute("INSERT INTO access_photo_stack_preferences VALUES('family-a',?,1,?,0)",
                       (self.f.member_id,json.dumps({'covers':{},'separate':[['bad']]})));db.commit()
        self.assertEqual(self.get().status_code,503)
        self.assertEqual(self.get(token=self.f.owner_token).status_code,200)

    def test_live_read_cap_falls_back_without_hiding_an_ordinary_gallery(self):
        with patch('app.access.library_photo_stacks.MAX_ASSETS',1):
            self.assertEqual(self.get().status_code,404)
        self.assertEqual(self.f.get('/assets?library=family-a').status_code,200)

    def test_read_budget_aborts_and_is_cleared_before_next_request(self):
        with self.f.connection() as db:
            domain=LibraryPhotoStacks(AccessService(db,clock=lambda:self.f.now))
            with patch('app.access.library_photo_stacks.time.monotonic',side_effect=[0]+[100]*1000):
                from app.access.transport import TransportError
                with self.assertRaises(TransportError) as caught:domain.gallery(self.token,'family-a')
                self.assertEqual(caught.exception.status,503)
            self.assertEqual(domain.gallery(self.token,'family-a')['total'],1)

    def test_multiple_group_tiles_do_not_repeat_the_library_scan(self):
        with self.f.connection() as db:
            for i in range(26):
                ident=1000+i
                db.execute("INSERT INTO assets(id,path,hash_sha256,status,mime,taken_at,perceptual_hash) VALUES(?,?,?,'active','image/jpeg',?,?)",
                           (ident,f'x/{ident}',f'h{ident}',f'2026-05-{i//2+1:02d} 12:00:00','0'*16))
                db.execute("INSERT INTO access_asset_libraries VALUES(?,'family-a')",(ident,))
            db.commit()
        self.build(self.built['index_revision']);self.f.trace.clear()
        self.assertEqual(len(self.get().json()['photo_stacks']['groups']),12)
        scans=[q for q in self.f.trace if q.startswith('WITH live(')]
        self.assertEqual(len(scans),1)

    def test_index_builder_refuses_bound_primary_without_current_deletion_history(self):
        from app.access.runtime import AccessConnection
        with self.f.connection() as db:
            db.execute('INSERT INTO access_original_deletion_state(id,namespace,applied_seq,applied_digest) VALUES(1,?,0,?)',
                       ('123e4567-e89b-42d3-a456-426614174000','0'*64));db.commit()
            with self.assertRaisesRegex(ValueError,'deletion_history_guard_required'):
                rebuild_photo_stack_index(db,'family-a',expected_generation=self.built['index_revision'])
            self.assertFalse(db.in_transaction)
            self.assertEqual(db.execute('SELECT generation FROM access_photo_stack_indexes').fetchone()[0],self.built['index_revision'])
        class StaleGuard:
            def assert_current(self,db):raise RuntimeError('Synthetic stale deletion history')
        with closing(sqlite3.connect(self.f.path,factory=AccessConnection)) as db:
            db.execute('PRAGMA foreign_keys=ON');db.original_deletions=StaleGuard()
            with self.assertRaisesRegex(RuntimeError,'Synthetic stale deletion history'):
                rebuild_photo_stack_index(db,'family-a',expected_generation=self.built['index_revision'])
            self.assertFalse(db.in_transaction)
            self.assertEqual(db.execute('SELECT generation FROM access_photo_stack_indexes').fetchone()[0],self.built['index_revision'])

    def test_optimistic_builder_preserves_previous_index_when_source_changes(self):
        from app.access.photo_stack_index import build_library_photo_stacks
        with self.f.connection() as db:db.execute('UPDATE assets SET width=800 WHERE id=101');db.commit()
        def changed(rows):
            with closing(sqlite3.connect(self.f.path)) as db:
                db.execute('UPDATE assets SET width=900 WHERE id=101');db.commit()
            return build_library_photo_stacks(rows)
        with self.f.connection() as db,patch('app.access.photo_stack_index.build_library_photo_stacks',side_effect=changed):
            with self.assertRaises(Conflict):rebuild_photo_stack_index(db,'family-a',expected_generation=self.built['index_revision'])
        self.assertEqual(self.get().json()['photo_stacks']['index_revision'],self.built['index_revision'])


if __name__=='__main__':unittest.main()
