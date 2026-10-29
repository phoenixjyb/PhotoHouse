"""Local-model adapter contract fixtures; real Windows/model proof is separate."""
import asyncio
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
import uuid

SERVER = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(SERVER / 'backend'), str(SERVER / 'scripts'), str(SERVER / 'tests/security')]

from app.access.agent_decision import validate_state
from app.access.agent_local_runtime import LocalToolAgentRuntime
from app.access.agent_process import ProcessAgentDecisionProvider
from app.access.assistant_agent import AgentScope, AgentUnavailable
from app.access.selected_story_native import NativeStoryLaunch
from app.access.selected_story_operations import PreparationScope
from app.access.selected_story_process import ProcessSelectedStoryError, REQUEST_ENV, RESPONSE_ENV
import test_assistant_agent_workspace as _workspace_fixture
BASE, TOKEN = _workspace_fixture.BASE, _workspace_fixture.TOKEN
from test_selected_story_process import FileKernel
from test_selected_story_native import EXE, EXE_HASH
import httpx


def projection():
    return {'outcome_handle': 'owned_outcome_123', 'kind': 'results', 'summary': 'One photo',
            'total': 1, 'has_more': False, 'truncated': False, 'items': []}


def scope():
    return AgentScope('synthetic-account', 'family-a', str(uuid.uuid4()), str(uuid.uuid4()),
                      0, 'synthetic-lease', 'generation', time.monotonic() + 10)


class ScriptedDecisionProvider:
    """Test decisions only, never presented as local-model execution evidence."""
    def __init__(self, *, forged=False, settle=True):
        self.calls, self.settled = [], []
        self.forged, self.settle = forged, settle

    async def decide(self, state, scope):
        self.calls.append((state, scope))
        if self.forged:
            return {'finish': 'forged'}
        observations = state['observations']
        if not observations:
            return {'tool': 'get_search_capabilities'}
        if len(observations) == 1:
            return {'tool': 'search_media'}
        handle = observations[-1]['result']['outcome_handle']
        if len(observations) == 2:
            return {'tool': 'inspect_current_results', 'outcome_handle': handle}
        return {'finish': handle}

    async def stop_and_reconcile(self, scope):
        self.settled.append(scope)
        return self.settle


class LocalRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_model_decisions_drive_tools_and_cleanup_is_scope_bound(self):
        provider = ScriptedDecisionProvider()
        runtime = LocalToolAgentRuntime(provider, enabled=True)
        selected = scope(); runtime.bind_scope(selected)
        invalidation = threading.Event(); calls = []
        async def dispatch(name, arguments):
            calls.append((name, arguments))
            return {'search_version': 2} if name == 'get_search_capabilities' else projection()
        result = await runtime.run({'version': 1, 'text': 'Find photos', 'locale': 'en'}, dispatch, invalidation)
        self.assertEqual(result, {'outcome_handle': 'owned_outcome_123'})
        self.assertEqual([name for name, _ in calls], ['get_search_capabilities', 'search_media', 'inspect_current_results'])
        self.assertFalse(await runtime.cleanup(replace(selected, request_id=str(uuid.uuid4()))))
        self.assertTrue(await runtime.cleanup(selected))
        self.assertTrue(runtime.last_trace['completed'])
        self.assertEqual(runtime.last_trace['model_invocations'], 4)
        self.assertTrue(invalidation.is_set())

    async def test_default_off_forged_outcome_and_uncertain_native_cleanup_refuse(self):
        provider = ScriptedDecisionProvider()
        with self.assertRaises(AgentUnavailable):
            LocalToolAgentRuntime(provider).bind_scope(scope())
        self.assertEqual(provider.calls, [])
        for forged, settled in ((True, True), (False, False)):
            provider = ScriptedDecisionProvider(forged=forged, settle=settled)
            runtime = LocalToolAgentRuntime(provider, enabled=True); selected = scope();runtime.bind_scope(selected)
            calls = []
            async def dispatch(name, arguments):
                calls.append(name);return projection()
            with self.assertRaises((ValueError, AgentUnavailable)):
                await runtime.run({'version': 1, 'text': 'Find photos', 'locale': 'en'}, dispatch, threading.Event())
            self.assertEqual(calls, [])
            self.assertEqual(await runtime.cleanup(selected), settled)
            if not settled:
                with self.assertRaises(AgentUnavailable):runtime.bind_scope(scope())

    async def test_cancelled_model_is_owned_until_reconciled(self):
        entered = asyncio.Event()
        class Slow(ScriptedDecisionProvider):
            async def decide(self, state, selected):
                self.calls.append((state, selected));entered.set()
                while not selected.cancelled():await asyncio.sleep(.005)
                raise AgentUnavailable()
        provider = Slow();runtime=LocalToolAgentRuntime(provider,enabled=True);selected=scope();runtime.bind_scope(selected);invalid=threading.Event()
        task=asyncio.create_task(runtime.run({'version':1,'text':'Find photos','locale':'en'},lambda *_:None,invalid));await entered.wait();invalid.set();task.cancel()
        with self.assertRaises(BaseException):await task
        self.assertTrue(await asyncio.wait_for(runtime.cleanup(selected),1))
        self.assertFalse(runtime.last_trace['completed'])


