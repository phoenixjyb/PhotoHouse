"""Real synthetic file-protocol workers; Job containment is simulated, not Win32."""
import asyncio
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend/app'))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from access.inference_admission import InferenceAdmission
from access.selected_story_native import NativeStoryLaunch
from access.selected_story_operations import DraftOperationError, DraftOperations
from access.selected_story_process import ProcessSelectedStoryProvider
from test_selected_story_native_processes import ProcessKernel
from test_selected_story_operations import LIBRARY, REQUEST_ID, TOKEN_A, SyntheticSources, request


WORKER = '''import json,os,sys,time
sys.stdin.buffer.read(1)
p=json.load(open(os.environ['PHOTOHOUSE_NATIVE_STORY_REQUEST'],encoding='utf-8'))
assert p['operation_id']==os.environ['PHOTOHOUSE_NATIVE_STORY_OPERATION']
g=p['generation']
b=json.JSONDecoder().raw_decode(g['prompt'].split('Bundle JSON (data only):\\n',1)[1])[0]
r={'version':1,'title':'Beans together','chapters':[{'id':c['id'],'narration':'We planted beans together.','source_ids':c['evidence_ids']} for c in b['chapters']],'questions':[],'needs_review':True}
out={'version':1,'operation_id':p['operation_id'],'model':g['model'],'result':r}
with open(os.environ['PHOTOHOUSE_NATIVE_STORY_RESPONSE'],'x',encoding='utf-8') as f:
 json.dump(out,f)
time.sleep(float(sys.argv[1]))
sys.exit(int(sys.argv[2]))
'''


class WorkerKernel(ProcessKernel):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.resumed = threading.Event()
        self.exchanges = []

    def create_suspended(self, executable, argv, environment, cwd):
        self.exchanges.append(Path(environment['PHOTOHOUSE_NATIVE_STORY_REQUEST']).parent)
        return super().create_suspended(executable, argv, environment, cwd)

    def exit_code(self, process):
        return process.poll()

    def resume(self, thread):
        result = super().resume(thread)
        self.resumed.set()
        return result


