"""Real synthetic children under a simulated Job kernel; never Win32 acceptance.

The fixture owns every Popen it starts. Its application gate models suspension;
its explicit process list models containment. This is not a POSIX production
fallback and does not claim that process groups contain arbitrary descendants.
"""
import asyncio
from dataclasses import dataclass, field
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend/app'))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from access.inference_admission import InferenceAdmission
from access.selected_story_native import NativeStoryLaunch, NativeStoryProcessOwner
from access.selected_story_operations import DraftOperationError, DraftOperations, PreparationScope
from test_selected_story_operations import LIBRARY, REQUEST_ID, TOKEN_A, SyntheticSources, request


CHILD = 'import sys,time; sys.stdin.buffer.read(1); time.sleep(120)'
QUICK_CHILD = 'import sys; sys.stdin.buffer.read(1)'


@dataclass(eq=False)
class Job:
    members: list = field(default_factory=list)
    closed: bool = False


class ProcessKernel:
    """Native API test double using real, known, independently owned children."""
    def __init__(self, *, helpers=1, quick_root=False, hold_create=False):
        self.helpers, self.quick_root = helpers, quick_root
        self.created, self.release_create = threading.Event(), threading.Event()
        if not hold_create:
            self.release_create.set()
        self.children, self.jobs, self.events = [], [], []
        self.assigned = {}
        self.refuse_termination = False

    def free_ram(self):
        return 16 * 1024**3

    def sha256_file(self, path, deadline):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    def create_job(self, memory, processes):
        job = Job()
        self.jobs.append(job)
        self.events.append(('job', memory, processes))
        return job

    def create_suspended(self, executable, argv, environment, cwd):
        child = subprocess.Popen(argv, executable=executable, env=environment, cwd=cwd,
                                 stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, close_fds=True)
        self.children.append(child)
        self.created.set()
        if not self.release_create.wait(5):
            # Keep the explicit handles in the return receipt even on fixture timeout.
            self.events.append('create-wait-expired')
        return child, child.stdin, child.pid

    def assign(self, job, process):
        job.members.append(process)
        self.assigned[process] = job
        self.events.append('assign')
        return True

    def resume(self, thread):
        process = next(p for p in self.children if p.stdin is thread)
        if process not in self.assigned:
            raise RuntimeError('Fixture root was not assigned')
        thread.write(b'R')
        thread.flush()
        self.events.append('resume')
        for _ in range(self.helpers):
            child = subprocess.Popen([sys.executable, '-I', '-B', '-c', 'import time; time.sleep(120)'],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                env={'PATH': os.defpath}, close_fds=True)
            self.children.append(child)
            self.assigned[process].members.append(child)
        return True

    def wait_process(self, process, milliseconds):
        return 'exited' if process.poll() is not None else 'timeout'

    def terminate_process(self, process):
        if process.poll() is None:
            process.kill()
        self.events.append('terminate-root')
        return True

    def terminate_job(self, job):
        if self.refuse_termination:
            return False
        for process in job.members:
            if process.poll() is None:
                process.kill()
        self.events.append('terminate-job')
        return True

    def active_processes(self, job):
        count = sum(p.poll() is None for p in job.members)
        self.events.append(('active', count))
        return count

    def close(self, handle):
        if isinstance(handle, Job):
            if any(p.poll() is None for p in handle.members):
                raise RuntimeError('Fixture Job still has active processes')
            handle.closed = True
            self.events.append('close-job')
        elif isinstance(handle, subprocess.Popen):
            if handle.poll() is None:
                raise RuntimeError('Fixture root has not been reaped')
            self.events.append('close-root')
        else:
            handle.close()
            self.events.append('close-thread')

    def finish(self):
        self.release_create.set()
        for child in self.children:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=5)
            if child.stdin and not child.stdin.closed:
                child.stdin.close()


class SyntheticContainedProvider:
    def __init__(self, owner, *, hold=False):
        self.owner = owner
        self.started, self.release = asyncio.Event(), asyncio.Event()
        if not hold:
            self.release.set()

    async def prepare(self, bundle, scope):
        await self.owner.begin(scope)
        self.started.set()
        await self.release.wait()
        return {'version': 1, 'title': 'Beans together',
                'chapters': [{'id': c['id'], 'narration': 'We planted beans together.',
                              'source_ids': c['evidence_ids']} for c in bundle['chapters']],
                'questions': [], 'needs_review': True}

    async def stop_and_reconcile(self, scope):
        return await self.owner.stop_and_reconcile(scope)


