"""Synthetic integration tests for local selected-story admission and cleanup."""

import asyncio
import json
import sys
from pathlib import Path
import unittest

import httpx

ROOT = Path(__file__).resolve().parents[2]
SECURITY_TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'backend/app'))
sys.path.insert(0, str(SECURITY_TESTS))

from access.inference_admission import InferenceAdmission
from access.selected_story_local import LocalSelectedStoryProvider
from access.selected_story_operations import DraftOperationError, DraftOperations
from test_selected_story_operations import (
    LIBRARY, REQUEST_ID, TOKEN_A, TOKEN_B, ChangingSources, SyntheticSources, request,
)


MODEL = 'qwen-local'


def narrative():
    return {'version': 1, 'title': 'Beans together',
            'chapters': [{'id': 'chapter-1', 'narration': 'We planted beans together.',
                          'source_ids': ['family-synthetic-note-4']}],
            'questions': [], 'needs_review': True}


def provider_envelope():
    return json.dumps({'model': MODEL, 'done': True,
                       'response': json.dumps(narrative())}).encode()


class ResponseStream(httpx.AsyncByteStream):
    def __init__(self, *, hold=False):
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.closed = asyncio.Event()
        if not hold:
            self.release.set()

    async def __aiter__(self):
        self.started.set()
        await self.release.wait()
        yield provider_envelope()

    async def aclose(self):
        self.closed.set()


class NativeOwner:
    def __init__(self, *, proof=True, hold=False):
        self.proof = proof
        self.calls = []
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        if not hold:
            self.release.set()

    async def stop_and_reconcile(self, scope):
        self.calls.append(scope)
        self.started.set()
        await self.release.wait()
        return self.proof


class TwoAccountSources(SyntheticSources):
    def __init__(self):
        super().__init__()
        self.accounts[TOKEN_B] = 'account-b'


