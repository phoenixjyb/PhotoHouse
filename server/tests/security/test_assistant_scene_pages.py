"""Generated authenticated continuation pages for reviewed scene results."""
from contextlib import closing
from dataclasses import replace
import asyncio
import hashlib
import json
import math
import sqlite3
import threading
import time
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import httpx

from app.access.semantic_encoder import LocalSemanticEncoder, canonical_vector_checksum
from app.access.service import AccessService
import test_assistant_scene_search as scene_fixture
import test_visual_vector_loader as vector_fixtures


BASE = '/assistant/workspace/v1'


class AssistantScenePagesTests(unittest.TestCase):
    """Use the real API/store/ranker with generated SQLite/vector fixtures."""

    def setUp(self):
        self.scene = scene_fixture.AssistantSceneSearchTests(
            'test_full_cohort_integrity_is_rechecked_even_outside_the_saved_first_page')
        self.scene.setUp()
        self.addCleanup(self.scene.doCleanups)

    def _add_ranked_assets(self):
        # Existing generated fixture contributes two eligible family-a images.
        # Add 19 exact top-score vectors and 24 lower-score vectors: 45 total.
        with closing(sqlite3.connect(self.scene.source.database)) as db, db:
            db.execute('PRAGMA foreign_keys=ON')
            holder = SimpleNamespace(db=db, root=self.scene.pilot.root)
            for aid in range(1000, 1043):
                vector = (1.0, 0.0) if aid < 1019 else (0.5, math.sqrt(0.75))
                source_hash = hashlib.sha256(str(aid).encode()).hexdigest()
                db.execute('INSERT INTO assets(id,status,mime,hash_sha256) VALUES(?,?,?,?)',
                           (aid, 'active', 'image/jpeg', source_hash))
                db.execute('INSERT INTO access_asset_libraries VALUES(?,?)', (aid, 'family-a'))
                path, record = vector_fixtures.VisualVectorLoaderTests.add_vector(
                    holder, aid, vector, source_hash=source_hash)
                self.scene.pilot.files[str(aid)] = (path, record)
            db.commit()
            index = scene_fixture.reviewed(AccessService(db, clock=lambda: scene_fixture.NOW))
        index_patch = patch.object(self.scene.source.discovery_runtime.provider, 'get',
                                    return_value=index)
        index_patch.start()
        self._index_patch = index_patch
        self.addCleanup(index_patch.stop)

    def _refresh_reviewed_index(self):
        with closing(sqlite3.connect(self.scene.source.database)) as db:
            db.execute('PRAGMA foreign_keys=ON')
            index = scene_fixture.reviewed(
                AccessService(db, clock=lambda: scene_fixture.NOW))
        self._index_patch.return_value = index

    def _install_embeddings(self, vectors, callback=None):
        values = iter(vectors)
        calls = []
        binding = self.scene.pilot.runtime.encoder.binding

        def provider(request):
            payload = json.loads(request.content)
            calls.append(payload)
            if callback is not None:
                callback()
            vector = list(next(values))
            return httpx.Response(200, json={
                'version': 1,
                'binding_sha256': binding.binding_sha256,
                'query_sha256': hashlib.sha256(payload['query'].encode()).hexdigest(),
                'vector': vector,
                'checksum_sha256': canonical_vector_checksum(vector),
            })

        encoder = LocalSemanticEncoder(binding, 'http://127.0.0.1:43210/v1/encode-text',
                                       transport=httpx.MockTransport(provider))
        runtime = replace(self.scene.pilot.runtime, encoder=encoder)
        self.scene.pilot.runtime = runtime
        self.scene.app.state.semantic_search_runtime = runtime
        return calls

    def _scene_result(self):
        self._add_ranked_assets()
        scope = self.scene.scope('find photos')
        request_id = str(uuid.uuid4())
        response = self.scene.send('a kite', 1, scene=True, rid=request_id)
        self.assertEqual(response.status_code, 200, response.text)
        value = response.json()
        self.scene_revision = value['revision']
        return scope, request_id, value['result']

    def _page(self, request_id, page, digest=None, *, library='family-a', revision=None,
              thread_id=None, extra=None):
        revision = getattr(self, 'scene_revision', 1) if revision is None else revision
        body = {'version': 1, 'library_id': library, 'expected_revision': revision,
                'page': page}
        if digest is not None:
            body['ranking_sha256'] = digest
        body.update(extra or {})
        thread_id = thread_id or self.scene.thread
        return self.scene.client.post(
            f'{BASE}/threads/{thread_id}/requests/{request_id}/scene-pages',
            headers=self.scene.headers, json=body)

    def test_pages_are_exact_rank_slices_and_leave_durable_first_page_unchanged(self):
        _scope, request_id, original = self._scene_result()
        self.assertEqual(original['total'], 45)
        before_calls = len(self.scene.pilot.calls)
        page2 = self._page(request_id, 2)
        self.assertEqual(page2.status_code, 200, page2.text)
        page2_value = page2.json()
        self.assertEqual(set(page2_value), {
            'version', 'thread_id', 'request_id', 'revision', 'page', 'page_size',
            'total', 'has_more', 'binding', 'fingerprint', 'ranking_sha256',
            'items', 'semantic'})
        self.assertEqual((page2_value['page'], page2_value['page_size'],
                          page2_value['total'], page2_value['has_more']), (2, 20, 45, True))
        self.assertEqual(len(page2_value['ranking_sha256']), 64)
        page3 = self._page(request_id, 3, page2_value['ranking_sha256'])
        self.assertEqual(page3.status_code, 200, page3.text)
        page3_value = page3.json()
        self.assertEqual((page3_value['page'], len(page3_value['items']),
                          page3_value['has_more']), (3, 5, False))
        self.assertEqual(page3_value['ranking_sha256'], page2_value['ranking_sha256'])
        page1 = self._page(request_id, 1, page2_value['ranking_sha256'])
        self.assertEqual(page1.status_code, 200, page1.text)
        page1_value = page1.json()
        self.assertEqual(page1_value['ranking_sha256'], page2_value['ranking_sha256'])

        first_ids = [item['id'] for item in original['items']]
        second_ids = [item['id'] for item in page2_value['items']]
        third_ids = [item['id'] for item in page3_value['items']]
        all_scores = ([item['semantic_score'] for item in original['items']] +
                      [item['semantic_score'] for item in page2_value['items']] +
                      [item['semantic_score'] for item in page3_value['items']])
        combined = first_ids + second_ids + third_ids
        self.assertEqual(len(combined), 45)
        self.assertEqual(len(set(combined)), 45)
        self.assertEqual(all_scores, sorted(all_scores, reverse=True))
        self.assertEqual([item['id'] for item in page1_value['items']], first_ids)
        self.assertEqual([item['semantic_score'] for item in page1_value['items']],
                         [item['semantic_score'] for item in original['items']])
        self.assertEqual([item['semantic_score'] for item in page1_value['items']],
                         sorted((item['semantic_score'] for item in page1_value['items']),
                                reverse=True))
        self.assertEqual(len(self.scene.pilot.calls) - before_calls, 3)

        # Recovery continues to serve the persisted first page without encoding,
        # and explicit continuation does not create/update turns or exchanges.
        with closing(sqlite3.connect(self.scene.store.path)) as db:
            before = db.execute('''SELECT status,revision,result_summary FROM turn_requests
                                   WHERE request_id=?''', (request_id,)).fetchone()
            turn_before = db.execute('SELECT revision FROM threads WHERE thread_id=?',
                                     (self.scene.thread,)).fetchone()
            exchange_before = db.execute('SELECT COUNT(*) FROM exchanges').fetchone()[0]
        recovered = self.scene.read(request_id)
        self.assertEqual(recovered.status_code, 200, recovered.text)
        self.assertEqual(recovered.json()['result'], original)
        self.assertEqual(len(self.scene.pilot.calls) - before_calls, 3)
        with closing(sqlite3.connect(self.scene.store.path)) as db:
            after = db.execute('''SELECT status,revision,result_summary FROM turn_requests
                                  WHERE request_id=?''', (request_id,)).fetchone()
            turn_after = db.execute('SELECT revision FROM threads WHERE thread_id=?',
                                    (self.scene.thread,)).fetchone()
            exchange_after = db.execute('SELECT COUNT(*) FROM exchanges').fetchone()[0]
        self.assertEqual((after, turn_after, exchange_after),
                         (before, turn_before, exchange_before))

    def test_rank_prefix_and_unseen_tail_digest_changes_return_no_cards(self):
        _scope, request_id, original = self._scene_result()
        established = self._page(request_id, 2)
        self.assertEqual(established.status_code, 200, established.text)
        digest = established.json()['ranking_sha256']

        # A changed query vector keeps the exact-score prefix but changes the
        # tail's binary64 scores. The old continuation digest must refuse it.
        self._install_embeddings([(1.0, 1e-8)])
        changed_tail = self._page(request_id, 3, digest)
        self.assertIn(changed_tail.status_code, (409, 503), changed_tail.text)
        self.assertNotIn('items', changed_tail.json())

        # A rank change that moves the stored first 20 is rejected even when
        # the caller starts a fresh, hashless page-2 continuation.
        self._install_embeddings([(0.0, 1.0)])
        changed_prefix = self._page(request_id, 2)
        self.assertIn(changed_prefix.status_code, (409, 503), changed_prefix.text)
        self.assertNotIn('items', changed_prefix.json())
        self.assertEqual(self.scene.read(request_id).json()['result'], original)

    def test_wire_schema_and_scoped_request_identity_fail_closed(self):
        _scope, request_id, _original = self._scene_result()
        current_revision = self.scene_revision
        bad_bodies = (
            {'version': True, 'library_id': 'family-a', 'expected_revision': current_revision, 'page': 2},
            {'version': 1.0, 'library_id': 'family-a', 'expected_revision': current_revision, 'page': 2},
            {'version': 1, 'library_id': 'family-a', 'expected_revision': True, 'page': 2},
            {'version': 1, 'library_id': 'family-a', 'expected_revision': float(current_revision), 'page': 2},
            {'version': 1, 'library_id': 'family-a', 'expected_revision': current_revision, 'page': True},
            {'version': 1, 'library_id': 'family-a', 'expected_revision': current_revision, 'page': 2.0},
            {'version': 1, 'library_id': 'family-a', 'expected_revision': current_revision, 'page': 2,
             'ranking_sha256': 'A' * 64},
            {'version': 1, 'library_id': 'family-a', 'expected_revision': current_revision, 'page': 2,
             'ranking_sha256': None},
            {'version': 1, 'library_id': 'family-a', 'expected_revision': current_revision, 'page': 2,
             'ranking_sha256': False},
            {'version': 1, 'library_id': 'family-a', 'expected_revision': current_revision, 'page': 2,
             'ranking_sha256': []},
            {'version': 1, 'library_id': 'family-a', 'expected_revision': current_revision, 'page': 2,
             'ranking_sha256': 7.0},
            {'version': 1, 'library_id': 'family-a', 'expected_revision': current_revision, 'page': 2,
             'query': 'ignore stored server query'},
            {'version': 1, 'library_id': 'family-a', 'expected_revision': current_revision, 'page': 5001},
            {'version': 1, 'library_id': 'family-a', 'expected_revision': current_revision, 'page': 3},
        )
        provider_calls = len(self.scene.pilot.calls)
        for body in bad_bodies:
            with self.subTest(body=body):
                response = self.scene.client.post(
                    f'{BASE}/threads/{self.scene.thread}/requests/{request_id}/scene-pages',
                    headers=self.scene.headers, json=body)
                self.assertEqual(response.status_code, 400, response.text)
                self.assertEqual(response.json().get('error'), 'invalid_request')
                self.assertNotIn('items', response.json())
        self.assertEqual(len(self.scene.pilot.calls), provider_calls)

        wrong_request = self._page(str(uuid.uuid4()), 2)
        self.assertIn(wrong_request.status_code, (404, 409), wrong_request.text)
        self.assertNotIn('items', wrong_request.json())
        wrong_revision = self._page(request_id, 2, revision=0)
        self.assertIn(wrong_revision.status_code, (404, 409), wrong_revision.text)
        self.assertNotIn('items', wrong_revision.json())
        wrong_library = self._page(request_id, 2, library='family-b')
        self.assertIn(wrong_library.status_code, (401, 403, 404, 409), wrong_library.text)
        self.assertNotIn('items', wrong_library.json())
        wrong_thread = self._page(request_id, 2, thread_id=str(uuid.uuid4()))
        self.assertIn(wrong_thread.status_code, (404, 409), wrong_thread.text)
        self.assertNotIn('items', wrong_thread.json())

    def test_capability_is_closed_and_newer_request_of_any_status_blocks_old_rank(self):
        _scope, request_id, _original = self._scene_result()
        capability = self.scene.client.get(
            BASE + '/scene-page-capabilities?library_id=family-a', headers=self.scene.auth)
        self.assertEqual(capability.status_code, 200, capability.text)
        self.assertEqual(capability.json(), {'version': 1, 'available': True, 'page_size': 20})
        self.scene.app.state.assistant_semantic_search_enabled = False
        unavailable = self.scene.client.get(
            BASE + '/scene-page-capabilities?library_id=family-a', headers=self.scene.auth)
        self.assertEqual(unavailable.json(),
                         {'version': 1, 'available': False, 'page_size': 20})
        self.scene.app.state.assistant_semantic_search_enabled = True

        with closing(sqlite3.connect(self.scene.store.path)) as db:
            db.row_factory = sqlite3.Row
            original = db.execute('SELECT * FROM turn_requests WHERE request_id=?',
                                  (request_id,)).fetchone()
            thread_revision = db.execute('SELECT revision FROM threads WHERE thread_id=?',
                                         (self.scene.thread,)).fetchone()[0]
        now = int(scene_fixture.NOW)
        statuses = ('pending', 'failed', 'interrupted', 'completed', 'expired')
        for status in statuses:
            blocker_id = str(uuid.uuid4())
            if status == 'pending':
                row = (blocker_id, self.scene.thread, original['account_id'], 'family-a',
                       'pending', now + 1, now + 3600, thread_revision, 'new request',
                       'lease', now + 30, thread_revision, None, None)
            elif status in ('failed', 'interrupted'):
                row = (blocker_id, self.scene.thread, original['account_id'], 'family-a',
                       status, now + 1, now + 3600, thread_revision, 'new request',
                       None, None, thread_revision, None,
                       'scene_query_unsupported' if status == 'failed' else 'interrupted')
            elif status == 'expired':
                row = (blocker_id, self.scene.thread, original['account_id'], 'family-a',
                       'completed', now + 1, now - 1, thread_revision, 'expired result',
                       None, None, thread_revision, original['result_summary'], None)
            else:
                row = (blocker_id, self.scene.thread, original['account_id'], 'family-a',
                       'completed', now + 1, now + 3600, thread_revision, 'new result',
                       None, None, thread_revision, original['result_summary'], None)
            with closing(sqlite3.connect(self.scene.store.path)) as db, db:
                db.execute('''INSERT INTO turn_requests(request_id,thread_id,account_id,library_id,
                    status,created_at,expires_at,expected_revision,input_text,lease_id,
                    lease_expires_at,revision,result_summary,error_code)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', row)
            response = self._page(request_id, 2)
            self.assertIn(response.status_code, (404, 409),
                          f'{status} did not suppress old request: {response.text}')
            self.assertNotIn('items', response.json())
            with closing(sqlite3.connect(self.scene.store.path)) as db, db:
                db.execute('DELETE FROM turn_requests WHERE request_id=?', (blocker_id,))

    def test_source_or_membership_change_during_encode_suppresses_page(self):
        _scope, request_id, _original = self._scene_result()
        self.scene.pilot.during_encode = lambda: self.scene.source.mutate(
            "UPDATE access_memberships SET status='revoked' WHERE account_id='one'")
        response = self._page(request_id, 2)
        self.assertIn(response.status_code, (401, 403, 409, 503), response.text)
        self.assertNotIn('items', response.json())

    def test_discovery_source_change_during_encode_suppresses_page(self):
        _scope, request_id, _original = self._scene_result()
        self.scene.pilot.during_encode = lambda: self.scene.source.mutate(
            "UPDATE assets SET taken_at='2026-02-03' WHERE id=1000")
        response = self._page(request_id, 2)
        self.assertIn(response.status_code, (409, 503), response.text)
        self.assertNotIn('items', response.json())

    def test_legacy_vector_file_change_after_preload_refuses_and_restores(self):
        _scope, request_id, original = self._scene_result()
        self.assertIsNone(self.scene.pilot.runtime.serving_limits)
        vector_path = self.scene.pilot.files['1000'][0]
        original_bytes = vector_path.read_bytes()
        established = self._page(request_id, 2)
        self.assertEqual(established.status_code, 200, established.text)
        ranking_digest = established.json()['ranking_sha256']
        calls_before_mutation = len(self.scene.pilot.calls)

        try:
            # In the legacy fixture path, vectors are preloaded before provider
            # execution. A post-encode check must catch this mid-request edit.
            self.scene.pilot.during_encode = lambda: vector_path.write_bytes(
                b'changed generated vector artifact')
            changed = self._page(request_id, 3, ranking_digest)
            self.assertIn(changed.status_code, (409, 503), changed.text)
            self.assertNotIn('items', changed.json())
        finally:
            self.scene.pilot.during_encode = None
            vector_path.write_bytes(original_bytes)

        restored = self._page(request_id, 3, ranking_digest)
        self.assertEqual(restored.status_code, 200, restored.text)
        self.assertEqual(restored.json()['ranking_sha256'], ranking_digest)
        call_count = len(self.scene.pilot.calls)
        recovered = self.scene.read(request_id)
        self.assertEqual(recovered.status_code, 200, recovered.text)
        self.assertEqual(recovered.json()['result'], original)
        self.assertEqual(len(self.scene.pilot.calls), call_count)

    def test_elapsed_deadline_after_provider_completion_suppresses_page(self):
        _scope, request_id, _original = self._scene_result()
        budget = self.scene.pilot.runtime.budget
        clock_value = {'now': 0.0}
        budget.clock = lambda: clock_value['now']
        self.scene.pilot.during_encode = lambda: clock_value.__setitem__(
            'now', float(budget.search_seconds) + 1.0)
        response = self._page(request_id, 2)
        self.assertEqual(response.status_code, 503, response.text)
        self.assertNotIn('items', response.json())

    def test_deadline_elapsed_during_final_store_read_suppresses_page(self):
        _scope, request_id, original = self._scene_result()
        budget = self.scene.pilot.runtime.budget
        old_clock = budget.clock
        clock_value = {'now': 0.0}
        budget.clock = lambda: clock_value['now']
        original_read = self.scene.store.get_scene_page_source
        calls = {'count': 0}

        def final_read_advances_clock(*args, **kwargs):
            result = original_read(*args, **kwargs)
            calls['count'] += 1
            if calls['count'] == 2:
                clock_value['now'] = float(budget.search_seconds) + 1.0
            return result

        try:
            with patch.object(self.scene.store, 'get_scene_page_source',
                              side_effect=final_read_advances_clock):
                response = self._page(request_id, 2)
            self.assertEqual(calls['count'], 2)
            self.assertEqual(response.status_code, 503, response.text)
            self.assertNotIn('items', response.json())
        finally:
            budget.clock = old_clock
        call_count = len(self.scene.pilot.calls)
        recovered = self.scene.read(request_id)
        self.assertEqual(recovered.status_code, 200, recovered.text)
        self.assertEqual(recovered.json()['result'], original)
        self.assertEqual(len(self.scene.pilot.calls), call_count)

    def test_owner_role_loss_during_final_store_read_suppresses_cards(self):
        with closing(sqlite3.connect(self.scene.source.database)) as db, db:
            db.execute("UPDATE access_memberships SET role='owner' "
                       "WHERE account_id='one' AND library_id='family-a'")
        runtime = replace(self.scene.pilot.runtime, pilot_owner_account_id='one')
        self.scene.pilot.runtime = runtime
        self.scene.app.state.semantic_search_runtime = runtime
        _scope, request_id, _original = self._scene_result()

        original_read = self.scene.store.get_scene_page_source
        calls = {'count': 0}

        def final_read_revokes_owner(*args, **kwargs):
            result = original_read(*args, **kwargs)
            calls['count'] += 1
            if calls['count'] == 2:
                self.scene.source.mutate(
                    "UPDATE access_memberships SET role='viewer' "
                    "WHERE account_id='one' AND library_id='family-a'")
            return result

        with patch.object(self.scene.store, 'get_scene_page_source',
                          side_effect=final_read_revokes_owner):
            lost = self._page(request_id, 2)
        self.assertEqual(calls['count'], 2)
        self.assertIn(lost.status_code, (401, 403, 409, 503), lost.text)
        self.assertNotIn('items', lost.json())

        with closing(sqlite3.connect(self.scene.source.database)) as db, db:
            db.execute("UPDATE access_memberships SET role='owner' "
                       "WHERE account_id='one' AND library_id='family-a'")
        self._refresh_reviewed_index()
        thread = self.scene.client.post(BASE + '/threads', headers=self.scene.auth,
                                        json={'library_id': 'family-a'})
        self.assertEqual(thread.status_code, 201, thread.text)
        self.scene.thread = thread.json()['thread']['thread_id']
        self.scene.scope('find photos')
        next_id = str(uuid.uuid4())
        next_scene = self.scene.send('a kite', 1, scene=True, rid=next_id)
        self.assertEqual(next_scene.status_code, 200, next_scene.text)
        self.scene_revision = next_scene.json()['revision']
        resumed = self._page(next_id, 2)
        self.assertEqual(resumed.status_code, 200, resumed.text)

    def test_peer_disconnect_during_provider_does_not_publish_cards(self):
        _scope, request_id, _original = self._scene_result()
        disconnected = threading.Event()
        disconnect_delivered = threading.Event()

        def provider_completes_after_disconnect():
            disconnected.set()
            if not disconnect_delivered.wait(3.0):
                raise AssertionError('route watcher did not observe generated disconnect')
            # Let the ASGI watcher process the disconnect before the provider
            # returns to the ranking path.
            time.sleep(0.05)

        self.scene.pilot.during_encode = provider_completes_after_disconnect
        body = json.dumps({'version': 1, 'library_id': 'family-a',
                           'expected_revision': self.scene_revision, 'page': 2},
                          separators=(',', ':')).encode()
        headers = [
            (b'host', b'photohouse.example.test'),
            (b'authorization', b'Bearer ' + ('a' * 43).encode()),
            (b'x-photohouse-search-version', b'4'),
            (b'content-type', b'application/json'),
            (b'content-length', str(len(body)).encode()),
        ]
        scope = {'type': 'http', 'asgi': {'version': '3.0', 'spec_version': '2.3'},
                 'http_version': '1.1', 'method': 'POST', 'scheme': 'https',
                 'path': f'{BASE}/threads/{self.scene.thread}/requests/{request_id}/scene-pages',
                 'raw_path': f'{BASE}/threads/{self.scene.thread}/requests/{request_id}/scene-pages'.encode(),
                 'query_string': b'', 'root_path': '', 'headers': headers,
                 'server': ('photohouse.example.test', 443), 'client': ('testclient', 50123),
                 'state': {}}
        first = {'pending': True}
        sent = []

        async def receive():
            if first['pending']:
                first['pending'] = False
                return {'type': 'http.request', 'body': body, 'more_body': False}
            deadline = asyncio.get_running_loop().time() + 5.0
            while not disconnected.is_set():
                if asyncio.get_running_loop().time() > deadline:
                    raise TimeoutError('generated provider did not reach disconnect gate')
                await asyncio.sleep(0.001)
            disconnect_delivered.set()
            return {'type': 'http.disconnect'}

        async def send(message):
            sent.append(message)

        asyncio.run(self.scene.app(scope, receive, send))
        self.assertTrue(disconnected.is_set())
        start = next(message for message in sent if message['type'] == 'http.response.start')
        payload = b''.join(message.get('body', b'') for message in sent
                           if message['type'] == 'http.response.body')
        self.assertNotEqual(start['status'], 200)
        if payload:
            self.assertNotIn(b'"items"', payload)

    def test_serving_off_or_runtime_replacement_during_encode_suppresses_cards(self):
        _scope, request_id, _original = self._scene_result()
        self.scene.pilot.during_encode = lambda: setattr(
            self.scene.app.state, 'assistant_semantic_search_enabled', False)
        off = self._page(request_id, 2)
        self.assertIn(off.status_code, (409, 503), off.text)
        self.assertNotIn('items', off.json())
        self.scene.pilot.during_encode = None
        self.scene.app.state.assistant_semantic_search_enabled = True

        old_discovery = self.scene.app.state.discovery_runtime
        self.scene.pilot.during_encode = lambda: setattr(
            self.scene.app.state, 'discovery_runtime', replace(old_discovery))
        replaced = self._page(request_id, 2)
        self.assertIn(replaced.status_code, (409, 503), replaced.text)
        self.assertNotIn('items', replaced.json())
        self.scene.pilot.during_encode = None

