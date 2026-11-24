"""Generated in-process external-reader checks. No external token or listener."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_phone_discovery_http import Fixture, NOW, TOKEN, SECOND, OTHER
from test_network_guard import install_no_external_sockets
from app.access import external_search
from app.access.discovery_provider import MemoryIndexProvider
from app.access.external_search import ExternalSearchRefused, ExternalSearchSession


CLIENT = 'synthetic-reader'


class ExternalSearchTests(unittest.TestCase):
    def setUp(self):
        temporary = self.enterContext(tempfile.TemporaryDirectory(prefix='external-search-'))
        self.fixture = Fixture(Path(temporary) / 'synthetic.sqlite')
        self.now = NOW
        runtime = self.fixture.runtime
        self.runtime = replace(runtime, access=replace(runtime.access, clock=lambda: self.now))
        self.reader = self.new_reader()
        self.addCleanup(self.reader.revoke)
        install_no_external_sockets(self)

    def new_reader(self, *, client=CLIENT, token=TOKEN, library='family-a'):
        return ExternalSearchSession(self.runtime, client_id=client, library=library,
                                     host_session=token, expires_at=NOW + 120)

    def test_search_and_detail_project_only_safe_current_metadata(self):
        result = self.reader.search_media(CLIENT, query='family',
            filters={'media':['image'], 'date':{'from':'2025-12-01', 'to':'2025-12-01'}})
        self.assertEqual(set(result), {'version', 'items', 'total', 'next_cursor', 'coverage'})
        self.assertEqual((result['total'], result['next_cursor'], result['coverage']),
                         (1, None, 'complete_catalog'))
        item, = result['items']
        self.assertEqual(set(item), {'media_ref', 'kind', 'captured_date'})
        self.assertRegex(item['media_ref'], r'^[A-Za-z0-9_-]{32}$')
        self.assertEqual((item['kind'], item['captured_date']), ('image', '2025-12-01'))
        self.assertEqual(self.reader.get_media_detail(CLIENT, item['media_ref']), item)
        with self.assertRaisesRegex(ExternalSearchRefused, '^access_denied$'):
            self.reader.get_media_detail(CLIENT, '103')
        self.assertEqual(self.reader.search_media(CLIENT, query='Foreign caption secret')['total'], 0)
        with self.assertRaisesRegex(ExternalSearchRefused, '^access_denied$'):
            self.reader.get_media_detail(CLIENT, item['media_ref'])

    def test_paging_and_retry_are_bound_to_the_current_client_and_search(self):
        first = self.reader.search_media(CLIENT, page_size=1)
        current = first['items'][0]['media_ref']
        cursor = first['next_cursor']
        reader = self.new_reader(client='second-reader', token=SECOND)
        self.addCleanup(reader.revoke)
        reader.search_media('second-reader', page_size=1)
        with self.assertRaisesRegex(ExternalSearchRefused, '^access_denied$'):
            self.reader.get_media_detail('second-reader', current)
        with self.assertRaisesRegex(ExternalSearchRefused, '^access_denied$'):
            reader.get_media_detail('second-reader', current)
        with self.assertRaisesRegex(ExternalSearchRefused, '^search_changed$'):
            reader.search_media('second-reader', cursor=cursor)
        next_page = self.reader.search_media(CLIENT, cursor=cursor)
        self.assertEqual(next_page, self.reader.search_media(CLIENT, cursor=cursor))
        self.assertEqual(next_page['total'], first['total'])
        self.assertNotEqual(next_page['items'][0]['media_ref'], current)
        self.assertEqual(self.reader.get_media_detail(CLIENT, current), first['items'][0])
        with self.assertRaisesRegex(ExternalSearchRefused, '^invalid_request$'):
            self.reader.search_media(CLIENT, query='family', cursor=cursor)

    def test_host_access_external_expiry_and_revocation_are_rechecked(self):
        first = self.reader.search_media(CLIENT)
        saved = first['items'][0]['media_ref']
        for sql, reset in (
            ("UPDATE access_sessions SET revoked=1 WHERE account_id='one'",
             "UPDATE access_sessions SET revoked=0 WHERE account_id='one'"),
            ("UPDATE access_memberships SET status='revoked' WHERE account_id='one'",
             "UPDATE access_memberships SET status='approved' WHERE account_id='one'"),
        ):
            self.fixture.update(sql)
            with self.subTest(sql=sql), patch.object(self.fixture.provider, 'get',
                    side_effect=AssertionError('Provider read after host authorization changed')):
                with self.assertRaisesRegex(ExternalSearchRefused, '^access_denied$'):
                    self.reader.get_media_detail(CLIENT, saved)
            self.fixture.update(reset)
            saved = self.reader.search_media(CLIENT)['items'][0]['media_ref']

        other = self.new_reader(token=OTHER)
        revoked = self.new_reader()
        self.addCleanup(other.revoke)
        self.addCleanup(revoked.revoke)
        revocable = revoked.search_media(CLIENT)['items'][0]['media_ref']
        self.now = NOW + 120
        with patch.object(self.fixture.provider, 'get', side_effect=AssertionError('Unauthorized provider read')):
            with self.assertRaisesRegex(ExternalSearchRefused, '^access_denied$'):
                self.reader.search_media(CLIENT)
            self.now = NOW
            with self.assertRaisesRegex(ExternalSearchRefused, '^access_denied$'):
                self.reader.search_media(CLIENT)
            revoked.revoke()
            with self.assertRaisesRegex(ExternalSearchRefused, '^access_denied$'):
                revoked.get_media_detail(CLIENT, revocable)
            with self.assertRaisesRegex(ExternalSearchRefused, '^access_denied$'):
                other.search_media(CLIENT)

    def test_disabled_caption_search_does_not_fall_back_to_an_unfiltered_page(self):
        index = self.fixture.index
        limited = replace(index, enabled=tuple(field for field in index.enabled if field != 'caption'))
        self.runtime = replace(self.runtime, provider=MemoryIndexProvider((limited,)))
        reader = self.new_reader()
        self.addCleanup(reader.revoke)
        with self.assertRaisesRegex(ExternalSearchRefused, '^filter_unavailable$'):
            reader.search_media(CLIENT, query='portrait')
        self.assertEqual(reader.search_media(CLIENT, filters={'media':['video']})['total'], 1)

    def test_stale_library_source_withholds_old_search_and_detail(self):
        first = self.reader.search_media(CLIENT, page_size=1)
        saved, cursor = first['items'][0]['media_ref'], first['next_cursor']
        self.fixture.update("UPDATE assets SET status='hidden' WHERE id = 9223372036854775807")
        with self.assertRaisesRegex(ExternalSearchRefused, '^search_changed$'):
            self.reader.get_media_detail(CLIENT, saved)
        with self.assertRaisesRegex(ExternalSearchRefused, '^search_changed$'):
            self.reader.search_media(CLIENT, cursor=cursor)
        with self.assertRaisesRegex(ExternalSearchRefused, '^access_denied$'):
            self.reader.get_media_detail(CLIENT, saved)

    def test_revocation_during_a_provider_read_prevents_disclosure(self):
        existing = self.fixture.provider.get

        def revoke_while_reading(library):
            self.reader.revoke()
            return existing(library)

        with patch.object(self.fixture.provider, 'get', side_effect=revoke_while_reading):
            with self.assertRaisesRegex(ExternalSearchRefused, '^access_denied$'):
                self.reader.search_media(CLIENT)
        with self.assertRaisesRegex(ExternalSearchRefused, '^access_denied$'):
            self.reader.search_media(CLIENT)

    def test_cached_references_and_cursors_are_bounded_and_invalid_filters_fail_before_lookup(self):
        with patch.object(self.fixture.provider, 'get', side_effect=AssertionError('Invalid request looked up data')):
            for fields in ({'filters':{'people':['301']}}, {'filters':{'date':{'from':'2026-02-30','to':None}}},
                           {'query':'x'*513}, {'page_size':True}, {'filters':{'media':['image','image']}}):
                with self.subTest(fields=fields), self.assertRaisesRegex(ExternalSearchRefused, '^invalid_request$'):
                    self.reader.search_media(CLIENT, **fields)
        with patch.object(external_search, 'MAX_REFERENCES', 2), patch.object(external_search, 'MAX_CURSORS', 1):
            first = self.reader.search_media(CLIENT, page_size=1)
            next_page = self.reader.search_media(CLIENT, cursor=first['next_cursor'])
            newest = self.reader.search_media(CLIENT, cursor=next_page['next_cursor'])
            self.assertEqual(self.reader.get_media_detail(CLIENT, newest['items'][0]['media_ref']),
                             newest['items'][0])
            with self.assertRaisesRegex(ExternalSearchRefused, '^access_denied$'):
                self.reader.get_media_detail(CLIENT, first['items'][0]['media_ref'])
            with self.assertRaisesRegex(ExternalSearchRefused, '^search_changed$'):
                self.reader.search_media(CLIENT, cursor=first['next_cursor'])


if __name__ == '__main__':
    unittest.main()
