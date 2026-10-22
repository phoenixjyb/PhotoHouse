"""Default-off, process-local ownership for bounded read-only assistant turns.

This is not a model runner or a durable queue. The workspace owns durable request
identity. This owner keeps reservation, detached work and reconciliation alive.
"""
import asyncio
from dataclasses import dataclass
from functools import partial
import math
import secrets
import threading
import time

from starlette.concurrency import run_in_threadpool

from .assistant_workspace_store import WorkspaceStoreConflict
from .transport import TransportError


class AgentUnavailable(TransportError):
    def __init__(self):
        super().__init__(503, 'Local assistant unavailable')


@dataclass(frozen=True)
class AgentIdentity:
    account_id: str
    library_id: str
    thread_id: str
    request_id: str
    expected_revision: int
    text: str

    @property
    def key(self):
        return self.account_id, self.library_id, self.request_id


@dataclass(frozen=True)
class AgentScope:
    account_id: str
    library_id: str
    thread_id: str
    request_id: str
    expected_revision: int
    lease_id: str
    scope_generation: str
    deadline_monotonic: float


@dataclass(frozen=True)
class AgentBudget:
    max_domain_call_attempts: int = 4
    max_parallel_domain_calls: int = 1
    max_wall_seconds: float = 60
    max_tool_result_bytes: int = 16384

    def __post_init__(self):
        if (type(self.max_domain_call_attempts) is not int or
                not 1 <= self.max_domain_call_attempts <= 4 or
                type(self.max_parallel_domain_calls) is not int or
                self.max_parallel_domain_calls != 1 or
                type(self.max_wall_seconds) not in (int, float) or
                not math.isfinite(self.max_wall_seconds) or
                not 0 < self.max_wall_seconds <= 60 or
                type(self.max_tool_result_bytes) is not int or
                not 1 <= self.max_tool_result_bytes <= 16384):
            raise ValueError('Invalid agent budget')


class AgentOperation:
    def __init__(self, owner, identity):
        self.owner, self.identity = owner, identity
        self.result = asyncio.get_running_loop().create_future()
        self.result.add_done_callback(self._observe)
        self.task = None
        self.scope = None
        self.deadline = None
        self.invalidation = threading.Event()
        self.phase = 'reserving'
        self.calls = 0
        self.tool_busy = False
        self.runtime_started = False
        self.tasks = set()

    @staticmethod
    def _observe(task):
        if not task.cancelled():
            task.exception()

    def start(self):
        self.deadline = self.owner.clock() + self.owner.budget.max_wall_seconds

    def bind(self, lease):
        ident = self.identity
        self.scope = AgentScope(ident.account_id, ident.library_id, ident.thread_id,
            ident.request_id, ident.expected_revision, lease,
            secrets.token_urlsafe(24), self.deadline)
        self.phase = 'running'

    def check(self):
        if self.cancelled():
            raise AgentUnavailable()

    def cancelled(self):
        """Cheap cooperative callback; no database I/O inside row/progress checks."""
        return (self.invalidation.is_set() or self.phase not in ('reserving', 'running') or
                self.deadline is None or self.owner.clock() >= self.deadline)

    def spawn(self, awaitable):
        task = asyncio.create_task(awaitable)
        self.tasks.add(task)
        task.add_done_callback(self._observe)
        return task

    def spawn_call(self, function, *args, **kwargs):
        return self.spawn(run_in_threadpool(partial(function, *args, **kwargs)))

    async def wait(self, task, *, finalizing=False):
        if finalizing:
            if self.invalidation.is_set() or self.owner.clock() >= self.deadline:
                raise AgentUnavailable()
        else:
            self.check()
        remaining = self.deadline - self.owner.clock()
        # Shielding retains ownership of a committing threadpool call on timeout.
        return await asyncio.wait_for(asyncio.shield(task), remaining)

    async def call(self, function, *args, **kwargs):
        self.check()
        return await self.wait(self.spawn_call(function, *args, **kwargs))

    async def reconcile(self, task):
        """Retain ownership after the HTTP outcome; quarantine uncertain cleanup."""
        try:
            return await asyncio.wait_for(asyncio.shield(task), self.owner.cleanup_seconds)
        except TimeoutError:
            self.owner.healthy = False
            self.publish_error(AgentUnavailable())
            # No new admission while this owned operation remains unsettled.
            return await asyncio.shield(task)

    def invalidate(self):
        self.invalidation.set()
        self.phase = 'terminal'

    def publish(self, value):
        if not self.result.done():
            self.result.set_result(value)

    def publish_error(self, error):
        if not self.result.done():
            self.result.set_exception(error)

    async def dispatch(self, tools, name, arguments):
        # No await separates attempt accounting and the concurrent-call claim.
        self.calls += 1
        self.check()
        if self.calls > self.owner.budget.max_domain_call_attempts or self.tool_busy:
            self.invalidate()
            raise AgentUnavailable()
        self.tool_busy = True
        task = self.spawn_call(tools.dispatch, name, arguments)
        try:
            value = await self.wait(task)
            import json
            if len(json.dumps(value, ensure_ascii=False, allow_nan=False,
                              separators=(',', ':')).encode('utf-8')) > self.owner.budget.max_tool_result_bytes:
                self.invalidate()
                raise AgentUnavailable()
            return value
        finally:
            if task.done():
                self.tool_busy = False
            else:
                # Keep the slot owned until the actual synchronous read settles.
                task.add_done_callback(lambda _task: setattr(self, 'tool_busy', False))