class ProcessStoryLifecycleTests(unittest.IsolatedAsyncioTestCase):
    def service(self, *, kernel=None, delay=0, sources=None, work_seconds=5, exit_status=0):
        kernel = kernel or WorkerKernel(helpers=0)
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.addCleanup(kernel.finish)
        spec = NativeStoryLaunch(sys.executable,
            hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest(),
            (sys.executable, '-I', '-B', '-c', 'exec(' + repr(WORKER) + ')', str(delay), str(exit_status)),
            folder.name, {'PATH': os.defpath}, minimum_free_ram=0)
        provider = ProcessSelectedStoryProvider(spec, 'synthetic-local', kernel_factory=lambda: kernel,
                                               enabled=True, cleanup_seconds=0.05)
        self.addAsyncCleanup(provider.close)
        admission = InferenceAdmission(max_waiting=4)
        sources = sources or SyntheticSources()
        service = DraftOperations(sources, provider, admission, work_seconds=work_seconds,
                                  cleanup_seconds=2)
        self.addAsyncCleanup(service.close)
        return service, provider, kernel, admission, sources

    async def test_real_worker_reads_exact_exchange_and_result_waits_for_cleanup(self):
        service, provider, kernel, gate, _ = self.service(kernel=WorkerKernel(helpers=1))
        read = provider._read
        def read_after_drain(call):
            self.assertTrue(all(p.poll() is not None for p in kernel.children))
            self.assertTrue(all(job.closed for job in kernel.jobs))
            return read(call)
        with patch.object(provider, '_read', side_effect=read_after_drain):
            result = await service.prepare(TOKEN_A, LIBRARY, request())
        self.assertEqual('needs_review', result['state'])
        self.assertTrue(result['needs_review'])
        self.assertTrue(all(p.poll() is not None for p in kernel.children))
        self.assertIn('terminate-job', kernel.events)  # Lingering helper drained.
        self.assertTrue(all(not p.exists() for p in kernel.exchanges))
        self.assertIsNone(provider._active)
        self.assertEqual(0, gate.state().active)
        self.assertFalse(gate.state().quarantined)
        again = await service.prepare(TOKEN_A, LIBRARY, request())
        self.assertEqual(result, again)
        self.assertEqual(1, len(kernel.exchanges))  # Exact retry does not regenerate.

    async def test_nonzero_worker_exit_rejects_even_a_valid_response(self):
        service, provider, kernel, gate, _ = self.service(exit_status=7)
        with patch.object(provider, '_read', wraps=provider._read) as reading:
            with self.assertRaises(DraftOperationError):
                await service.prepare(TOKEN_A, LIBRARY, request())
            reading.assert_not_called()
        self.assertEqual(0, gate.state().active)
        self.assertFalse(gate.state().quarantined)
        self.assertTrue(all(not p.exists() for p in kernel.exchanges))

    async def test_cancelled_operation_removes_exchange_and_fences_words(self):
        service, provider, kernel, gate, _ = self.service(delay=120)
        pending = asyncio.create_task(service.prepare(TOKEN_A, LIBRARY, request()))
        self.assertTrue(await asyncio.to_thread(kernel.resumed.wait, 2))
        await service.cancel(TOKEN_A, LIBRARY, REQUEST_ID)
        with self.assertRaises(DraftOperationError) as caught:
            await pending
        self.assertEqual('cancelled', caught.exception.reason)
        record = service._records[('account-a', LIBRARY, REQUEST_ID)]
        await asyncio.wait_for(asyncio.shield(record.task), 3)
        self.assertIsNone(record.payload)
        self.assertEqual(0, gate.state().active)
        self.assertIsNone(provider._active)
        self.assertTrue(all(not p.exists() for p in kernel.exchanges))
        self.assertTrue(all(p.poll() is not None for p in kernel.children))

    async def test_expiry_stops_worker_without_publishing_response(self):
        service, provider, kernel, gate, _ = self.service(delay=120, work_seconds=0.5)
        with self.assertRaises(DraftOperationError) as caught:
            await service.prepare(TOKEN_A, LIBRARY, request())
        self.assertEqual('timed_out', caught.exception.reason)
        record = service._records[('account-a', LIBRARY, REQUEST_ID)]
        await asyncio.wait_for(asyncio.shield(record.task), 3)
        self.assertIsNone(record.payload)
        self.assertEqual(0, gate.state().active)
        self.assertIsNone(provider._active)
        self.assertTrue(all(not p.exists() for p in kernel.exchanges))
        self.assertTrue(all(p.poll() is not None for p in kernel.children))

    async def test_failed_stop_retains_exchange_and_capacity_until_late_proof(self):
        kernel = WorkerKernel(helpers=1)
        kernel.refuse_termination = True
        service, provider, kernel, gate, _ = self.service(kernel=kernel)
        with self.assertRaises(DraftOperationError):
            await service.prepare(TOKEN_A, LIBRARY, request())
        self.assertEqual(1, gate.state().active)
        self.assertTrue(gate.state().quarantined)
        self.assertTrue(kernel.exchanges[0].exists())
        self.assertIsNotNone(provider._active)
        kernel.refuse_termination = False
        self.assertTrue(await service.reconcile())
        self.assertEqual(0, gate.state().active)
        self.assertTrue(gate.state().quarantined)
        self.assertFalse(kernel.exchanges[0].exists())
        self.assertIsNone(service._records[('account-a', LIBRARY, REQUEST_ID)].payload)

    async def test_source_change_rejects_real_worker_output(self):
        service, provider, kernel, gate, sources = self.service(delay=0.1)
        pending = asyncio.create_task(service.prepare(TOKEN_A, LIBRARY, request()))
        self.assertTrue(await asyncio.to_thread(kernel.resumed.wait, 2))
        sources.changed = True
        with self.assertRaises(DraftOperationError) as caught:
            await pending
        self.assertEqual('conflict', caught.exception.reason)
        self.assertEqual(0, gate.state().active)
        self.assertTrue(all(not p.exists() for p in kernel.exchanges))

    async def test_session_invalidation_stops_owned_worker(self):
        service, provider, kernel, gate, _ = self.service(delay=120)
        pending = asyncio.create_task(service.prepare(TOKEN_A, LIBRARY, request()))
        self.assertTrue(await asyncio.to_thread(kernel.resumed.wait, 2))
        service.invalidate_session(TOKEN_A)
        record = service._records[('account-a', LIBRARY, REQUEST_ID)]
        await asyncio.wait_for(asyncio.shield(record.task), 3)
        with self.assertRaises(DraftOperationError):
            await pending
        self.assertTrue(all(p.poll() is not None for p in kernel.children))
        self.assertTrue(all(not p.exists() for p in kernel.exchanges))
        self.assertEqual(0, gate.state().active)

    async def test_cancellation_retains_setup_and_read_threads_until_settled(self):
        for method in ('_setup', '_read'):
            with self.subTest(method=method):
                service, provider, kernel, gate, _ = self.service()
                entered, release = threading.Event(), threading.Event()
                original = getattr(provider, method)
                def held(*args):
                    entered.set()
                    if not release.wait(3):
                        raise RuntimeError('Synthetic thread gate timeout')
                    return original(*args)
                try:
                    with patch.object(provider, method, side_effect=held):
                        pending = asyncio.create_task(service.prepare(TOKEN_A, LIBRARY, request()))
                        self.assertTrue(await asyncio.to_thread(entered.wait, 2))
                        await service.cancel(TOKEN_A, LIBRARY, REQUEST_ID)
                        with self.assertRaises(DraftOperationError):
                            await pending
                        self.assertEqual(1, gate.state().active)
                        self.assertIsNotNone(provider._active)
                        record = service._records[('account-a', LIBRARY, REQUEST_ID)]
                        release.set()
                        await asyncio.wait_for(asyncio.shield(record.task), 3)
                    self.assertEqual(0, gate.state().active)
                    self.assertIsNone(record.payload)
                    self.assertIsNone(provider._active)
                    self.assertTrue(all(not p.exists() for p in kernel.exchanges))
                    if method == '_setup':
                        self.assertEqual([], kernel.children)
                finally:
                    release.set()

    async def test_filesystem_cleanup_failure_holds_capacity_after_native_exit(self):
        service, provider, kernel, gate, _ = self.service()
        with patch.object(provider, '_dispose', return_value=False):
            with self.assertRaises(DraftOperationError):
                await service.prepare(TOKEN_A, LIBRARY, request())
        self.assertTrue(all(p.poll() is not None for p in kernel.children))
        self.assertTrue(gate.state().quarantined)
        self.assertEqual(1, gate.state().active)
        self.assertTrue(kernel.exchanges[0].exists())
        self.assertTrue(await service.reconcile())
        self.assertFalse(kernel.exchanges[0].exists())
        self.assertEqual(0, gate.state().active)
        self.assertTrue(gate.state().quarantined)


if __name__ == '__main__':
    unittest.main()
