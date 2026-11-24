"""Ordinary workspace result paging revalidates saved v1/v2/v3 turns."""
from contextlib import closing
from dataclasses import replace
import sqlite3
import unittest
import uuid
from unittest.mock import patch

from app.access import discovery as discovery_engine
from app.access.assistant_search import SearchRuntime
from app.access.discovery_provider import MemoryIndexProvider, ReviewedFace
from app.access.discovery_transport import DiscoveryRuntime
from app.access.service import AccessService
import test_assistant_workspace_turn_http as workspace_fixture
from phone_discovery_fixture import NOW, TOKEN, reviewed

BASE = '/assistant/workspace/v1'


class DormantPlanner:
    def __init__(self):
        self.calls = []

    def propose(self, *args):
        self.calls.append(args)
        raise AssertionError('ordinary paging must not invoke intent planning')


class AssistantResultPagesTests(unittest.TestCase):
    connection = workspace_fixture.AssistantWorkspaceTurnHttpTests.connection
    _make_client = workspace_fixture.AssistantWorkspaceTurnHttpTests._make_client
    request = workspace_fixture.AssistantWorkspaceTurnHttpTests.request
    thread = workspace_fixture.AssistantWorkspaceTurnHttpTests.thread
    turn = workspace_fixture.AssistantWorkspaceTurnHttpTests.turn
    enable_search = workspace_fixture.AssistantWorkspaceTurnHttpTests.enable_search
    update = workspace_fixture.AssistantWorkspaceTurnHttpTests.update

    def setUp(self):
        workspace_fixture.AssistantWorkspaceTurnHttpTests.setUp(self)
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute("UPDATE assets SET taken_at='2026-01-03' WHERE id=102")
            for offset, asset_id in enumerate(range(1000, 1045)):
                mime = 'video/mp4' if offset % 2 else 'image/jpeg'
                month = offset % 12 + 1
                db.execute('''INSERT INTO assets(id,path,status,mime,width,height,duration_sec,taken_at)
                    VALUES(?,?,?,?,?,?,?,?)''',
                    (asset_id, 'generated-only', 'active', mime, 640, 480,
                     2.0 if mime.startswith('video/') else None,
                     f'2026-{month:02d}-01'))
                db.execute('INSERT INTO access_asset_libraries VALUES(?,?)',
                           (asset_id, 'family-a'))
                db.execute('INSERT INTO face_detections VALUES(?,?,?,?)',
                           (100 + offset, asset_id, 301, 'manual'))
        self.enable_search()
        with closing(sqlite3.connect(self.database)) as db:
            db.execute('PRAGMA foreign_keys=ON')
            index = reviewed(AccessService(db, clock=lambda: self.now[0]))
        index = replace(index, assignments=index.assignments + tuple(
            ReviewedFace(str(100 + offset), str(asset_id), '301')
            for offset, asset_id in enumerate(range(1000, 1045))))
        self.discovery = DiscoveryRuntime(
            self.access, MemoryIndexProvider((index,)), discovery_engine.ReadBudget())
        self.app.state.discovery_runtime = self.discovery
        self.planner = DormantPlanner()
        self.app.state.assistant_intent_planner = self.planner
        self.auth = {'Authorization': 'Bearer ' + TOKEN}

    def _headers(self, version):
        headers = dict(self.auth)
        if version in (2, 3):
            headers['X-PhotoHouse-Search-Version'] = str(version)
        return headers

    def _turn_with_many_results(self, version=2):
        thread_id = self.thread()['thread_id']
        headers = self._headers(version)
        request_id = str(uuid.uuid4())
        query = 'find photos' if version == 1 else 'find Sample Child from 2026'
        response = self.turn(thread_id, request_id, 0, query, headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        envelope = response.json()
        self.assertEqual(envelope['result']['version'], version)
        self.assertEqual(envelope['result']['kind'], 'results', envelope)
        self.assertGreater(envelope['result']['total'], 20)
        return thread_id, request_id, envelope, headers

    def _page(self, thread_id, request_id, revision, page, *, version=2,
              library='family-a', extra=None, headers=None):
        body = {'version': 1, 'library_id': library,
                'expected_revision': revision, 'page': page}
        body.update(extra or {})
        return self.client.post(
            f'{BASE}/threads/{thread_id}/requests/{request_id}/result-pages',
            headers=headers or self._headers(version), json=body)

    def test_mixed_media_pages_preserve_order_and_do_not_create_turns_or_call_planner(self):
        capabilities = self.request(
            'GET', '/result-page-capabilities?library_id=family-a').json()
        self.assertEqual(capabilities, {'version': 1, 'available': True, 'page_size': 20})

        for version in (1, 2, 3):
            with self.subTest(version=version):
                thread_id, request_id, envelope, headers = self._turn_with_many_results(version)
                original = envelope['result']
                before = self.workspace.get_thread('one', 'family-a', thread_id)
                with closing(sqlite3.connect(self.workspace.path)) as db:
                    requests_before = db.execute(
                        'SELECT COUNT(*) FROM turn_requests WHERE thread_id=?',
                        (thread_id,)).fetchone()[0]
                calls_before = len(self.planner.calls)
                page2 = self._page(thread_id, request_id, envelope['revision'], 2,
                                   version=version, headers=headers)
                self.assertEqual(page2.status_code, 200, page2.text)
                value = page2.json()
                self.assertEqual(set(value), {
                    'version', 'library_id', 'thread_id', 'request_id', 'revision',
                    'search_version', 'binding', 'fingerprint', 'page', 'page_size',
                    'total', 'has_more', 'items'})
                self.assertEqual((value['version'], value['search_version'], value['page'],
                                  value['page_size'], value['total'], value['has_more']),
                                 (1, version, 2, 20, original['total'], original['total'] > 40))
                self.assertEqual(value['binding'], original['context']['binding'])
                self.assertEqual(value['fingerprint'], original['context']['fingerprint'])
                self.assertEqual(len(value['items']), min(20, original['total'] - 20))
                if original['total'] > 40:
                    page3 = self._page(thread_id, request_id, envelope['revision'], 3,
                                       version=version, headers=headers)
                    self.assertEqual(page3.status_code, 200, page3.text)
                    last_page = page3.json()
                    self.assertFalse(last_page['has_more'])
                    self.assertEqual(len(last_page['items']), original['total'] - 40)
                    third_ids = [item['id'] for item in last_page['items']]
                else:
                    self.assertFalse(value['has_more'])
                    third_ids = []
                first_ids = [item['id'] for item in original['items']]
                second_ids = [item['id'] for item in value['items']]
                combined = first_ids + second_ids + third_ids
                self.assertEqual(len(combined), len(set(combined)))
                self.assertEqual(combined, sorted(combined, key=int, reverse=True))
                media = {item['kind'] for item in original['items'] + value['items']}
                self.assertIn('image', media)
                if version > 1:
                    self.assertIn('video', media)
                after = self.workspace.get_thread('one', 'family-a', thread_id)
                self.assertEqual(after, before)
                with closing(sqlite3.connect(self.workspace.path)) as db:
                    requests_after = db.execute(
                        'SELECT COUNT(*) FROM turn_requests WHERE thread_id=?',
                        (thread_id,)).fetchone()[0]
                self.assertEqual(requests_after, requests_before)
                self.assertEqual(len(self.planner.calls), calls_before)

    def test_request_shape_version_header_and_page_bounds_fail_closed(self):
        thread_id, request_id, envelope, _headers = self._turn_with_many_results(2)
        revision = envelope['revision']
        path = f'{BASE}/threads/{thread_id}/requests/{request_id}/result-pages'
        bad = (
            {'version': True, 'library_id': 'family-a', 'expected_revision': revision, 'page': 2},
            {'version': 1.0, 'library_id': 'family-a', 'expected_revision': revision, 'page': 2},
            {'version': 1, 'library_id': 'family-a', 'expected_revision': True, 'page': 2},
            {'version': 1, 'library_id': 'family-a', 'expected_revision': revision, 'page': True},
            {'version': 1, 'library_id': 'family-a', 'expected_revision': revision, 'page': 2,
             'query': 'client query must not replace the saved filters'},
            {'version': 1, 'library_id': 'family-a', 'expected_revision': revision, 'page': 5001},
        )
        for body in bad:
            response = self.client.post(path, headers=self._headers(2), json=body)
            self.assertEqual(response.status_code, 400, response.text)
            self.assertNotIn('items', response.json())
        beyond = self._page(thread_id, request_id, revision, 4, version=2)
        self.assertEqual(beyond.status_code, 409, beyond.text)
        self.assertNotIn('items', beyond.json())
        bad_header = self._page(thread_id, request_id, revision, 2, version=2,
                                headers={**self.auth, 'X-PhotoHouse-Search-Version': '4'})
        self.assertEqual(bad_header.status_code, 400, bad_header.text)
        self.assertNotIn('items', bad_header.json())
        wrong_request = self._page(thread_id, str(uuid.uuid4()), revision, 2, version=2)
        self.assertIn(wrong_request.status_code, (404, 409), wrong_request.text)
        self.assertNotIn('items', wrong_request.json())
        wrong_revision = self._page(thread_id, request_id, 0, 2, version=2)
        self.assertIn(wrong_revision.status_code, (404, 409), wrong_revision.text)
        self.assertNotIn('items', wrong_revision.json())
        wrong_thread = self._page(str(uuid.uuid4()), request_id, revision, 2, version=2)
        self.assertIn(wrong_thread.status_code, (404, 409), wrong_thread.text)
        self.assertNotIn('items', wrong_thread.json())
        wrong_library = self._page(thread_id, request_id, revision, 2,
                                   version=2, library='family-b')
        self.assertIn(wrong_library.status_code, (401, 403, 404, 409), wrong_library.text)
        self.assertNotIn('items', wrong_library.json())

    def test_original_search_version_and_current_membership_are_required(self):
        thread_id, request_id, envelope, _headers = self._turn_with_many_results(2)
        wrong_version = self._page(thread_id, request_id, envelope['revision'], 2,
                                   version=1)
        self.assertEqual(wrong_version.status_code, 409, wrong_version.text)
        self.assertNotIn('items', wrong_version.json())

        self.update("UPDATE access_memberships SET status='revoked' WHERE account_id='one'")
        denied = self._page(thread_id, request_id, envelope['revision'], 2, version=2)
        self.assertIn(denied.status_code, (401, 403))
        self.assertNotIn('items', denied.json())

    def test_newer_pending_or_failed_request_blocks_old_page(self):
        thread_id, request_id, envelope, headers = self._turn_with_many_results(2)
        now = int(self.now[0])
        revision = envelope['revision']
        with closing(sqlite3.connect(self.workspace.path)) as db:
            db.row_factory = sqlite3.Row
            original = db.execute('SELECT * FROM turn_requests WHERE request_id=?',
                                  (request_id,)).fetchone()
        for status in ('pending', 'failed'):
            blocker_id = str(uuid.uuid4())
            if status == 'pending':
                row = (blocker_id, thread_id, original['account_id'], 'family-a', 'pending',
                       now + 1, now + 3600, revision, 'newer request', 'lease', now + 30,
                       revision, None, None)
            else:
                row = (blocker_id, thread_id, original['account_id'], 'family-a', 'failed',
                       now + 1, now + 3600, revision, 'newer request', None, None,
                       revision, None, 'request_cancelled')
            with closing(sqlite3.connect(self.workspace.path)) as db, db:
                db.execute('''INSERT INTO turn_requests(request_id,thread_id,account_id,library_id,
                    status,created_at,expires_at,expected_revision,input_text,lease_id,
                    lease_expires_at,revision,result_summary,error_code)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', row)
            response = self._page(thread_id, request_id, revision, 2, version=2,
                                  headers=headers)
            self.assertEqual(response.status_code, 409, response.text)
            self.assertNotIn('items', response.json())
            with closing(sqlite3.connect(self.workspace.path)) as db, db:
                db.execute('DELETE FROM turn_requests WHERE request_id=?', (blocker_id,))

    def test_source_change_after_page_search_suppresses_cards(self):
        thread_id, request_id, envelope, headers = self._turn_with_many_results(2)
        original_call = SearchRuntime.call
        changed = False

        def mutate_after_search(runtime, operation, token, library, cancelled, values):
            nonlocal changed
            result = original_call(runtime, operation, token, library, cancelled, values)
            if operation == 'search' and values.get('page') == 2 and not changed:
                changed = True
                self.update("UPDATE assets SET taken_at='2026-12-31' WHERE id=1000")
            return result

        path = f'{BASE}/threads/{thread_id}/requests/{request_id}/result-pages'
        with patch.object(SearchRuntime, 'call', new=mutate_after_search):
            response = self.client.post(path, headers=headers, json={
                'version': 1, 'library_id': 'family-a',
                'expected_revision': envelope['revision'], 'page': 2})
        self.assertIn(response.status_code, (409, 503), response.text)
        self.assertNotIn('items', response.json())


if __name__ == '__main__':
    unittest.main()
