"""Private, read-only upload preparation evidence contract."""
from contextlib import closing
from unittest.mock import patch
import json
import unittest

import test_upload as fixture


class UploadPreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): fixture.UploadTests.setUpClass()

    @classmethod
    def tearDownClass(cls): fixture.UploadTests.tearDownClass()

    def setUp(self):
        self.f = fixture.UploadTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.client = self.f.client()
        self.headers = {'Authorization': 'Bearer ' + self.f.member_token}

    def get(self, path='/upload-preparation', **kwargs):
        return self.client.get(path, headers=kwargs.pop('headers', self.headers), **kwargs)

    def mutate(self, sql, args=()):
        with closing(self.f.connection()) as db:
            db.execute(sql, args); db.commit()

    def accepted(self, pad=b''):
        return self.f.upload(fixture.png(64, 64, pad))['asset_id']

    def available(self, asset_id):
        self.mutate("UPDATE access_uploads SET state='assigned' WHERE asset_id=?", (asset_id,))
        self.mutate("INSERT INTO access_asset_libraries VALUES (?,'family-a')", (asset_id,))
        self.mutate("UPDATE tasks SET state='pending' WHERE state='awaiting_review' AND json_extract(payload_json,'$.asset_id')=?", (int(asset_id),))

    def add_task(self, task_type, asset_id, state, payload=None, error=None):
        payload = {'asset_id': int(asset_id)} if payload is None else payload
        self.mutate('''INSERT INTO tasks(type,payload_json,state,priority,retry_count,cancel_requested,
            scheduled_at,last_error) VALUES (?,?,?,1,0,0,datetime('now'),?)''',
            (task_type, json.dumps(payload), state, error))

    def test_old_upload_history_keeps_exact_v69_shape_and_values(self):
        aid = self.accepted()
        old = self.get('/uploads').json()
        self.assertEqual({'page', 'page_size', 'total', 'items'}, set(old))
        self.assertEqual({'asset_id', 'created_at', 'bytes', 'kind', 'state', 'library_id'},
                         set(old['items'][0]))
        self.assertEqual({'page': 1, 'page_size': 10, 'total': 1, 'items': [{
            'asset_id': aid, 'created_at': fixture.NOW, 'bytes': len(fixture.png(64, 64)),
            'kind': 'image', 'state': 'awaiting_review', 'library_id': None}]}, old)

    def test_own_paging_and_available_item_safe_shape(self):
        ids = [self.accepted(str(i).encode()) for i in range(12)]
        self.f.upload(fixture.png(64, 64, b'other account'), token=self.f.owner_token)
        self.available(ids[-1])
        first, second = self.get().json(), self.get('/upload-preparation?page=2').json()
        self.assertEqual((1, 10, 12), (first['page'], first['page_size'], first['total']))
        self.assertEqual(ids[::-1][:10], [r['asset_id'] for r in first['items']])
        self.assertEqual(ids[::-1][10:], [r['asset_id'] for r in second['items']])
        item = next(x for x in first['items'] if x['asset_id'] == ids[-1])
        self.assertEqual({'asset_id', 'created_at', 'bytes', 'kind', 'state', 'library_id', 'processing'}, set(item))
        self.assertEqual('available', item['state'])
        self.assertEqual({'preview': 'pending', 'index': 'pending', 'faces': 'pending',
                          'caption': 'pending', 'video_probe': 'not_applicable'},
                         item['processing']['stages'])
        self.assertEqual({'image_vector': False, 'caption': False, 'face_detections': False},
                         item['processing']['records'])
        self.assertEqual({'preview': 'unknown', 'playback': 'not_applicable'},
                         item['processing']['availability'])
        self.assertEqual(200, self.get('/upload-preparation?page=100000').status_code)
        self.assertEqual([], self.get('/upload-preparation?page=100000').json()['items'])

    def test_latest_task_id_wins_and_record_flags_are_existence_only(self):
        aid = self.accepted(); self.available(aid)
        self.add_task('thumb', aid, 'finished')
        self.add_task('thumb', aid, 'pending', error='private secret path')
        self.add_task('embed', aid, 'finished', {'asset_id': int(aid), 'modality': 'image'})
        self.add_task('face', aid, 'failed')
        self.add_task('caption', aid, 'running')
        self.mutate("INSERT INTO embeddings(asset_id,modality,model,dim,storage_path) VALUES (?,'image','secret-model',2,'secret-path')", (aid,))
        self.mutate("INSERT INTO captions(asset_id,text,model,superseded) VALUES (?,'secret caption','secret-model',0)", (aid,))
        self.mutate("INSERT INTO face_detections(asset_id,bbox_x,bbox_y,bbox_w,bbox_h) VALUES (?,0,0,1,1)", (aid,))
        result = self.get()
        self.assertEqual(200, result.status_code)
        item = result.json()['items'][0]
        self.assertEqual({'preview': 'pending', 'index': 'finished', 'faces': 'failed',
                          'caption': 'running', 'video_probe': 'not_applicable'},
                         item['processing']['stages'])
        self.assertEqual({'image_vector': True, 'caption': True, 'face_detections': True},
                         item['processing']['records'])
        for private in ('secret', 'path', 'model', 'last_error', 'payload_json', 'task_id'):
            self.assertNotIn(private, result.text)
        self.assertEqual('no-store', result.headers['cache-control'])

    def test_malformed_payload_extra_fields_and_unknown_states_fail_closed(self):
        aid = self.accepted(); self.available(aid)
        self.add_task('thumb', aid, 'mystery')
        self.add_task('caption', aid, 'finished', {'asset_id': int(aid), 'private': 'unexpected'})
        self.add_task('embed', aid, 'finished', {'asset_id': int(aid), 'modality': 'video'})
        item = self.get().json()['items'][0]
        self.assertEqual('unknown', item['processing']['stages']['preview'])
        self.assertEqual('unknown', item['processing']['stages']['caption'])
        self.assertEqual('unknown', item['processing']['stages']['index'])

    def test_unavailable_receipts_revoked_access_and_deleted_assets_have_no_processing(self):
        aid = self.accepted()
        result = self.get().json()['items'][0]
        self.assertEqual('awaiting_review', result['state']); self.assertIsNone(result['processing'])
        self.available(aid)
        self.mutate("UPDATE access_memberships SET status='revoked' WHERE account_id=?", (self.f.member_id,))
        self.assertEqual(401, self.get().status_code)

    def test_unavailable_inaccessible_or_missing_asset_does_not_expose_processing(self):
        aid = self.accepted(); self.available(aid)
        self.mutate("INSERT INTO access_libraries(id,state,bootstrap_operator) SELECT 'private-other','active',bootstrap_operator FROM access_libraries WHERE id='family-a'")
        self.mutate("UPDATE access_asset_libraries SET library_id='private-other' WHERE asset_id=?", (aid,))
        result = self.get().json()['items'][0]
        self.assertEqual('unavailable', result['state']); self.assertIsNone(result['library_id'])
        self.assertIsNone(result['processing'])
        self.assertNotIn('private-other', json.dumps(result))

        # Simulate a legacy orphan receipt, without changing the route's live snapshot.
        with closing(self.f.connection()) as db:
            db.execute('PRAGMA foreign_keys=OFF')
            db.execute('DELETE FROM assets WHERE id=?', (aid,)); db.commit()
        result = self.get().json()
        self.assertEqual(1, result['total'])
        self.assertEqual([], result['items'])

    def test_page_query_is_closed_and_duplicate_refused(self):
        for suffix in ('?page=0', '?page=-1', '?page=100001', '?page=x',
                       '?page=1&page=2', '?account_id=other', '?library=family-a', '?token=secret'):
            self.assertEqual(400, self.get('/upload-preparation' + suffix).status_code, suffix)
        self.assertEqual(401, self.get(headers={}).status_code)
        self.assertEqual(403, self.client.post('/upload-preparation', headers=self.headers).status_code)
        self.assertEqual(403, self.client.head('/upload-preparation', headers=self.headers).status_code)

    def test_read_has_no_filesystem_or_database_side_effects(self):
        aid = self.accepted(); self.available(aid)
        before_tasks = [tuple(r) for r in self.f.rows('SELECT * FROM tasks ORDER BY id')]
        before_receipts = [tuple(r) for r in self.f.rows('SELECT * FROM access_uploads ORDER BY id')]
        original_stat = fixture.Path.stat
        def no_media_stat(path, *args, **kwargs):
            if path.is_relative_to(self.f.incoming) or path.is_relative_to(self.f.originals):
                raise AssertionError('No media IO')
            return original_stat(path, *args, **kwargs)
        with patch('pathlib.Path.stat', no_media_stat):
            response = self.get()
        self.assertEqual(200, response.status_code)
        self.assertEqual(before_tasks, [tuple(r) for r in self.f.rows('SELECT * FROM tasks ORDER BY id')])
        self.assertEqual(before_receipts, [tuple(r) for r in self.f.rows('SELECT * FROM access_uploads ORDER BY id')])

    def test_video_reports_only_probe_and_no_image_only_readiness(self):
        # Exercise the projection with a synthetic safe video receipt, without media bytes.
        aid = self.accepted()
        self.available(aid)
        self.mutate("UPDATE assets SET mime='video/mp4' WHERE id=?", (aid,))
        self.mutate("UPDATE access_uploads SET bytes=1024 WHERE asset_id=?", (aid,))
        self.add_task('video_probe', aid, 'finished')
        self.add_task('video_embed', aid, 'finished')
        self.add_task('video_embed', aid, 'failed', error='private video-index path')
        self.add_task('embed', aid, 'finished', {'asset_id': int(aid), 'modality': 'image'})
        self.add_task('caption', aid, 'finished')
        item = self.get().json()['items'][0]
        self.assertEqual({'preview': 'unknown', 'index': 'failed', 'faces': 'not_applicable',
                          'caption': 'finished', 'video_probe': 'finished'}, item['processing']['stages'])
        self.assertEqual({'preview': 'unknown', 'playback': 'unknown'}, item['processing']['availability'])


if __name__ == '__main__': unittest.main()
