"""Default-off ownership of a dedicated native story process containment.

No PID adoption, endpoint discovery, shared-service stop, model loading, or default
binding. The injected kernel must create suspended children and enforce a private
non-breakaway containment, including descendants. Windows has such a kernel;
process groups alone are not a production substitute.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import math
import ntpath
import os
import re
import threading
import time
from types import MappingProxyType

from .memory_narrative import _canonical_uuid
from .selected_story_operations import PreparationScope


OPERATION_ENV = 'PHOTOHOUSE_NATIVE_STORY_OPERATION'
_SHA = re.compile(r'\A[0-9a-f]{64}\Z', re.ASCII)


class NativeStoryOwnerError(RuntimeError):
    def __init__(self, category):
        self.category = category if category in {
            'disabled', 'invalid_scope', 'busy', 'closed', 'cancelled', 'launch_failed',
        } else 'launch_failed'
        super().__init__('Native story process unavailable')


def _plain(value, limit):
    return (type(value) is str and bool(value) and len(value.encode('utf-8')) <= limit
            and not any(ord(c) < 32 or 127 <= ord(c) < 160 for c in value))


def _absolute(value):
    return _plain(value, 4096) and (os.path.isabs(value) or ntpath.isabs(value))


@dataclass(frozen=True, repr=False)
class NativeStoryLaunch:
    executable: str
    # Preflight digest only; deployment must protect path components from replacement.
    executable_sha256: str
    argv: tuple
    cwd: str
    environment: object
    memory_limit: int = 4 * 1024**3
    process_limit: int = 8
    minimum_free_ram: int = 8 * 1024**3

    def __post_init__(self):
        try:
            valid = (_absolute(self.executable) and _absolute(self.cwd)
                and type(self.executable_sha256) is str and _SHA.fullmatch(self.executable_sha256)
                and type(self.argv) in (list, tuple) and 1 <= len(self.argv) <= 64
                and self.argv[0] == self.executable and all(_plain(v, 4096) for v in self.argv)
                and sum(len(v.encode('utf-8')) for v in self.argv) <= 16384
                and type(self.environment) is dict and 1 <= len(self.environment) <= 64
                and all(_plain(k, 256) and '=' not in k and _plain(v, 8192)
                        for k, v in self.environment.items())
                and len({k.upper() for k in self.environment}) == len(self.environment)
                and OPERATION_ENV not in {k.upper() for k in self.environment}
                and sum(len((k + v).encode('utf-8')) for k, v in self.environment.items()) <= 32768
                and type(self.memory_limit) is int and 0 < self.memory_limit <= 64 * 1024**3
                and type(self.process_limit) is int and 1 <= self.process_limit <= 16
                and type(self.minimum_free_ram) is int and 0 <= self.minimum_free_ram <= 256 * 1024**3)
        except (ValueError, TypeError, UnicodeError):
            valid = False
        if not valid:
            raise ValueError('Invalid explicit native story launch')
        object.__setattr__(self, 'argv', tuple(self.argv))
        object.__setattr__(self, 'environment', MappingProxyType(dict(self.environment)))


@dataclass(repr=False)
class _NativeCall:
    scope: PreparationScope
    stop: threading.Event = field(default_factory=threading.Event)
    api: object = None
    job: object = None
    process: object = None
    thread: object = None
    assigned: bool = False
    uncertain_spawn: bool = False
    close_failed: bool = False
    launch: asyncio.Task | None = None
    cleanup: asyncio.Task | None = None
    waiting: asyncio.Task | None = None


class NativeStoryProcessOwner:
    """One retained private containment; exact scope identity controls cleanup.

    This certifies only the process tree actually launched in its containment.
    An HTTP provider must not use it directly as proof about an unrelated server.
    A separately qualified provider-to-process binding must own all inference.
    """
    proof_domain = 'owned_process_tree'

    def __init__(self, launch, *, kernel_factory, enabled=False, cleanup_seconds=5,
                 monotonic=time.monotonic, sleep=time.sleep):
        if (type(launch) is not NativeStoryLaunch or not callable(kernel_factory)
                or type(enabled) is not bool or type(cleanup_seconds) not in (int, float)
                or not math.isfinite(cleanup_seconds) or not 0 < cleanup_seconds <= 10
                or not callable(monotonic) or not callable(sleep)):
            raise ValueError('Invalid native story owner configuration')
        self.launch_spec, self.kernel_factory, self.enabled = launch, kernel_factory, enabled
        self.cleanup_seconds, self.clock, self.sleep = float(cleanup_seconds), monotonic, sleep
        self._loop = None
        self._active = None
        self._last_settled_scope = None
        self._closed = False

    def _bind(self):
        loop = asyncio.get_running_loop()
        if self._loop is None:
            self._loop = loop
        elif self._loop is not loop:
            raise NativeStoryOwnerError('invalid_scope')

    @staticmethod
    def _scope(scope):
        try:
            if type(scope) is not PreparationScope:
                return False
            _canonical_uuid(scope.operation_id, 'operation')
            return math.isfinite(scope.deadline_monotonic)
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _allowed(call):
        if call.stop.is_set() or call.scope.cancelled():
            raise NativeStoryOwnerError('cancelled')

    async def begin(self, scope):
        self._bind()
        if not self.enabled:
            raise NativeStoryOwnerError('disabled')
        if self._closed:
            raise NativeStoryOwnerError('closed')
        if not self._scope(scope):
            raise NativeStoryOwnerError('invalid_scope')
        if self._active is not None:
            raise NativeStoryOwnerError('busy')
        if (self._last_settled_scope is not None and
                self._last_settled_scope.operation_id == scope.operation_id):
            raise NativeStoryOwnerError('invalid_scope')
        call = _NativeCall(scope)
        self._active = call
        call.launch = asyncio.create_task(asyncio.to_thread(self._launch, call))
        if not await asyncio.shield(call.launch):
            raise NativeStoryOwnerError('cancelled' if call.stop.is_set() or scope.cancelled()
                                        else 'launch_failed')
        self._allowed(call)
        return True  # Launch readiness, never endpoint binding or cleanup proof.

    async def _wait_exit(self, call):
        await asyncio.shield(call.launch)
        while True:
            self._allowed(call)
            try:
                state = await asyncio.to_thread(call.api.wait_process, call.process, 0)
            except Exception:
                raise NativeStoryOwnerError('launch_failed') from None
            self._allowed(call)
            if state == 'exited':
                try:
                    code = await asyncio.to_thread(call.api.exit_code, call.process)
                except Exception:
                    raise NativeStoryOwnerError('launch_failed') from None
                if type(code) is not int or code != 0:
                    raise NativeStoryOwnerError('launch_failed')
                return True  # Root readiness only; not Job drain or cleanup proof.
            if state != 'timeout':
                raise NativeStoryOwnerError('launch_failed')
            await asyncio.sleep(0.025)

    async def wait_for_exit(self, scope):
        self._bind()
        call = self._active
        if call is None or call.scope is not scope or call.stop.is_set():
            raise NativeStoryOwnerError('invalid_scope')
        if call.waiting is None:
            call.waiting = asyncio.create_task(self._wait_exit(call))
        return await asyncio.shield(call.waiting)

    def _launch(self, call):
        try:
            self._allowed(call)
            spec = self.launch_spec
            call.api = self.kernel_factory()
            if call.api.free_ram() < spec.minimum_free_ram:
                return False
            self._allowed(call)
            if call.api.sha256_file(spec.executable, call.scope.deadline_monotonic) != spec.executable_sha256:
                return False
            self._allowed(call)
            call.job = call.api.create_job(spec.memory_limit, spec.process_limit)
            if not call.job:
                return False
            self._allowed(call)
            environment = dict(spec.environment)
            environment[OPERATION_ENV] = call.scope.operation_id
            call.uncertain_spawn = True
            created = call.api.create_suspended(spec.executable, list(spec.argv), environment, spec.cwd)
            if type(created) is not tuple or len(created) != 3:
                return False
            call.process, call.thread, pid = created
            # Even partial returned handles remain owned and must be reconciled.
            if not call.process and not call.thread and type(pid) is int and pid == 0:
                call.uncertain_spawn = False  # Kernel's explicit no-child outcome.
                return False
            if not call.process or not call.thread or type(pid) is not int or pid <= 0:
                return False
            call.uncertain_spawn = False
            self._allowed(call)
            if call.api.assign(call.job, call.process) is not True:
                return False
            call.assigned = True
            self._allowed(call)
            if call.api.resume(call.thread) is not True:
                return False
            self._allowed(call)
            return True
        except Exception:
            return False  # Retain any created handles; expose no native diagnostics.

    def _stop_native(self, call):
        api = call.api
        if call.close_failed:
            return False  # Never retry a handle whose close outcome is uncertain.
        if api is None:
            return True  # Factory never established any native ownership.
        try:
            # Scope-private job only: root exit alone says nothing about children.
            if call.assigned:
                count = api.active_processes(call.job)
                if type(count) is not int or count < 0:
                    return False
                root = api.wait_process(call.process, 0)
                if root not in {'exited', 'timeout'}:
                    return False
                if count or root != 'exited':
                    api.terminate_job(call.job)  # Signal acknowledgement is not proof.
            elif call.process:
                api.terminate_process(call.process)  # Still suspended; never resumed.
            elif call.uncertain_spawn:
                # The kernel lost/failed its child-create receipt. The private
                # job may be killed defensively, but an unassigned child is unknown.
                if call.job:
                    api.terminate_job(call.job)
                return False
            until = self.clock() + self.cleanup_seconds
            while True:
                root = api.wait_process(call.process, 0) if call.process else 'exited'
                count = api.active_processes(call.job) if call.job else 0
                if root not in {'exited', 'timeout'} or type(count) is not int or count < 0:
                    return False
                if root == 'exited' and count == 0:
                    break
                remaining = until - self.clock()
                if remaining <= 0:
                    return False
                self.sleep(min(0.025, remaining))
            if call.uncertain_spawn:
                return False
            for name in ('thread', 'process', 'job'):
                handle = getattr(call, name)
                if handle:
                    try:
                        api.close(handle)
                    except Exception:
                        call.close_failed = True
                        return False
                    setattr(call, name, None)
            return True
        except Exception:
            return False

    async def _cleanup(self, call):
        await asyncio.shield(call.launch)  # A cancelled waiter cannot abandon launch.
        if call.waiting is not None:
            try:
                await asyncio.shield(call.waiting)
            except Exception:
                pass
        proof = await asyncio.to_thread(self._stop_native, call)
        if proof is True and self._active is call:
            self._active = None
            self._last_settled_scope = call.scope
        return proof is True

    async def stop_and_reconcile(self, scope):
        self._bind()
        if not self._scope(scope):
            return False
        if self._last_settled_scope is scope:
            return True
        call = self._active
        if call is None or call.scope is not scope:
            return False
        call.stop.set()
        if (call.cleanup is None or call.cleanup.cancelled() or
                call.cleanup.done() and (call.cleanup.exception() is not None
                                        or call.cleanup.result() is not True)):
            call.cleanup = asyncio.create_task(self._cleanup(call))
        return await asyncio.shield(call.cleanup)

    async def close(self):
        self._bind()
        self._closed = True
        call = self._active
        return True if call is None else await self.stop_and_reconcile(call.scope)
