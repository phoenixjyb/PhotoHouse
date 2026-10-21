"""Generated-store ASGI-to-real-synthetic-child integration (containment is simulated)."""
import asyncio
from contextlib import closing
import hashlib
import httpx
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_library_reads as library_fixture
from app.access.host_inference_admission import (
    HostCapacity, HostInferenceAdmission, HostResourceProfile, initialize_host_admission,
)
from app.access.runtime import RuntimeConfiguration
from app.access.service import AccessService
from app.access.selected_story_native import NativeStoryLaunch
from app.access.selected_story_process import ProcessSelectedStoryProvider, process_launch_digest
from test_selected_story_process_lifecycle import WORKER, WorkerKernel, worker_environment


ORIGIN = 'https://photohouse.test'
LIBRARY = 'family-a'
CLEARANCE = '33333333-3333-4333-8333-333333333333'
REQUEST_ID = '22222222-2222-4222-8222-222222222222'
OTHER_REQUEST_ID = '44444444-4444-4444-8444-444444444444'
GiB = 1024 ** 3


class SelectedStoryRuntimeProcessIntegrationTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        library_fixture.LibraryReadTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        library_fixture.LibraryReadTests.tearDownClass()

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='photohouse-runtime-process-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.database = self.root / 'generated-family.sqlite'
        with closing(sqlite3.connect(self.database)) as target:
            library_fixture.LibraryReadTests.template.backup(target)
        with closing(sqlite3.connect(self.database)) as db:
            db.execute('PRAGMA foreign_keys=ON')
            self.second_owner_token = AccessService(db,
                clock=lambda: library_fixture.NOW).login(
                    library_fixture.OWNER, library_fixture.PASSWORD)
        self.originals = self.root / 'originals'
        self.derived = self.root / 'derived'
        self.originals.mkdir()
        self.derived.mkdir()
        self.exchange_root = self.root / 'story-exchange'
        self.exchange_root.mkdir(mode=0o700)
        if os.name == 'posix':
            os.chmod(self.exchange_root, 0o700)

        self.host_root = self.root / 'host-claim'
        self.host_root.mkdir(mode=0o700)
        if os.name == 'posix':
            os.chmod(self.host_root, 0o700)
        self.executable = Path(getattr(sys, '_base_executable', sys.executable)).resolve()
        self.launch = NativeStoryLaunch(
            str(self.executable),
            hashlib.sha256(self.executable.read_bytes()).hexdigest(),
            (str(self.executable), '-I', '-B', '-c', 'exec(' + repr(WORKER) + ')', '0', '0'),
            str(self.root), worker_environment(), minimum_free_ram=0)
        self.profile = HostResourceProfile(
            'cpu', process_launch_digest(self.launch, exchange_root=self.exchange_root),
            8 * GiB, GiB)
        initialize_host_admission(self.host_root, enabled=True)

        def capacity():
            return HostCapacity('cpu', CLEARANCE, time.monotonic(), 16 * GiB, 4 * GiB, False)

        self.host = HostInferenceAdmission(self.host_root, self.profile,
            capacity_probe=capacity, enabled=True)
        self.host.set_maintenance(False, clearance_id=CLEARANCE)
        # The fake Job tracks only explicitly returned root children. Use a
        # resolved base interpreter and no untracked helper descendants.
        self.kernel = WorkerKernel(helpers=0)
        self.addCleanup(self.kernel.finish)
        self.provider = ProcessSelectedStoryProvider(
            self.launch, 'synthetic-local', kernel_factory=lambda: self.kernel, enabled=True,
            cleanup_seconds=2, host_admission=self.host, exchange_root=self.exchange_root)
        self.configuration = RuntimeConfiguration(
            self.database, ORIGIN, (self.originals,), self.derived,
            selected_story_provider=self.provider, selected_story_drafts_enabled=True,
            selected_story_ui_enabled=True, memory_collaboration_enabled=True)
        self.app = self.configuration.build_app()

    async def client(self):
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url=ORIGIN)

    async def prepare_request(self, client, request_id=REQUEST_ID, token=None):
        token = token or library_fixture.LibraryReadTests.owner_token
        headers = {'Authorization': 'Bearer ' + token}
        preview = await client.post('/story-workspace/preview?library=' + LIBRARY,
            headers=headers, json={'asset_ids': '101', 'theme': 'everyday',
                                   'language': 'en', 'title': 'Synthetic family day'})
        if preview.status_code != 200:
            return preview, None
        evidence = preview.json()['items'][0]['evidence']
        self.assertTrue(evidence)
        source_id = evidence[0]['id']
        body = {
            'version': 1, 'request_id': request_id,
            'target': {'story_id': None, 'base_revision': '0'},
            'selection': {
                'asset_ids': ['101'],
                'selection_revision': preview.json()['selection_revision'],
                'source_policy': 'chapter_sources_v1',
                'chapters': [{'id': 'chapter-1', 'title': 'Family day',
                              'asset_ids': ['101'], 'evidence_ids': [source_id]}],
            },
            'theme': 'everyday', 'language': 'en', 'title': 'Synthetic family day',
            'author_direction': 'Keep the synthetic draft brief.',
        }
        response = await client.post('/story-workspace/drafts/prepare?library=' + LIBRARY,
                                     headers=headers, json=body)
        return response, body

    async def cancel(self, client, request_id=REQUEST_ID, token=None):
        token = token or library_fixture.LibraryReadTests.owner_token
        return await client.post('/story-workspace/drafts/cancel?library=' + LIBRARY,
            headers={'Authorization': 'Bearer ' + token},
            json={'version': 1, 'request_id': request_id})

    def claim_count(self):
        with closing(sqlite3.connect(self.host.path)) as db:
            return db.execute('SELECT count(*) FROM claim').fetchone()[0]

    def saved_story_count(self):
        with closing(sqlite3.connect(self.database)) as db:
            return db.execute('SELECT count(*) FROM access_stories').fetchone()[0]

    def bind_worker(self, launch):
        self.profile = HostResourceProfile(
            'cpu', process_launch_digest(launch, exchange_root=self.exchange_root),
            8 * GiB, GiB)
        self.host = HostInferenceAdmission(self.host_root, self.profile,
            capacity_probe=lambda: HostCapacity('cpu', CLEARANCE, time.monotonic(),
                                                16 * GiB, 4 * GiB, False), enabled=True)
        self.host.set_maintenance(False, clearance_id=CLEARANCE)
        self.provider = ProcessSelectedStoryProvider(
            launch, 'synthetic-local', kernel_factory=lambda: self.kernel, enabled=True,
            cleanup_seconds=2, host_admission=self.host, exchange_root=self.exchange_root)
        self.configuration = RuntimeConfiguration(
            self.database, ORIGIN, (self.originals,), self.derived,
            selected_story_provider=self.provider, selected_story_drafts_enabled=True,
            selected_story_ui_enabled=True, memory_collaboration_enabled=True)
        self.app = self.configuration.build_app()

    async def test_protected_prepare_exact_retry_uses_one_child_and_never_saves_story(self):
        before = self.saved_story_count()
        with patch('app.access.memory_jobs.maintenance', return_value=None):
            async with self.app.router.lifespan_context(self.app):
                async with await self.client() as client:
                    first, body = await self.prepare_request(client)
                    self.assertEqual(first.status_code, 200, first.text)
                    self.assertEqual(first.json()['state'], 'needs_review')
                    self.assertTrue(self.kernel.resumed.is_set())
                    retry = await client.post('/story-workspace/drafts/prepare?library=' + LIBRARY,
                        headers={'Authorization': 'Bearer ' + library_fixture.LibraryReadTests.owner_token},
                        json=body)
                    self.assertEqual(retry.status_code, 200, retry.text)
                    self.assertEqual(first.json(), retry.json())
        self.assertEqual(len(self.kernel.exchanges), 1)
        self.assertTrue(all(child.poll() is not None for child in self.kernel.children))
        self.assertTrue(all(not directory.exists() for directory in self.kernel.exchanges))
        self.assertEqual(self.claim_count(), 0)
        self.assertEqual(self.saved_story_count(), before)

    async def test_cancel_after_resumed_child_fences_result_and_reconciles_private_exchange(self):
        before = self.saved_story_count()
        slow_launch = NativeStoryLaunch(
            self.launch.executable, self.launch.executable_sha256,
            self.launch.argv[:-2] + ('120', '0'), self.launch.cwd,
            dict(self.launch.environment), minimum_free_ram=0)
        # Bind the host store to the same explicit launch and exchange root.
        self.bind_worker(slow_launch)

        with patch('app.access.memory_jobs.maintenance', return_value=None):
            async with self.app.router.lifespan_context(self.app):
                async with await self.client() as client:
                    pending = asyncio.create_task(self.prepare_request(client))
                    self.assertTrue(await asyncio.to_thread(self.kernel.resumed.wait, 5))
                    self.assertEqual(self.claim_count(), 1)
                    busy, _ = await self.prepare_request(client, OTHER_REQUEST_ID)
                    self.assertEqual(busy.status_code, 429)
                    cancelled = await self.cancel(client)
                    self.assertEqual(cancelled.status_code, 200, cancelled.text)
                    self.assertTrue(cancelled.json()['matched'])
                    response, _ = await asyncio.wait_for(pending, 5)
                    self.assertEqual(response.status_code, 409)
                    self.assertEqual(response.json()['code'], 'draft_cancelled')
        self.assertTrue(all(child.poll() is not None for child in self.kernel.children))
        self.assertTrue(all(not directory.exists() for directory in self.kernel.exchanges))
        self.assertEqual(self.claim_count(), 0)
        self.assertEqual(self.saved_story_count(), before)

    async def test_foreign_session_cannot_cancel_owner_child_then_owner_logout_reaps_it(self):
        slow_launch = NativeStoryLaunch(
            self.launch.executable, self.launch.executable_sha256,
            self.launch.argv[:-2] + ('120', '0'), self.launch.cwd,
            dict(self.launch.environment), minimum_free_ram=0)
        self.bind_worker(slow_launch)
        with patch('app.access.memory_jobs.maintenance', return_value=None):
            async with self.app.router.lifespan_context(self.app):
                async with await self.client() as client:
                    pending = asyncio.create_task(self.prepare_request(client))
                    self.assertTrue(await asyncio.to_thread(self.kernel.resumed.wait, 5))
                    foreign = await self.cancel(client,
                        token=self.second_owner_token)
                    self.assertEqual(foreign.status_code, 409, foreign.text)
                    self.assertEqual(foreign.json()['code'], 'draft_scope_changed')
                    self.assertTrue(any(child.poll() is None for child in self.kernel.children))
                    self.assertEqual(self.claim_count(), 1)
                    logout = await client.post('/auth/logout', headers={
                        'Authorization': 'Bearer ' + library_fixture.LibraryReadTests.owner_token})
                    self.assertEqual(logout.status_code, 200, logout.text)
                    response, body = await asyncio.wait_for(pending, 5)
                    # The logout barrier fences before the revocation commit.
                    # An in-flight delivery can observe either fixed refusal;
                    # after logout completes, the same request must fail auth.
                    self.assertIn((response.status_code, response.json()['code']), {
                        (401, 'draft_access_denied'), (409, 'draft_scope_changed')})
                    self.assertEqual(set(response.json()), {'detail', 'code'})
                    retry = await client.post('/story-workspace/drafts/prepare?library=' + LIBRARY,
                        headers={'Authorization': 'Bearer ' + library_fixture.LibraryReadTests.owner_token},
                        json=body)
                    self.assertEqual(retry.status_code, 401, retry.text)
                    self.assertEqual(retry.json()['code'], 'draft_access_denied')
        self.assertTrue(all(child.poll() is not None for child in self.kernel.children))
        self.assertTrue(all(not directory.exists() for directory in self.kernel.exchanges))
        self.assertEqual(self.claim_count(), 0)


if __name__ == '__main__':
    unittest.main()
