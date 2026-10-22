"""App/session ownership tests for selected-story access changes."""

import asyncio
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))

from app.access.credentials import DUMMY_HASH, session_digest
from app.access.inference_admission import InferenceAdmission
from app.access.schema import apply_schema
from app.access.selected_story_lifecycle import SelectedStoryLifecycle
from app.access.selected_story_operations import DraftOperationError, DraftPrincipal
from app.access.selected_story_snapshot import SourceSnapshot
from app.access.transport import AccessRuntime, TransportError
from app.main import create_app


ORIGIN = 'https://photohouse.test'
OWNER_TOKEN = 'O' * 43
MEMBER_TOKEN = 'M' * 43
OTHER_TOKEN = 'X' * 43
UNKNOWN_TOKEN = 'Z' * 43
NOW = 2_000_000_000
REQUEST_ID = '22222222-2222-4222-8222-222222222222'
OPERATION_ID = '33333333-3333-4333-8333-333333333333'
SELECTION_REVISION = 'a' * 64


def draft_request(request_id=REQUEST_ID):
    return {
        'version': 1, 'request_id': request_id,
        'target': {'story_id': None, 'base_revision': '0'},
        'selection': {'asset_ids': ['17000017'], 'selection_revision': SELECTION_REVISION,
                      'source_policy': 'chapter_sources_v1',
                      'chapters': [{'id': 'chapter-1', 'title': 'Preparing the bed',
                                    'asset_ids': ['17000017'],
                                    'evidence_ids': ['family-synthetic-note-4']}]},
        'theme': 'everyday', 'language': 'en', 'title': 'A garden day',
        'author_direction': 'Keep it brief.',
    }


def draft_snapshot(account_id, library, request):
    canonical = lambda value: json.dumps(value, sort_keys=True, ensure_ascii=False,
                                         separators=(',', ':')).encode()
    request_digest = hashlib.sha256(canonical([account_id, library, request])).hexdigest()
    source = {'source_id': 'family-synthetic-note-4', 'selected_asset_ids': ['17000017'],
              'source_kind': 'family_note', 'source_revision': 3,
              'source_digest': 'b' * 64, 'byline': 'Synthetic Aunt'}
    document = {'version': 1, 'request_id': request['request_id'], 'library_id': library,
                'target': request['target'], 'selection_revision': SELECTION_REVISION,
                'source_policy': 'chapter_sources_v1',
                'chapters': [{'id': 'chapter-1', 'title': 'Preparing the bed',
                              'asset_ids': ['17000017'], 'sources': [source]}]}
    bundle = {'version': 3, 'library_id': library,
              'target': {'type': 'draft', 'id': OPERATION_ID, 'revision': 0},
              'selection_revision': SELECTION_REVISION, 'language': 'en', 'theme': 'everyday',
              'title': 'A garden day', 'instructions': 'Keep it brief.',
              'chapters': [{'id': 'chapter-1', 'title': 'Preparing the bed', 'narration': '',
                            'asset_ids': ['17000017'], 'evidence_ids': ['family-synthetic-note-4']}],
              'sources': [{'id': 'family-synthetic-note-4', 'kind': 'family',
                           'source_kind': 'family_note', 'text': 'We planted beans together.',
                           'asset_id': '17000017', 'author': 'Synthetic Aunt'}],
              'recent_turns': []}
    return SourceSnapshot(account_id, library, request_digest, OPERATION_ID,
                          canonical(request), canonical(document), canonical(bundle),
                          b'{"authorized":"synthetic"}')


class Provider:
    async def prepare(self, bundle, scope):
        return {'version': 1, 'title': 'Beans together',
                'chapters': [{'id': 'chapter-1', 'narration': 'We planted beans together.',
                              'source_ids': ['family-synthetic-note-4']}],
                'questions': [], 'needs_review': True}

    async def stop_and_reconcile(self, scope):
        return True


class SyncProvider:
    def prepare(self, bundle, scope):
        return None

    async def stop_and_reconcile(self, scope):
        return True


