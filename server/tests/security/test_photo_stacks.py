"""Opt-in, page-local visual stacks over authorized synthetic gallery rows."""
import unittest

import test_library_reads as fixture
from app.access.photo_stacks import build_photo_stacks


def row(asset_id, *, mime='image/jpeg', taken_at='2026-04-05 12:00:00',
        phash='0000000000000000', account=None, batch=None):
    return (asset_id, mime, 640, 480, None, taken_at, phash, account, batch)


def stacks(*rows):
    return build_photo_stacks(rows)


class PhotoStackAlgorithmTests(unittest.TestCase):
    def test_full_capture_time_and_hash_threshold_are_both_required(self):
        self.assertEqual(stacks(row(1), row(2, taken_at='2026-04-05 12:05:00',
                                          phash='000000000000003f'))['groups'][0]['reason'],
                         'near_capture')
        self.assertEqual(stacks(row(1), row(2, taken_at='2026-04-05 12:05:01'))['groups'], [])
        self.assertEqual(stacks(row(1), row(2, phash='000000000000007f'))['groups'], [])

    def test_timezone_awareness_must_match_and_offsets_compare_as_instants(self):
        same_instant = stacks(row(1, taken_at='2026-04-05T12:00:00Z'),
                              row(2, taken_at='2026-04-05T14:05:00+02:00'))
        self.assertEqual(same_instant['groups'][0]['reason'], 'near_capture')
        mixed = stacks(row(1, taken_at='2026-04-05T12:00:00Z'),
                       row(2, taken_at='2026-04-05 12:00:00'))
        self.assertEqual(mixed['groups'], [])

    def test_date_only_falls_back_only_to_same_upload_and_stricter_hash(self):
        first = row(1, taken_at='2026-04-05', phash='0000000000000000',
                    account='account-a', batch='batch-a')
        second = row(2, taken_at='2026-04-05', phash='0000000000000003',
                     account='account-a', batch='batch-a')
        result = stacks(first, second)
        self.assertEqual(result['groups'][0]['reason'], 'same_upload')
        self.assertEqual(stacks(first, row(2, taken_at='2026-04-05',
            phash='0000000000000007', account='account-a', batch='batch-a'))['groups'], [])
        self.assertEqual(stacks(first, row(2, taken_at=None, phash=second[6],
            account='account-a', batch=None))['groups'], [])

    def test_conflicting_recorded_dates_veto_same_upload_fallback(self):
        first = row(1, taken_at='2026-04-05', account='account-a', batch='batch-a')
        second = row(2, taken_at='2026-04-06', phash='0000000000000003',
                     account='account-a', batch='batch-a')
        self.assertEqual(stacks(first, second)['groups'], [])

    def test_one_reliable_time_and_one_unknown_never_use_upload_fallback(self):
        first = row(1, account='account-a', batch='batch-a')
        second = row(2, taken_at=None, account='account-a', batch='batch-a')
        self.assertEqual(stacks(first, second)['groups'], [])

    def test_invalid_hashes_and_nonphotos_are_not_grouped(self):
        self.assertEqual(stacks(row(1, phash='not-a-hash'), row(2, phash='not-a-hash'))['groups'], [])
        self.assertEqual(stacks(row(1, mime='video/mp4'), row(2, mime='video/mp4'))['groups'], [])
        self.assertEqual(stacks(row(1, phash=None), row(2))['groups'], [])

    def test_complete_link_prevents_similarity_chains(self):
        result = stacks(row(9, phash='0000000000000000'),
                        row(4, phash='000000000000003f'),
                        row(2, phash='00000000000000ff'))
        self.assertEqual(result['groups'], [{
            'id': '4', 'cover_asset_id': '9', 'asset_ids': ['9', '4'],
            'count': 2, 'reason': 'near_capture'}])

    def test_groups_preserve_gallery_order_and_use_lowest_id_as_group_id(self):
        result = stacks(row(9), row(4, phash='0000000000000001'))
        self.assertEqual(result, {'version': 1, 'scope': 'page', 'groups': [{
            'id': '4', 'cover_asset_id': '9', 'asset_ids': ['9', '4'],
            'count': 2, 'reason': 'near_capture'}]})

    def test_pure_projection_fails_closed_above_maximum_page(self):
        result = build_photo_stacks([row(index) for index in range(1, 102)])
        self.assertEqual(result, {'version': 1, 'scope': 'page', 'groups': []})


class PhotoStackRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = fixture.LibraryReadTests
        cls.fixture.setUpClass()

    @classmethod
    def tearDownClass(cls):
        cls.fixture.tearDownClass()

    def setUp(self):
        self.f = fixture.LibraryReadTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.member = self.f.member_token
        self._prepare_gallery()

    def _prepare_gallery(self):
        with self.f.connection() as db:
            db.execute("UPDATE assets SET taken_at='2026-04-05 12:00:00', perceptual_hash=? WHERE id=101",
                       ('0' * 16,))
            db.execute("UPDATE assets SET taken_at='2026-04-05 12:04:00', perceptual_hash=? WHERE id=102",
                       ('0' * 15 + 'f',))
            # A matching inactive row and a matching foreign-library row must
            # never enter the authorized gallery page or its stack metadata.
            db.execute("UPDATE assets SET taken_at='2026-04-05 12:02:00', perceptual_hash=? WHERE id IN (103,201)",
                       ('0' * 16,))
            for receipt_id, asset_id in ((1, 101), (2, 102)):
                db.execute('''INSERT INTO access_uploads(id,asset_id,account_id,incoming_label,
                    batch,original_name,sha256,bytes,state,created_at)
                    VALUES (?,?,?,'synthetic',?,'synthetic.jpg',?,10,'assigned',?)''',
                    (receipt_id, asset_id, self.f.member_id, 'a' * 32,
                     ('b' * 63) + str(receipt_id), 1770000000 + receipt_id))
            db.commit()

    def test_default_wire_shape_is_unchanged_and_opt_in_keeps_every_item(self):
        default = self.f.get('/assets?library=family-a').json()
        self.assertEqual(set(default), {'library_id', 'page', 'page_size', 'total',
                                        'originals_allowed', 'items'})
        self.assertEqual(set(default['items'][0]), {'id', 'kind', 'width', 'height',
            'duration_sec', 'taken_at', 'thumbnail_url'})
        opted = self.f.get('/assets?library=family-a&photo_stacks=1').json()
        self.assertEqual({key: opted[key] for key in default}, default)
        self.assertEqual(opted['photo_stacks'], {'version': 1, 'scope': 'page', 'groups': [{
            'id': '101', 'cover_asset_id': '102', 'asset_ids': ['102', '101'],
            'count': 2, 'reason': 'near_capture'}]})
        self.assertNotIn('batch', self.f.get('/assets?library=family-a&photo_stacks=1').text)
        self.assertNotIn('account', self.f.get('/assets?library=family-a&photo_stacks=1').text)
        self.assertNotIn('phash', self.f.get('/assets?library=family-a&photo_stacks=1').text)

    def test_opted_projection_keeps_date_hint_shape_without_leaking_path(self):
        result = self.f.get('/assets?library=family-a&photo_stacks=1&date_hints=1').json()
        self.assertEqual(len(result['items']), 2)
        self.assertTrue(all('date_hint' in item for item in result['items']))
        self.assertNotIn('private-synthetic', str(result))
        self.assertEqual(result['photo_stacks']['groups'][0]['asset_ids'], ['102', '101'])

    def test_groups_are_page_scoped_and_items_are_never_removed(self):
        page_one = self.f.get('/assets?library=family-a&photo_stacks=1&page_size=1').json()
        page_two = self.f.get('/assets?library=family-a&photo_stacks=1&page_size=1&page=2').json()
        self.assertEqual(len(page_one['items']), 1)
        self.assertEqual(len(page_two['items']), 1)
        self.assertEqual(page_one['photo_stacks']['groups'], [])
        self.assertEqual(page_two['photo_stacks']['groups'], [])

    def test_invalid_opt_in_is_refused(self):
        for query in ('photo_stacks=yes', 'photo_stacks=2', 'photo_stacks=0&photo_stacks=1'):
            with self.subTest(query=query):
                self.assertEqual(400, self.f.get('/assets?library=family-a&' + query).status_code)
        self.assertEqual(400, self.f.get('/assets?library=family-a&page_size=101&photo_stacks=1').status_code)
        self.assertEqual(200, self.f.get('/assets?library=family-a&page_size=100&photo_stacks=1').status_code)

    def test_revoked_membership_is_denied_before_stack_projection(self):
        self.f.mutate("UPDATE access_memberships SET status='revoked' WHERE account_id=?",
                      (self.f.member_id,))
        self.assertEqual(401, self.f.get('/assets?library=family-a&photo_stacks=1').status_code)

    def test_projection_is_read_only(self):
        self.f.trace.clear()
        response = self.f.get('/assets?library=family-a&photo_stacks=1')
        self.assertEqual(200, response.status_code)
        writes = [statement for statement in self.f.trace
                  if statement.lstrip().split(None, 1)[0].upper()
                  in {'INSERT', 'UPDATE', 'DELETE', 'REPLACE', 'CREATE', 'DROP', 'ALTER'}]
        self.assertEqual(writes, [])


if __name__ == '__main__':
    unittest.main()
