"""Unwired, event-loop-local admission for bounded household inference owners.

No authentication, provider I/O, jobs, HTTP states or durable recovery lives
here. Callers retain ownership until resources are reconciled explicitly.
"""
import asyncio
from collections import deque
from dataclasses import dataclass
import math
import re


class AdmissionError(RuntimeError):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, repr=False)
class AdmissionIdentity:
    account_id: str
    library_id: str
    request_id: str
    profile: str
    request_digest: str

    def __post_init__(self):
        for value in (self.account_id, self.library_id, self.request_id, self.profile):
            try:
                valid = (type(value) is str and 0 < len(value) <= 256
                         and len(value.encode('utf-8')) <= 256
                         and not any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in value))
            except UnicodeError:
                valid = False
            if not valid:
                raise ValueError('invalid_admission_identity')
        if (type(self.request_digest) is not str or
                re.fullmatch(r'[0-9a-f]{64}', self.request_digest) is None):
            raise ValueError('invalid_admission_digest')

    @property
    def key(self):
        return self.account_id, self.library_id, self.request_id


@dataclass(frozen=True)
class AdmissionState:
    active: int
    waiting: int
    closed: bool
    quarantined: bool


class AdmissionPermit:
    def __init__(self, owner, identity):
        self._owner = owner
        self._identity = identity
        self._finished = False

    @property
    def identity(self):
        return self._identity

    def finish(self, *, reconciled):
        """Explicit resource settlement; cancellation alone is never enough."""
        return self._owner._finish(self, reconciled)


class _Waiter:
    def __init__(self, identity, loop, deadline):
        self.identity = identity
        self.deadline = deadline
        self.future = loop.create_future()
        self.timer = None


class InferenceAdmission:
    def __init__(self, *, max_waiting=4, wait_seconds=20):
        if (type(max_waiting) is not int or not 0 <= max_waiting <= 4 or
                type(wait_seconds) not in (int, float) or
                not 0 < wait_seconds <= 20 or not math.isfinite(wait_seconds)):
            raise ValueError('invalid_admission_limits')
        self._max_waiting = max_waiting
        self._wait_seconds = wait_seconds
        self._loop = None
        self._active = None
        self._waiting = deque()
        self._owned = {}
        self._accounts_waiting = set()
        self._closed = False
        self._quarantined = False

    @property
    def max_waiting(self):
        return self._max_waiting

    @property
    def wait_seconds(self):
        return self._wait_seconds

    def _bind(self):
        loop = asyncio.get_running_loop()
        if self._loop is None:
            self._loop = loop
        elif self._loop is not loop:
            raise RuntimeError('admission_event_loop_mismatch')
        return loop

    def state(self):
        self._bind()
        return AdmissionState(int(self._active is not None), len(self._waiting),
                              self._closed, self._quarantined)

    async def acquire(self, identity, *, wait=True):
        loop = self._bind()
        if type(identity) is not AdmissionIdentity or type(wait) is not bool:
            raise ValueError('invalid_admission_request')
        existing = self._owned.get(identity.key)
        if existing is not None:
            reason = 'duplicate_owned' if existing.identity == identity else 'request_conflict'
            raise AdmissionError(reason)
        if self._closed or self._quarantined:
            raise AdmissionError('quarantined' if self._quarantined else 'closed')
        self._promote()
        if self._active is None:
            return self._grant(identity)
        if not wait:
            raise AdmissionError('busy')
        if identity.account_id in self._accounts_waiting:
            raise AdmissionError('account_waiting')
        if len(self._waiting) >= self.max_waiting:
            raise AdmissionError('waiting_full')
        entry = _Waiter(identity, loop, loop.time() + self.wait_seconds)
        self._waiting.append(entry)
        self._accounts_waiting.add(identity.account_id)
        self._owned[identity.key] = entry
        entry.timer = loop.call_at(entry.deadline, self._expire, entry)
        try:
            return await asyncio.shield(entry.future)
        except asyncio.CancelledError:
            if entry.future.done():
                if not entry.future.cancelled() and entry.future.exception() is None:
                    # The acquire never returned: provider work cannot have started.
                    entry.future.result().finish(reconciled=True)
            else:
                self._remove(entry)
                entry.future.cancel()
            raise

    def _grant(self, identity):
        permit = AdmissionPermit(self, identity)
        self._active = permit
        self._owned[identity.key] = permit
        return permit

    def _remove(self, entry):
        if self._owned.get(entry.identity.key) is not entry:
            return False
        self._waiting.remove(entry)
        self._accounts_waiting.remove(entry.identity.account_id)
        del self._owned[entry.identity.key]
        entry.timer.cancel()
        return True

    def _expire(self, entry):
        if self._remove(entry):
            entry.future.set_exception(AdmissionError('waiting_expired'))

    def _promote(self):
        if self._active is not None or self._closed or self._quarantined:
            return
        while self._waiting:
            entry = self._waiting[0]
            self._remove(entry)
            if self._loop.time() >= entry.deadline:
                entry.future.set_exception(AdmissionError('waiting_expired'))
                continue
            entry.future.set_result(self._grant(entry.identity))
            return

    def _finish(self, permit, reconciled):
        self._bind()
        if type(reconciled) is not bool:
            raise ValueError('explicit_reconciliation_required')
        if permit._finished:
            return False
        if self._active is not permit:
            raise AdmissionError('permit_owner_mismatch')
        if not reconciled:
            self._quarantined = True
            self._reject_waiters('quarantined')
            return False
        permit._finished = True
        self._active = None
        del self._owned[permit.identity.key]
        self._promote()
        return True

    def _reject_waiters(self, reason):
        while self._waiting:
            entry = self._waiting[0]
            self._remove(entry)
            entry.future.set_exception(AdmissionError(reason))

    def close(self):
        self._bind()
        self._closed = True
        self._reject_waiters('closed')
