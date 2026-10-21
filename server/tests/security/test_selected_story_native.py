"""Synthetic ownership tests for default-off native selected-story processes."""

import asyncio
import hashlib
import threading
import time
import unittest

from backend.app.access.selected_story_local import LocalSelectedStoryProvider
from backend.app.access.selected_story_native import (
    OPERATION_ENV,
    NativeStoryLaunch,
    NativeStoryOwnerError,
    NativeStoryProcessOwner,
)
from backend.app.access.selected_story_operations import PreparationScope


OPERATION_ID = 'abcdefab-cdef-4abc-8def-abcdefabcdef'
OTHER_ID = '12345678-1234-4234-8234-123456789abc'
EXE = '/synthetic/native-story-worker'
EXE_HASH = hashlib.sha256(b'synthetic executable').hexdigest()


def make_scope(operation_id=OPERATION_ID):
    return PreparationScope(operation_id, time.monotonic() + 30, threading.Event(), time.monotonic)


def launch_spec(**changes):
    values = {
        'executable': EXE,
        'executable_sha256': EXE_HASH,
        'argv': [EXE, '--synthetic'],
        'cwd': '/synthetic',
        'environment': {'PATH': '/synthetic/bin'},
    }
    values.update(changes)
    return NativeStoryLaunch(**values)


class FakeKernel:
    """Pure fake handles and state; these tests never start a native process."""

    def __init__(self, **changes):
        self.events = []
        self.create_result = ('process', 'thread', 101)
        self.create_started = threading.Event()
        self.create_release = threading.Event()
        self.block_create = False
        self.process_exited = True
        self.active = 0
        self.terminate_clears = False
        self.terminate_result = True
        self.inventory_error = None
        self.close_error = None
        self.ram = 64 * 1024**3
        self.digest = EXE_HASH
        self.__dict__.update(changes)

    def free_ram(self):
        self.events.append('free_ram')
        return self.ram

    def sha256_file(self, path, deadline):
        self.events.append(('sha256', path))
        return self.digest

    def create_job(self, memory, processes):
        self.events.append(('create_job', memory, processes))
        return 'job'

    def create_suspended(self, executable, argv, environment, cwd):
        self.events.append(('create_suspended', executable, tuple(argv), dict(environment), cwd))
        self.create_started.set()
        if self.block_create:
            self.create_release.wait(5)
        return self.create_result

    def assign(self, job, process):
        self.events.append(('assign', job, process))
        return True

    def resume(self, thread):
        self.events.append(('resume', thread))
        return True

    def wait_process(self, process, milliseconds):
        self.events.append(('wait_process', process, milliseconds))
        return 'exited' if self.process_exited else 'timeout'

    def active_processes(self, job):
        self.events.append(('active_processes', job, self.active))
        if self.inventory_error is not None:
            raise self.inventory_error
        return self.active

    def terminate_job(self, job):
        self.events.append(('terminate_job', job))
        if self.terminate_clears:
            self.active = 0
            self.process_exited = True
        return self.terminate_result

    def terminate_process(self, process):
        self.events.append(('terminate_process', process))
        self.process_exited = True
        return True

    def close(self, handle):
        self.events.append(('close', handle))
        if self.close_error == handle:
            raise OSError('synthetic close failure')


