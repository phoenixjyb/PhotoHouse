"""In-process security checks for private assistant history/preferences."""
from contextlib import closing, contextmanager
import asyncio
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
from starlette.requests import Request
from app.access.transport import AccessRuntime, COOKIE, TransportError, csrf_token
from app.access.assistant_workspace_store import (AssistantWorkspaceStore, initialize,
                                                   WorkspaceStoreUnavailable)
from app.access.runtime import RuntimeConfiguration
from app.main import create_app
from phone_discovery_fixture import create, TOKEN, SECOND, NOW
from app.access import assistant_workspace_transport as workspace_transport

ORIGIN = 'https://photohouse.example.test'
BASE = '/assistant/workspace/v1'


class AssistantWorkspaceHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.database = self.root / 'synthetic.sqlite'
        with closing(sqlite3.connect(self.database)) as connection, connection:
            create(connection)
        self.now = [NOW]
        self.workspace_path = self.root / 'assistant-workspace.sqlite'
        self.store = initialize(self.workspace_path, clock=lambda: self.now[0])
        self.access = AccessRuntime(self.connection, ORIGIN, clock=lambda: self.now[0])
        self.app = create_app(access_runtime=self.access, assistant_enabled=True,
                              assistant_workspace_store=self.store)
        self.client = TestClient(self.app, base_url=ORIGIN)
        self.addCleanup(self.client.close)
        self.auth = {'Authorization': 'Bearer ' + TOKEN}

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
        if headers is None:
            headers = self.auth
        if raw is not None:
            headers = dict(headers, **{'Content-Type': 'application/json'})
            return self.client.request(method, BASE + path, content=raw, headers=headers)
        return self.client.request(method, BASE + path, json=body, headers=headers)

    def test_request_body_rejects_framing_mismatch_and_times_out_without_waiting(self):
        async def request_for(body, content_length):
            messages = iter([{'type': 'http.request', 'body': body, 'more_body': False}])

            async def receive():
                try:
                    return next(messages)
                except StopIteration:
                    return {'type': 'http.disconnect'}

            return Request({'type': 'http', 'method': 'POST', 'path': '/test',
                'headers': [(b'content-type', b'application/json'),
                            (b'content-length', str(content_length).encode())],
                'query_string': b'', 'server': ('photohouse.example.test', 443),
                'client': ('127.0.0.1', 12345), 'scheme': 'https', 'http_version': '1.1'}, receive)

        mismatched = asyncio.run(request_for(b'{"library_id":"family-a"}', 100))
        with self.assertRaises(workspace_transport.WorkspaceInvalid):
            asyncio.run(workspace_transport._body(mismatched, {'library_id'}))

        class ImmediateTimeout:
            async def __aenter__(self):
                raise TimeoutError()

            async def __aexit__(self, *_args):
                return False

        stalled_body = b'{"library_id":"family-a"}'
        stalled = asyncio.run(request_for(stalled_body, len(stalled_body)))
        with patch.object(workspace_transport.asyncio, 'timeout',
                          side_effect=lambda _seconds: ImmediateTimeout()):
            with self.assertRaises(TransportError) as raised:
                asyncio.run(workspace_transport._body(stalled, {'library_id'}))
        self.assertEqual(raised.exception.status, 408)

    def test_owned_threads_are_account_and_library_scoped_and_redact_bindings(self):
        self.update("INSERT INTO access_memberships VALUES('one','family-b','approved','viewer',1,NULL,0,'one')")
        thread = self.request('POST', '/threads', body={'library_id': 'family-a'}).json()['thread']
        self.assertEqual(thread['revision'], 0)
        self.store.append_exchange('one', 'family-a', thread['thread_id'], str(uuid.uuid4()), 0,
            'Find the park photos', 'I found two photos.',
            [dict(type='media', id='103', revision='a' * 64, fingerprint='b' * 64),
             dict(type='story', id='private-story', revision='c' * 64, fingerprint='d' * 64)],
            [str(uuid.uuid4())])
        listed = self.request('GET', '/threads?library_id=family-a').json()['threads']
        self.assertEqual([entry['thread_id'] for entry in listed], [thread['thread_id']])
        self.assertEqual(self.request('GET', '/threads?library_id=family-b').json()['threads'], [])
        for headers, library in (({'Authorization': 'Bearer ' + SECOND}, 'family-a'),
                                 (self.auth, 'family-b')):
            self.assertEqual(self.request('GET', f"/threads/{thread['thread_id']}?library_id={library}",
                                           headers=headers).status_code, 404)
        detail = self.request('GET', f"/threads/{thread['thread_id']}?library_id=family-a").json()
        exchange = detail['exchanges'][0]
        self.assertEqual(exchange['input_text'], 'Find the park photos')
        self.assertEqual(exchange['reply'], 'I found two photos.')
        self.assertEqual(exchange['cards'], [
            {'type': 'media', 'count': 1, 'actionable': False},
            {'type': 'story', 'count': 1, 'actionable': False}])
        self.assertEqual(exchange['receipt_count'], 1)
        for secret in ('private-story', '"id":"103"', 'a' * 64, 'b' * 64):
            self.assertNotIn(secret, self.request('GET', f"/threads/{thread['thread_id']}?library_id=family-a").text)
        response = self.request('GET', f"/threads/{thread['thread_id']}?library_id=family-a")
        self.assertEqual(response.headers['cache-control'], 'no-store')
        self.assertNotIn('trusted_context', response.text)
        self.assertNotIn('open_asset', response.text)

    def test_preferences_require_library_scope_and_are_account_owned_with_cas(self):
        self.update("INSERT INTO access_memberships VALUES('one','family-b','approved','viewer',1,NULL,0,'one')")
        self.assertEqual(self.request('GET', '/preferences?library_id=family-a').json()['revision'], 0)
        self.assertEqual(self.request('GET', '/preferences').status_code, 400)
        updated = self.request('PUT', '/preferences', body={'library_id': 'family-a',
            'expected_revision': 0, 'locale': 'zh', 'voice_pace': 'slow'})
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json(), {'version': 1, 'locale': 'zh', 'reply_length': None,
                                           'voice_pace': 'slow', 'revision': 1})
        self.assertEqual(self.request('GET', '/preferences?library_id=family-b').json()['locale'], 'zh')
        self.assertEqual(self.request('PUT', '/preferences', body={'library_id': 'family-a',
                         'expected_revision': 0, 'locale': 'en'}).status_code, 409)
        reset = self.request('POST', '/preferences/reset', body={'library_id': 'family-b',
                           'expected_revision': 1})
        self.assertEqual(reset.status_code, 200)
        self.assertEqual(reset.json()['revision'], 2)
        self.assertIsNone(self.request('GET', '/preferences?library_id=family-a').json()['locale'])

    def test_user_supplied_revisions_enums_and_identifiers_fail_as_generic_400(self):
        for revision in (True, -1, (1 << 63) - 1, '0'):
            response = self.request('POST', '/preferences/reset', body={
                'library_id': 'family-a', 'expected_revision': revision})
            self.assertEqual(response.status_code, 400, response.text)
        for value in ('unsupported', 4, [], {}):
            response = self.request('PUT', '/preferences', body={'library_id': 'family-a',
                'expected_revision': 0, 'locale': value})
            self.assertEqual(response.status_code, 400, response.text)
        empty = self.request('PUT', '/preferences', body={'library_id': 'family-a',
            'expected_revision': 0})
        self.assertEqual(empty.status_code, 400)
        bad_id = '00000000-0000-0000-0000-000000000000'
        invalid = self.request('GET', f'/threads/{bad_id}?library_id=family-a')
        self.assertEqual(invalid.status_code, 400, invalid.text)

    def test_auth_membership_revocation_csrf_origin_and_duplicate_schemas(self):
        cookie = { 'Cookie': COOKIE + '=' + TOKEN, 'Origin': ORIGIN }
        no_csrf = self.request('POST', '/threads', body={'library_id': 'family-a'}, headers=cookie)
        self.assertEqual(no_csrf.status_code, 403)
        good_cookie = dict(cookie, **{'X-CSRF-Token': csrf_token(TOKEN)})
        self.assertEqual(self.request('POST', '/threads', body={'library_id': 'family-a'},
                                      headers=good_cookie).status_code, 201)
        wrong_origin = dict(good_cookie, Origin='https://evil.example.test')
        self.assertEqual(self.request('POST', '/threads', body={'library_id': 'family-a'},
                                      headers=wrong_origin).status_code, 403)
        self.assertEqual(self.request('GET', '/threads?library_id=family-a&library_id=family-a').status_code, 400)
        duplicate = self.request('POST', '/threads', raw=b'{"library_id":"family-a","library_id":"family-a"}')
        self.assertEqual(duplicate.status_code, 400)
        unknown = self.request('POST', '/threads', body={'library_id': 'family-a', 'account_id': 'two'})
        self.assertEqual(unknown.status_code, 400)
        created = self.request('POST', '/threads', body={'library_id': 'family-a'}).json()['thread']
        self.update("UPDATE access_memberships SET status='requested' WHERE account_id='one' AND library_id='family-a'")
        self.assertEqual(self.request('GET', f"/threads/{created['thread_id']}?library_id=family-a").status_code, 401)

    def test_off_missing_or_malformed_store_is_unavailable_and_does_not_create(self):
        absent = self.root / 'absent.sqlite'
        closed = TestClient(create_app(access_runtime=self.access, assistant_enabled=True), base_url=ORIGIN)
        self.addCleanup(closed.close)
        capability = closed.get(BASE + '/capabilities?library_id=family-a', headers=self.auth)
        self.assertEqual(capability.status_code, 200)
        self.assertFalse(capability.json()['available'])
        self.assertEqual(closed.get(BASE + '/threads?library_id=family-a', headers=self.auth).status_code, 503)
        self.assertFalse(absent.exists())
        off = TestClient(create_app(access_runtime=self.access), base_url=ORIGIN)
        self.addCleanup(off.close)
        self.assertFalse(off.get(BASE + '/capabilities?library_id=family-a',
                                 headers=self.auth).json()['available'])
        self.assertEqual(off.get(BASE + '/threads?library_id=family-a',
                                 headers=self.auth).status_code, 503)
        self.store.path = absent
        response = self.client.get(BASE + '/capabilities?library_id=family-a', headers=self.auth)
        self.assertFalse(response.json()['available'])
        self.assertNotIn(str(self.workspace_path), response.text)
        self.assertEqual(self.client.get(BASE + '/threads?library_id=family-a',
                                         headers=self.auth).status_code, 503)
        self.assertFalse(absent.exists())

    def test_thread_revision_delete_expiry_and_fixed_retention(self):
        created = self.request('POST', '/threads', body={'library_id': 'family-a'}).json()['thread']
        bad = self.request('DELETE', f"/threads/{created['thread_id']}",
                           body={'library_id': 'family-a', 'expected_revision': 2})
        self.assertEqual(bad.status_code, 409)
        deleted = self.request('DELETE', f"/threads/{created['thread_id']}",
                               body={'library_id': 'family-a', 'expected_revision': 0})
        self.assertTrue(deleted.json()['deleted'])
        self.assertEqual(self.request('GET', f"/threads/{created['thread_id']}?library_id=family-a").status_code, 404)
        expiring = self.request('POST', '/threads', body={'library_id': 'family-a'}).json()['thread']
        self.store.append_exchange('one', 'family-a', expiring['thread_id'], str(uuid.uuid4()), 0,
                                   'question', 'answer', [], [])
        self.update("UPDATE access_sessions SET expires_at=? WHERE account_id='one'", (2**63 - 1,))
        self.now[0] += 30 * 86400 + 1
        self.assertEqual(self.request('GET', f"/threads/{expiring['thread_id']}?library_id=family-a").status_code, 404)
        self.store.prune()
        with self.store.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM exchanges').fetchone()[0], 0)

    def test_lifespan_prunes_expired_history_and_tracks_workspace_health(self):
        thread_id = self.store.create_thread('one', 'family-a')['thread_id']
        self.now[0] += 30 * 86400 + 1
        self.update("UPDATE access_sessions SET expires_at=? WHERE account_id='one'", (2**63 - 1,))
        with TestClient(self.app, base_url=ORIGIN) as running:
            self.assertTrue(running.get(BASE + '/capabilities?library_id=family-a',
                                        headers=self.auth).json()['available'])
            self.assertTrue(self.app.state.assistant_workspace_healthy)
            with self.store.connection() as db:
                self.assertEqual(db.execute('SELECT count(*) FROM threads WHERE thread_id=?',
                                            (thread_id,)).fetchone()[0], 0)

    def test_capability_requires_current_membership_and_v1_routes_remain_unmodified(self):
        capability = self.request('GET', '/capabilities?library_id=family-a')
        self.assertEqual(capability.json(), {'version': 1, 'available': True,
            'threads': True, 'preferences': True, 'preferences_applied': False,
            'server_owned_turns': False, 'applied_preferences': []})
        self.assertEqual(self.client.get('/assistant/v1/capabilities?library_id=family-a',
                         headers=self.auth).status_code, 200)
        self.assertEqual(self.client.post('/assistant/workspace/v1/threads/extra',
                         json={'library_id': 'family-a'}, headers=self.auth).status_code, 403)
        self.update("UPDATE access_memberships SET status='requested' WHERE account_id='one'")
        self.assertEqual(self.request('GET', '/capabilities?library_id=family-a').status_code, 401)

    def test_runtime_configuration_uses_only_explicit_separate_existing_workspace_path(self):
        with self.assertRaises(ValueError):
            RuntimeConfiguration(self.database, ORIGIN, (self.root / 'originals',),
                                 self.root / 'derived', assistant_workspace_path=self.workspace_path).build_app()
        configured = RuntimeConfiguration(self.database, ORIGIN, (self.root / 'originals',),
            self.root / 'derived', assistant_enabled=True,
            assistant_workspace_path=self.workspace_path)
        app = configured.build_app(clock=lambda: self.now[0])
        self.assertIsInstance(app.state.assistant_workspace_store, AssistantWorkspaceStore)
        missing = self.root / 'missing-workspace.sqlite'
        with self.assertRaises(WorkspaceStoreUnavailable):
            RuntimeConfiguration(self.database, ORIGIN, (self.root / 'originals',),
                self.root / 'derived', assistant_enabled=True,
                assistant_workspace_path=missing).build_app(clock=lambda: self.now[0])
        self.assertFalse(missing.exists())


if __name__ == '__main__':
    unittest.main()
