"""Synthetic lifecycle checks for selected-source draft operations."""

import asyncio
import hashlib
import json
import sys
from pathlib import Path
import threading
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend/app'))

from access.credentials import session_digest
from access.inference_admission import AdmissionIdentity, InferenceAdmission
from access.selected_story_operations import (
    DraftOperationError, DraftOperations, DraftPrincipal, SelectedStorySources,
)
from access.selected_story_snapshot import SourceSnapshot
from access.transport import TransportError


LIBRARY = 'synthetic-library'
TOKEN_A = 'A' * 43
TOKEN_B = 'B' * 43
REQUEST_ID = '22222222-2222-4222-8222-222222222222'
SELECTION_REVISION = 'a' * 64


def request(request_id=REQUEST_ID, *, direction='Keep it brief.'):
    return {
        'version': 1,
        'request_id': request_id,
        'target': {'story_id': None, 'base_revision': '0'},
        'selection': {
            'asset_ids': ['17000017'],
            'selection_revision': SELECTION_REVISION,
            'source_policy': 'chapter_sources_v1',
            'chapters': [{
                'id': 'chapter-1', 'title': 'Preparing the bed',
                'asset_ids': ['17000017'], 'evidence_ids': ['family-synthetic-note-4'],
            }],
        },
        'theme': 'everyday', 'language': 'en', 'title': 'A garden day',
        'author_direction': direction,
    }


class SyntheticSources(SelectedStorySources):
    def __init__(self):
        self.accounts = {TOKEN_A: 'account-a', TOKEN_B: 'account-a'}
        self.resolve_calls = 0
        self.revalidate_calls = 0
        self.changed = False

    def authenticate(self, token, library):
        account = self.accounts.get(token)
        if account is None or library != LIBRARY:
            raise PermissionError('denied')
        return DraftPrincipal(account, session_digest(token))

    def resolve(self, token, library, req):
        self.resolve_calls += 1
        account = self.accounts[token]
        canonical = json.dumps([account, library, req], sort_keys=True,
                               ensure_ascii=False, separators=(',', ':')).encode()
        digest = hashlib.sha256(canonical).hexdigest()
        source = {
            'source_id': 'family-synthetic-note-4', 'source_kind': 'family_note',
            'origin_asset_id': '17000017', 'source_revision': 3,
            'source_digest': 'b' * 64, 'byline': 'Synthetic Aunt',
            'text': 'We planted beans together.',
        }
        document = {
            'version': 1, 'request_id': req['request_id'], 'library_id': library,
            'target': req['target'], 'selection_revision': SELECTION_REVISION,
            'source_policy': 'chapter_sources_v1',
            'media': [{'asset_id': '17000017', 'kind': 'image',
                       'recorded_at': '2024-05-12', 'stack_id': None}],
            'chapters': [{'id': 'chapter-1', 'title': 'Preparing the bed',
                          'asset_ids': ['17000017'],
                          'sources': [source | {'selected_asset_ids': ['17000017']}]}],
        }
        operation_id = str(uuid.uuid4())
        bundle = {
            'version': 3, 'library_id': library,
            'target': {'type': 'draft', 'id': operation_id, 'revision': 0},
            'selection_revision': SELECTION_REVISION, 'language': req['language'],
            'theme': req['theme'], 'title': req['title'],
            'instructions': req['author_direction'],
            'chapters': [{'id': 'chapter-1', 'title': 'Preparing the bed',
                          'asset_ids': ['17000017'], 'evidence_ids': [source['source_id']],
                          'narration': ''}],
            'sources': [{'id': source['source_id'], 'source_kind': 'family_note',
                         'kind': 'family', 'text': source['text'],
                         'asset_id': source['origin_asset_id'], 'author': source['byline']}],
            'recent_turns': [],
        }
        return SourceSnapshot(
            account, library, digest, operation_id,
            json.dumps(req, sort_keys=True, ensure_ascii=False,
                       separators=(',', ':')).encode(),
            json.dumps(document, sort_keys=True, ensure_ascii=False,
                       separators=(',', ':')).encode(),
            json.dumps(bundle, sort_keys=True, ensure_ascii=False,
                       separators=(',', ':')).encode(),
            b'{"authorized":"synthetic"}',
        )

    def revalidate(self, token, snapshot):
        self.revalidate_calls += 1
        if token not in self.accounts or self.changed:
            raise TransportError(409, 'Story references changed')