class NativeStoryProcessOwnerTests(unittest.IsolatedAsyncioTestCase):
    def make_owner(self, kernel=None, *, enabled=True, **kwargs):
        kernel = kernel or FakeKernel()
        factory_calls = []

        def factory():
            factory_calls.append('called')
            return kernel

        owner = NativeStoryProcessOwner(launch_spec(), kernel_factory=factory,
                                        enabled=enabled, cleanup_seconds=0.05,
                                        **kwargs)
        return owner, kernel, factory_calls

    async def test_launch_is_assigned_before_resume_and_retained_until_root_and_job_are_empty(self):
        kernel = FakeKernel(active=2)
        owner, _, _ = self.make_owner(kernel)
        scope = make_scope()

        self.assertTrue(await owner.begin(scope))
        launch = next(event for event in kernel.events if isinstance(event, tuple)
                      and event[0] == 'create_suspended')
        self.assertEqual(launch[3][OPERATION_ENV], OPERATION_ID)
        self.assertLess(kernel.events.index(('assign', 'job', 'process')),
                        kernel.events.index(('resume', 'thread')))

        stopping = asyncio.create_task(owner.stop_and_reconcile(scope))
        await asyncio.sleep(0.01)
        self.assertFalse(stopping.done())
        self.assertTrue(any(event[0] == 'terminate_job' for event in kernel.events
                            if isinstance(event, tuple)))
        kernel.active = 0
        self.assertTrue(await asyncio.wait_for(stopping, 1))
        self.assertEqual(owner._active, None)
        self.assertLess(kernel.events.index(('wait_process', 'process', 0)),
                        kernel.events.index(('close', 'thread')))
        self.assertLess(kernel.events.index(('active_processes', 'job', 0)),
                        kernel.events.index(('close', 'job')))

    async def test_cancellation_during_slow_create_retains_launch_and_cleans_returned_child(self):
        kernel = FakeKernel(block_create=True)
        owner, _, _ = self.make_owner(kernel)
        scope = make_scope()
        beginning = asyncio.create_task(owner.begin(scope))
        await asyncio.wait_for(asyncio.to_thread(kernel.create_started.wait, 2), 3)
        beginning.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await beginning

        stopping = asyncio.create_task(owner.stop_and_reconcile(scope))
        await asyncio.sleep(0)
        self.assertFalse(stopping.done())
        kernel.create_release.set()
        self.assertTrue(await asyncio.wait_for(stopping, 1))
        self.assertIn(('terminate_process', 'process'), kernel.events)
        self.assertNotIn(('assign', 'job', 'process'), kernel.events)
        self.assertNotIn(('resume', 'thread'), kernel.events)

    async def test_expired_scope_never_constructs_kernel(self):
        owner, kernel, factories = self.make_owner()
        scope = PreparationScope(OPERATION_ID, time.monotonic() - 1,
                                 threading.Event(), time.monotonic)
        with self.assertRaises(NativeStoryOwnerError):
            await owner.begin(scope)
        self.assertEqual([], factories)
        self.assertTrue(await owner.stop_and_reconcile(scope))

    async def test_invalidation_after_assignment_prevents_resume_and_drains_job(self):
        kernel = FakeKernel(active=1, terminate_clears=True)
        owner, _, _ = self.make_owner(kernel)
        scope = make_scope()
        original = kernel.assign
        def assign(*args):
            result = original(*args)
            scope._invalidation.set()
            return result
        kernel.assign = assign
        with self.assertRaises(NativeStoryOwnerError):
            await owner.begin(scope)
        self.assertTrue(await owner.stop_and_reconcile(scope))
        self.assertNotIn(('resume', 'thread'), kernel.events)
        self.assertIn(('terminate_job', 'job'), kernel.events)

    async def test_preflight_refusals_never_create_a_process(self):
        for changes in ({'ram': 0}, {'digest': '0' * 64}):
            with self.subTest(changes=changes):
                owner, kernel, _ = self.make_owner(FakeKernel(**changes))
                scope = make_scope()
                with self.assertRaises(NativeStoryOwnerError):
                    await owner.begin(scope)
                self.assertTrue(await owner.stop_and_reconcile(scope))
                self.assertFalse(any(isinstance(e, tuple) and e[0] == 'create_suspended'
                                     for e in kernel.events))

    async def test_assignment_failure_stops_only_the_suspended_owned_root(self):
        kernel = FakeKernel()
        kernel.assign = lambda *args: False
        owner, _, _ = self.make_owner(kernel)
        scope = make_scope()
        with self.assertRaises(NativeStoryOwnerError):
            await owner.begin(scope)
        self.assertTrue(await owner.stop_and_reconcile(scope))
        self.assertIn(('terminate_process', 'process'), kernel.events)
        self.assertNotIn(('resume', 'thread'), kernel.events)

    async def test_empty_job_does_not_prove_root_exit(self):
        kernel = FakeKernel(process_exited=False, active=0)
        now = [0.0]
        owner, _, _ = self.make_owner(kernel, monotonic=lambda: now[0],
                                     sleep=lambda duration: now.__setitem__(0, now[0] + duration))
        scope = make_scope()
        await owner.begin(scope)
        self.assertIs(await owner.stop_and_reconcile(scope), False)
        self.assertIs(owner._active.scope, scope)
        self.assertNotIn(('close', 'job'), kernel.events)

    async def test_departing_cleanup_waiter_does_not_abandon_cleanup(self):
        kernel = FakeKernel(active=1)
        owner, _, _ = self.make_owner(kernel)
        scope = make_scope()
        await owner.begin(scope)
        waiter = asyncio.create_task(owner.stop_and_reconcile(scope))
        await asyncio.sleep(0.005)
        retained = owner._active.cleanup
        waiter.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await waiter
        self.assertFalse(retained.cancelled())
        kernel.active = 0
        self.assertTrue(await owner.stop_and_reconcile(scope))
        self.assertTrue(retained.result())

    async def test_bad_inventory_cannot_release_scope(self):
        kernel = FakeKernel()
        owner, _, _ = self.make_owner(kernel)
        scope = make_scope()
        await owner.begin(scope)
        kernel.active = -1

        self.assertIs(await owner.stop_and_reconcile(scope), False)
        self.assertIs(owner._active.scope, scope)
        self.assertFalse(any(event[0] == 'close' for event in kernel.events
                             if isinstance(event, tuple)))

    async def test_failed_termination_with_remaining_child_cannot_release_scope(self):
        kernel = FakeKernel(active=1, terminate_result=False)
        now = [0.0]
        def sleep(duration):
            now[0] += duration
        owner, _, _ = self.make_owner(kernel, monotonic=lambda: now[0], sleep=sleep)
        scope = make_scope()
        await owner.begin(scope)

        self.assertIs(await owner.stop_and_reconcile(scope), False)
        self.assertIs(owner._active.scope, scope)
        self.assertTrue(any(event[0] == 'terminate_job' for event in kernel.events
                            if isinstance(event, tuple)))
        self.assertNotIn(('close', 'job'), kernel.events)

    async def test_handle_close_failure_cannot_release_or_be_retried_as_proof(self):
        kernel = FakeKernel(close_error='process')
        owner, _, _ = self.make_owner(kernel)
        scope = make_scope()
        await owner.begin(scope)

        self.assertIs(await owner.stop_and_reconcile(scope), False)
        self.assertIs(owner._active.scope, scope)
        self.assertIs(await owner.stop_and_reconcile(scope), False)
        self.assertEqual(kernel.events.count(('close', 'process')), 1)

    async def test_no_child_is_released_but_partial_creation_stays_unproven(self):
        no_child = FakeKernel(create_result=(None, None, 0))
        owner, _, _ = self.make_owner(no_child)
        scope = make_scope()
        with self.assertRaisesRegex(NativeStoryOwnerError, 'Native story process unavailable'):
            await owner.begin(scope)
        self.assertTrue(await owner.stop_and_reconcile(scope))
        self.assertNotIn(('terminate_job', 'job'), no_child.events)

        partial = FakeKernel(create_result=('partial-process', None, 0))
        owner, _, _ = self.make_owner(partial)
        scope = make_scope(OTHER_ID)
        with self.assertRaises(NativeStoryOwnerError):
            await owner.begin(scope)
        self.assertIs(await owner.stop_and_reconcile(scope), False)
        self.assertIs(owner._active.scope, scope)
        self.assertIn(('terminate_process', 'partial-process'), partial.events)
        self.assertNotIn(('resume', 'thread'), partial.events)

    async def test_uncertain_create_receipt_never_claims_cleanup(self):
        kernel = FakeKernel(create_result=None)
        owner, _, _ = self.make_owner(kernel)
        scope = make_scope()
        with self.assertRaises(NativeStoryOwnerError):
            await owner.begin(scope)
        self.assertIs(await owner.stop_and_reconcile(scope), False)
        self.assertIs(owner._active.scope, scope)

    async def test_wrong_scope_unknown_scope_and_operation_id_reuse_are_rejected(self):
        kernel = FakeKernel()
        owner, _, _ = self.make_owner(kernel)
        scope = make_scope()
        await owner.begin(scope)

        self.assertIs(await owner.stop_and_reconcile(make_scope()), False)
        self.assertIs(await owner.stop_and_reconcile(make_scope(OTHER_ID)), False)
        self.assertTrue(await owner.stop_and_reconcile(scope))
        self.assertTrue(await owner.stop_and_reconcile(scope))
        with self.assertRaisesRegex(NativeStoryOwnerError, 'Native story process unavailable'):
            await owner.begin(make_scope())
        self.assertIs(await owner.stop_and_reconcile(make_scope(OTHER_ID)), False)

    async def test_only_one_call_can_be_active_and_close_blocks_future_begins(self):
        owner, _, factory_calls = self.make_owner()
        first = make_scope()
        await owner.begin(first)
        with self.assertRaises(NativeStoryOwnerError):
            await owner.begin(make_scope(OTHER_ID))
        self.assertTrue(await owner.close())
        with self.assertRaises(NativeStoryOwnerError):
            await owner.begin(make_scope(OTHER_ID))
        self.assertEqual(factory_calls, ['called'])

    async def test_default_off_does_not_call_kernel_factory(self):
        owner, _, factory_calls = self.make_owner(enabled=False)
        with self.assertRaises(NativeStoryOwnerError):
            await owner.begin(make_scope())
        self.assertEqual(factory_calls, [])

    def test_launch_spec_is_validated_and_copied(self):
        environment = {'PATH': '/synthetic/bin'}
        argv = [EXE, '--synthetic']
        spec = launch_spec(environment=environment, argv=argv)
        environment['NEW'] = 'value'
        argv.append('--later')

        self.assertEqual(dict(spec.environment), {'PATH': '/synthetic/bin'})
        self.assertEqual(spec.argv, (EXE, '--synthetic'))
        with self.assertRaises(TypeError):
            spec.environment['X'] = 'Y'
        with self.assertRaises(ValueError):
            launch_spec(environment={OPERATION_ENV: 'forged'})
        with self.assertRaises(ValueError):
            launch_spec(executable_sha256='not-a-digest')

    def test_configuration_rejects_boolean_enabled_value_and_invalid_cleanup_bound(self):
        spec = launch_spec()
        for enabled, cleanup_seconds in ((1, 1), (True, 0), (True, 10.1)):
            with self.subTest(enabled=enabled, cleanup_seconds=cleanup_seconds):
                with self.assertRaises(ValueError):
                    NativeStoryProcessOwner(spec, kernel_factory=FakeKernel,
                                            enabled=enabled, cleanup_seconds=cleanup_seconds)

    def test_http_provider_rejects_owned_process_tree_as_endpoint_proof(self):
        owner, _, _ = self.make_owner()
        with self.assertRaisesRegex(ValueError, 'Qualified provider-to-process binding required'):
            LocalSelectedStoryProvider('http://127.0.0.1:11434', 'qwen-local',
                                       enabled=True, native_owner=owner)


if __name__ == '__main__':
    unittest.main()
