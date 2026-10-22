"""HTTP boundary tests for protected, opt-in selected-story draft operations."""

import asyncio
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))

import test_selected_story_lifecycle as lifecycle_fixture
import test_shared_memory_evidence as source_fixture
from app.access.selected_story_operations import DraftOperationError
from app.access.transport import csrf_token
from app.main import create_app


ORIGIN = 'https://photohouse.test'
PREPARE = '/story-workspace/drafts/prepare?library=library-a'
CANCEL = '/story-workspace/drafts/cancel?library=library-a'
REQUEST_ID = lifecycle_fixture.REQUEST_ID


class HoldingProvider:
    def __init__(self, *, hold=False, bad_output=False, cleanup_hold=False):
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        if not hold:
            self.release.set()
        self.cleanup_started = asyncio.Event()
        self.release_cleanup = asyncio.Event()
        if not cleanup_hold:
            self.release_cleanup.set()
        self.bad_output = bad_output
        self.prepare_calls = 0
        self.cleanup_calls = 0

    async def prepare(self, bundle, scope):
        self.prepare_calls += 1
        self.started.set()
        await self.release.wait()
        if self.bad_output:
            raise RuntimeError('synthetic provider secret')
        return {
            'version': 1, 'title': 'Beans together',
            'chapters': [{'id': chapter['id'], 'narration': 'We planted beans together.',
                          'source_ids': list(chapter['evidence_ids'])}
                         for chapter in bundle['chapters']],
            'questions': [], 'needs_review': True,
        }

    async def stop_and_reconcile(self, scope):
        self.cleanup_calls += 1
        self.cleanup_started.set()
        await self.release_cleanup.wait()
        return True


class LightweightTransportTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = lifecycle_fixture.Database()
        self.addCleanup(self.db.close)
        self.runtime = self.db.runtime()

    def app(self, provider=None, *, enabled=True):
        return create_app(access_runtime=self.runtime, selected_story_provider=provider,
                          memory_collaboration_enabled=provider is not None,
                          selected_story_drafts_enabled=enabled)

    def wire_sources(self, app):
        lifecycle = app.state.selected_story_lifecycle
        lifecycle.sources.resolve = lambda token, library, request: lifecycle_fixture.draft_snapshot(
            'synthetic-owner' if token == lifecycle_fixture.OWNER_TOKEN else 'synthetic-member',
            library, request)
        lifecycle.sources.revalidate = lambda token, snapshot: None
        return lifecycle

    async def with_client(self, app):
        client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN)
        return client

    async def request(self, client, body=None, *, token=lifecycle_fixture.OWNER_TOKEN,
                      path=PREPARE, headers=None, content=None):
        sent = {'Authorization': 'Bearer ' + token}
        if headers:
            sent.update(headers)
        if content is not None:
            return await client.post(path, headers=sent, content=content)
        return await client.post(path, headers=sent, json=body)

    async def test_default_off_provider_injection_and_factory_validation(self):
        provider = HoldingProvider()
        app = create_app(access_runtime=self.runtime, selected_story_provider=provider,
                         memory_collaboration_enabled=True)
        self.assertIs(app.state.selected_story_drafts_enabled, False)
        self.wire_sources(app)
        with patch('app.access.memory_jobs.maintenance', lambda runtime: None):
            async with app.router.lifespan_context(app):
                async with await self.with_client(app) as client:
                    response = await self.request(client, lifecycle_fixture.draft_request())
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['code'], 'draft_unavailable')
        self.assertEqual(provider.prepare_calls, 0)
        unstarted = self.app(provider)
        async with await self.with_client(unstarted) as client:
            unavailable = await self.request(client, lifecycle_fixture.draft_request())
        self.assertEqual(unavailable.status_code, 503)
        self.assertEqual(provider.prepare_calls, 0)
        with self.assertRaises(ValueError):
            create_app(access_runtime=self.runtime, selected_story_drafts_enabled=True)
        for invalid in (1, None, 'true'):
            with self.assertRaises(ValueError):
                create_app(access_runtime=self.runtime, selected_story_provider=provider,
                           memory_collaboration_enabled=True,
                           selected_story_drafts_enabled=invalid)

    async def test_http_prepare_uses_existing_strict_operations_and_returns_detached_result(self):
        provider = HoldingProvider()
        app = self.app(provider)
        lifecycle = self.wire_sources(app)
        with patch('app.access.memory_jobs.maintenance', lambda runtime: None):
            async with app.router.lifespan_context(app):
                async with await self.with_client(app) as client:
                    first = await self.request(client, lifecycle_fixture.draft_request())
                    self.assertEqual(first.status_code, 200, first.text)
                    payload = first.json()
                    self.assertEqual(payload['state'], 'needs_review')
                    self.assertEqual(payload['chapters'][0]['narration'],
                                     'We planted beans together.')
                    payload['chapters'][0]['narration'] = 'caller mutation'
                    again = await self.request(client, lifecycle_fixture.draft_request())
        self.assertEqual(again.status_code, 200, again.text)
        self.assertEqual(again.json()['chapters'][0]['narration'],
                         'We planted beans together.')
        self.assertEqual(provider.prepare_calls, 1)
        self.assertTrue(lifecycle.operations._records)

    async def test_bearer_cookie_csrf_and_revoked_session_are_enforced(self):
        provider = HoldingProvider()
        app = self.app(provider)
        self.wire_sources(app)
        token = lifecycle_fixture.OWNER_TOKEN
        with patch('app.access.memory_jobs.maintenance', lambda runtime: None):
            async with app.router.lifespan_context(app):
                async with await self.with_client(app) as client:
                    no_auth = await client.post(PREPARE, json=lifecycle_fixture.draft_request())
                    self.assertEqual(no_auth.status_code, 401)
                    cookie = {'Cookie': '__Host-ph_session=' + token,
                              'Origin': ORIGIN, 'Sec-Fetch-Site': 'same-origin'}
                    bad_csrf = await client.post(PREPARE, headers=cookie,
                                                 json=lifecycle_fixture.draft_request())
                    self.assertEqual(bad_csrf.status_code, 403)
                    good_cookie = cookie | {'X-CSRF-Token': csrf_token(token)}
                    good = await client.post(PREPARE, headers=good_cookie,
                                             json=lifecycle_fixture.draft_request())
                    self.assertEqual(good.status_code, 200, good.text)
                    cancel_body = {'version': 1, 'request_id': REQUEST_ID}
                    denied_cancel = await client.post(CANCEL, headers=cookie, json=cancel_body)
                    self.assertEqual(denied_cancel.status_code, 403)
                    allowed_cancel = await client.post(CANCEL, headers=good_cookie, json=cancel_body)
                    self.assertEqual(allowed_cancel.status_code, 200)
                    self.assertTrue(allowed_cancel.json()['matched'])
                    logout = await client.post('/auth/logout',
                        headers={'Authorization': 'Bearer ' + token})
                    self.assertEqual(logout.status_code, 200, logout.text)
                    replay = await self.request(client, lifecycle_fixture.draft_request(
                        '44444444-4444-4444-8444-444444444444'))
        self.assertEqual(replay.status_code, 401)
        self.assertEqual(replay.json()['code'], 'draft_access_denied')

    async def test_unknown_library_is_not_authorized(self):
        app = self.app(HoldingProvider())
        self.wire_sources(app)
        with patch('app.access.memory_jobs.maintenance', lambda runtime: None):
            async with app.router.lifespan_context(app):
                async with await self.with_client(app) as client:
                    response = await self.request(client, lifecycle_fixture.draft_request(),
                        path=PREPARE.replace('library-a', 'unknown-library'))
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['code'], 'draft_access_denied')

    async def test_strict_json_parser_rejects_duplicate_constants_encodings_and_bad_shape(self):
        app = self.app(HoldingProvider())
        self.wire_sources(app)
        valid = json.dumps(lifecycle_fixture.draft_request(), separators=(',', ':'))
        malformed = [
            ('{"version":1,"version":1}', {'Content-Type': 'application/json'}),
            (valid, {'Content-Type': 'application/json', 'Content-Encoding': 'gzip'}),
            (valid, {'Content-Type': 'text/plain'}),
            (json.dumps(lifecycle_fixture.draft_request() | {'extra': True}),
             {'Content-Type': 'application/json'}),
            (json.dumps(lifecycle_fixture.draft_request() | {'selection': {'asset_ids': [True]}}),
             {'Content-Type': 'application/json'}),
        ]
        with patch('app.access.memory_jobs.maintenance', lambda runtime: None):
            async with app.router.lifespan_context(app):
                async with await self.with_client(app) as client:
                    for index, (body, headers) in enumerate(malformed):
                        with self.subTest(body=body[:40]):
                            response = await self.request(client, headers=headers,
                                                          content=body.encode())
                            self.assertEqual(response.status_code, 400, response.text)
                            expected_detail = 'Invalid draft request' if index >= 3 else 'Invalid request'
                            self.assertEqual(response.json()['detail'], expected_detail)
                    parser_cases = [
                        b'[]', b'null',
                        valid.replace('"base_revision":"0"', '"base_revision":"0","base_revision":"0"').encode(),
                        valid.replace('"author_direction":"Keep it brief."', '"author_direction":NaN').encode(),
                        valid.replace('"author_direction":"Keep it brief."', '"author_direction":Infinity').encode(),
                        valid.encode() + b'\xff',
                        valid.encode('utf-16'),
                    ]
                    for body in parser_cases:
                        with self.subTest(parser_bytes=body[:20]):
                            response = await self.request(client, headers={'Content-Type': 'application/json'},
                                                          content=body)
                            self.assertEqual(response.status_code, 400, response.text)
                            self.assertEqual(response.json()['detail'], 'Invalid request')
                            self.assertEqual(response.headers['cache-control'], 'no-store')
                    mismatch = await self.request(client, headers={
                        'Content-Type': 'application/json', 'Content-Length': '0'}, content=valid.encode())
                    self.assertEqual(mismatch.status_code, 400)
                    async def chunks():
                        yield b' ' * (16 * 1024)
                        yield b' ' * (16 * 1024 + 1)
                    streamed = await self.request(client, headers={'Content-Type': 'application/json'},
                                                  content=chunks())
                    self.assertEqual(streamed.status_code, 413)
                    oversized = await self.request(client, headers={'Content-Type': 'application/json'},
                                                   content=b' ' * (32 * 1024 + 1))
                    self.assertEqual(oversized.status_code, 413)

    async def test_query_smuggling_missing_and_repeated_library_are_rejected(self):
        app = self.app(HoldingProvider())
        self.wire_sources(app)
        with patch('app.access.memory_jobs.maintenance', lambda runtime: None):
            async with app.router.lifespan_context(app):
                async with await self.with_client(app) as client:
                    missing = await self.request(client, lifecycle_fixture.draft_request(),
                                                 path='/story-workspace/drafts/prepare')
                    repeated = await self.request(client, lifecycle_fixture.draft_request(),
                                                  path=PREPARE + '&library=library-b')
                    extra = await self.request(client, lifecycle_fixture.draft_request(),
                                               path=PREPARE + '&redirect=https://evil.test')
        self.assertEqual([missing.status_code, repeated.status_code, extra.status_code], [400, 400, 400])

    async def test_retry_conflict_and_busy_have_fixed_wire_errors(self):
        provider = HoldingProvider(hold=True)
        app = self.app(provider)
        self.wire_sources(app)
        with patch('app.access.memory_jobs.maintenance', lambda runtime: None):
            async with app.router.lifespan_context(app):
                async with await self.with_client(app) as client:
                    pending = asyncio.create_task(self.request(client, lifecycle_fixture.draft_request()))
                    await asyncio.wait_for(provider.started.wait(), 2)
                    busy = await self.request(client, lifecycle_fixture.draft_request(
                        '44444444-4444-4444-8444-444444444444'))
                    conflict_body = lifecycle_fixture.draft_request() | {'author_direction': 'Different.'}
                    conflict = await self.request(client, conflict_body)
                    provider.release.set()
                    complete = await pending
        self.assertEqual(busy.status_code, 429)
        self.assertEqual(busy.json()['code'], 'draft_busy')
        self.assertEqual(busy.headers.get('retry-after'), '2')
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()['code'], 'draft_conflict')
        self.assertEqual(complete.status_code, 200)
        self.assertEqual(provider.prepare_calls, 1)

    async def test_disconnected_prepare_waiter_recovers_the_owned_generation(self):
        provider = HoldingProvider(hold=True)
        app = self.app(provider)
        self.wire_sources(app)
        with patch('app.access.memory_jobs.maintenance', lambda runtime: None):
            async with app.router.lifespan_context(app):
                async with await self.with_client(app) as client:
                    waiting = asyncio.create_task(self.request(client, lifecycle_fixture.draft_request()))
                    await asyncio.wait_for(provider.started.wait(), 5)
                    waiting.cancel()
                    with self.assertRaises(asyncio.CancelledError):
                        await waiting
                    self.assertEqual(app.state.inference_admission.state().active, 1)
                    retry = asyncio.create_task(self.request(client, lifecycle_fixture.draft_request()))
                    provider.release.set()
                    recovered = await asyncio.wait_for(retry, 5)
        self.assertEqual(recovered.status_code, 200, recovered.text)
        self.assertEqual(provider.prepare_calls, 1)

    async def test_fixed_expiry_exact_retry_returns_a_new_proposal(self):
        provider = HoldingProvider()
        app = self.app(provider)
        lifecycle = self.wire_sources(app)
        now = [100.0]
        with patch('app.access.memory_jobs.maintenance', lambda runtime: None):
            async with app.router.lifespan_context(app):
                lifecycle.operations.clock = lambda: now[0]
                lifecycle.operations.result_seconds = 1
                async with await self.with_client(app) as client:
                    first = await self.request(client, lifecycle_fixture.draft_request())
                    now[0] = 102.0
                    second = await self.request(client, lifecycle_fixture.draft_request())
                    now[0] = 102.5
                    retained = await self.request(client, lifecycle_fixture.draft_request())
        self.assertEqual([first.status_code, second.status_code, retained.status_code], [200, 200, 200])
        self.assertNotEqual(first.json()['draft_id'], second.json()['draft_id'])
        self.assertEqual(second.json(), retained.json())
        self.assertEqual(provider.prepare_calls, 2)

    async def test_other_session_and_viewer_cannot_read_or_cancel_a_proposal(self):
        provider = HoldingProvider()
        app = self.app(provider)
        self.wire_sources(app)
        with patch('app.access.memory_jobs.maintenance', lambda runtime: None):
            async with app.router.lifespan_context(app):
                async with await self.with_client(app) as client:
                    first = await self.request(client, lifecycle_fixture.draft_request(),
                                               token=lifecycle_fixture.MEMBER_TOKEN)
                    self.assertEqual(first.status_code, 200)
                    for path, body in ((PREPARE, lifecycle_fixture.draft_request()),
                                       (CANCEL, {'version': 1, 'request_id': REQUEST_ID})):
                        with self.subTest(other_session_path=path):
                            response = await self.request(client, body, path=path,
                                                          token=lifecycle_fixture.OTHER_TOKEN)
                            self.assertEqual(response.status_code, 409)
                            self.assertEqual(response.json()['code'], 'draft_scope_changed')
                    other_library = await self.request(client,
                        {'version': 1, 'request_id': REQUEST_ID},
                        path=CANCEL.replace('library-a', 'library-b'),
                        token=lifecycle_fixture.MEMBER_TOKEN)
                    self.assertEqual(other_library.status_code, 200)
                    self.assertFalse(other_library.json()['matched'])
                    retained = await self.request(client, lifecycle_fixture.draft_request(),
                                                  token=lifecycle_fixture.MEMBER_TOKEN)
                    self.assertEqual(retained.status_code, 200)
                    self.assertEqual(retained.json()['draft_id'], first.json()['draft_id'])
                    with self.db.connection() as db:
                        db.execute("UPDATE access_memberships SET role='viewer' WHERE account_id='synthetic-member'")
                        db.commit()
                    for path, body in ((PREPARE, lifecycle_fixture.draft_request()),
                                       (CANCEL, {'version': 1, 'request_id': REQUEST_ID})):
                        with self.subTest(viewer_path=path):
                            response = await self.request(client, body, path=path,
                                                          token=lifecycle_fixture.MEMBER_TOKEN)
                            self.assertEqual(response.status_code, 401)
                            self.assertEqual(response.json()['code'], 'draft_access_denied')
        self.assertEqual(provider.prepare_calls, 1)

    async def test_cancel_inflight_fences_late_result_and_keeps_admission_until_cleanup(self):
        provider = HoldingProvider(hold=True, cleanup_hold=True)
        app = self.app(provider)
        self.wire_sources(app)
        with patch('app.access.memory_jobs.maintenance', lambda runtime: None):
            async with app.router.lifespan_context(app):
                async with await self.with_client(app) as client:
                    pending = asyncio.create_task(self.request(client, lifecycle_fixture.draft_request()))
                    await asyncio.wait_for(provider.started.wait(), 2)
                    cancelling = asyncio.create_task(self.request(client,
                        {'version': 1, 'request_id': REQUEST_ID}, path=CANCEL))
                    await asyncio.wait_for(provider.cleanup_started.wait(), 2)
                    second = await self.request(client, lifecycle_fixture.draft_request(
                        '44444444-4444-4444-8444-444444444444'))
                    self.assertEqual(second.status_code, 429)
                    provider.release.set()
                    provider.release_cleanup.set()
                    canceled, fenced = await asyncio.gather(cancelling, pending)
        self.assertEqual(canceled.status_code, 200, canceled.text)
        self.assertTrue(canceled.json()['matched'])
        self.assertEqual(fenced.status_code, 409)
        self.assertEqual(fenced.json()['code'], 'draft_cancelled')
        self.assertEqual(provider.cleanup_calls, 1)

    async def test_cancel_unknown_is_false_and_does_not_tombstone_future_prepare(self):
        app = self.app(HoldingProvider())
        self.wire_sources(app)
        unknown = {'version': 1, 'request_id': '44444444-4444-4444-8444-444444444444'}
        with patch('app.access.memory_jobs.maintenance', lambda runtime: None):
            async with app.router.lifespan_context(app):
                async with await self.with_client(app) as client:
                    cancelled = await self.request(client, unknown, path=CANCEL)
                    future = await self.request(client, lifecycle_fixture.draft_request(
                        unknown['request_id']))
        self.assertEqual(cancelled.status_code, 200)
        self.assertFalse(cancelled.json()['matched'])
        self.assertEqual(future.status_code, 200, future.text)

    async def test_cancel_parser_caps_body_and_requires_canonical_request(self):
        app = self.app(HoldingProvider())
        self.wire_sources(app)
        with patch('app.access.memory_jobs.maintenance', lambda runtime: None):
            async with app.router.lifespan_context(app):
                async with await self.with_client(app) as client:
                    invalid_bodies = ({'version': True, 'request_id': REQUEST_ID},
                                      {'version': 1,
                                       'request_id': 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'.upper()},
                                      {'version': 1, 'request_id': REQUEST_ID, 'extra': 1})
                    for body in invalid_bodies:
                        with self.subTest(body=body):
                            response = await self.request(client, body, path=CANCEL)
                            self.assertEqual(response.status_code, 400, response.text)
                            self.assertEqual(response.json()['code'], 'draft_invalid_request')
                    too_large = await self.request(client, headers={'Content-Type': 'application/json'},
                        content=b' ' * 513, path=CANCEL)
        self.assertEqual(too_large.status_code, 413)

    async def test_operation_reasons_map_to_fixed_codes_and_retry_policy(self):
        app = self.app(HoldingProvider())
        lifecycle = self.wire_sources(app)
        expected = {
            'denied': (401, 'draft_access_denied', None),
            'invalid_request': (400, 'draft_invalid_request', None),
            'conflict': (409, 'draft_conflict', None),
            'scope_changed': (409, 'draft_scope_changed', None),
            'cancelled': (409, 'draft_cancelled', None),
            'busy': (429, 'draft_busy', '2'),
            'registry_full': (429, 'draft_capacity', None),
            'timed_out': (504, 'draft_timed_out', None),
            'unavailable': (503, 'draft_unavailable', None),
        }
        with patch('app.access.memory_jobs.maintenance', lambda runtime: None):
            async with app.router.lifespan_context(app):
                async with await self.with_client(app) as client:
                    for reason, (status, code, retry) in expected.items():
                        async def fail(*args, _reason=reason):
                            raise DraftOperationError(_reason)
                        lifecycle.operations.prepare = fail
                        response = await self.request(client, lifecycle_fixture.draft_request(
                            str(__import__('uuid').uuid4())))
                        self.assertEqual((response.status_code, response.json()['code']),
                                         (status, code), reason)
                        self.assertEqual(response.headers.get('retry-after'), retry)

    async def test_provider_failure_is_sanitized_and_never_echoes_exception(self):
        provider = HoldingProvider(bad_output=True)
        app = self.app(provider)
        self.wire_sources(app)
        with patch('app.access.memory_jobs.maintenance', lambda runtime: None):
            async with app.router.lifespan_context(app):
                async with await self.with_client(app) as client:
                    response = await self.request(client, lifecycle_fixture.draft_request())
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {'detail': 'Draft preparation unavailable',
                                           'code': 'draft_unavailable'})
        self.assertNotIn('synthetic provider secret', response.text)
        self.assertNotIn('family-synthetic-note-4', response.text)


    async def test_model_claims_of_save_authority_are_rejected_without_echo(self):
        class MalformedProvider(HoldingProvider):
            async def prepare(self, bundle, scope):
                return {'version': 1, 'title': 'synthetic private provider wording',
                        'chapters': [], 'questions': [], 'needs_review': False,
                        'state': 'saved'}
        app = self.app(MalformedProvider())
        self.wire_sources(app)
        with patch('app.access.memory_jobs.maintenance', lambda runtime: None):
            async with app.router.lifespan_context(app):
                async with await self.with_client(app) as client:
                    response = await self.request(client, lifecycle_fixture.draft_request())
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {'detail': 'Draft preparation unavailable',
                                           'code': 'draft_unavailable'})
        self.assertNotIn('synthetic private provider wording', response.text)


