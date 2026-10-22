"""Integrated default-off local-agent turns over generated PhotoHouse data."""
import asyncio
import sys
import tempfile
import threading
import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'tests' / 'security')]

from app.main import create_app
from app.access.assistant_agent import AgentBudget
from app.access.assistant_workspace_store import initialize_v2, LEASE_SECONDS
from app.access.assistant_journal import initialize as initialize_journal
from app.access.search_pending import PENDING_TTL_SECONDS
import test_semantic_search as generated
from phone_discovery_fixture import NOW, TOKEN

BASE = '/assistant/workspace/v1'
PROFILE = 'agent_media_search_v1'


class SyntheticRuntime:
    """Deterministic adapter that can only return a host-issued result handle."""

    def __init__(self, *, entered=None, release=None, after_search=None,
                 capability_attempts=1):
        self.entered = entered
        self.release = release
        self.after_search = after_search
        self.capability_attempts = capability_attempts
        self.calls = []
        self.tools = []
        self.inputs = []

    async def run(self, turn_input, tool_dispatch, invalidation):
        self.calls.append(turn_input)
        self.inputs.append(turn_input)
        if self.entered is not None:
            self.entered.set()
        if self.release is not None:
            await asyncio.to_thread(self.release.wait)
        for _ in range(self.capability_attempts):
            value = await tool_dispatch('get_search_capabilities', {})
            self.tools.append(('get_search_capabilities', value))
        projection = await tool_dispatch('search_media', {})
        self.tools.append(('search_media', projection))
        if self.after_search is not None:
            self.after_search()
        await tool_dispatch('inspect_current_results', {
            'outcome_handle': projection['outcome_handle']})
        self.tools.append(('inspect_current_results', projection['outcome_handle']))
        return {'outcome_handle': projection['outcome_handle']}


class AssistantAgentWorkspaceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Reuse only the generated reviewed SQLite/provider fixture; requests in
        # this module use their own context-managed ASGI client and lifespan.
        self.data = generated.SemanticSearchTests(
            'test_semantic_scores_replace_literal_eligibility_only_on_the_explicit_api')
        self.data.setUp()
        self.addCleanup(self.data.doCleanups)
        self.source = self.data.fixture
        self.now = [NOW]
        self.source.access = replace(self.source.access, clock=lambda: self.now[0])
        self.source.discovery_runtime = replace(self.source.discovery_runtime,
                                                access=self.source.access)
        self.temp = tempfile.TemporaryDirectory(prefix='agent-workspace-')
        self.addCleanup(self.temp.cleanup)
        self.store = initialize_v2(Path(self.temp.name).resolve() / 'workspace.sqlite',
                                    clock=lambda: self.now[0])
        self.runtime = SyntheticRuntime()
        self.app = self.make_app(self.runtime)
        self._client = None

    def make_app(self, runtime=None, **kwargs):
        return create_app(access_runtime=self.source.access,
            discovery_runtime=self.source.discovery_runtime,
            assistant_enabled=True, assistant_workspace_store=self.store,
            assistant_agent_runtime=runtime, **kwargs)

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self._lifespan = self.app.router.lifespan_context(self.app)
        await self._lifespan.__aenter__()
        self.addAsyncCleanup(self._lifespan.__aexit__, None, None, None)
        self._client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url='https://photohouse.example.test')
        await self._client.__aenter__()
        self.addAsyncCleanup(self._client.__aexit__, None, None, None)
        self.auth = {'Authorization': 'Bearer ' + TOKEN}
        self.v2 = self.auth | {'X-PhotoHouse-Search-Version': '2'}
        response = await self._client.post(BASE + '/threads', headers=self.auth,
                                           json={'library_id': 'family-a'})
        self.assertEqual(response.status_code, 201, response.text)
        self.thread = response.json()['thread']['thread_id']

    async def post_turn(self, text, revision=0, *, request_id=None, agent=False,
                        accepts=None, headers=None, memory_parent=None):
        body = {'library_id': 'family-a', 'request_id': request_id or str(uuid.uuid4()),
                'expected_revision': revision, 'text': text}
        if agent:
            body['accepts'] = [PROFILE] if accepts is None else accepts
        if memory_parent is not None:
            body['memory_parent'] = memory_parent
        return await self._client.post(
            f'{BASE}/threads/{self.thread}/turns',
            headers=headers or self.v2, json=body)

    async def read_turn(self, request_id, *, headers=None):
        return await self._client.get(
            f'{BASE}/threads/{self.thread}/requests/{request_id}?library_id=family-a',
            headers=headers or self.v2)

    async def settle(self):
        operation = self.app.state.assistant_agent_supervisor.active
        if operation is not None:
            await asyncio.wait_for(asyncio.shield(operation.task), 5)

    async def test_exact_profile_runs_real_protected_search_and_returns_domain_exchange(self):
        response = await self.post_turn(
            'find photos of Sample Child in September 2032', agent=True)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body['status'], 'completed')
        self.assertFalse(body['recovered'])
        result = body['result']
        self.assertEqual(result['kind'], 'results')
        self.assertEqual(result['filters']['people'], {'ids': ['301'], 'match': 'any'})
        self.assertEqual(result['filters']['date'], {
            'from': '2032-09-01', 'to': '2032-09-30'})
        self.assertEqual([item['id'] for item in result['items']], ['103', '101'])
        self.assertEqual(len(self.runtime.calls), 1)
        self.assertEqual(self.runtime.inputs[0], {
            'version': 1, 'text': 'find photos of Sample Child in September 2032',
            'locale': None})
        self.assertEqual([name for name, _ in self.runtime.tools], [
            'get_search_capabilities', 'search_media', 'inspect_current_results'])
        self.assertNotIn('outcome_handle', response.text)
        self.assertNotIn('item_handle', response.text)

    async def test_ordinary_turn_is_default_and_never_calls_injected_runtime(self):
        response = await self.post_turn('find photos in 2032')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['status'], 'completed')
        self.assertEqual(self.runtime.calls, [])

        # A separate app with no injected adapter stays closed to a fresh agent
        # profile while preserving the ordinary request path.
        disabled = self.make_app(None)
        async with disabled.router.lifespan_context(disabled):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=disabled),
                                         base_url='https://photohouse.example.test') as client:
                ordinary = await client.post(
                    f'{BASE}/threads/{self.thread}/turns', headers=self.v2,
                    json={'library_id': 'family-a', 'request_id': str(uuid.uuid4()),
                          'expected_revision': 1, 'text': 'find photos in 2032'})
                self.assertEqual(ordinary.status_code, 200, ordinary.text)
                unavailable = await client.post(
                    f'{BASE}/threads/{self.thread}/turns', headers=self.v2,
                    json={'library_id': 'family-a', 'request_id': str(uuid.uuid4()),
                          'expected_revision': 2, 'text': 'find photos in 2032',
                          'accepts': [PROFILE]})
                self.assertEqual(unavailable.status_code, 503, unavailable.text)
                self.assertNotIn('items', unavailable.text)
        self.assertEqual(self.runtime.calls, [])

    async def test_negotiation_is_exact_and_rejected_profiles_do_not_call_runtime(self):
        rid = str(uuid.uuid4())
        for headers, accepts, extra in (
                (self.auth | {'X-PhotoHouse-Search-Version': '1'}, [PROFILE], {}),
                (self.auth | {'X-PhotoHouse-Search-Version': '3'}, [PROFILE], {}),
                (self.auth | {'X-PhotoHouse-Search-Version': '4'}, [PROFILE], {}),
                (self.v2, ['other_profile'], {}),
                (self.v2, [PROFILE, 'other_profile'], {}),
                (self.v2, [PROFILE], {'memory_parent': {
                    'request_id': str(uuid.uuid4()), 'revision': 0}})):
            response = await self.post_turn('find photos in 2032', request_id=rid,
                                            agent=True, accepts=accepts,
                                            headers=headers, **extra)
            self.assertIn(response.status_code, (400, 409), response.text)
            self.assertEqual(self.runtime.calls, [])

    async def test_replay_ignores_changed_accepts_and_adapter_loss_and_collision_stays_conflict(self):
        rid = str(uuid.uuid4())
        first = await self.post_turn('find photos in 2032', request_id=rid, agent=True)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(len(self.runtime.calls), 1)
        result = first.json()['result']

        replay = await self.post_turn('find photos in 2032', revision=0,
            request_id=rid, agent=True, accepts=['unsupported_profile'])
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertTrue(replay.json()['recovered'])
        self.assertEqual(replay.json()['result'], result)
        self.app.state.assistant_agent_supervisor = None
        recovered = await self.read_turn(rid)
        self.assertEqual(recovered.status_code, 200, recovered.text)
        self.assertTrue(recovered.json()['recovered'])
        self.assertEqual(recovered.json()['result'], result)
        conflict = await self.post_turn('find videos in 2032', request_id=rid,
                                        agent=True)
        self.assertEqual(conflict.status_code, 409, conflict.text)
        self.assertEqual(len(self.runtime.calls), 1)

    async def test_changed_source_between_search_and_final_selection_withholds_result(self):
        def mutate_source():
            self.source.mutate(
                "UPDATE access_stories SET revision=2,text='changed source' WHERE id='note-101'")
        self.runtime.after_search = mutate_source
        response = await self.post_turn('find photos in 2032', agent=True)
        self.assertEqual(response.status_code, 409, response.text)
        self.assertNotIn('items', response.text)
        self.assertEqual(len(self.runtime.calls), 1)

    async def test_membership_revocation_during_runtime_withholds_final_result(self):
        def revoke_membership():
            self.source.mutate(
                "UPDATE access_memberships SET status='revoked' WHERE account_id='one'")
        self.runtime.after_search = revoke_membership
        response = await self.post_turn('find photos in 2032', agent=True)
        self.assertEqual(response.status_code, 401, response.text)
        self.assertNotIn('items', response.text)
        self.assertEqual(len(self.runtime.calls), 1)
        request_id = response.json().get('request_id')
        # Durable recovery can report the terminal failure without executing a
        # second interpretation, even if the optional runtime is removed.
        if request_id:
            self.app.state.assistant_agent_supervisor = None
            recovered = await self.read_turn(request_id)
            self.assertEqual(recovered.status_code, 200, recovered.text)
            self.assertNotEqual(recovered.json()['status'], 'completed')
        self.assertEqual(len(self.runtime.calls), 1)

    async def test_fourth_call_budget_counts_rejected_attempts_and_prevents_completion(self):
        self.runtime.capability_attempts = 5
        response = await self.post_turn('find photos in 2032', agent=True)
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(len(self.runtime.calls), 1)
        self.assertEqual(len(self.runtime.tools), 4)
        self.assertNotIn('items', response.text)

    async def test_detached_waiter_keeps_supervised_reservation_and_allows_get_recovery(self):
        entered, release = threading.Event(), threading.Event()
        self.runtime = SyntheticRuntime(entered=entered, release=release)
        self.app.state.assistant_agent_supervisor.runtime = self.runtime
        rid = str(uuid.uuid4())

        async def request():
            return await self.post_turn('find photos in 2032', request_id=rid, agent=True)

        # Cancellation of the ASGI waiter models disconnect/stop-waiting. A
        # synchronous barrier proves the supervisor still owns accepted work.
        task = asyncio.create_task(request())
        try:
            reached = await asyncio.to_thread(entered.wait, 5)
            self.assertTrue(reached, 'runtime did not reach its deterministic barrier')
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertIsNotNone(self.app.state.assistant_agent_supervisor.active)
            operation = self.app.state.assistant_agent_supervisor.active
            self.assertIsNotNone(operation)
            release.set()
            await asyncio.wait_for(operation.task, 5)
            self.assertIsNone(self.app.state.assistant_agent_supervisor.active)
        finally:
            release.set()
        recovered = await self.read_turn(rid)
        self.assertEqual(recovered.status_code, 200, recovered.text)
        self.assertEqual(recovered.json()['status'], 'completed')
        self.assertEqual(len(self.runtime.calls), 1)

    async def test_agent_ordinal_open_is_projected_as_a_read_only_choice(self):
        first = await self.post_turn('find photos in 2032')
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()['status'], 'completed')
        self.runtime = SyntheticRuntime()
        self.app.state.assistant_agent_supervisor.runtime = self.runtime
        opened = await self.post_turn('open the first result', revision=1, agent=True)
        self.assertEqual(opened.status_code, 200, opened.text)
        result = opened.json()['result']
        self.assertEqual(result['kind'], 'results')
        self.assertIsNone(result['effect'])
        self.assertEqual(result['reply'], 'Select a result to open it.')
        self.assertEqual([item['id'] for item in result['items']], ['103', '101'])
        self.assertEqual(self.runtime.calls[0]['text'], 'open the first result')

    async def test_busy_lane_is_global_and_matching_duplicate_joins_without_a_second_run(self):
        entered, release = threading.Event(), threading.Event()
        self.runtime = SyntheticRuntime(entered=entered, release=release)
        self.app.state.assistant_agent_supervisor.runtime = self.runtime
        rid = str(uuid.uuid4())
        first_task = asyncio.create_task(self.post_turn(
            'find photos in 2032', request_id=rid, agent=True))
        try:
            reached = await asyncio.to_thread(entered.wait, 5)
            self.assertTrue(reached, 'runtime did not reach its deterministic barrier')
            duplicate_task = asyncio.create_task(self.post_turn(
                'find photos in 2032', request_id=rid, agent=True,
                accepts=['changed_profile']))
            second_thread = await self._client.post(BASE + '/threads', headers=self.auth,
                                                     json={'library_id': 'family-a'})
            self.assertEqual(second_thread.status_code, 201, second_thread.text)
            second_id = second_thread.json()['thread']['thread_id']
            busy = await self._client.post(
                f'{BASE}/threads/{second_id}/turns', headers=self.v2,
                json={'library_id': 'family-a', 'request_id': str(uuid.uuid4()),
                      'expected_revision': 0, 'text': 'find photos in 2032',
                      'accepts': [PROFILE]})
            self.assertEqual(busy.status_code, 503, busy.text)
            release.set()
            first, duplicate = await asyncio.gather(first_task, duplicate_task)
            self.assertEqual(first.status_code, 200, first.text)
            self.assertEqual(duplicate.status_code, 200, duplicate.text)
            self.assertEqual(duplicate.json()['result'], first.json()['result'])
            self.assertEqual(len(self.runtime.calls), 1)
            self.assertIsNone(self.app.state.assistant_agent_supervisor.active)
        finally:
            release.set()
            if not first_task.done():
                await asyncio.gather(first_task, return_exceptions=True)

    async def test_duplicate_joins_at_reservation_barrier_before_runtime_and_changed_accepts(self):
        entered, release, joined = threading.Event(), threading.Event(), threading.Event()
        original_begin = self.store.begin_turn
        original_response = __import__(
            'app.access.assistant_workspace_transport', fromlist=['_agent_response'])._agent_response

        def gated_begin(*args, **kwargs):
            if not kwargs.get('existing_only', False):
                entered.set()
                release.wait(5)
            return original_begin(*args, **kwargs)

        response_count = 0
        async def observe_join(*args, **kwargs):
            nonlocal response_count
            response_count += 1
            if response_count == 2:
                joined.set()
            return await original_response(*args, **kwargs)

        rid = str(uuid.uuid4())
        with patch.object(self.store, 'begin_turn', side_effect=gated_begin), \
             patch('app.access.assistant_workspace_transport._agent_response',
                   side_effect=observe_join):
            first_task = asyncio.create_task(self.post_turn(
                'find photos in 2032', request_id=rid, agent=True))
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait, 5),
                                'reservation did not reach its barrier')
                duplicate_task = asyncio.create_task(self.post_turn(
                    'find photos in 2032', request_id=rid, agent=True,
                    accepts=['changed_profile']))
                self.assertTrue(await asyncio.to_thread(joined.wait, 5),
                                'duplicate did not join the registered operation')
                release.set()
                first, duplicate = await asyncio.gather(first_task, duplicate_task)
            finally:
                release.set()
                if not first_task.done():
                    await asyncio.gather(first_task, return_exceptions=True)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(duplicate.status_code, 200, duplicate.text)
        self.assertEqual(first.json()['result'], duplicate.json()['result'])
        self.assertEqual(len(self.runtime.calls), 1)

    async def test_lost_complete_reply_recovers_committed_result_without_rerun(self):
        complete = self.store.complete_turn
        def commit_then_lose_reply(*args, **kwargs):
            complete(*args, **kwargs)
            raise OSError('simulated lost completion reply')
        rid = str(uuid.uuid4())
        with patch.object(self.store, 'complete_turn', side_effect=commit_then_lose_reply):
            response = await self.post_turn('find photos in 2032', request_id=rid, agent=True)
        self.assertEqual(response.status_code, 503, response.text)
        await self.settle()
        self.app.state.assistant_agent_supervisor = None
        recovered = await self.read_turn(rid)
        self.assertEqual(recovered.status_code, 200, recovered.text)
        self.assertEqual(recovered.json()['status'], 'completed')
        self.assertTrue(recovered.json()['recovered'])
        self.assertEqual(len(self.runtime.calls), 1)

    async def test_deadline_fences_a_late_selector_and_recovers_failed_request(self):
        entered, release = threading.Event(), threading.Event()

        class LateRuntime:
            def __init__(self):
                self.calls = 0

            async def run(inner, turn_input, tool_dispatch, invalidation):
                inner.calls += 1
                projection = await tool_dispatch('search_media', {})
                entered.set()
                try:
                    await asyncio.to_thread(release.wait)
                except asyncio.CancelledError:
                    # Simulate an adapter that returns a valid result after its
                    # host deadline; the supervisor must keep it from committing.
                    await asyncio.to_thread(release.wait)
                return {'outcome_handle': projection['outcome_handle']}

        runtime = LateRuntime()
        supervisor = self.app.state.assistant_agent_supervisor
        supervisor.runtime = runtime
        supervisor.budget = AgentBudget(max_wall_seconds=0.5)
        rid = str(uuid.uuid4())
        request_task = asyncio.create_task(self.post_turn(
            'find photos in 2032', request_id=rid, agent=True))
        try:
            self.assertTrue(await asyncio.to_thread(entered.wait, 5),
                            'runtime did not reach its deterministic barrier')
            response = await asyncio.wait_for(request_task, 2)
            self.assertEqual(response.status_code, 503, response.text)
            self.assertNotIn('items', response.text)
            operation = supervisor.active
            self.assertIsNotNone(operation)
            release.set()
            await asyncio.wait_for(operation.task, 5)
        finally:
            release.set()
            if not request_task.done():
                await asyncio.gather(request_task, return_exceptions=True)
        self.app.state.assistant_agent_supervisor = None
        recovered = await self.read_turn(rid)
        self.assertEqual(recovered.status_code, 200, recovered.text)
        self.assertIn(recovered.json()['status'], ('failed', 'interrupted'))
        self.assertIsNone(recovered.json()['result'])
        self.assertEqual(runtime.calls, 1)

    async def test_ordinary_vague_date_clarification_continues_through_agent_without_losing_person(self):
        first = await self.post_turn('Find photos of Sample Child from childhood')
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()['result']['kind'], 'clarification')
        self.assertIsNone(first.json()['result']['context'])
        self.runtime = SyntheticRuntime()
        self.app.state.assistant_agent_supervisor.runtime = self.runtime
        followup = await self.post_turn('in 2032', revision=1, agent=True)
        self.assertEqual(followup.status_code, 200, followup.text)
        result = followup.json()['result']
        self.assertEqual(result['filters']['people'], {'ids': ['301'], 'match': 'any'})
        self.assertEqual(result['filters']['date'], {
            'from': '2032-01-01', 'to': '2032-12-31'})
        self.assertEqual(self.runtime.calls[0]['text'], 'in 2032')

    async def test_stale_reservation_conflict_does_not_disable_future_valid_work(self):
        class ScopedCleanup(SyntheticRuntime):
            def __init__(inner):
                super().__init__()
                inner.scopes = []

            async def cleanup(inner, scope):
                self.assertIsNotNone(scope)
                inner.scopes.append(scope)
                return True

        self.runtime = ScopedCleanup()
        self.app.state.assistant_agent_supervisor.runtime = self.runtime
        ordinary = await self.post_turn('find photos in 2032')
        self.assertEqual(ordinary.status_code, 200, ordinary.text)
        conflict = await self.post_turn('find photos in 2032', revision=0, agent=True)
        self.assertEqual(conflict.status_code, 409, conflict.text)
        await self.settle()
        self.assertTrue(self.app.state.assistant_agent_supervisor.healthy)
        self.assertEqual(self.runtime.scopes, [])
        accepted = await self.post_turn('find photos in 2032', revision=1, agent=True)
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(accepted.json()['status'], 'completed')
        await self.settle()
        self.assertEqual(len(self.runtime.calls), 1)
        self.assertEqual(len(self.runtime.scopes), 1)

    async def test_journal_finish_commit_then_lost_reply_is_read_back_without_second_finish(self):
        journal = initialize_journal(Path(self.temp.name).resolve() / 'journal.sqlite')
        journal.clock = lambda: self.now[0]
        self.app.state.assistant_journal = journal
        original = journal.finish
        finishes = []

        def committed_reply_lost(*args, **kwargs):
            finishes.append(args)
            original(*args, **kwargs)
            raise OSError('synthetic terminal receipt reply loss')

        rid = str(uuid.uuid4())
        with patch.object(journal, 'finish', side_effect=committed_reply_lost):
            response = await self.post_turn('find photos in 2032', request_id=rid, agent=True)
            await self.settle()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers['X-PhotoHouse-Receipt-Status'], 'succeeded')
        self.assertEqual(len(finishes), 1)
        self.assertEqual(journal.get(rid, 'one', 'family-a')['status'], 'succeeded')
        self.assertTrue(self.app.state.assistant_agent_supervisor.healthy)
        replay = await self.read_turn(rid)
        self.assertEqual(replay.json()['status'], 'completed')
        self.assertEqual(len(self.runtime.calls), 1)

    async def test_lost_journal_begin_reply_reconciles_owned_receipt_without_model_execution(self):
        journal = initialize_journal(Path(self.temp.name).resolve() / 'journal.sqlite')
        journal.clock = lambda: self.now[0]
        self.app.state.assistant_journal = journal
        original = journal.begin

        def begin_then_lose_reply(*args, **kwargs):
            original(*args, **kwargs)
            raise OSError('synthetic initial receipt reply loss')

        rid = str(uuid.uuid4())
        with patch.object(journal, 'begin', side_effect=begin_then_lose_reply):
            response = await self.post_turn('find photos in 2032', request_id=rid, agent=True)
            await self.settle()
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(journal.get(rid, 'one', 'family-a')['status'], 'failed')
        self.assertEqual((await self.read_turn(rid)).json()['status'], 'failed')
        self.assertEqual(self.runtime.calls, [])
        self.assertTrue(self.app.state.assistant_agent_supervisor.healthy)

    async def test_detachment_after_reservation_commit_keeps_lease_and_operation_owned(self):
        entered, release = threading.Event(), threading.Event()
        original = self.store.begin_turn

        def commit_then_gate(*args, **kwargs):
            row = original(*args, **kwargs)
            if not kwargs.get('existing_only', False):
                entered.set()
                release.wait(5)
            return row

        rid = str(uuid.uuid4())
        with patch.object(self.store, 'begin_turn', side_effect=commit_then_gate):
            waiter = asyncio.create_task(self.post_turn('find photos in 2032',
                                                       request_id=rid, agent=True))
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait, 5))
                operation = self.app.state.assistant_agent_supervisor.active
                waiter.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await waiter
                pending = await self.read_turn(rid)
                self.assertEqual(pending.json()['status'], 'pending')
                self.assertIs(self.app.state.assistant_agent_supervisor.active, operation)
                release.set()
                await asyncio.wait_for(operation.task, 5)
            finally:
                release.set()
        recovered = await self.read_turn(rid)
        self.assertEqual(recovered.json()['status'], 'completed')
        self.assertEqual(len(self.runtime.calls), 1)

    async def test_lease_expiry_during_runtime_cannot_disclose_or_complete(self):
        self.runtime.after_search = lambda: self.now.__setitem__(0, self.now[0] + LEASE_SECONDS + 1)
        rid = str(uuid.uuid4())
        response = await self.post_turn('find photos in 2032', request_id=rid, agent=True)
        self.assertEqual(response.status_code, 409, response.text)
        await self.settle()
        recovered = await self.read_turn(rid)
        self.assertEqual(recovered.json()['status'], 'interrupted')
        self.assertIsNone(recovered.json()['result'])
        self.assertEqual(len(self.runtime.calls), 1)

    async def test_expiry_inside_complete_returns_interrupted_instead_of_claiming_success(self):
        original = self.store.complete_turn

        def expire_before_commit(*args, **kwargs):
            self.now[0] += LEASE_SECONDS + 1
            return original(*args, **kwargs)

        with patch.object(self.store, 'complete_turn', side_effect=expire_before_commit):
            response = await self.post_turn('find photos in 2032', agent=True)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['status'], 'interrupted')
        self.assertEqual(response.json()['error'], 'turn_interrupted')
        self.assertIsNone(response.json()['result'])

    async def test_cleanup_retains_admission_and_false_ack_quarantines_only_optional_lane(self):
        entered, release = threading.Event(), threading.Event()

        class UncertainCleanup(SyntheticRuntime):
            async def cleanup(inner, scope):
                self.assertIsNotNone(scope.lease_id)
                entered.set()
                await asyncio.to_thread(release.wait)
                return False

        supervisor = self.app.state.assistant_agent_supervisor
        supervisor.runtime = UncertainCleanup()
        try:
            response = await self.post_turn('find photos in 2032', agent=True)
            self.assertEqual(response.json()['status'], 'completed')
            self.assertTrue(await asyncio.to_thread(entered.wait, 5))
            operation = supervisor.active
            busy = await self.post_turn('find photos in 2032', revision=1, agent=True)
            self.assertEqual(busy.status_code, 503, busy.text)
            release.set()
            await asyncio.wait_for(operation.task, 5)
            self.assertFalse(supervisor.healthy)
            disabled = await self.post_turn('find photos in 2032', revision=1, agent=True)
            self.assertEqual(disabled.status_code, 503, disabled.text)
            ordinary = await self.post_turn('find photos in 2032', revision=1)
            self.assertEqual(ordinary.status_code, 200, ordinary.text)
            self.assertEqual(ordinary.json()['status'], 'completed')
        finally:
            release.set()

    async def test_exclusion_pending_crosses_agent_ordinary_and_expiry_without_broadening(self):
        first = await self.post_turn('find photos of a dog that is not on grass', agent=True)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()['result']['kind'], 'clarification')
        pending = self.store.get_turn('one', 'family-a', self.thread,
            first.json()['request_id'])['result_summary']['pending_intent']
        self.assertEqual(pending['question'], 'exclusion')
        self.assertNotIn('pending_intent', first.text)
        self.now[0] += PENDING_TTL_SECONDS + 1
        short = await self.post_turn('red coats', revision=1)
        self.assertEqual(short.status_code, 200, short.text)
        self.assertEqual(short.json()['result']['kind'], 'clarification')
        guarded = await self.post_turn('September', revision=2, agent=True)
        self.assertEqual(guarded.status_code, 200, guarded.text)
        self.assertEqual(guarded.json()['result']['kind'], 'clarification')
        carried = self.store.get_turn('one', 'family-a', self.thread,
            guarded.json()['request_id'])['result_summary']['pending_intent']
        self.assertEqual(carried, pending)
        fresh = await self.post_turn('find photos of Sample Child in September 2032',
                                     revision=3, agent=True)
        self.assertEqual(fresh.status_code, 200, fresh.text)
        self.assertEqual(fresh.json()['result']['kind'], 'results')
        summary = self.store.get_turn('one', 'family-a', self.thread,
            fresh.json()['request_id'])['result_summary']
        self.assertNotIn('pending_intent', summary)

    async def test_parallel_tool_attempt_invalidates_run_instead_of_queuing_a_second_read(self):
        class ParallelRuntime:
            async def run(inner, turn_input, tool_dispatch, invalidation):
                await asyncio.gather(tool_dispatch('search_media', {}),
                                     tool_dispatch('get_search_capabilities', {}))

        self.app.state.assistant_agent_supervisor.runtime = ParallelRuntime()
        rid = str(uuid.uuid4())
        response = await self.post_turn('find photos in 2032', request_id=rid, agent=True)
        self.assertEqual(response.status_code, 503, response.text)
        await self.settle()
        recovered = await self.read_turn(rid)
        self.assertEqual(recovered.json()['status'], 'failed')
        self.assertIsNone(recovered.json()['result'])

    async def test_rejected_tool_attempts_consume_budget_even_when_adapter_catches_errors(self):
        class RejectedAttempts:
            async def run(inner, turn_input, tool_dispatch, invalidation):
                for _ in range(4):
                    try:
                        await tool_dispatch('search_media', {'query': 'find everything'})
                    except ValueError:
                        pass
                projection = await tool_dispatch('search_media', {})
                return {'outcome_handle': projection['outcome_handle']}

        self.app.state.assistant_agent_supervisor.runtime = RejectedAttempts()
        response = await self.post_turn('find photos in 2032', agent=True)
        self.assertEqual(response.status_code, 503, response.text)
        self.assertNotIn('items', response.text)
        await self.settle()
        thread = self.store.get_thread('one', 'family-a', self.thread)
        self.assertEqual(thread['thread']['revision'], 0)
        self.assertEqual(thread['exchanges'], [])

    async def test_commit_crossing_deadline_is_reconciled_without_rollback_or_reinterpretation(self):
        entered, release = threading.Event(), threading.Event()
        original = self.store.complete_turn
        supervisor = self.app.state.assistant_agent_supervisor
        supervisor.budget = AgentBudget(max_wall_seconds=0.5)

        def commit_then_gate(*args, **kwargs):
            result = original(*args, **kwargs)
            entered.set()
            release.wait(5)
            return result

        rid = str(uuid.uuid4())
        with patch.object(self.store, 'complete_turn', side_effect=commit_then_gate):
            waiter = asyncio.create_task(self.post_turn('find photos in 2032',
                                                       request_id=rid, agent=True))
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait, 5))
                operation = supervisor.active
                response = await asyncio.wait_for(waiter, 2)
                self.assertEqual(response.status_code, 503, response.text)
                recovered = await self.read_turn(rid)
                self.assertEqual(recovered.json()['status'], 'completed')
                self.assertTrue(recovered.json()['result']['items'])
                self.assertIs(supervisor.active, operation)
                release.set()
                await asyncio.wait_for(operation.task, 5)
            finally:
                release.set()
        self.assertTrue(supervisor.healthy)
        replay = await self.post_turn('find photos in 2032', request_id=rid, agent=True)
        self.assertEqual(replay.json()['status'], 'completed')
        self.assertEqual(len(self.runtime.calls), 1)

    async def test_lifespan_shutdown_owns_runtime_invalidation_and_durable_failure(self):
        entered = asyncio.Event()
        cleaned = []

        class WaitingRuntime:
            async def run(inner, turn_input, tool_dispatch, invalidation):
                entered.set()
                await asyncio.Event().wait()

            async def cleanup(inner, scope):
                cleaned.append(scope)
                return True

        supervisor = self.app.state.assistant_agent_supervisor
        supervisor.runtime = WaitingRuntime()
        rid = str(uuid.uuid4())
        waiter = asyncio.create_task(self.post_turn('find photos in 2032',
                                                   request_id=rid, agent=True))
        await asyncio.wait_for(entered.wait(), 5)
        operation = supervisor.active
        await supervisor.close()
        response = await asyncio.wait_for(waiter, 5)
        self.assertEqual(response.status_code, 503, response.text)
        self.assertTrue(operation.invalidation.is_set())
        self.assertIsNone(supervisor.active)
        self.assertEqual(cleaned, [operation.scope])
        recovered = await self.read_turn(rid)
        self.assertEqual(recovered.json()['status'], 'failed')
        self.assertIsNone(recovered.json()['result'])


if __name__ == '__main__':
    unittest.main()