class Database:
    def __init__(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'access.sqlite'
        with self.connection() as db, db:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('CREATE TABLE assets(id INTEGER PRIMARY KEY)')
            apply_schema(db.execute)
            for account_id, phone in (
                    ('synthetic-owner', '+12025550100'),
                    ('synthetic-member', '+12025550101'),
                    ('synthetic-other', '+12025550102')):
                db.execute('INSERT INTO access_accounts(id,phone_login,password_hash) VALUES (?,?,?)',
                           (account_id, phone, DUMMY_HASH))
            db.execute("INSERT INTO access_libraries(id,bootstrap_operator) VALUES ('library-a','synthetic-owner')")
            db.execute("INSERT INTO access_libraries(id,bootstrap_operator) VALUES ('library-b','synthetic-owner')")
            db.execute("INSERT INTO access_memberships(account_id,library_id,status,role,revision,approved_by) VALUES ('synthetic-owner','library-a','approved','owner',1,'synthetic-owner')")
            db.execute("INSERT INTO access_memberships(account_id,library_id,status,role,revision,approved_by) VALUES ('synthetic-owner','library-b','approved','owner',1,'synthetic-owner')")
            db.execute("INSERT INTO access_memberships(account_id,library_id,status,role,revision,approved_by) VALUES ('synthetic-member','library-a','approved','contributor',1,'synthetic-owner')")
            db.execute("INSERT INTO access_memberships(account_id,library_id,status,role,revision,approved_by) VALUES ('synthetic-member','library-b','approved','contributor',1,'synthetic-owner')")
            for token, account in ((OWNER_TOKEN, 'synthetic-owner'),
                                   (MEMBER_TOKEN, 'synthetic-member'),
                                   (OTHER_TOKEN, 'synthetic-member')):
                db.execute('INSERT INTO access_sessions(digest,account_id,expires_at) VALUES (?,?,?)',
                           (session_digest(token), account, NOW + 1000))

    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        return db

    @contextmanager
    def connection(self):
        db = self.connect()
        try:
            yield db
        finally:
            db.close()

    def runtime(self):
        return AccessRuntime(self.connection, ORIGIN, clock=lambda: NOW)

    def close(self):
        self.temp.cleanup()


class DatabaseFixtureTests(unittest.TestCase):
    def test_initialization_closes_its_connection_without_garbage_collection(self):
        opened = []
        connect = sqlite3.connect
        def tracked_connect(*args, **kwargs):
            db = connect(*args, **kwargs)
            opened.append(db)  # Keep a strong reference after initialization.
            return db
        fixture = None
        try:
            with patch.object(sqlite3, 'connect', side_effect=tracked_connect):
                fixture = Database()
            self.assertEqual(1, len(opened))
            with self.assertRaises(sqlite3.ProgrammingError):
                opened[0].execute('SELECT 1')
            with fixture.connection() as db:
                self.assertEqual(3, db.execute('SELECT COUNT(*) FROM access_sessions').fetchone()[0])
        finally:
            for db in opened:
                db.close()
            if fixture is not None:
                fixture.close()


class SelectedStoryLifecycleAppTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = Database()
        self.addCleanup(self.db.close)
        self.runtime = self.db.runtime()

    def app(self, **kwargs):
        return create_app(access_runtime=self.runtime, **kwargs)

    async def lifespan_client(self, app):
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN)

    async def test_default_off_and_invalid_injections_fail_closed(self):
        default = create_app()
        self.assertIsNone(default.state.selected_story_lifecycle)
        self.assertIsNone(default.state.selected_story_operations)
        self.assertIsNone(default.state.inference_admission)
        with self.assertRaises(ValueError):
            create_app(selected_story_provider=Provider())
        with self.assertRaises(ValueError):
            create_app(selected_story_provider=Provider(), memory_collaboration_enabled=True)
        with self.assertRaises(ValueError):
            create_app(access_runtime=self.runtime, selected_story_provider=SyncProvider(),
                       memory_collaboration_enabled=True)

    async def test_enabled_app_owns_one_lifecycle_and_shared_closed_gate(self):
        app = self.app(selected_story_provider=Provider(), memory_collaboration_enabled=True,
                       memory_groups_enabled=True)
        lifecycle = app.state.selected_story_lifecycle
        self.assertIsNone(app.state.selected_story_operations)
        self.assertIs(app.state.inference_admission, lifecycle.admission)
        with patch('app.access.memory_jobs.maintenance', lambda runtime: None):
            async with app.router.lifespan_context(app):
                self.assertIs(app.state.selected_story_operations, lifecycle.operations)
                self.assertIsNot(lifecycle.sources.runtime, self.runtime)
                self.assertTrue(lifecycle.sources.runtime.memory_groups_enabled)
                self.assertIs(type(lifecycle.admission), InferenceAdmission)
                self.assertEqual(lifecycle.admission.max_waiting, 0)
            self.assertTrue(lifecycle.closing)
            self.assertTrue(lifecycle.admission._closed)
            self.assertIsNotNone(lifecycle.shutdown_task)
            with self.assertRaises(RuntimeError):
                lifecycle.start()
            self.assertIs(app.state.selected_story_operations, lifecycle.operations)

    async def test_startup_maintenance_failure_still_closes_started_lifecycle(self):
        app = self.app(selected_story_provider=Provider(), memory_collaboration_enabled=True)
        lifecycle = app.state.selected_story_lifecycle
        with patch('app.access.memory_jobs.maintenance', side_effect=RuntimeError('synthetic maintenance failure')):
            with self.assertRaisesRegex(RuntimeError, 'synthetic maintenance failure'):
                async with app.router.lifespan_context(app):
                    self.fail('maintenance should fail before lifespan yields')
        self.assertTrue(lifecycle.closing)
        self.assertTrue(lifecycle.admission._closed)
        self.assertIsNotNone(lifecycle.shutdown_task)

    async def test_cancelled_close_waiter_does_not_replace_owned_shutdown(self):
        lifecycle = SelectedStoryLifecycle(self.runtime, Provider())
        lifecycle.start()
        entered, release = asyncio.Event(), asyncio.Event()

        async def slow_close():
            entered.set()
            await release.wait()
            return True

        lifecycle.operations.close = slow_close
        first = asyncio.create_task(lifecycle.close())
        await entered.wait()
        owned = lifecycle.shutdown_task
        first.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await first
        self.assertIs(lifecycle.shutdown_task, owned)
        self.assertTrue(lifecycle.admission._closed)
        second = asyncio.create_task(lifecycle.close())
        self.assertIs(lifecycle.shutdown_task, owned)
        release.set()
        self.assertTrue(await second)
        self.assertIs(lifecycle.shutdown_task, owned)

    async def test_logout_purges_ready_draft_and_database_auth_denies_replay(self):
        app = self.app(selected_story_provider=Provider(), memory_collaboration_enabled=True)
        lifecycle = app.state.selected_story_lifecycle
        lifecycle.sources.resolve = lambda token, library, request: draft_snapshot(
            'synthetic-owner', library, request)
        lifecycle.sources.revalidate = lambda token, snapshot: None
        with patch('app.access.memory_jobs.maintenance', lambda runtime: None):
            async with app.router.lifespan_context(app):
                result = await lifecycle.operations.prepare(OWNER_TOKEN, 'library-a', draft_request())
                self.assertEqual(result['state'], 'needs_review')
                record = next(iter(lifecycle.operations._records.values()))
                self.assertEqual(record.state, 'ready')
                await lifecycle.access_change('logout', OWNER_TOKEN)
                self.assertIsNone(record.payload)
                with self.assertRaises(DraftOperationError):
                    await lifecycle.operations.prepare(OWNER_TOKEN, 'library-a', draft_request())
                with self.db.connection() as db:
                    revoked = db.execute('SELECT revoked FROM access_sessions WHERE digest=?',
                        (session_digest(OWNER_TOKEN),)).fetchone()['revoked']
                self.assertEqual(revoked, 1)

    async def test_failed_logout_releases_temporary_barrier_and_keeps_db_policy(self):
        app = self.app(selected_story_provider=Provider(), memory_collaboration_enabled=True)
        lifecycle = app.state.selected_story_lifecycle
        lifecycle.sources.resolve = lambda token, library, request: draft_snapshot(
            'synthetic-member', library, request)
        lifecycle.sources.revalidate = lambda token, snapshot: None
        with patch('app.access.memory_jobs.maintenance', lambda runtime: None):
            async with app.router.lifespan_context(app):
                await lifecycle.operations.prepare(MEMBER_TOKEN, 'library-a', draft_request())
                record = next(iter(lifecycle.operations._records.values()))
                self.assertEqual(record.state, 'ready')
                original = self.runtime.call

                def failed_call(runtime, action, *args, **kwargs):
                    if action == 'logout':
                        raise RuntimeError('synthetic DB write failure')
                    return original(action, *args, **kwargs)

                with patch.object(AccessRuntime, 'call', failed_call):
                    with self.assertRaises(RuntimeError):
                        await lifecycle.access_change('logout', MEMBER_TOKEN)
                digest = session_digest(MEMBER_TOKEN)
                self.assertNotIn(digest, lifecycle.operations._session_barriers)
                self.assertNotIn(digest, lifecycle.operations._invalid_sessions)
                self.assertIsNone(record.payload)
                self.assertEqual(record.error, 'scope_changed')
                principal = await lifecycle.operations._authenticate(MEMBER_TOKEN, 'library-a')
                self.assertEqual(principal.account_id, 'synthetic-member')

    async def test_access_mutations_are_bounded_at_sixteen_owned_tasks(self):
        lifecycle = SelectedStoryLifecycle(self.runtime, Provider())
        lifecycle.start()
        started = threading.Event()
        release = threading.Event()
        count_lock = threading.Lock()
        started_count = 0
        original = AccessRuntime.call

        def blocked_call(runtime, action, *args, **kwargs):
            nonlocal started_count
            if action == 'logout':
                with count_lock:
                    started_count += 1
                    if started_count == 16:
                        started.set()
                if not release.wait(5):
                    raise RuntimeError('synthetic access mutation wait timed out')
            return original(runtime, action, *args, **kwargs)

        tokens = [f'{value:043d}' for value in range(16)]
        with patch.object(AccessRuntime, 'call', blocked_call):
            pending = [asyncio.create_task(lifecycle.access_change('logout', token))
                       for token in tokens]
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 5))
                self.assertEqual(len(lifecycle._mutations), 16)
                with self.assertRaises(TransportError) as caught:
                    await lifecycle.access_change('logout', '9' * 43)
                self.assertEqual(caught.exception.status, 503)
            finally:
                release.set()
            outcomes = await asyncio.gather(*pending, return_exceptions=True)
        self.assertTrue(all(not isinstance(outcome, BaseException) for outcome in outcomes))
        self.assertEqual(lifecycle._mutations, set())
        await lifecycle.close()

    async def test_successful_revoke_invalidates_only_matching_library_record(self):
        app = self.app(selected_story_provider=Provider(), memory_collaboration_enabled=True)
        lifecycle = app.state.selected_story_lifecycle
        lifecycle.sources.resolve = lambda token, library, request: draft_snapshot(
            'synthetic-member', library, request)
        lifecycle.sources.revalidate = lambda token, snapshot: None
        with patch('app.access.memory_jobs.maintenance', lambda runtime: None):
            async with app.router.lifespan_context(app):
                request_a, request_b = draft_request(REQUEST_ID), draft_request(
                    '44444444-4444-4444-8444-444444444444')
                await lifecycle.operations.prepare(MEMBER_TOKEN, 'library-a', request_a)
                await lifecycle.operations.prepare(MEMBER_TOKEN, 'library-b', request_b)
                records = {record.identity.library_id: record
                           for record in lifecycle.operations._records.values()}
                self.assertEqual({name: record.state for name, record in records.items()},
                                 {'library-a': 'ready', 'library-b': 'ready'})
                await lifecycle.access_change('revoke_membership', OWNER_TOKEN,
                    'library-a', 'synthetic-member', expected_revision=1)
                self.assertIsNone(records['library-a'].payload)
                self.assertEqual(records['library-a'].error, 'scope_changed')
                self.assertEqual(records['library-b'].state, 'ready')
                self.assertIsNotNone(records['library-b'].payload)
                retained = await lifecycle.operations.prepare(MEMBER_TOKEN, 'library-b', request_b)
                self.assertEqual(retained['state'], 'needs_review')

    async def test_logout_barrier_blocks_only_matching_session_during_db_write(self):
        app = self.app(selected_story_provider=Provider(), memory_collaboration_enabled=True)
        lifecycle = app.state.selected_story_lifecycle
        with patch('app.access.memory_jobs.maintenance', lambda runtime: None):
            async with app.router.lifespan_context(app):
                blocker = threading.Event()
                started = threading.Event()
                original = self.runtime.call

                def delayed_call(runtime, action, *args, **kwargs):
                    if action == 'logout' and args[0] == MEMBER_TOKEN:
                        started.set()
                        if not blocker.wait(5):
                            raise RuntimeError('synthetic DB wait timed out')
                    return original(action, *args, **kwargs)

                client = await self.lifespan_client(app)
                with patch.object(AccessRuntime, 'call', delayed_call):
                    async with client:
                        request = asyncio.create_task(client.post('/auth/logout',
                            headers={'Authorization': f'Bearer {MEMBER_TOKEN}'}))
                        self.assertTrue(await asyncio.to_thread(started.wait, 5))
                        self.assertIn(session_digest(MEMBER_TOKEN), lifecycle.operations._session_barriers)
                        with self.assertRaises(DraftOperationError):
                            lifecycle.operations._check_session(DraftPrincipal('synthetic-member', session_digest(MEMBER_TOKEN)))
                        lifecycle.operations._check_session(DraftPrincipal('synthetic-member', session_digest(OTHER_TOKEN)))
                        request.cancel()
                        with self.assertRaises(asyncio.CancelledError):
                            await request
                        self.assertIn(session_digest(MEMBER_TOKEN), lifecycle.operations._session_barriers)
                        blocker.set()
                        for _ in range(100):
                            with self.db.connection() as db:
                                revoked = db.execute('SELECT revoked FROM access_sessions WHERE digest=?',
                                    (session_digest(MEMBER_TOKEN),)).fetchone()['revoked']
                            if revoked:
                                break
                            await asyncio.sleep(.01)
                        self.assertEqual(revoked, 1)
                        for _ in range(100):
                            if session_digest(MEMBER_TOKEN) not in lifecycle.operations._session_barriers:
                                break
                            await asyncio.sleep(.01)
                        self.assertNotIn(session_digest(MEMBER_TOKEN), lifecycle.operations._session_barriers)

    async def test_unknown_logout_does_not_leave_permanent_session_hash(self):
        app = self.app(selected_story_provider=Provider(), memory_collaboration_enabled=True)
        lifecycle = app.state.selected_story_lifecycle
        with patch('app.access.memory_jobs.maintenance', lambda runtime: None):
            async with app.router.lifespan_context(app):
                client = await self.lifespan_client(app)
                async with client:
                    response = await client.post('/auth/logout',
                        headers={'Authorization': f'Bearer {UNKNOWN_TOKEN}'})
                self.assertEqual(response.status_code, 200)
                digest = session_digest(UNKNOWN_TOKEN)
                self.assertNotIn(digest, lifecycle.operations._session_barriers)
                self.assertNotIn(digest, lifecycle.operations._invalid_sessions)

    async def test_membership_hook_runs_only_after_success_and_only_for_target_scope(self):
        app = self.app(selected_story_provider=Provider(), memory_collaboration_enabled=True)
        lifecycle = app.state.selected_story_lifecycle
        calls = []
        with patch('app.access.memory_jobs.maintenance', lambda runtime: None):
            async with app.router.lifespan_context(app):
                original = lifecycle.operations.invalidate_membership
                lifecycle.operations.invalidate_membership = lambda account, library: (calls.append((account, library)), original(account, library))
                client = await self.lifespan_client(app)
                async with client:
                    unauthorized = await client.post('/libraries/library-a/members/synthetic-member/revoke',
                        headers={'Authorization': f'Bearer {MEMBER_TOKEN}'}, json={'revision': '1'})
                    self.assertEqual(unauthorized.status_code, 401)
                    self.assertEqual(calls, [])
                    denied = await client.post('/libraries/library-a/members/synthetic-member/revoke',
                        headers={'Authorization': f'Bearer {OWNER_TOKEN}'}, json={'revision': '99'})
                    self.assertEqual(denied.status_code, 409)
                    self.assertEqual(calls, [])
                    success = await client.post('/libraries/library-a/members/synthetic-member/revoke',
                        headers={'Authorization': f'Bearer {OWNER_TOKEN}'}, json={'revision': '1'})
                    self.assertEqual(success.status_code, 200)
                    self.assertEqual(calls, [('synthetic-member', 'library-a')])
                    with self.db.connection() as db:
                        status = db.execute("SELECT status FROM access_memberships WHERE account_id='synthetic-member' AND library_id='library-a'").fetchone()['status']
                        unaffected = db.execute("SELECT status FROM access_memberships WHERE account_id='synthetic-member' AND library_id='library-b'").fetchone()['status']
                    self.assertEqual(status, 'revoked')
                    self.assertEqual(unaffected, 'approved')


if __name__ == '__main__':
    unittest.main()