class AgentProcessTests(unittest.IsolatedAsyncioTestCase):
    async def test_exact_file_exchange_and_forged_binding_refusal(self):
        for response_operation in ('same', str(uuid.uuid4())):
            native_scope=PreparationScope(str(uuid.uuid4()),time.monotonic()+5,threading.Event(),time.monotonic)
            def writer(environment):
                request=json.loads(Path(environment[REQUEST_ENV]).read_bytes())
                self.assertEqual(request['kind'],'agent_decision_v1')
                self.assertEqual(request['operation_id'],native_scope.operation_id)
                out={'version':1,'operation_id':native_scope.operation_id if response_operation=='same' else response_operation,'model':'qwen-local','result':{'tool':'search_media'}}
                path=Path(environment[RESPONSE_ENV]);path.write_text(json.dumps(out));os.chmod(path,0o600)
            kernel=FileKernel(writer)
            launch=NativeStoryLaunch(EXE,EXE_HASH,(EXE,'-I','-B','synthetic_worker.py'),'/synthetic',{'PATH':'/synthetic/bin'})
            provider=ProcessAgentDecisionProvider(launch,'qwen-local',kernel_factory=lambda:kernel,enabled=True,cleanup_seconds=.05)
            state=validate_state({'version':1,'text':'Find photos','locale':'en'},[])
            if response_operation=='same':self.assertEqual(await provider.decide(state,native_scope),{'tool':'search_media'})
            else:
                with self.assertRaises(ProcessSelectedStoryError):await provider.decide(state,native_scope)
            self.assertTrue(await provider.stop_and_reconcile(native_scope));self.assertIsNone(provider._active)
            self.assertIn('resume',kernel.events)
            self.assertTrue(await provider.close())


class AgentWorkspaceIntegrationTests(unittest.IsolatedAsyncioTestCase):
    make_app=_workspace_fixture.AssistantAgentWorkspaceTests.make_app
    post_turn=_workspace_fixture.AssistantAgentWorkspaceTests.post_turn
    read_turn=_workspace_fixture.AssistantAgentWorkspaceTests.read_turn
    settle=_workspace_fixture.AssistantAgentWorkspaceTests.settle
    def setUp(self):
        _workspace_fixture.AssistantAgentWorkspaceTests.setUp(self)
        self.provider=ScriptedDecisionProvider();self.runtime=LocalToolAgentRuntime(self.provider,enabled=True);self.app=self.make_app(self.runtime)
    async def asyncSetUp(self):
        self._lifespan=self.app.router.lifespan_context(self.app);await self._lifespan.__aenter__();self.addAsyncCleanup(self._lifespan.__aexit__,None,None,None)
        self._client=httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),base_url='https://photohouse.example.test');await self._client.__aenter__();self.addAsyncCleanup(self._client.__aexit__,None,None,None)
        self.auth={'Authorization':'Bearer '+TOKEN};self.v2=self.auth|{'X-PhotoHouse-Search-Version':'2'}
        response=await self._client.post(BASE+'/threads',headers=self.auth,json={'library_id':'family-a'});self.assertEqual(response.status_code,201,response.text);self.thread=response.json()['thread']['thread_id']
    async def test_real_protected_search_receipt_and_get_recovery(self):
        rid=str(uuid.uuid4());response=await self.post_turn('find photos of Sample Child in September 2032',request_id=rid,agent=True)
        self.assertEqual(response.status_code,200,response.text);body=response.json();self.assertEqual(body['status'],'completed');self.assertEqual([row['id']for row in body['result']['items']],['103','101']);await self.settle();self.assertTrue(self.runtime.last_trace['native_resources_reconciled'])
        count=len(self.provider.calls);recovered=await self.read_turn(rid);self.assertEqual(recovered.status_code,200,recovered.text);self.assertTrue(recovered.json()['recovered']);self.assertEqual(len(self.provider.calls),count)
    async def test_capability_is_optional_scoped_and_ordinary_search_unchanged(self):
        path=BASE+'/agent-capabilities?library_id=family-a';r=await self._client.get(path,headers=self.v2);self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json(),{'version':1,'available':True,'profile':'agent_media_search_v1'})
        self.assertIn((await self._client.get(path)).status_code,(401,403));r=await self.post_turn('find photos',agent=False);self.assertEqual(r.status_code,200,r.text);self.assertEqual(self.provider.calls,[])
        self.app.state.assistant_agent_supervisor=None;r=await self._client.get(path,headers=self.v2);self.assertFalse(r.json()['available'])