class RealSnapshotTransportTests(unittest.IsolatedAsyncioTestCase):
    """One small generated-library integration check through actual source resolution."""

    @classmethod
    def setUpClass(cls):
        source_fixture.SharedMemoryEvidenceTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        source_fixture.SharedMemoryEvidenceTests.tearDownClass()

    def setUp(self):
        self.fixture = source_fixture.SharedMemoryEvidenceTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    async def test_resolves_real_selected_source_and_denies_foreign_library_asset(self):
        provider = HoldingProvider()
        app = create_app(access_runtime=self.fixture.runtime, selected_story_provider=provider,
                         memory_collaboration_enabled=True, memory_groups_enabled=True,
                         selected_story_drafts_enabled=True)
        preview = self.fixture.preview('102').json()
        source_id = self.fixture.source_id
        request = {
            'version': 1, 'request_id': REQUEST_ID,
            'target': {'story_id': None, 'base_revision': '0'},
            'selection': {'asset_ids': ['102'],
                          'selection_revision': preview['selection_revision'],
                          'source_policy': 'chapter_sources_v1',
                          'chapters': [{'id': 'chapter-1', 'title': 'Preparing the bed',
                                        'asset_ids': ['102'], 'evidence_ids': [source_id]}]},
            'theme': 'everyday', 'language': 'en', 'title': 'A garden day',
            'author_direction': 'Keep it brief.',
        }
        with patch('app.access.memory_jobs.maintenance', lambda runtime: None):
            async with app.router.lifespan_context(app):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                             base_url=ORIGIN) as client:
                    good = await client.post(PREPARE.replace('library-a', 'family-a'),
                        headers=self.fixture.headers, json=request)
                    foreign = json.loads(json.dumps(request))
                    foreign['request_id'] = '44444444-4444-4444-8444-444444444444'
                    foreign['selection']['asset_ids'] = ['201']
                    foreign['selection']['selection_revision'] = '0' * 64
                    foreign['selection']['chapters'][0]['asset_ids'] = ['201']
                    foreign['selection']['chapters'][0]['evidence_ids'] = []
                    denied = await client.post(PREPARE.replace('library-a', 'family-a'),
                        headers=self.fixture.headers, json=foreign)
        self.assertEqual(good.status_code, 200, good.text)
        result = good.json()
        citations = result['chapters'][0]['citations']
        self.assertIn(source_id, [source['source_id'] for source in citations])
        self.assertEqual(citations[0]['byline'], 'A parent')
        self.assertEqual(denied.status_code, 401)
        self.assertEqual(denied.json()['code'], 'draft_access_denied')


if __name__ == '__main__':
    unittest.main()