class BlockingSources(SyntheticSources):
    def __init__(self):
        super().__init__()
        self.resolve_started = threading.Event()
        self.release_resolve = threading.Event()

    def resolve(self, token, library, req):
        self.resolve_started.set()
        if not self.release_resolve.wait(5):
            raise RuntimeError('synthetic source wait timed out')
        return super().resolve(token, library, req)


class BlockingAuthSources(SyntheticSources):
    def __init__(self):
        super().__init__()
        self.lock = threading.Lock()
        self.started_count = self.finished_count = 0
        self.auth_started = threading.Event()
        self.all_finished = threading.Event()
        self.release_auth = threading.Event()

    def authenticate(self, token, library):
        with self.lock:
            self.started_count += 1
            self.auth_started.set()
        if not self.release_auth.wait(5):
            raise RuntimeError('synthetic authentication wait timed out')
        result = super().authenticate(token, library)
        with self.lock:
            self.finished_count += 1
            if self.finished_count == 16:
                self.all_finished.set()
        return result


class ChangingSources(SyntheticSources):
    def __init__(self):
        super().__init__()
        self.revision = 3

    def resolve(self, token, library, req):
        snapshot = super().resolve(token, library, req)
        document = snapshot.document()
        document['chapters'][0]['sources'][0]['source_revision'] = self.revision
        return SourceSnapshot(
            snapshot.account_id, snapshot.library_id, snapshot.request_digest,
            snapshot.operation_id, snapshot._request_bytes,
            json.dumps(document, sort_keys=True, ensure_ascii=False,
                       separators=(',', ':')).encode(), snapshot._bundle_bytes,
            snapshot._authorization_bytes,
        )


class SyntheticProvider:
    def __init__(self, *, hold=False, cleanup=True, cleanup_results=None, fail=False):
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        if not hold:
            self.release.set()
        self.cleanup = cleanup
        self.cleanup_results = list(cleanup_results or [])
        self.fail = fail
        self.prepare_calls = 0
        self.cleanup_calls = 0

    async def prepare(self, bundle, scope):
        self.prepare_calls += 1
        self.started.set()
        await self.release.wait()
        if self.fail:
            raise RuntimeError('synthetic provider failure')
        return {
            'version': 1, 'title': 'Beans together',
            'chapters': [{'id': 'chapter-1', 'narration': 'We planted beans together.',
                          'source_ids': ['family-synthetic-note-4']}],
            'questions': [], 'needs_review': True,
        }

    async def stop_and_reconcile(self, scope):
        self.cleanup_calls += 1
        if self.cleanup_results:
            return self.cleanup_results.pop(0)
        return self.cleanup


class BlockingCleanupProvider(SyntheticProvider):
    def __init__(self):
        super().__init__()
        self.cleanup_started = asyncio.Event()
        self.release_cleanup = asyncio.Event()
        self.cleanup_finished = asyncio.Event()

    async def stop_and_reconcile(self, scope):
        self.cleanup_calls += 1
        self.cleanup_started.set()
        await self.release_cleanup.wait()
        self.cleanup_finished.set()
        return True


