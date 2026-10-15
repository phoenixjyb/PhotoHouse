"""HTTP contract and security checks for durable private assistant turns."""
from contextlib import closing, contextmanager
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))

from fastapi.testclient import TestClient
from app.access import discovery as d
from app.access import assistant as assistant_module
from app.access.discovery_provider import MemoryIndexProvider
from app.access.discovery_transport import DiscoveryRuntime
from app.access.assistant_journal import initialize as initialize_journal
from app.access.assistant_workspace_store import LEASE_SECONDS, initialize_v2
from app.access.service import AccessService
from app.access.transport import AccessRuntime
from app.main import create_app
from phone_discovery_fixture import create, reviewed, TOKEN, SECOND, NOW

ORIGIN = 'https://photohouse.example.test'
BASE = '/assistant/workspace/v1'


def new_id():
    return str(uuid.uuid4())


class AssistantWorkspaceTurnHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.database = self.root / 'synthetic.sqlite'
        with closing(sqlite3.connect(self.database)) as connection, connection:
            create(connection)
            index = reviewed(AccessService(connection, clock=lambda: NOW))
        self.now = [NOW]
        self.access = AccessRuntime(self.connection, ORIGIN, clock=lambda: self.now[0])
        self.discovery = DiscoveryRuntime(self.access, MemoryIndexProvider((index,)), d.ReadBudget())
        self.workspace = initialize_v2(self.root / 'workspace-v2.sqlite',
                                       clock=lambda: self.now[0])
        self.journal = None
        self._make_client()
        self.auth = {'Authorization': 'Bearer ' + TOKEN}

    def _make_client(self):
        self.app = create_app(access_runtime=self.access, discovery_runtime=self.discovery,
                              assistant_enabled=True,
                              assistant_workspace_store=self.workspace,
                              assistant_journal=self.journal)
        self.client = TestClient(self.app, base_url=ORIGIN)
        self.addCleanup(self.client.close)

    @contextmanager
    def connection(self):
        connection = sqlite3.connect(self.database, timeout=.25)
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('PRAGMA query_only=ON')
        try:
            yield connection
        finally:
            connection.close()

    def update(self, sql, params=()):
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute(sql, params)

    def request(self, method, path, *, body=None, headers=None, raw=None):
        selected = self.auth if headers is None else headers
        if raw is not None:
            selected = dict(selected, **{'Content-Type': 'application/json'})
            return self.client.request(method, BASE + path, content=raw, headers=selected)
        return self.client.request(method, BASE + path, json=body, headers=selected)

    def thread(self, *, client_id=None, headers=None):
        body = {'library_id': 'family-a'}
        if client_id is not None:
            body['thread_id'] = client_id
        response = self.request('POST', '/threads', body=body, headers=headers)
        self.assertIn(response.status_code, (200, 201), response.text)
        return response.json()['thread']

    def turn(self, thread_id, request_id=None, revision=0, text='找照片', *,
             library='family-a', headers=None, raw=None):
        body = {'library_id': library, 'request_id': request_id or new_id(),
                'expected_revision': revision, 'text': text}
        if raw is not None:
            return self.request('POST', f'/threads/{thread_id}/turns', headers=headers, raw=raw)
        return self.request('POST', f'/threads/{thread_id}/turns', body=body, headers=headers)

    def test_capabilities_admit_server_owned_turns_only_with_discovery_and_healthy_v2_store(self):
        capabilities = self.request('GET', '/capabilities?library_id=family-a').json()
        self.assertTrue(capabilities['server_owned_turns'])
        self.assertEqual(capabilities['applied_preferences'], ['locale'])

        unavailable = TestClient(create_app(access_runtime=self.access,
            assistant_enabled=True, assistant_workspace_store=self.workspace), base_url=ORIGIN)
        self.addCleanup(unavailable.close)
        response = unavailable.get(BASE + '/capabilities?library_id=family-a', headers=self.auth)
        self.assertFalse(response.json()['server_owned_turns'])
        self.assertEqual(response.json().get('applied_preferences', []), [])

        self.app.state.assistant_workspace_healthy = False
        response = self.request('GET', '/capabilities?library_id=family-a')
        self.assertFalse(response.json()['server_owned_turns'])

    def enable_search(self):
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute('''CREATE TABLE access_stories (
                id TEXT PRIMARY KEY, asset_id INTEGER, library_id TEXT, author_id TEXT,
                revision INTEGER, title TEXT, text TEXT, updated_at INTEGER, deleted INTEGER)''')
        return self.auth | {'X-PhotoHouse-Search-Version': '2'}

    def test_search_v2_capability_is_negotiated_and_other_workspace_routes_stay_legacy(self):
        headers = self.enable_search()
        legacy = self.request('GET', '/capabilities?library_id=family-a')
        self.assertNotIn('search', legacy.json())
        current = self.request('GET', '/capabilities?library_id=family-a', headers=headers)
        self.assertEqual(current.status_code, 200, current.text)
        self.assertEqual(current.json()['version'], 1)
        self.assertEqual(current.json()['search'],
                         {'version': 2, 'date_basis': 'capture', 'perspective': None})
        for path in ('/threads?library_id=family-a', '/preferences?library_id=family-a',
                     '/saved-memory-capabilities?library_id=family-a'):
            self.assertEqual(self.request('GET', path, headers=headers).status_code, 400)
        denied = self.request('GET', '/capabilities?library_id=family-a',
                              headers={'X-PhotoHouse-Search-Version': '2'})
        self.assertEqual(denied.status_code, 401)

    def test_search_v2_text_refinement_open_recovery_and_original_version_are_preserved(self):
        headers = self.enable_search()
        tid = self.thread()['thread_id']
        first_id = new_id()
        found = self.turn(tid, first_id, text='找照片', headers=headers)
        self.assertEqual(found.status_code, 200, found.text)
        result = found.json()['result']
        self.assertEqual((found.json()['version'], result['version']), (1, 2))
        self.assertEqual(result['context']['search_version'], 2)
        self.assertEqual([item['id'] for item in result['items']], ['103', '101'])
        self.assertEqual(result['interpretation'], {'date_basis': 'capture',
            'people': [], 'tags': [], 'locations': [], 'perspective': None})

        opened_id = new_id()
        opened = self.turn(tid, opened_id, revision=1, text='打开第二个', headers=headers)
        self.assertEqual(opened.status_code, 200, opened.text)
        self.assertEqual(opened.json()['result']['effect'], {'type': 'open_asset', 'asset_id': '101'})
        restored = self.request('GET', f'/threads/{tid}/requests/{opened_id}?library_id=family-a', headers=headers)
        self.assertEqual(restored.status_code, 200, restored.text)
        self.assertTrue(restored.json()['recovered'])
        self.assertEqual(restored.json()['result']['version'], 2)
        self.assertEqual(restored.json()['result']['kind'], 'results')
        self.assertIsNone(restored.json()['result']['effect'])
        self.assertEqual([item['id'] for item in restored.json()['result']['items']], ['103', '101'])
        downgrade = self.request('GET', f'/threads/{tid}/requests/{opened_id}?library_id=family-a')
        self.assertEqual(downgrade.status_code, 409)
        replay = self.turn(tid, first_id, text='找照片')
        self.assertEqual(replay.status_code, 409)

        narrowed = self.turn(tid, revision=2, text='只看2026年的', headers=headers)
        self.assertEqual(narrowed.status_code, 200, narrowed.text)
        self.assertEqual([item['id'] for item in narrowed.json()['result']['items']], ['101'])
        self.assertEqual(narrowed.json()['result']['items'][0]['match_reasons'],
                         [{'source': 'capture_date', 'value': '2026-01-02'}])
        text = self.turn(tid, revision=3, text='找包含“Portrait”的照片', headers=headers)
        self.assertEqual(text.status_code, 200, text.text)
        self.assertEqual(text.json()['result']['filters'], {'media': ['image'], 'text': 'Portrait'})
        self.assertEqual(text.json()['result']['items'][0]['match_reasons'][0]['source'], 'generated_caption')
        row = self.workspace.get_turn('one', 'family-a', tid, text.json()['request_id'])
        self.assertNotIn('interpretation', row['result_summary'])
        self.assertNotIn('items', row['result_summary'])

    def test_search_v2_rehydrates_reviewed_labels_and_checks_current_source_and_membership(self):
        headers = self.enable_search()
        tid = self.thread()['thread_id']
        response = self.turn(tid, text='找示例儿童和示例成人一起的照片', headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()['result']
        self.assertEqual(result['filters']['people'], {'ids': ['301', '302'], 'match': 'all'})
        self.assertEqual(result['interpretation']['people'], [
            {'id': '301', 'label': 'Sample Child / 示例儿童'},
            {'id': '302', 'label': 'Sample Adult / 示例成人'}])
        request_id = response.json()['request_id']
        path = f'/threads/{tid}/requests/{request_id}?library_id=family-a'
        fresh = self.request('GET', path, headers=headers)
        self.assertEqual(fresh.status_code, 200, fresh.text)
        self.assertEqual(fresh.json()['result']['interpretation'], result['interpretation'])
        self.update('UPDATE captions SET text=? WHERE id=2', ('Changed source',))
        self.assertEqual(self.request('GET', path, headers=headers).status_code, 409)
        self.update("UPDATE access_memberships SET status='revoked' WHERE account_id='one'")
        self.assertIn(self.request('GET', path, headers=headers).status_code, (401, 403))

    def test_search_v2_client_reads_legacy_without_reinterpreting_and_can_start_new_search(self):
        headers = self.enable_search()
        tid = self.thread()['thread_id']
        legacy = self.turn(tid)
        rid = legacy.json()['request_id']
        read = self.request('GET', f'/threads/{tid}/requests/{rid}?library_id=family-a', headers=headers)
        self.assertEqual(read.status_code, 200, read.text)
        self.assertEqual(read.json()['result']['version'], 1)
        self.assertNotIn('interpretation', read.json()['result'])
        refine = self.turn(tid, revision=1, text='只看2026年的', headers=headers)
        self.assertEqual(refine.status_code, 409)
        fresh = self.turn(tid, revision=1, text='找包含“Portrait”的照片', headers=headers)
        self.assertEqual(fresh.status_code, 200, fresh.text)
        self.assertEqual(fresh.json()['result']['version'], 2)

    def test_server_owned_context_preference_effect_recovery_and_exchange_ids(self):
        saved = self.request('PUT', '/preferences', body={
            'library_id': 'family-a', 'expected_revision': 0, 'locale': 'en'})
        self.assertEqual(saved.status_code, 200, saved.text)
        thread = self.thread()

        found = self.turn(thread['thread_id'], text='找照片')
        self.assertEqual(found.status_code, 200, found.text)
        envelope = found.json()
        self.assertEqual(set(envelope), {'version', 'thread_id', 'request_id', 'status',
                                         'revision', 'recovered', 'error', 'result'})
        self.assertEqual((envelope['version'], envelope['status'], envelope['revision']),
                         (1, 'completed', 1))
        self.assertFalse(envelope['recovered'])
        self.assertEqual(envelope['result']['kind'], 'results')
        self.assertIn('Found', envelope['result']['reply'])
        self.assertIsNone(envelope['result']['effect'])

        opened_id = new_id()
        opened = self.turn(thread['thread_id'], opened_id, 1, 'open the first result')
        self.assertEqual(opened.status_code, 200, opened.text)
        self.assertEqual(opened.json()['result']['kind'], 'open')
        self.assertEqual(opened.json()['result']['effect']['type'], 'open_asset')
        self.assertFalse(opened.json()['recovered'])

        recovered_path = f"/threads/{thread['thread_id']}/requests/{opened_id}?library_id=family-a"
        recovered = self.request('GET', recovered_path)
        self.assertEqual(recovered.status_code, 200, recovered.text)
        self.assertTrue(recovered.json()['recovered'])
        self.assertEqual(recovered.json()['result']['kind'], 'results')
        self.assertIsNone(recovered.json()['result']['effect'])

        repeated = self.turn(thread['thread_id'], opened_id, 1, 'open the first result')
        self.assertEqual(repeated.status_code, 200, repeated.text)
        self.assertTrue(repeated.json()['recovered'])
        self.assertEqual(repeated.json()['result']['kind'], 'results')
        self.assertIsNone(repeated.json()['result']['effect'])

        detail = self.request('GET', f"/threads/{thread['thread_id']}?library_id=family-a").json()
        self.assertEqual(detail['latest_request_id'], opened_id)
        self.assertEqual([exchange['request_id'] for exchange in detail['exchanges']],
                         [envelope['request_id'], opened_id])

    def test_duplicate_request_id_does_not_call_engine_and_stale_revision_conflicts(self):
        thread = self.thread()
        request_id = new_id()
        with patch('app.access.assistant._turn', wraps=assistant_module._turn) as engine_turn:
            first = self.turn(thread['thread_id'], request_id, 0, '找照片')
            self.assertEqual(first.status_code, 200, first.text)
            self.assertEqual(engine_turn.call_count, 1)
            replay = self.turn(thread['thread_id'], request_id, 0, '找照片')
            self.assertEqual(replay.status_code, 200, replay.text)
            self.assertTrue(replay.json()['recovered'])
            self.assertEqual(engine_turn.call_count, 1)

        stale = self.turn(thread['thread_id'], new_id(), 0, '找视频')
        self.assertEqual(stale.status_code, 409, stale.text)
        detail = self.request('GET', f"/threads/{thread['thread_id']}?library_id=family-a").json()
        self.assertEqual(detail['thread']['revision'], 1)
        self.assertEqual(len(detail['exchanges']), 1)

    def test_thread_creation_is_idempotent_and_never_adopts_foreign_threads(self):
        client_id = new_id()
        first = self.thread(client_id=client_id)
        again = self.thread(client_id=client_id)
        self.assertEqual(first['thread_id'], client_id)
        self.assertEqual(again['thread_id'], client_id)

        for owner_token in (SECOND,):
            owner = {'Authorization': 'Bearer ' + owner_token}
            conflict = self.request('POST', '/threads', headers=owner,
                                    body={'library_id': 'family-a', 'thread_id': client_id})
            self.assertIn(conflict.status_code, (404, 409), conflict.text)

    def test_exact_body_uuid_revision_utf8_size_and_client_supplied_context_are_rejected(self):
        thread = self.thread()
        invalid = [
            {'library_id': 'family-a', 'request_id': 'not-a-uuid',
             'expected_revision': 0, 'text': 'find photos'},
            {'library_id': 'family-a', 'request_id': new_id(),
             'expected_revision': True, 'text': 'find photos'},
            {'library_id': 'family-a', 'request_id': new_id(),
             'expected_revision': 0, 'text': 'find photos', 'context': {}},
            {'library_id': 'family-a', 'request_id': new_id(),
             'expected_revision': 0, 'text': 'find photos', 'reply': 'forged'},
            {'library_id': 'family-a', 'request_id': new_id(),
             'expected_revision': 0, 'text': 'find photos', 'effect': {'type': 'open_asset'}},
            {'library_id': 'family-a', 'request_id': new_id(),
             'expected_revision': 0, 'text': 'find\u0000photos'},
            {'library_id': 'family-a', 'request_id': new_id(),
             'expected_revision': 0, 'text': 'find\u007fphotos'},
        ]
        for body in invalid:
            with self.subTest(body=body):
                response = self.request('POST', f"/threads/{thread['thread_id']}/turns", body=body)
                self.assertEqual(response.status_code, 400, response.text)
        duplicate = self.turn(thread['thread_id'], raw=(
            '{"library_id":"family-a","request_id":"%s","expected_revision":0,'
            '"text":"find photos","text":"find videos"}' % new_id()))
        self.assertEqual(duplicate.status_code, 400, duplicate.text)
        over_limit = self.turn(thread['thread_id'], text='找' * 342)
        self.assertEqual(over_limit.status_code, 400, over_limit.text)
        boundary = self.turn(thread['thread_id'], text='找' * 341)
        self.assertEqual(boundary.status_code, 200, boundary.text)
        too_large = self.turn(thread['thread_id'], raw=b' ' * (20 * 1024 + 1))
        self.assertEqual(too_large.status_code, 413, too_large.text)

    def test_expired_compute_lease_cannot_commit_and_get_reports_interrupted(self):
        thread = self.thread()
        request_id = new_id()
        original = assistant_module._turn

        def late_result(*args, **kwargs):
            result = original(*args, **kwargs)
            self.now[0] += LEASE_SECONDS
            return result

        with patch('app.access.assistant._turn', side_effect=late_result):
            late = self.turn(thread['thread_id'], request_id, 0, '找照片')
        self.assertEqual(late.status_code, 200, late.text)
        self.assertEqual(late.json()['status'], 'interrupted')
        self.assertFalse(late.json()['recovered'])
        recovered = self.request('GET',
            f"/threads/{thread['thread_id']}/requests/{request_id}?library_id=family-a")
        self.assertEqual(recovered.status_code, 200, recovered.text)
        self.assertEqual(recovered.json()['status'], 'interrupted')
        self.assertTrue(recovered.json()['recovered'])
        self.assertIsNone(recovered.json()['result'])
        self.assertEqual(self.workspace.get_thread('one', 'family-a', thread['thread_id'])['thread']['revision'], 0)

    def test_recovery_revalidates_current_source_binding(self):
        thread = self.thread()
        created = self.turn(thread['thread_id'], text='找照片')
        self.assertEqual(created.status_code, 200, created.text)
        request_id = created.json()['request_id']
        # A source change invalidates the discovery fingerprint saved with this result.
        self.update("UPDATE captions SET text='Changed after search' WHERE asset_id=103")
        recovered = self.request('GET',
            f"/threads/{thread['thread_id']}/requests/{request_id}?library_id=family-a")
        self.assertIn(recovered.status_code, (404, 409), recovered.text)

    def test_foreign_account_library_and_revoked_membership_are_unavailable(self):
        thread = self.thread()
        self.update("INSERT INTO access_memberships VALUES('one','family-b','approved','viewer',1,NULL,0,'one')")
        for headers, library in (({'Authorization': 'Bearer ' + SECOND}, 'family-a'),
                                 (self.auth, 'family-b')):
            self.assertEqual(self.request('GET',
                f"/threads/{thread['thread_id']}?library_id={library}", headers=headers).status_code,
                404)
            self.assertEqual(self.request('GET',
                f"/threads/{thread['thread_id']}/requests/{new_id()}?library_id={library}",
                headers=headers).status_code, 404)
        self.update("UPDATE access_memberships SET status='requested' "
                    "WHERE account_id='one' AND library_id='family-a'")
        denied = self.turn(thread['thread_id'])
        self.assertEqual(denied.status_code, 401, denied.text)

    def test_journal_finalize_failure_keeps_committed_workspace_request_recoverable(self):
        self.journal = initialize_journal(self.root / 'journal.sqlite')
        self.journal.clock = lambda: self.now[0]
        self.client.close()
        self._make_client()
        self.auth = {'Authorization': 'Bearer ' + TOKEN}
        thread = self.thread()
        request_id = new_id()
        with patch.object(self.journal, 'finish', side_effect=RuntimeError('synthetic journal fault')):
            uncertain = self.turn(thread['thread_id'], request_id, 0, '找照片')
        self.assertEqual(uncertain.status_code, 503, uncertain.text)
        self.assertEqual(self.workspace.get_thread('one', 'family-a', thread['thread_id'])['thread']['revision'], 1)

        with patch('app.access.assistant._turn', side_effect=AssertionError('must not rerun')):
            recovered = self.request('GET',
                f"/threads/{thread['thread_id']}/requests/{request_id}?library_id=family-a")
            self.assertEqual(recovered.status_code, 200, recovered.text)
            self.assertTrue(recovered.json()['recovered'])
            replay = self.turn(thread['thread_id'], request_id, 0, '找照片')
            self.assertEqual(replay.status_code, 200, replay.text)
            self.assertTrue(replay.json()['recovered'])


if __name__ == '__main__':
    unittest.main()
