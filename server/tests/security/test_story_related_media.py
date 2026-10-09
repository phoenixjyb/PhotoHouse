"""Protected, read-only related-media candidates over synthetic library metadata."""
import json
import unittest

import test_library_reads as fixture
from app.access.boundary import ClosedBoundary
from app.access.transport import COOKIE, csrf_token


class StoryRelatedMediaTests(unittest.TestCase):
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

    def request(self, *, asset_ids='101', before_id='', library='family-a', headers=None, raw=None):
        selected_headers = dict(self.headers if headers is None else headers)
        if raw is not None:
            selected_headers.setdefault('Content-Type', 'application/json')
        return self.client.post('/story-workspace/related-media?library=' + library,
            headers=selected_headers,
            content=raw if raw is not None else None,
            json=None if raw is not None else {'asset_ids': asset_ids, 'before_id': before_id})

    def add_asset(self, ident, *, day, mime='image/jpeg', library='family-a', status='active', path=None):
        self.f.mutate('''INSERT INTO assets(id,path,hash_sha256,status,mime,width,height,taken_at)
            VALUES (?,?,?,?,?,640,480,?)''',
            (ident, path or f'private-synthetic/{ident}.jpg', f'private-hash-{ident}',
             status, mime, day))
        if library is not None:
            self.f.mutate('INSERT INTO access_asset_libraries VALUES (?,?)', (ident, library))

    def test_authorized_same_day_photo_and_video_are_safe_review_candidates(self):
        self.add_asset(110, day='2026-01-01T23:40:00-08:00', mime='video/mp4')
        self.add_asset(111, day='2026-01-01 08:00:00', mime='image/jpeg')
        self.add_asset(112, day='2026-01-02')
        self.f.trace.clear()

        response = self.request()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers['cache-control'], 'no-store')
        result = response.json()
        self.assertEqual(result['version'], 1)
        self.assertEqual(result['library_id'], 'family-a')
        self.assertEqual(result['seed_asset_ids'], ['101'])
        self.assertEqual(result['recorded_days'], ['2026-01-01'])
        self.assertTrue(result['needs_review'])
        self.assertFalse(result['has_more'])
        self.assertIsNone(result['next_before_id'])
        self.assertEqual([item['id'] for item in result['items']], ['111', '110'])
        self.assertEqual([item['kind'] for item in result['items']], ['image', 'video'])
        self.assertTrue(all(item['match_reason'] == 'same_recorded_capture_day' for item in result['items']))
        self.assertTrue(all(set(item) == {'id','kind','width','height','duration_sec','taken_at',
                                          'thumbnail_url','match_reason'} for item in result['items']))
        self.assertNotIn('private-synthetic', response.text)
        self.assertNotIn('private-hash', response.text)
        self.assertNotIn('caption-', response.text)
        self.assertFalse(any(sql.lstrip().upper().startswith(('INSERT','UPDATE','DELETE'))
                             for sql in self.f.trace))

    def test_all_seeds_must_be_current_active_and_mapped_before_candidates_are_read(self):
        self.add_asset(113, day='2026-01-01')
        for seed in ('201', '103', '999', '123456'):
            with self.subTest(seed=seed):
                self.f.trace.clear()
                response = self.request(asset_ids='101,' + seed)
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json(), {'detail': 'Access denied'})
                self.assertFalse(any('ORDER BY a.id DESC LIMIT' in sql for sql in self.f.trace))
        self.assertEqual(self.request(library='family-b').status_code, 401)
        self.assertEqual(self.request(headers={}).status_code, 401)

    def test_only_valid_recorded_dates_match_and_date_hints_never_supply_days(self):
        self.add_asset(114, day='2026-01-01garbage')
        self.add_asset(115, day='2026-01-01T25:00:00')
        self.add_asset(116, day='2026-01-01T08:00:00Z')

        self.f.mutate("UPDATE assets SET taken_at=NULL,path='private-synthetic/2026-01-01.jpg' WHERE id=101")
        no_recorded_date = self.request().json()
        self.assertEqual(no_recorded_date['recorded_days'], [])
        self.assertEqual(no_recorded_date['items'], [])

        self.f.mutate("UPDATE assets SET path='private-synthetic/unknown.jpg' WHERE id=101")
        self.f.mutate('''INSERT INTO access_uploads(id,asset_id,account_id,incoming_label,
            batch,original_name,sha256,bytes,state,created_at,destination_library_id)
            VALUES (1,101,?,'synthetic-member',?,'unknown.jpg',?,10,'assigned',1767225600,'family-a')''',
            (self.f.member_id, 'a' * 32, 'b' * 64))
        received_only = self.request().json()
        self.assertEqual(received_only['recorded_days'], [])
        self.assertEqual(received_only['items'], [])

        self.f.mutate("UPDATE assets SET taken_at='2026-02-30',path='private-synthetic/mmexport1700000000000.jpg' WHERE id=101")
        invalid_seed = self.request().json()
        self.assertEqual(invalid_seed['recorded_days'], [])
        self.assertEqual(invalid_seed['items'], [])

        self.f.mutate("UPDATE assets SET taken_at='2026-01-01' WHERE id=101")
        valid_seed = self.request().json()
        self.assertEqual([item['id'] for item in valid_seed['items']], ['116'])

    def test_keyset_pages_are_descending_and_capped_at_twenty_items(self):
        for ident in range(120, 145):
            self.add_asset(ident, day='2026-01-01')
        first = self.request().json()
        self.assertEqual(len(first['items']), 20)
        self.assertEqual([item['id'] for item in first['items']],
                         [str(ident) for ident in range(144, 124, -1)])
        self.assertTrue(first['has_more'])
        self.assertEqual(first['next_before_id'], '125')
        second = self.request(before_id=first['next_before_id']).json()
        self.assertEqual([item['id'] for item in second['items']],
                         [str(ident) for ident in range(124, 119, -1)])
        self.assertFalse(second['has_more'])
        self.assertIsNone(second['next_before_id'])

    def test_invalid_prefix_rows_advance_the_bounded_scan_cursor(self):
        for ident in range(1002, 1082):
            self.add_asset(ident, day='2026-01-01garbage')
        self.add_asset(1001, day='2026-01-01T08:00:00')
        first = self.request().json()
        self.assertEqual(first['items'], [])
        self.assertTrue(first['has_more'])
        self.assertEqual(first['next_before_id'], '1002')
        second = self.request(before_id=first['next_before_id']).json()
        self.assertEqual([item['id'] for item in second['items']], ['1001'])
        self.assertFalse(second['has_more'])
        self.assertIsNone(second['next_before_id'])

    def test_cookie_csrf_body_bounds_and_closed_boundary(self):
        headers = {'Cookie': COOKIE + '=' + self.f.member_token,
                   'Origin': 'https://photohouse.test'}
        self.assertEqual(self.request(headers=headers).status_code, 403)
        headers['X-CSRF-Token'] = csrf_token(self.f.member_token)
        self.assertEqual(self.request(headers=headers).status_code, 200)
        self.assertEqual(self.request(raw='{"asset_ids":"101","before_id":"","x":"y"}').status_code, 400)
        self.assertEqual(self.request(raw='{"asset_ids":"101","asset_ids":"102","before_id":""}').status_code, 400)
        for asset_ids, before_id in (('101,101',''), ('101,0101',''), (','.join(map(str, range(1,26))), ''),
                                     ('101','01'), ('101','9223372036854775808')):
            with self.subTest(asset_ids=asset_ids[:24], before_id=before_id):
                self.assertEqual(self.request(asset_ids=asset_ids, before_id=before_id).status_code, 400)
        oversized = json.dumps({'asset_ids':'1'*5000, 'before_id':''})
        self.assertEqual(self.request(raw=oversized).status_code, 413)
        self.assertTrue(ClosedBoundary.allowed('POST', '/story-workspace/related-media'))
        self.assertFalse(ClosedBoundary.allowed('GET', '/story-workspace/related-media'))
        self.assertFalse(ClosedBoundary.allowed('POST', '/story-workspace/related-media/extra'))
        self.assertEqual(self.client.get('/story-workspace/related-media?library=family-a',
            headers=self.headers).status_code, 403)
        self.assertEqual(self.client.post('/story-workspace/related-media/extra?library=family-a',
            headers=self.headers, json={'asset_ids':'101','before_id':''}).status_code, 403)


if __name__ == '__main__': unittest.main()
