"""Explicit async loopback narrative adapter; never grants native stop authority.

No default binding, model discovery, installation, fallback or retry. A separately
qualified native owner must reconcile every dispatched request, even a completed
HTTP response. Client disconnect/close is not native work termination proof.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import inspect
import math
import re

import httpx

from .memory_narrative import (
    MAX_OUTPUT_BYTES, MAX_PROVIDER_BYTES, _generation_payload, _json_bytes,
    _strict_loads, _validate_bundle, validate_narrative,
)
from .selected_story_operations import PreparationScope


_LOOPBACK = re.compile(r'\Ahttp://(127\.0\.0\.1|\[::1\]):([1-9][0-9]{0,4})(/api/generate)?/?\Z', re.ASCII)
_MODEL = re.compile(r'\A[A-Za-z0-9][A-Za-z0-9._:/@-]{0,119}\Z', re.ASCII)
_MAX_REQUEST_BYTES = 128 * 1024


class LocalSelectedStoryError(RuntimeError):
    """Fixed diagnostics only; never retain source, URL or provider response text."""
    def __init__(self, category):
        self.category = category if category in {
            'disabled', 'busy', 'invalid_input', 'cancelled', 'transport', 'invalid_response',
        } else 'transport'
        super().__init__('Local selected-story provider unavailable')


@dataclass(repr=False)
class _Call:
    scope: PreparationScope
    settled: asyncio.Event = field(default_factory=asyncio.Event)
    dispatched: bool = False
    cleanup: asyncio.Task | None = None


class LocalSelectedStoryProvider:
    """One adapter-owned request at a time, with explicit native reconciliation.

    ``native_owner.stop_and_reconcile(scope)`` is trusted host code, never model
    output. It must prove that all native work for that exact scope has stopped.
    It also owns qualification of the configured server/model's local execution,
    retention, startup/crash behavior and participating inference consumers.
    Loopback routing and a model label alone cannot establish those properties.
    """
    def __init__(self, url, model, *, enabled=False, native_owner=None,
                 timeout=45, transport=None):
        match = _LOOPBACK.fullmatch(url) if type(url) is str else None
        if not match or int(match[2]) > 65535:
            raise ValueError('Explicit literal loopback generation URL required')
        if (type(model) is not str or not _MODEL.fullmatch(model) or '://' in model):
            raise ValueError('Explicit local model identifier required')
        if (type(enabled) is not bool or type(timeout) not in (int, float)
                or not math.isfinite(timeout) or not 0 < timeout <= 60):
            raise ValueError('Invalid local selected-story configuration')
        if ((enabled or native_owner is not None) and
                not inspect.iscoroutinefunction(getattr(native_owner, 'stop_and_reconcile', None))):
            raise ValueError('Explicit async native work owner required')
        if getattr(native_owner, 'proof_domain', None) == 'owned_process_tree':
            raise ValueError('Qualified provider-to-process binding required')
        if transport is not None and not isinstance(transport, httpx.AsyncBaseTransport):
            raise ValueError('Async provider transport required')
        self.url = f'http://{match[1]}:{match[2]}/api/generate'
        self.model, self.enabled, self.native_owner = model, enabled, native_owner
        self.timeout, self.transport = float(timeout), transport
        self._loop = None
        self._active = None
        self._last_settled_scope = None

    def _bind(self):
        loop = asyncio.get_running_loop()
        if self._loop is None:
            self._loop = loop
        elif self._loop is not loop:
            raise LocalSelectedStoryError('transport')

    @staticmethod
    def _check(scope):
        if scope.cancelled():
            raise LocalSelectedStoryError('cancelled')

    async def prepare(self, bundle, scope):
        self._bind()
        if not self.enabled:
            raise LocalSelectedStoryError('disabled')
        if type(scope) is not PreparationScope:
            raise LocalSelectedStoryError('invalid_input')
        if (self._last_settled_scope is not None and
                self._last_settled_scope.operation_id == scope.operation_id):
            raise LocalSelectedStoryError('invalid_input')
        if self._active is not None:
            raise LocalSelectedStoryError('busy')
        self._check(scope)
        try:
            clean = _validate_bundle(bundle, allow_draft=True)
            if clean['version'] != 3 or clean['target']['id'] != scope.operation_id:
                raise ValueError('Invalid preparation scope')
            payload = _json_bytes(_generation_payload(clean, 'narrative', self.model),
                                  'local generation request', _MAX_REQUEST_BYTES)
            remaining = min(self.timeout, scope.deadline_monotonic - scope._clock())
            if not math.isfinite(remaining) or remaining <= 0:
                raise LocalSelectedStoryError('cancelled')
        except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
            raise LocalSelectedStoryError('invalid_input') from None
        call = _Call(scope)
        self._active = call  # No await between the admission check and ownership.
        try:
            # Total timeout also bounds an awaited header/read, not just chunks.
            async with asyncio.timeout(remaining):
                self._check(scope)
                async with httpx.AsyncClient(timeout=remaining, trust_env=False,
                        follow_redirects=False, transport=self.transport) as client:
                    self._check(scope)
                    # Mark conservatively before dispatch: a failed send may have
                    # reached the model. Only a native owner may resolve that.
                    call.dispatched = True
                    async with client.stream('POST', self.url, content=payload, headers={
                            'Content-Type': 'application/json', 'Accept': 'application/json',
                            'Accept-Encoding': 'identity',
                            'X-PhotoHouse-Operation-ID': scope.operation_id,
                    }) as response:
                        self._check(scope)
                        content_type = response.headers.get('content-type', '').split(';')[0].strip().lower()
                        encoding = response.headers.get('content-encoding', '').strip().lower()
                        length = response.headers.get('content-length')
                        if (response.status_code != 200 or content_type != 'application/json'
                                or encoding not in {'', 'identity'}
                                or (length is not None and (not length.isascii()
                                    or not length.isdecimal() or len(length) > 10
                                    or int(length) > MAX_PROVIDER_BYTES))):
                            raise LocalSelectedStoryError('invalid_response')
                        body = bytearray()
                        async for chunk in response.aiter_raw():
                            self._check(scope)
                            if len(body) + len(chunk) > MAX_PROVIDER_BYTES:
                                raise LocalSelectedStoryError('invalid_response')
                            body.extend(chunk)
                        if length is not None and int(length) != len(body):
                            raise LocalSelectedStoryError('invalid_response')
                self._check(scope)
                envelope = _strict_loads(bytes(body))
                if (type(envelope) is not dict or envelope.get('model') != self.model
                        or envelope.get('done') is not True or 'error' in envelope
                        or envelope.get('done_reason', 'stop') != 'stop'
                        or type(envelope.get('response')) is not str
                        or len(envelope['response'].encode('utf-8', errors='strict')) > MAX_OUTPUT_BYTES):
                    raise LocalSelectedStoryError('invalid_response')
                result = validate_narrative(_strict_loads(envelope['response'].encode('utf-8')), clean)
                self._check(scope)
                return result
        except LocalSelectedStoryError:
            raise
        except (TimeoutError, httpx.HTTPError):
            raise LocalSelectedStoryError('transport') from None
        except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
            raise LocalSelectedStoryError('invalid_response') from None
        except Exception:
            raise LocalSelectedStoryError('transport') from None
        finally:
            # This event certifies only that our async HTTP work has unwound.
            # Keep the record until native reconciliation, without storing prose.
            call.settled.set()

    async def _reconcile(self, call):
        await call.settled.wait()
        proof = not call.dispatched
        if call.dispatched:
            try:
                proof = await self.native_owner.stop_and_reconcile(call.scope) is True
            except Exception:
                proof = False
        if proof and self._active is call:
            self._active = None
            self._last_settled_scope = call.scope  # One bounded idempotency record.
        return proof

    async def stop_and_reconcile(self, scope):
        self._bind()
        if type(scope) is not PreparationScope:
            return False
        call = self._active
        if call is None or self._last_settled_scope is scope:
            # Includes a prepare task cancelled before its first Python step.
            return True
        if call.scope is not scope:
            return False
        if (call.cleanup is None or call.cleanup.cancelled() or
                (call.cleanup.done() and (call.cleanup.exception() is not None
                                         or call.cleanup.result() is not True))):
            call.cleanup = asyncio.create_task(self._reconcile(call))
        # The retained record owns cleanup even when an awaiting caller leaves.
        return await asyncio.shield(call.cleanup)