class SelectedStoryOperationTests(unittest.IsolatedAsyncioTestCase):
    def make_service(self, *, provider=None, sources=None, **limits):
        sources = sources or SyntheticSources()
        provider = provider or SyntheticProvider()
        admission = InferenceAdmission(max_waiting=0, wait_seconds=1)
        service = DraftOperations(sources, provider, admission, **limits)
        self.addAsyncCleanup(service.close)
        return service, sources, provider, admission

    async def reason(self, reason, awaitable):
        with self.assertRaises(DraftOperationError) as caught:
            await awaitable
        self.assertEqual(caught.exception.reason, reason)

    async def test_result_is_review_only_and_returns_server_bound_source(self):
        service, sources, provider, _ = self.make_service()
        result = await service.prepare(TOKEN_A, LIBRARY, request())
        self.assertEqual(result['state'], 'needs_review')
        self.assertEqual(result['chapters'][0]['title'], 'Preparing the bed')
        self.assertEqual(result['chapters'][0]['citations'][0]['source_revision'], 3)
        self.assertEqual(result['chapters'][0]['citations'][0]['byline'], 'Synthetic Aunt')
        self.assertEqual(provider.cleanup_calls, 1)
        # The operation checks current inputs before result assembly, and the
        # retained-result path checks them again before each delivery.
        self.assertEqual(sources.revalidate_calls, 2)
        result['chapters'][0]['narration'] = 'caller mutation'
        retained = await service.prepare(TOKEN_A, LIBRARY, request())
        self.assertNotEqual(retained['chapters'][0]['narration'], 'caller mutation')
        self.assertEqual(provider.prepare_calls, 1)

    async def test_identical_active_requests_share_one_provider_generation(self):
        provider = SyntheticProvider(hold=True)
        service, _, _, _ = self.make_service(provider=provider)
        first = asyncio.create_task(service.prepare(TOKEN_A, LIBRARY, request()))
        await asyncio.wait_for(provider.started.wait(), 5)
        second = asyncio.create_task(service.prepare(TOKEN_A, LIBRARY, request()))
        provider.release.set()
        one, two = await asyncio.gather(first, second)
        self.assertEqual(one, two)
        self.assertEqual(provider.prepare_calls, 1)

    async def test_changed_request_body_conflicts_while_id_is_active(self):
        provider = SyntheticProvider(hold=True)
        service, _, _, _ = self.make_service(provider=provider)
        first = asyncio.create_task(service.prepare(TOKEN_A, LIBRARY, request()))
        await asyncio.wait_for(provider.started.wait(), 5)
        await self.reason('conflict', service.prepare(
            TOKEN_A, LIBRARY, request(direction='Use a different style.')))
        provider.release.set()
        await first

    async def test_new_session_for_same_account_cannot_join_or_read_operation(self):
        provider = SyntheticProvider(hold=True)
        service, _, _, _ = self.make_service(provider=provider)
        first = asyncio.create_task(service.prepare(TOKEN_A, LIBRARY, request()))
        await asyncio.wait_for(provider.started.wait(), 5)
        await self.reason('scope_changed', service.prepare(TOKEN_B, LIBRARY, request()))
        provider.release.set()
        await first

    async def test_invalid_request_is_rejected_without_source_resolution(self):
        service, sources, provider, _ = self.make_service()
        malformed = request() | {'unexpected': True}
        await self.reason('invalid_request', service.prepare(TOKEN_A, LIBRARY, malformed))
        self.assertEqual(sources.resolve_calls, 0)
        self.assertEqual(provider.prepare_calls, 0)

    async def test_current_scope_is_revalidated_before_returning_output(self):
        service, sources, provider, _ = self.make_service()
        sources.changed = True
        await self.reason('conflict', service.prepare(TOKEN_A, LIBRARY, request()))
        self.assertEqual(provider.cleanup_calls, 1)

    async def test_cancel_stops_generation_and_fences_late_output(self):
        provider = SyntheticProvider(hold=True)
        service, _, _, _ = self.make_service(provider=provider)
        pending = asyncio.create_task(service.prepare(TOKEN_A, LIBRARY, request()))
        await asyncio.wait_for(provider.started.wait(), 5)
        cancelled = await service.cancel(TOKEN_A, LIBRARY, REQUEST_ID)
        self.assertTrue(cancelled)
        await self.reason('cancelled', pending)
        provider.release.set()
        self.assertEqual(provider.cleanup_calls, 1)

    async def test_cancelled_awaiter_detaches_without_releasing_provider_lane(self):
        provider = SyntheticProvider(hold=True)
        service, _, _, admission = self.make_service(provider=provider)
        pending = asyncio.create_task(service.prepare(TOKEN_A, LIBRARY, request()))
        await asyncio.wait_for(provider.started.wait(), 5)
        pending.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await pending
        provider.release.set()
        await asyncio.wait_for(service.prepare(TOKEN_A, LIBRARY, request()), 1)
        self.assertEqual(provider.prepare_calls, 1)
        self.assertEqual(admission.state().active, 0)

    async def test_cancelled_awaiter_keeps_blocked_source_thread_owned(self):
        sources = BlockingSources()
        provider = SyntheticProvider()
        service, _, _, admission = self.make_service(provider=provider, sources=sources)
        first = asyncio.create_task(service.prepare(TOKEN_A, LIBRARY, request()))
        await asyncio.wait_for(asyncio.to_thread(sources.resolve_started.wait), 5)
        first.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await first
        joined = asyncio.create_task(service.prepare(TOKEN_A, LIBRARY, request()))
        sources.release_resolve.set()
        await asyncio.wait_for(joined, 5)
        self.assertEqual(sources.resolve_calls, 1)
        self.assertEqual(provider.prepare_calls, 1)
        self.assertEqual(admission.state().active, 0)

    async def test_unconfirmed_cleanup_quarantines_shared_admission(self):
        provider = SyntheticProvider(cleanup=False)
        service, _, _, admission = self.make_service(provider=provider)
        await self.reason('unavailable', service.prepare(TOKEN_A, LIBRARY, request()))
        self.assertTrue(admission.state().quarantined)

    async def test_reconcile_retries_cleanup_without_clearing_shared_quarantine(self):
        provider = SyntheticProvider(cleanup_results=[False, True])
        service, _, _, admission = self.make_service(provider=provider)
        await self.reason('unavailable', service.prepare(TOKEN_A, LIBRARY, request()))
        self.assertTrue(await service.reconcile())
        self.assertEqual(provider.cleanup_calls, 2)
        self.assertTrue(admission.state().quarantined)

    async def test_provider_failure_is_terminal_for_the_request_id(self):
        provider = SyntheticProvider(fail=True)
        service, _, _, _ = self.make_service(provider=provider)
        await self.reason('unavailable', service.prepare(TOKEN_A, LIBRARY, request()))
        await self.reason('unavailable', service.prepare(TOKEN_A, LIBRARY, request()))
        self.assertEqual(provider.prepare_calls, 1)

    async def test_close_fences_new_work_and_drains_owned_provider_task(self):
        provider = SyntheticProvider(hold=True)
        service, _, _, _ = self.make_service(provider=provider)
        pending = asyncio.create_task(service.prepare(TOKEN_A, LIBRARY, request()))
        await asyncio.wait_for(provider.started.wait(), 5)
        closing = asyncio.create_task(service.close())
        await self.reason('closed', service.prepare(TOKEN_A, LIBRARY,
                                                    request('33333333-3333-4333-8333-333333333333')))
        provider.release.set()
        await closing
        await self.reason('closed', pending)

    async def test_expiry_restarts_with_a_new_draft_id_and_current_snapshot(self):
        now = [100.0]
        wall = [1_800_000_000.0]
        service, sources, provider, _ = self.make_service(
            result_seconds=1, monotonic=lambda: now[0], wall_clock=lambda: wall[0])
        first = await service.prepare(TOKEN_A, LIBRARY, request())
        now[0] += 2
        second = await service.prepare(TOKEN_A, LIBRARY, request())
        self.assertNotEqual(first['draft_id'], second['draft_id'])
        self.assertEqual(provider.prepare_calls, 2)
        self.assertEqual(sources.resolve_calls, 2)

    async def test_expired_request_id_still_conflicts_when_body_changes(self):
        now = [100.0]
        service, _, _, _ = self.make_service(result_seconds=1, identity_seconds=5,
                                              monotonic=lambda: now[0])
        await service.prepare(TOKEN_A, LIBRARY, request())
        now[0] += 2
        await self.reason('conflict', service.prepare(
            TOKEN_A, LIBRARY, request(direction='Changed after expiry.')))

    async def test_accepted_rerun_refreshes_identity_expiry(self):
        now = [100.0]
        service, provider_sources, provider, _ = self.make_service(
            result_seconds=1, identity_seconds=5, monotonic=lambda: now[0])
        first = await service.prepare(TOKEN_A, LIBRARY, request())
        now[0] = 104.8
        second = await service.prepare(TOKEN_A, LIBRARY, request())
        self.assertNotEqual(first['draft_id'], second['draft_id'])
        now[0] = 106.0
        await self.reason('conflict', service.prepare(
            TOKEN_A, LIBRARY, request(direction='Different at old identity deadline.')))
        self.assertEqual(provider.prepare_calls, 2)
        self.assertEqual(provider_sources.resolve_calls, 2)

    async def test_global_read_bound_keeps_cancelled_worker_ownership_until_close(self):
        sources = BlockingAuthSources()
        service, _, _, _ = self.make_service(sources=sources, cleanup_seconds=0.05)
        callers = [asyncio.create_task(service.prepare(TOKEN_A, LIBRARY, request()))
                   for _ in range(16)]
        try:
            await asyncio.wait_for(asyncio.to_thread(sources.auth_started.wait), 5)
            async def wait_for_read_bound():
                while len(service._reads) < 16:
                    await asyncio.sleep(0)
            await asyncio.wait_for(wait_for_read_bound(), 5)
            self.assertEqual(len(service._reads), 16)
            await self.reason('busy', service.prepare(
                TOKEN_A, LIBRARY, request('33333333-3333-4333-8333-333333333333')))
            for caller in callers:
                caller.cancel()
            await asyncio.gather(*callers, return_exceptions=True)
            self.assertEqual(len(service._reads), 16)
            self.assertFalse(await service.close())
        finally:
            for caller in callers:
                if not caller.done():
                    caller.cancel()
            sources.release_auth.set()
            await asyncio.gather(*callers, return_exceptions=True)
        await asyncio.wait_for(asyncio.to_thread(sources.all_finished.wait), 5)
        self.assertTrue(await asyncio.wait_for(service.close(), 5))

    async def test_session_invalidation_rejects_later_calls(self):
        service, _, _, _ = self.make_service()
        service.invalidate_session(TOKEN_A)
        await self.reason('scope_changed', service.prepare(TOKEN_A, LIBRARY, request()))

    async def test_busy_shared_lane_fails_fast(self):
        provider = SyntheticProvider(hold=True)
        service, _, _, admission = self.make_service(provider=provider)
        # Hold the real shared lane with a second service through the same admission.
        first = asyncio.create_task(service.prepare(TOKEN_A, LIBRARY, request()))
        await asyncio.wait_for(provider.started.wait(), 5)
        await self.reason('busy', service.prepare(
            TOKEN_B, LIBRARY, request('33333333-3333-4333-8333-333333333333')))
        provider.release.set()
        await first

    async def test_shared_admission_rejects_external_profile_then_allows_retry(self):
        service, _, provider, admission = self.make_service()
        identity = AdmissionIdentity('account-a', LIBRARY, 'external-operation',
                                     'saved_story_v1', 'c' * 64)
        permit = await admission.acquire(identity, wait=False)
        req = request('33333333-3333-4333-8333-333333333333')
        await self.reason('busy', service.prepare(TOKEN_A, LIBRARY, req))
        self.assertEqual(provider.prepare_calls, 0)
        permit.finish(reconciled=True)
        result = await service.prepare(TOKEN_A, LIBRARY, req)
        self.assertEqual(result['state'], 'needs_review')
        self.assertEqual(provider.prepare_calls, 1)

    async def test_result_expiry_does_not_slide_when_result_is_retrieved(self):
        now, wall = [100.0], [1_800_000_000.0]
        service, _, provider, _ = self.make_service(
            result_seconds=1, monotonic=lambda: now[0], wall_clock=lambda: wall[0])
        first = await service.prepare(TOKEN_A, LIBRARY, request())
        now[0] += 0.7
        retained = await service.prepare(TOKEN_A, LIBRARY, request())
        self.assertEqual(first['draft_id'], retained['draft_id'])
        self.assertEqual(first['expires_at'], retained['expires_at'])
        now[0] += 0.4
        rerun = await service.prepare(TOKEN_A, LIBRARY, request())
        self.assertNotEqual(first['draft_id'], rerun['draft_id'])
        self.assertEqual(provider.prepare_calls, 2)

    async def test_expired_rerun_refuses_changed_source_fingerprint_before_provider(self):
        now = [100.0]
        sources = ChangingSources()
        service, _, provider, _ = self.make_service(
            sources=sources, result_seconds=1, monotonic=lambda: now[0])
        await service.prepare(TOKEN_A, LIBRARY, request())
        sources.revision = 4
        now[0] += 2
        await self.reason('conflict', service.prepare(TOKEN_A, LIBRARY, request()))
        self.assertEqual(provider.prepare_calls, 1)

    async def test_registry_full_preserves_existing_result_and_fails_closed(self):
        service, _, provider, _ = self.make_service(max_records=1, max_retained=1)
        original = await service.prepare(TOKEN_A, LIBRARY, request())
        await self.reason('registry_full', service.prepare(
            TOKEN_A, LIBRARY, request('33333333-3333-4333-8333-333333333333')))
        recovered = await service.prepare(TOKEN_A, LIBRARY, request())
        self.assertEqual(original['draft_id'], recovered['draft_id'])
        self.assertEqual(provider.prepare_calls, 1)

    async def test_work_deadline_fences_late_provider_result(self):
        now = [100.0]
        provider = SyntheticProvider(hold=True)
        service, _, _, _ = self.make_service(provider=provider, work_seconds=1,
                                              monotonic=lambda: now[0])
        pending = asyncio.create_task(service.prepare(TOKEN_A, LIBRARY, request()))
        await asyncio.wait_for(provider.started.wait(), 5)
        now[0] += 2
        provider.release.set()
        await self.reason('timed_out', pending)
        self.assertEqual(provider.cleanup_calls, 1)

    async def test_cleanup_timeout_quarantines_then_late_proof_releases_active_slot(self):
        provider = BlockingCleanupProvider()
        service, _, _, admission = self.make_service(provider=provider, cleanup_seconds=0.05)
        await self.reason('unavailable', service.prepare(TOKEN_A, LIBRARY, request()))
        await asyncio.wait_for(provider.cleanup_started.wait(), 5)
        self.assertTrue(admission.state().quarantined)
        self.assertEqual(admission.state().active, 1)
        operation = service._records[('account-a', LIBRARY, REQUEST_ID)]
        late_settlement = next(task for task in tuple(service._tasks)
                               if task.get_coro().__name__ == '_late_settlement')
        provider.release_cleanup.set()
        await asyncio.wait_for(provider.cleanup_finished.wait(), 5)
        self.assertTrue(await asyncio.wait_for(asyncio.shield(operation.settlement), 5))
        await asyncio.wait_for(asyncio.shield(late_settlement), 5)
        self.assertFalse(operation.cleaning)
        self.assertIsNone(operation.permit)
        self.assertEqual(admission.state().active, 0)
        self.assertTrue(admission.state().quarantined)

    async def test_close_reports_unsettled_owned_source_thread(self):
        sources = BlockingSources()
        service, _, provider, admission = self.make_service(
            sources=sources, cleanup_seconds=0.05)
        pending = asyncio.create_task(service.prepare(TOKEN_A, LIBRARY, request()))
        await asyncio.wait_for(asyncio.to_thread(sources.resolve_started.wait), 5)
        self.assertFalse(await service.close())
        self.assertEqual(provider.prepare_calls, 0)
        self.assertEqual(admission.state().active, 1)
        sources.release_resolve.set()
        await asyncio.wait_for(asyncio.to_thread(sources.release_resolve.wait), 5)
        with self.assertRaises(DraftOperationError):
            await asyncio.wait_for(pending, 5)


if __name__ == '__main__':
    unittest.main()
