"""Explicit local-model PH-A1 runtime; host tools and outcomes remain authoritative."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import hashlib
import time
import uuid

from .agent_decision import validate_state, validate_decision
from .assistant_agent import AgentScope, AgentUnavailable
from .selected_story_operations import PreparationScope


@dataclass(repr=False)
class _Run:
    scope: AgentScope
    invalidation: object = None
    calls: list = field(default_factory=list)
    tools: list = field(default_factory=list)
    cleaning: list = field(default_factory=list)
    inference_count: int = 0
    finished: bool = False


class LocalToolAgentRuntime:
    """One bounded model-directed turn; no default provider or automatic retries."""
    def __init__(self, provider, *, enabled=False, clock=time.monotonic):
        if (not callable(getattr(provider, 'decide', None)) or
                not callable(getattr(provider, 'stop_and_reconcile', None)) or
                type(enabled) is not bool or not callable(clock)):
            raise ValueError('Explicit owned agent decision provider required')
        self.provider, self.enabled, self.clock = provider, enabled, clock
        self._active = None
        self._last_trace = None

    @property
    def last_trace(self):
        return None if self._last_trace is None else dict(self._last_trace,
            tools=list(self._last_trace['tools']))

    def bind_scope(self, scope):
        if (not self.enabled or type(scope) is not AgentScope or self._active is not None
                or self.clock() >= scope.deadline_monotonic):
            raise AgentUnavailable()
        self._active = _Run(scope)

    def _check(self, run):
        if (self._active is not run or run.invalidation.is_set()
                or self.clock() >= run.scope.deadline_monotonic):
            raise AgentUnavailable()

    async def _settle(self, task, scope):
        # Coroutine cancellation or model response alone is not native closure.
        try:
            await asyncio.shield(task)
        except BaseException:
            pass
        return await self.provider.stop_and_reconcile(scope) is True

    async def run(self, turn_input, tool_dispatch, invalidation):
        run = self._active
        if run is None or run.invalidation is not None or not callable(tool_dispatch):
            raise AgentUnavailable()
        run.invalidation = invalidation
        observations = []
        # Match the host's existing default locale when no preference is saved.
        turn_input = dict(turn_input, locale=turn_input.get('locale') or 'en')
        state = validate_state(turn_input, observations)
        for _ in range(5):  # Four domain attempts plus an outcome decision.
            self._check(run)
            scope = PreparationScope(str(uuid.uuid4()), run.scope.deadline_monotonic,
                                     invalidation, self.clock)
            task = asyncio.create_task(self.provider.decide(state, scope))
            run.calls.append((task, scope))
            run.inference_count += 1
            try:
                decision = validate_decision(await asyncio.shield(task), state)
            finally:
                cleanup = asyncio.create_task(self._settle(task, scope))
                run.cleaning.append(cleanup)
                if await asyncio.shield(cleanup) is not True:
                    raise AgentUnavailable()
            self._check(run)
            if 'finish' in decision:
                run.finished = True
                return {'outcome_handle': decision['finish']}
            if len(observations) >= 4:
                raise AgentUnavailable()
            name = decision['tool']
            arguments = ({'outcome_handle': decision['outcome_handle']}
                         if name == 'inspect_current_results' else {})
            run.tools.append(name)
            value = await tool_dispatch(name, arguments)
            self._check(run)
            observations.append({'tool': name, 'result': value})
            state = validate_state(turn_input, observations)
            if name == 'inspect_current_results':
                # Inspection is the terminal domain tool for this read-only
                # search profile. Its current host projection is authoritative;
                # another model call cannot add facts or approve access.
                inspected = validate_state(turn_input, [observations[-1]])
                terminal = validate_decision({'finish': value.get('outcome_handle')}, inspected)
                run.finished = True
                return {'outcome_handle': terminal['finish']}
        raise AgentUnavailable()

    async def cleanup(self, scope):
        run = self._active
        if run is None or run.scope is not scope:
            return False
        if run.invalidation is not None:
            run.invalidation.set()
        for task in run.cleaning:
            if await asyncio.shield(task) is not True:
                return False
        # Covers cancellation during task creation/settlement bookkeeping too.
        for task, model_scope in run.calls:
            if await self._settle(task, model_scope) is not True:
                return False
        self._last_trace = dict(model_invocations=run.inference_count,
            tools=list(run.tools), completed=run.finished, native_resources_reconciled=True,
            request_id_sha256=hashlib.sha256(scope.request_id.encode()).hexdigest())
        self._active = None
        return True
