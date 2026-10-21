"""Household draft ownership, exact retries and shared model admission.

An injected provider must implement async prepare(bundle, scope) and async
stop_and_reconcile(scope). Only EXACT True from the latter certifies that all
native work belonging to the scope stopped; coroutine completion is not proof.
App/session ownership lives in selected_story_lifecycle. No adapter to the
synchronous narrator or preparation HTTP route is added here.
"""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import threading
import time
import uuid

from .credentials import session_digest
from .host_inference_admission import HostAdmissionError
from .inference_admission import AdmissionError, AdmissionIdentity, InferenceAdmission
from .memory_narrative import _canonical_uuid, _text, validate_narrative
from .selected_story_snapshot import (
    SourceSnapshot, _encode, resolve_snapshot, revalidate_snapshot, validate_request,
)
from .service import AccessDenied, AccessService
from .transport import TransportError


class DraftOperationError(RuntimeError):
    def __init__(self, reason):
        if reason not in {'denied', 'invalid_request', 'conflict', 'busy', 'unavailable',
                          'cancelled', 'timed_out', 'closed', 'registry_full', 'scope_changed'}:
            reason = 'unavailable'
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, repr=False)
class DraftPrincipal:
    account_id: str
    session_digest: str


class SelectedStorySources:
    """Synchronous protected reads; the owner always runs these off its loop."""
    def __init__(self, runtime):
        self.runtime = runtime

    def authenticate(self, token, library):
        with self.runtime.connection_factory() as db:
            access = AccessService(db, clock=self.runtime.clock,
                                   memory_groups_enabled=self.runtime.memory_groups_enabled)
            with access._transaction():
                member = access._require(token, library, 'story.write')
                return DraftPrincipal(member['account_id'], session_digest(token))

    def resolve(self, token, library, request):
        return resolve_snapshot(self.runtime, token, library, request)

    def revalidate(self, token, snapshot):
        revalidate_snapshot(self.runtime, token, snapshot)


@dataclass(frozen=True, repr=False)
class PreparationScope:
    operation_id: str
    deadline_monotonic: float
    _invalidation: threading.Event
    _clock: object

    def cancelled(self):
        return self._invalidation.is_set() or self._clock() >= self.deadline_monotonic


class _Operation:
    def __init__(self, identity, principal, forget_at, previous=None):
        self.identity, self.session = identity, principal.session_digest
        self.forget_at = forget_at
        self.state, self.error = 'running', None
        self.invalidated = threading.Event()
        loop = asyncio.get_running_loop()
        self.abort, self.done = loop.create_future(), loop.create_future()
        self.task = self.permit = self.scope = self.snapshot = None
        self.provider_task = self.settlement = None
        self.provider_started = False
        self.cleaning = False
        self.work = set()
        self.payload = None
        self.expires = None
        self.timer = None
        self.source_fingerprint = previous.source_fingerprint if previous else None
        self.auth_fingerprint = previous.auth_fingerprint if previous else None


def _reason(error):
    if isinstance(error, DraftOperationError):
        return error.reason
    if isinstance(error, HostAdmissionError):
        return 'busy' if error.reason == 'busy' else 'unavailable'
    if isinstance(error, AccessDenied):
        return 'denied'
    if isinstance(error, TransportError):
        return {400: 'invalid_request', 422: 'invalid_request', 409: 'conflict',
                401: 'denied', 403: 'denied'}.get(error.status, 'unavailable')
    return 'unavailable'