class NativeStoryProcessTests(unittest.IsolatedAsyncioTestCase):
    def owner(self, kernel):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.addCleanup(kernel.finish)
        spec = NativeStoryLaunch(sys.executable, hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest(),
            (sys.executable, '-I', '-B', '-c', QUICK_CHILD if kernel.quick_root else CHILD),
            folder.name, {'PATH': os.defpath}, minimum_free_ram=0)
        owner = NativeStoryProcessOwner(spec, kernel_factory=lambda: kernel, enabled=True,
                                        cleanup_seconds=2)
        self.addAsyncCleanup(owner.close)
        return owner

    def scope(self):
        return PreparationScope('11111111-1111-4111-8111-111111111111', time.monotonic()+5,
                                threading.Event(), time.monotonic)

    async def test_real_synthetic_members_are_stopped_and_reaped_before_success(self):
        kernel = ProcessKernel(helpers=2)
        owner = self.owner(kernel)
        scope = self.scope()
        self.assertTrue(await owner.begin(scope))
        self.assertEqual(3, sum(p.poll() is None for p in kernel.children))
        self.assertLess(kernel.events.index('assign'), kernel.events.index('resume'))
        self.assertTrue(await owner.stop_and_reconcile(scope))
        self.assertTrue(all(p.poll() is not None for p in kernel.children))
        self.assertTrue(kernel.jobs[0].closed)
        self.assertIsNone(owner._active)

    async def test_root_exit_does_not_hide_a_lingering_contained_member(self):
        kernel = ProcessKernel(quick_root=True)
        owner = self.owner(kernel)
        scope = self.scope()
        await owner.begin(scope)
        await asyncio.to_thread(kernel.children[0].wait, 3)
        self.assertIsNone(kernel.children[1].poll())
        self.assertTrue(await owner.stop_and_reconcile(scope))
        self.assertIn('terminate-job', kernel.events)
        self.assertTrue(all(p.poll() is not None for p in kernel.children))

    async def test_wrong_scope_cannot_signal_any_process_or_an_unrelated_fixture(self):
        kernel = ProcessKernel()
        owner = self.owner(kernel)
        unrelated = subprocess.Popen([sys.executable, '-I', '-B', '-c', 'import time; time.sleep(120)'],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env={'PATH': os.defpath}, close_fds=True)
        self.addCleanup(lambda: (unrelated.kill() if unrelated.poll() is None else None,
                                 unrelated.wait(timeout=5)))
        scope = self.scope()
        await owner.begin(scope)
        self.assertFalse(await owner.stop_and_reconcile(self.scope()))
        self.assertNotIn('terminate-job', kernel.events)
        self.assertTrue(await owner.stop_and_reconcile(scope))
        self.assertIsNone(unrelated.poll())

    async def test_cancelled_launch_waiter_keeps_receipt_and_cleans_late_suspended_root(self):
        kernel = ProcessKernel(hold_create=True)
        owner = self.owner(kernel)
        scope = self.scope()
        starting = asyncio.create_task(owner.begin(scope))
        self.assertTrue(await asyncio.to_thread(kernel.created.wait, 2))
        starting.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await starting
        cleanup = asyncio.create_task(owner.stop_and_reconcile(scope))
        await asyncio.sleep(0)
        kernel.release_create.set()
        self.assertTrue(await asyncio.wait_for(cleanup, 3))
        self.assertNotIn('resume', kernel.events)
        self.assertTrue(all(p.poll() is not None for p in kernel.children))

    async def test_operation_success_is_published_only_after_real_fixture_cleanup(self):
        kernel = ProcessKernel()
        owner = self.owner(kernel)
        provider = SyntheticContainedProvider(owner)
        admission = InferenceAdmission(max_waiting=0)
        service = DraftOperations(SyntheticSources(), provider, admission)
        self.addAsyncCleanup(service.close)
        result = await service.prepare(TOKEN_A, LIBRARY, request())
        self.assertEqual('needs_review', result['state'])
        self.assertTrue(all(p.poll() is not None for p in kernel.children))
        self.assertEqual(0, admission.state().active)
        self.assertFalse(admission.state().quarantined)

    async def test_operation_cancel_fences_words_and_cleans_real_fixture_processes(self):
        kernel = ProcessKernel()
        owner = self.owner(kernel)
        provider = SyntheticContainedProvider(owner, hold=True)
        admission = InferenceAdmission(max_waiting=0)
        service = DraftOperations(SyntheticSources(), provider, admission)
        self.addAsyncCleanup(service.close)
        pending = asyncio.create_task(service.prepare(TOKEN_A, LIBRARY, request()))
        await asyncio.wait_for(provider.started.wait(), 3)
        self.assertTrue(await service.cancel(TOKEN_A, LIBRARY, REQUEST_ID))
        with self.assertRaises(DraftOperationError) as caught:
            await pending
        self.assertEqual('cancelled', caught.exception.reason)
        operation = service._records[('account-a', LIBRARY, REQUEST_ID)]
        await asyncio.wait_for(asyncio.shield(operation.task), 3)
        self.assertIsNone(operation.payload)
        self.assertEqual(0, admission.state().active)
        self.assertTrue(all(p.poll() is not None for p in kernel.children))

    async def test_unstopped_native_members_hold_capacity_and_late_proof_does_not_publish(self):
        kernel = ProcessKernel()
        kernel.refuse_termination = True
        owner = self.owner(kernel)
        owner.cleanup_seconds = 0.03
        provider = SyntheticContainedProvider(owner)
        admission = InferenceAdmission(max_waiting=0)
        service = DraftOperations(SyntheticSources(), provider, admission)
        self.addAsyncCleanup(service.close)
        with self.assertRaises(DraftOperationError) as caught:
            await service.prepare(TOKEN_A, LIBRARY, request())
        self.assertEqual('unavailable', caught.exception.reason)
        self.assertTrue(admission.state().quarantined)
        self.assertEqual(1, admission.state().active)
        self.assertTrue(any(p.poll() is None for p in kernel.children))
        kernel.refuse_termination = False
        self.assertTrue(await service.reconcile())
        self.assertEqual(0, admission.state().active)
        self.assertTrue(admission.state().quarantined)
        self.assertIsNone(service._records[('account-a', LIBRARY, REQUEST_ID)].payload)
        self.assertTrue(all(p.poll() is not None for p in kernel.children))


if __name__ == '__main__':
    unittest.main()