class LocalSelectedStoryLifecycleTests(unittest.IsolatedAsyncioTestCase):
    def make_service(self, *, sources=None, owner=None, stream=None, cleanup_seconds=1):
        sources = sources or SyntheticSources()
        owner = owner or NativeOwner()
        stream = stream or ResponseStream()
        requests = []

        async def handler(http_request):
            requests.append(http_request)
            response_stream = stream() if callable(stream) else stream
            return httpx.Response(200, stream=response_stream,
                                  headers={'content-type': 'application/json'})

        provider = LocalSelectedStoryProvider(
            'http://127.0.0.1:11434', MODEL, enabled=True, native_owner=owner,
            transport=httpx.MockTransport(handler))
        admission = InferenceAdmission(max_waiting=0, wait_seconds=1)
        service = DraftOperations(sources, provider, admission,
                                  cleanup_seconds=cleanup_seconds)
        self.addAsyncCleanup(service.close)
        return service, sources, provider, admission, owner, stream, requests

    async def expect_reason(self, reason, awaitable):
        with self.assertRaises(DraftOperationError) as caught:
            await awaitable
        self.assertEqual(reason, caught.exception.reason)

    async def test_native_false_quarantines_then_late_proof_settles_without_publishing(self):
        owner = NativeOwner(proof=False)
        service, _, provider, admission, _, _, requests = self.make_service(owner=owner)
        await self.expect_reason('unavailable', service.prepare(TOKEN_A, LIBRARY, request()))
        self.assertEqual(1, len(requests))
        self.assertEqual(1, len(owner.calls))
        self.assertTrue(admission.state().quarantined)
        self.assertEqual(1, admission.state().active)
        self.assertEqual('reconciling', service._records[
            ('account-a', LIBRARY, REQUEST_ID)].state)
        self.assertIsNotNone(provider._active)

        owner.proof = True
        self.assertTrue(await service.reconcile())
        operation = service._records[('account-a', LIBRARY, REQUEST_ID)]
        self.assertIsNone(operation.payload)
        self.assertIsNone(operation.snapshot)
        self.assertIsNone(provider._active)
        self.assertEqual(0, admission.state().active)
        self.assertTrue(admission.state().quarantined)
        self.assertEqual(2, len(owner.calls))

    async def test_cancelled_http_work_waits_for_native_proof_and_never_returns_draft(self):
        owner = NativeOwner(hold=True)
        stream = ResponseStream(hold=True)
        service, _, provider, admission, _, _, requests = self.make_service(
            owner=owner, stream=stream, cleanup_seconds=0.03)
        pending = asyncio.create_task(service.prepare(TOKEN_A, LIBRARY, request()))
        await asyncio.wait_for(stream.started.wait(), 1)
        self.assertEqual(1, len(requests))
        self.assertTrue(await service.cancel(TOKEN_A, LIBRARY, REQUEST_ID))
        await asyncio.wait_for(owner.started.wait(), 1)
        await self.expect_reason('cancelled', pending)
        self.assertTrue(stream.closed.is_set())

        async def quarantined():
            while not admission.state().quarantined:
                await asyncio.sleep(0)

        await asyncio.wait_for(quarantined(), 1)
        self.assertTrue(admission.state().quarantined)
        self.assertEqual(1, admission.state().active)
        operation = service._records[('account-a', LIBRARY, REQUEST_ID)]
        self.assertIsNone(operation.payload)
        self.assertIsNotNone(provider._active)

        owner.proof = True
        owner.release.set()
        await asyncio.wait_for(asyncio.shield(operation.settlement), 1)

        async def released():
            while operation.permit is not None:
                await asyncio.sleep(0)

        await asyncio.wait_for(released(), 1)
        self.assertEqual(0, admission.state().active)
        self.assertTrue(admission.state().quarantined)
        self.assertIsNone(operation.payload)
        self.assertIsNone(provider._active)

    async def test_distinct_accounts_fail_fast_without_hidden_queue_then_run_explicitly(self):
        owner = NativeOwner()
        first_stream = ResponseStream(hold=True)
        response_streams = iter((first_stream, ResponseStream()))

        def stream_factory():
            return next(response_streams)

        service, _, _, admission, _, _, requests = self.make_service(
            sources=TwoAccountSources(), owner=owner, stream=stream_factory)
        first = asyncio.create_task(service.prepare(TOKEN_A, LIBRARY, request()))
        await asyncio.wait_for(first_stream.started.wait(), 1)
        second_request = request('33333333-3333-4333-8333-333333333333')
        await self.expect_reason('busy', service.prepare(TOKEN_B, LIBRARY, second_request))
        self.assertEqual(1, len(requests))
        self.assertEqual(0, admission.state().waiting)
        self.assertEqual(1, admission.state().active)

        first_stream.release.set()
        first_result = await asyncio.wait_for(first, 1)
        self.assertEqual('needs_review', first_result['state'])
        self.assertEqual(0, admission.state().active)
        self.assertEqual(1, len(requests))

        second_result = await service.prepare(TOKEN_B, LIBRARY, second_request)
        self.assertEqual('needs_review', second_result['state'])
        self.assertEqual(2, len(requests))
        self.assertEqual(2, len(owner.calls))
        self.assertEqual(0, admission.state().active)

    async def test_source_change_after_successful_http_blocks_result_delivery(self):
        sources = ChangingSources()
        owner = NativeOwner()
        stream = ResponseStream(hold=True)
        service, _, provider, admission, _, _, requests = self.make_service(
            sources=sources, owner=owner, stream=stream)
        pending = asyncio.create_task(service.prepare(TOKEN_A, LIBRARY, request()))
        await asyncio.wait_for(stream.started.wait(), 1)
        self.assertEqual(1, len(requests))
        sources.changed = True
        stream.release.set()
        await self.expect_reason('conflict', pending)
        self.assertEqual(1, len(owner.calls))
        operation = service._records[('account-a', LIBRARY, REQUEST_ID)]
        self.assertIsNone(operation.payload)
        self.assertIsNone(operation.snapshot)
        self.assertIsNone(provider._active)
        self.assertEqual(0, admission.state().active)
        self.assertFalse(admission.state().quarantined)


if __name__ == '__main__':
    unittest.main()
