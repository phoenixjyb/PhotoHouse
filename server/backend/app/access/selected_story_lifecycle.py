"""Explicit app ownership for selected-story drafts; no routes or native adapter."""
import asyncio
from dataclasses import replace
import inspect

from starlette.concurrency import run_in_threadpool

from .inference_admission import InferenceAdmission
from .selected_story_operations import DraftOperationError, DraftOperations, SelectedStorySources
from .transport import AccessRuntime, TransportError


class SelectedStoryLifecycle:
    """One app lifetime, one nonqueued gate, bounded owned access mutations."""
    def __init__(self, access, provider, *, memory_groups_enabled=False):
        if (type(access) is not AccessRuntime or type(memory_groups_enabled) is not bool or
                not inspect.iscoroutinefunction(getattr(provider, 'prepare', None)) or
                not inspect.iscoroutinefunction(getattr(provider, 'stop_and_reconcile', None))):
            raise ValueError('Explicit access runtime and async selected-story provider required')
        self.access = access
        self.sources = SelectedStorySources(replace(access, memory_groups_enabled=memory_groups_enabled))
        self.provider = provider
        self.admission = InferenceAdmission(max_waiting=0)
        self.operations = None
        self.started = False
        self.closing = False
        self.shutdown_clean = None
        self.shutdown_task = None
        self._operation_close = None
        self._mutations = set()

    def start(self):
        # Reusing an app must never replace a closed/quarantined owner or gate.
        if self.started or self.closing:
            raise RuntimeError('selected_story_lifetime_already_started')
        self.started = True
        self.operations = DraftOperations(self.sources, self.provider, self.admission)

    async def access_change(self, action, *args, **kwargs):
        if not self.started or self.closing:
            raise TransportError(503, 'Access unavailable')
        if action not in {'logout', 'revoke_membership'}:
            raise ValueError('invalid_selected_story_access_change')
        if len(self._mutations) >= 16:
            raise TransportError(503, 'Access unavailable')
        task = asyncio.create_task(self._access_change(action, *args, **kwargs))
        self._mutations.add(task)
        def settled(value):
            self._mutations.discard(value)
            if not value.cancelled():
                value.exception()  # No unobserved exception or input/provider logging.
        task.add_done_callback(settled)
        # A disconnected response does not abandon a committed or pending change.
        return await asyncio.shield(task)

    async def _access_change(self, action, *args, **kwargs):
        if action == 'logout':
            # Temporary barrier, not a permanent tombstone for arbitrary tokens.
            # It outlives cancelled response waiters and blocks cached auth reads.
            try:
                with self.operations.session_barrier(args[0]):
                    return await run_in_threadpool(self.access.call, action, *args, **kwargs)
            except DraftOperationError:
                raise TransportError(503, 'Access unavailable') from None
        result = await run_in_threadpool(self.access.call, action, *args, **kwargs)
        # Only a successful authorized, revision-bound commit can fence this scope.
        self.operations.invalidate_membership(args[2], args[1])
        return result

    async def close(self):
        if self.shutdown_task is None:
            self.closing = True
            self.admission.close()  # Refuse all participating owners immediately.
            if self.operations is not None:
                self.operations.begin_close()
            self.shutdown_task = asyncio.create_task(self._close())
        return await asyncio.shield(self.shutdown_task)

    async def _close(self):
        if self.operations is None:
            self.shutdown_clean = True
            return True
        # Operation close fences words before waiting. Neither tasks nor the
        # closed gate are replaced when cleanup cannot certify settlement.
        self._operation_close = asyncio.create_task(self.operations.close())
        self._operation_close.add_done_callback(
            lambda task: None if task.cancelled() else task.exception())
        pending = tuple(self._mutations) + (self._operation_close,)
        await asyncio.wait(pending, timeout=self.operations.cleanup_seconds)
        self.shutdown_clean = (self._operation_close.done() and not self._operation_close.cancelled() and
            self._operation_close.exception() is None and self._operation_close.result() is True and
            not self._mutations)
        return self.shutdown_clean