class DraftOperations:
    def __init__(self, sources, provider, admission, *, work_seconds=60,
                 cleanup_seconds=10, result_seconds=1800, identity_seconds=86400,
                 max_records=128, max_retained=16, monotonic=time.monotonic,
                 wall_clock=time.time):
        for value, ceiling in ((work_seconds, 60), (cleanup_seconds, 10),
                               (result_seconds, 1800), (identity_seconds, 86400)):
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= ceiling:
                raise ValueError('invalid_draft_limits')
        if (identity_seconds < result_seconds or type(max_records) is not int or
                not 1 <= max_records <= 128 or type(max_retained) is not int or
                not 1 <= max_retained <= min(16, max_records) or
                type(admission) is not InferenceAdmission or
                not callable(monotonic) or not callable(wall_clock)):
            raise ValueError('invalid_draft_configuration')
        self.sources, self.provider, self.admission = sources, provider, admission
        self.work_seconds, self.cleanup_seconds = work_seconds, cleanup_seconds
        self.result_seconds, self.identity_seconds = result_seconds, identity_seconds
        self.max_records, self.max_retained = max_records, max_retained
        self.clock, self.wall_clock = monotonic, wall_clock
        self._loop = None
        self._records = {}
        self._tasks = set()
        self._reads = set()
        self._invalid_sessions = set()
        self._session_barriers = {}
        self._closed = False

    def _bind(self):
        loop = asyncio.get_running_loop()
        if self._loop is None:
            self._loop = loop
        elif self._loop is not loop:
            raise RuntimeError('draft_event_loop_mismatch')
        return loop

    def _spawn(self, awaitable):
        task = asyncio.create_task(awaitable)
        self._tasks.add(task)
        def settled(value):
            self._tasks.discard(value)
            if not value.cancelled():
                value.exception()
        task.add_done_callback(settled)
        return task

    def _check_session(self, principal):
        if self._closed:
            raise DraftOperationError('closed')
        if (principal.session_digest in self._invalid_sessions or
                principal.session_digest in self._session_barriers):
            raise DraftOperationError('scope_changed')

    def _read(self, function, *args):
        # Detached request waiters must not accumulate unlimited DB threads.
        if len(self._reads) >= 16:
            raise DraftOperationError('busy')
        task = self._spawn(asyncio.to_thread(function, *args))
        self._reads.add(task)
        task.add_done_callback(self._reads.discard)
        return task

    async def _authenticate(self, token, library):
        self._bind()
        if self._closed:
            raise DraftOperationError('closed')
        try:
            principal = await asyncio.shield(self._read(self.sources.authenticate, token, library))
            if type(principal) is not DraftPrincipal or principal.session_digest != session_digest(token):
                raise DraftOperationError('denied')
        except asyncio.CancelledError:
            raise
        except Exception as error:
            raise DraftOperationError(_reason(error)) from None
        self._check_session(principal)
        return principal

    def _notify(self, operation):
        if not operation.done.done():
            operation.done.set_result(None)  # Never retain prose or exceptions in a Future.

    def _fence(self, operation, reason):
        operation.invalidated.set()
        operation.error = operation.error or reason
        operation.payload = operation.snapshot = None
        if operation.timer is not None:
            operation.timer.cancel()
        if not operation.abort.done():
            operation.abort.set_result(None)
        if operation.permit is None:
            operation.state = 'cancelled'
        self._notify(operation)

    def _expire(self, operation):
        if operation.state == 'ready' and self.clock() >= operation.expires:
            operation.payload = operation.snapshot = None
            operation.state = 'expired'
            if operation.timer is not None:
                operation.timer.cancel()

    def _prune(self):
        now = self.clock()
        for key, operation in tuple(self._records.items()):
            self._expire(operation)
            if (operation.permit is None and operation.task.done() and
                    operation.state not in {'running', 'ready', 'reconciling'} and
                    now >= operation.forget_at):
                del self._records[key]

    async def prepare(self, token, library, request):
        try:
            _text(library, 128, 'library', nonblank=True)
            if any(ord(char) < 32 for char in library):
                raise ValueError('invalid_library')
            clean = validate_request(request)
        except (TransportError, ValueError):
            raise DraftOperationError('invalid_request') from None
        principal = await self._authenticate(token, library)
        digest = hashlib.sha256(_encode([principal.account_id, library, clean], 34 * 1024)).hexdigest()
        identity = AdmissionIdentity(principal.account_id, library, clean['request_id'],
                                     'selected_story_v1', digest)
        self._prune()
        operation = self._records.get(identity.key)
        # Lookup/register has no await: two first callers cannot create two owners.
        if operation is not None:
            if operation.identity != identity:
                raise DraftOperationError('conflict')
            if operation.session != principal.session_digest:
                raise DraftOperationError('scope_changed')
        if operation is None or operation.state in {'expired', 'retryable'}:
            if operation is None and len(self._records) >= self.max_records:
                raise DraftOperationError('registry_full')
            protected = sum(value.state in {'running', 'ready', 'reconciling'}
                            for value in self._records.values())
            if protected >= self.max_retained:
                raise DraftOperationError('registry_full')
            previous = operation
            forget_at = max(previous.forget_at, self.clock() + self.identity_seconds) if previous else self.clock() + self.identity_seconds
            operation = _Operation(identity, principal, forget_at, previous)
            self._records[identity.key] = operation
            operation.task = self._spawn(self._run(operation, token, library, clean))
        await asyncio.shield(operation.done)  # Disconnect cancels only this waiter.
        return await self._deliver(operation, token, library)

    def _check(self, operation):
        if operation.invalidated.is_set():
            raise DraftOperationError(operation.error or 'cancelled')
        if self.clock() >= operation.scope.deadline_monotonic:
            raise DraftOperationError('timed_out')

    async def _work(self, operation, function, *args):
        self._check(operation)
        task = self._read(function, *args)
        operation.work.add(task)
        await self._wait(operation, task)
        return task.result()

    async def _wait(self, operation, task):
        self._check(operation)
        remaining = operation.scope.deadline_monotonic - self.clock()
        done, _ = await asyncio.wait((task, operation.abort), timeout=max(0, remaining),
                                     return_when=asyncio.FIRST_COMPLETED)
        self._check(operation)
        if task not in done:
            raise DraftOperationError('timed_out')

    async def _run(self, operation, token, library, request):
        candidate = None
        try:
            try:
                operation.permit = await self.admission.acquire(operation.identity, wait=False)
            except AdmissionError as error:
                operation.state = 'retryable' if error.reason == 'busy' else 'failed'
                raise DraftOperationError('busy' if error.reason == 'busy' else 'unavailable') from None
            operation.scope = PreparationScope(str(uuid.uuid4()), self.clock() + self.work_seconds,
                                                operation.invalidated, self.clock)
            # Resolve after admission, reauthorizing source state and edit ownership.
            snapshot = await self._work(operation, self.sources.resolve, token, library, request)
            if (type(snapshot) is not SourceSnapshot or snapshot.account_id != operation.identity.account_id
                    or snapshot.library_id != library or snapshot.request_digest != operation.identity.request_digest):
                raise DraftOperationError('denied')
            source_hash = hashlib.sha256(snapshot._document_bytes).hexdigest()
            auth_hash = hashlib.sha256(snapshot._authorization_bytes).hexdigest()
            if (operation.source_fingerprint is not None and
                    (source_hash != operation.source_fingerprint or auth_hash != operation.auth_fingerprint)):
                raise DraftOperationError('conflict')
            operation.source_fingerprint, operation.auth_fingerprint = source_hash, auth_hash
            operation.snapshot = snapshot
            operation.scope = PreparationScope(snapshot.operation_id,
                operation.scope.deadline_monotonic, operation.invalidated, self.clock)
            operation.provider_started = True
            operation.provider_task = self._spawn(self.provider.prepare(snapshot.bundle(), operation.scope))
            operation.work.add(operation.provider_task)
            await self._wait(operation, operation.provider_task)
            narrative = validate_narrative(operation.provider_task.result(), snapshot.bundle())
            await self._work(operation, self.sources.revalidate, token, snapshot)
            candidate = (snapshot, narrative)
        except asyncio.CancelledError:
            self._fence(operation, 'cancelled')
        except Exception as error:
            operation.error = operation.error or _reason(error)
            if operation.error == 'busy' and (not operation.provider_started
                    or isinstance(error, HostAdmissionError)):
                operation.state = 'retryable'
        finally:
            if operation.permit is not None:
                # Fence provider work even on success, before asking for stop proof.
                operation.invalidated.set()
                clean = await self._cleanup(operation)
            else:
                clean = True
            if candidate is not None and operation.error is None and clean:
                try:
                    if self.clock() >= operation.scope.deadline_monotonic:
                        raise DraftOperationError('timed_out')
                    operation.expires = self.clock() + self.result_seconds
                    operation.payload = self._assemble(*candidate,
                        expires_wall=self.wall_clock() + self.result_seconds)
                    if self.clock() >= operation.scope.deadline_monotonic:
                        raise DraftOperationError('timed_out')
                    operation.forget_at = max(operation.forget_at, operation.expires)
                    operation.state = 'ready'
                    operation.timer = self._loop.call_later(self.result_seconds, self._expire, operation)
                except Exception as error:
                    operation.error = _reason(error)
            if operation.state != 'ready':
                operation.payload = operation.snapshot = None
                if operation.state not in {'retryable', 'reconciling'}:
                    operation.state = 'cancelled' if operation.error in {'cancelled', 'scope_changed', 'closed'} else 'failed'
                operation.error = operation.error or 'unavailable'
            self._notify(operation)

    async def _stop_and_drain(self, operation):
        if operation.provider_task is not None and not operation.provider_task.done():
            operation.provider_task.cancel()
        cleanup = None
        if operation.provider_started:
            try:
                cleanup = self._spawn(self.provider.stop_and_reconcile(operation.scope))
                operation.work.add(cleanup)
            except Exception:
                pass
        await asyncio.gather(*operation.work, return_exceptions=True)
        proof = not operation.provider_started
        if cleanup is not None:
            try:
                proof = cleanup.result() is True
            except BaseException:
                proof = False
        operation.work.clear()
        operation.provider_task = None
        return proof

    def _settled(self, operation, proof):
        operation.cleaning = False
        if proof is True:
            operation.permit.finish(reconciled=True)
            operation.permit = None
            if operation.state == 'reconciling':
                operation.state = 'failed'
            return True
        operation.permit.finish(reconciled=False)
        operation.state = 'reconciling'
        self._fence(operation, 'unavailable')
        return False

    async def _late_settlement(self, operation, task):
        proof = await asyncio.shield(task)
        self._settled(operation, proof)

    async def _cleanup(self, operation):
        if operation.cleaning:
            return False
        operation.cleaning = True
        operation.settlement = self._spawn(self._stop_and_drain(operation))
        done, _ = await asyncio.wait((operation.settlement,), timeout=self.cleanup_seconds)
        if not done:
            operation.permit.finish(reconciled=False)
            operation.state = 'reconciling'
            self._fence(operation, 'unavailable')
            self._spawn(self._late_settlement(operation, operation.settlement))
            return False
        return self._settled(operation, operation.settlement.result())

    def _assemble(self, snapshot, narrative, *, expires_wall):
        document = snapshot.document()
        expiry = datetime.fromtimestamp(expires_wall, timezone.utc).isoformat().replace('+00:00', 'Z')
        chapters = []
        for source_chapter, wording in zip(document['chapters'], narrative['chapters']):
            sources = {source['source_id']: source for source in source_chapter['sources']}
            chapters.append({'id': source_chapter['id'], 'title': source_chapter['title'],
                             'asset_ids': source_chapter['asset_ids'], 'narration': wording['narration'],
                             'citations': [{key: sources[reference][key] for key in
                                            ('source_id', 'selected_asset_ids', 'source_kind',
                                             'source_revision', 'source_digest', 'byline')}
                                           for reference in wording['source_ids']]})
        return _encode({'version': 1, 'request_id': document['request_id'],
                        'draft_id': str(uuid.uuid4()), 'state': 'needs_review', 'expires_at': expiry,
                        'selection_revision': document['selection_revision'],
                        'source_policy': document['source_policy'], 'title': narrative['title'],
                        'chapters': chapters, 'questions': narrative['questions'], 'needs_review': True}, 64 * 1024)

    async def _deliver(self, operation, token, library):
        principal = await self._authenticate(token, library)
        if principal.account_id != operation.identity.account_id or principal.session_digest != operation.session:
            raise DraftOperationError('scope_changed')
        self._expire(operation)
        if operation.error is not None:
            raise DraftOperationError(operation.error)
        if operation.state != 'ready' or self._records.get(operation.identity.key) is not operation:
            raise DraftOperationError('scope_changed')
        try:
            await asyncio.shield(self._read(self.sources.revalidate, token, operation.snapshot))
        except asyncio.CancelledError:
            raise
        except DraftOperationError as error:
            if error.reason != 'busy':
                self._fence(operation, error.reason)
            raise
        except Exception as error:
            self._fence(operation, _reason(error))
            raise DraftOperationError(_reason(error)) from None
        self._check_session(principal)
        self._expire(operation)
        if operation.error is not None:
            raise DraftOperationError(operation.error)
        if operation.state != 'ready' or self._records.get(operation.identity.key) is not operation:
            raise DraftOperationError('scope_changed')
        return json.loads(operation.payload)

    async def cancel(self, token, library, request_id):
        principal = await self._authenticate(token, library)
        try:
            _canonical_uuid(request_id, 'request id')
        except ValueError:
            raise DraftOperationError('invalid_request') from None
        operation = self._records.get((principal.account_id, library, request_id))
        if operation is None:
            return False
        if operation.session != principal.session_digest:
            raise DraftOperationError('scope_changed')
        self._fence(operation, 'cancelled')
        return True

    @contextmanager
    def session_barrier(self, token):
        """Trusted host logout barrier held until the revocation write settles.

        Unknown tokens consume only a bounded in-flight slot, never a permanent
        invalidation record. Current database policy governs later requests.
        """
        self._bind()
        digest = session_digest(token)
        if digest not in self._session_barriers and len(self._session_barriers) >= 16:
            raise DraftOperationError('busy')
        self._session_barriers[digest] = self._session_barriers.get(digest, 0) + 1
        for operation in self._records.values():
            if operation.session == digest:
                self._fence(operation, 'scope_changed')
        try:
            yield
        finally:
            remaining = self._session_barriers[digest] - 1
            if remaining:
                self._session_barriers[digest] = remaining
            else:
                del self._session_barriers[digest]

    def invalidate_membership(self, account_id, library_id):
        """Trusted post-commit hook; never accepts a client authorization claim."""
        self._bind()
        for operation in self._records.values():
            if (operation.identity.account_id == account_id and
                    operation.identity.library_id == library_id):
                self._fence(operation, 'scope_changed')

    def invalidate_session(self, token):
        """Trusted host lifecycle hook, not an unauthenticated cancellation API."""
        self._bind()
        digest = session_digest(token)
        if len(self._invalid_sessions) >= 1024 and digest not in self._invalid_sessions:
            self._closed = True  # No eviction that could revive an invalidated session.
        else:
            self._invalid_sessions.add(digest)
        for operation in self._records.values():
            if self._closed or operation.session == digest:
                self._fence(operation, 'closed' if self._closed else 'scope_changed')

    async def reconcile(self):
        self._bind()
        for operation in tuple(self._records.values()):
            if (operation.permit is not None and operation.task.done() and
                    not operation.cleaning):
                await self._cleanup(operation)
        return all(operation.permit is None for operation in self._records.values())

    def begin_close(self):
        """Fence synchronously before the app yields to shutdown cleanup tasks."""
        self._bind()
        self._closed = True
        for operation in self._records.values():
            self._fence(operation, 'closed')

    async def close(self):
        self.begin_close()
        tasks = tuple(self._tasks)
        if tasks:
            await asyncio.wait(tasks, timeout=self.cleanup_seconds)
        return (all(task.done() for task in self._tasks) and
                all(operation.permit is None for operation in self._records.values()))