class AgentSupervisor:
    """One nonqueued lane across accounts/threads in ONE application process."""
    def __init__(self, runtime, *, budget=None, cleanup_seconds=10, clock=time.monotonic):
        if not callable(getattr(runtime, 'run', None)):
            raise ValueError('Explicit agent runtime required')
        if (type(cleanup_seconds) not in (int, float) or
                not math.isfinite(cleanup_seconds) or not 0 < cleanup_seconds <= 10):
            raise ValueError('Invalid cleanup deadline')
        self.runtime = runtime
        self.budget = budget if budget is not None else AgentBudget()
        if type(self.budget) is not AgentBudget:
            raise ValueError('Explicit agent budget required')
        self.cleanup_seconds, self.clock = cleanup_seconds, clock
        self.healthy, self.closed = True, False
        self.operations = {}
        self.active = None
        self.loop = None

    def lookup(self, identity):
        operation = self.operations.get(identity.key)
        if operation is not None and operation.identity != identity:
            raise WorkspaceStoreConflict()
        return operation

    def submit(self, identity, execute):
        loop = asyncio.get_running_loop()
        if self.loop is not None and self.loop is not loop:
            raise AgentUnavailable()
        existing = self.lookup(identity)
        if existing is not None:
            return existing
        if self.closed or not self.healthy or self.active is not None:
            raise AgentUnavailable()
        self.loop = loop
        operation = AgentOperation(self, identity)
        self.operations[identity.key] = self.active = operation
        try:
            operation.task = asyncio.create_task(self._run(operation, execute))
            operation.task.add_done_callback(AgentOperation._observe)
        except BaseException:
            self.operations.pop(identity.key, None)
            self.active = None
            raise
        return operation

    async def _run(self, operation, execute):
        try:
            value = await execute(operation)
            operation.publish(value)
        except BaseException as error:
            operation.publish_error(AgentUnavailable() if isinstance(error, asyncio.CancelledError) else error)
        finally:
            operation.invalidate()
            # Cancellation/yield is not proof that runtime-owned resources stopped.
            cleanup = getattr(self.runtime, 'cleanup', None) if operation.runtime_started else None
            if cleanup is not None:
                try:
                    task = operation.spawn(cleanup(operation.scope))
                    if await operation.reconcile(task) is not True:
                        self.healthy = False
                except BaseException:
                    self.healthy = False
            pending = [task for task in operation.tasks if not task.done()]
            for task in pending:
                try:
                    await operation.reconcile(task)
                except BaseException:
                    pass
            self.operations.pop(operation.identity.key, None)
            if self.active is operation:
                self.active = None

    async def close(self):
        self.closed = True
        operations = list(self.operations.values())
        for operation in operations:
            operation.invalidate()
            # Wakes work waits while leaving protected threadpool calls owned.
            operation.task.cancel()
        if operations:
            _done, pending = await asyncio.wait(
                [op.task for op in operations], timeout=self.cleanup_seconds)
            if pending:
                self.healthy = False
