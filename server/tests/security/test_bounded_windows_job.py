"""Portable controller checks; these do not claim Win32 ABI acceptance."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from bounded_windows_job import (BOUNDED_JOB_QUERY_ENV, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
    JOB_OBJECT_LIMIT_ACTIVE_PROCESS, JOB_OBJECT_LIMIT_JOB_MEMORY, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
    CheckRefused, WindowsAPI, environment_block, run_bounded)
from run_editorial_rehearsal_group import SocketPairAllowance, audit_guard, database_within


class FakeAPI:
    def __init__(self, **changes):
        self.events = []
        self.ram = 16 * 1024**3
        self.assignment = self.resumption = self.termination = True
        self.wait = 'exited'
        self.code = 0
        self.descendants = 0
        self.kill_descendants = True
        self.job = 'job'
        self.process = 'process'
        self.thread = 'thread'
        self.__dict__.update(changes)

    def free_ram(self): return self.ram
    def create_job(self, memory, processes):
        self.events.append(('limits', memory, processes)); return self.job
    def create_suspended(self, executable, argv, environment, cwd):
        self.events.append(('suspended', executable, argv, environment, cwd))
        return self.process, self.thread, 7
    def assign(self, job, process):
        self.events.append('assign'); return self.assignment
    def resume(self, thread):
        self.events.append('resume'); return self.resumption
    def wait_process(self, process, milliseconds):
        self.events.append(('wait', milliseconds))
        return 'exited' if 'kill-job' in self.events or 'kill-process' in self.events else self.wait
    def exit_code(self, process): return self.code
    def terminate_process(self, process):
        self.events.append('kill-process'); return self.termination
    def terminate_job(self, job):
        self.events.append('kill-job')
        if self.kill_descendants: self.descendants = 0
        return self.termination
    def active_processes(self, job):
        self.events.append(('active', self.descendants)); return self.descendants
    def close(self, handle): self.events.append(('close', handle))


class ProvenFakeAPI(FakeAPI):
    def create_suspended_proven(self, executable, argv, environment, cwd, job):
        self.events.append(('proven-suspended', job, dict(environment)))
        return self.process, self.thread, 7, 'query-handle'


class WindowsJobControllerTests(unittest.TestCase):
    def launch(self, api, **kwargs):
        timeout_seconds = kwargs.pop('timeout_seconds', 2)
        return run_bounded(api, 'python.exe', ['python.exe', '-I', '-B', 'fixture.py'],
                           {'SystemRoot': 'C:\\Windows', 'TEMP': 'C:\\synthetic'},
                           'C:\\synthetic', timeout_seconds=timeout_seconds, **kwargs)

    def test_proof_opt_in_passes_the_created_job_and_closes_proof_before_job(self):
        api = ProvenFakeAPI()
        self.assertEqual(self.launch(api, require_child_job_proof=True), 0)
        launch = next(event for event in api.events if isinstance(event, tuple) and event[0] == 'proven-suspended')
        self.assertEqual(launch[1], 'job')
        self.assertNotIn(BOUNDED_JOB_QUERY_ENV, launch[2])
        self.assertLess(api.events.index(('close', 'query-handle')), api.events.index(('close', 'job')))
        self.assertEqual(api.events[-4:], [('close', 'thread'), ('close', 'process'),
                                           ('close', 'query-handle'), ('close', 'job')])

    def test_proof_mode_without_proven_api_fails_before_creating_a_job(self):
        api = FakeAPI()
        with self.assertRaisesRegex(CheckRefused, 'job_proof_unavailable'):
            self.launch(api, require_child_job_proof=True)
        self.assertEqual(api.events, [])

    def test_proof_launch_failure_closes_query_before_job_after_process_cleanup(self):
        api = ProvenFakeAPI(thread=None)
        with self.assertRaisesRegex(CheckRefused, 'process_create_failed'):
            self.launch(api, require_child_job_proof=True)
        self.assertLess(api.events.index('kill-process'), api.events.index(('close', 'query-handle')))
        self.assertLess(api.events.index(('close', 'query-handle')), api.events.index(('close', 'job')))

    def test_default_launch_still_uses_original_three_value_api(self):
        api = FakeAPI()
        self.assertEqual(self.launch(api), 0)
        self.assertTrue(any(isinstance(event, tuple) and event[0] == 'suspended' for event in api.events))
        self.assertFalse(any(isinstance(event, tuple) and event[0] == 'proven-suspended'
                             for event in api.events))

    def test_assigns_before_resume_and_waits_for_empty_job_before_closing(self):
        api = FakeAPI()
        self.assertEqual(self.launch(api), 0)
        self.assertLess(api.events.index('assign'), api.events.index('resume'))
        self.assertLess(api.events.index(('active', 0)), api.events.index(('close', 'job')))
        self.assertEqual(api.events[0], ('limits', 2 * 1024**3, 16))
        self.assertEqual(api.events[-3:], [('close', 'thread'), ('close', 'process'), ('close', 'job')])
        self.assertNotIn('kill-job', api.events)

    def test_unassigned_suspended_process_is_terminated_without_resuming(self):
        api = FakeAPI(assignment=False)
        with self.assertRaisesRegex(CheckRefused, 'job_assignment_failed'):
            self.launch(api)
        self.assertIn('kill-process', api.events)
        self.assertNotIn('resume', api.events)
        self.assertNotIn('kill-job', api.events)

    def test_resume_failure_terminates_only_owned_job(self):
        api = FakeAPI(resumption=False)
        with self.assertRaisesRegex(CheckRefused, 'process_resume_failed'):
            self.launch(api)
        self.assertIn('kill-job', api.events)
        self.assertNotIn('kill-process', api.events)

    def test_timeout_terminates_and_drains_before_closing(self):
        api = FakeAPI(wait='timeout', descendants=2)
        with self.assertRaisesRegex(CheckRefused, 'process_timeout'):
            self.launch(api)
        self.assertLess(api.events.index('kill-job'), api.events.index(('active', 0)))
        self.assertLess(api.events.index(('active', 0)), api.events.index(('close', 'job')))

    def test_cleanup_failure_is_not_reported_as_success(self):
        with self.assertRaisesRegex(CheckRefused, 'job_cleanup_failed'):
            self.launch(FakeAPI(wait='timeout', termination=False))

    def test_nonzero_exit_is_returned_after_drain_for_caller_to_reject(self):
        self.assertEqual(self.launch(FakeAPI(code=3)), 3)

    def test_low_ram_launches_nothing(self):
        api = FakeAPI(ram=7 * 1024**3)
        with self.assertRaisesRegex(CheckRefused, 'free_ram_below_minimum'):
            self.launch(api)
        self.assertEqual(api.events, [])

    def test_missing_job_does_not_create_process(self):
        api = FakeAPI(job=None)
        with self.assertRaisesRegex(CheckRefused, 'job_create_failed'):
            self.launch(api)
        self.assertEqual(len(api.events), 1)

    def test_lingering_descendant_after_parent_exit_is_failed_and_cleaned(self):
        api = FakeAPI(descendants=1)
        now = [0.0]
        def sleep(seconds): now[0] += seconds
        with self.assertRaisesRegex(CheckRefused, 'job_did_not_drain'):
            self.launch(api, timeout_seconds=20, monotonic=lambda: now[0], sleep=sleep)
        self.assertEqual(now[0], 5)
        self.assertIn('kill-job', api.events)
        self.assertEqual(api.descendants, 0)

    def test_selected_grace_allows_slow_descendant_to_exit_naturally(self):
        api = FakeAPI(descendants=1)
        now = [0.0]
        def sleep(seconds): now[0] += seconds
        def active_processes(_job):
            count = 1 if now[0] < 8 else 0
            api.events.append(('active', count))
            return count
        api.active_processes = active_processes

        self.assertEqual(self.launch(api, timeout_seconds=20, descendant_grace_seconds=10,
                                     monotonic=lambda: now[0], sleep=sleep), 0)
        self.assertAlmostEqual(now[0], 8, delta=0.05)
        self.assertNotIn('kill-job', api.events)
        self.assertLess(api.events.index(('active', 0)), api.events.index(('close', 'job')))

    def test_opt_in_terminates_live_descendants_and_returns_parent_exit_code(self):
        api = FakeAPI(descendants=2, code=7)
        self.assertEqual(self.launch(api, terminate_descendants_after_exit=True), 7)
        self.assertEqual(api.events.count('kill-job'), 1)
        killed = api.events.index('kill-job')
        drained = api.events.index(('active', 0), killed)
        self.assertLess(killed, drained)
        self.assertLess(drained, api.events.index(('close', 'job')))

    def test_opt_in_with_empty_job_skips_termination_and_preserves_nonzero_code(self):
        api = FakeAPI(descendants=0, code=9)
        self.assertEqual(self.launch(api, terminate_descendants_after_exit=True), 9)
        self.assertNotIn('kill-job', api.events)
        self.assertEqual(api.events.count(('active', 0)), 1)

    def test_invalid_descendant_exit_policy_refuses_before_launch(self):
        for value in (None, 0, 1, 'true'):
            with self.subTest(value=value):
                api = FakeAPI()
                with self.assertRaisesRegex(CheckRefused, 'invalid_descendant_exit_policy'):
                    self.launch(api, terminate_descendants_after_exit=value)
                self.assertEqual(api.events, [])

    def test_opt_in_termination_failure_is_refused_even_if_cleanup_reclaims_job(self):
        class DeclineOnceAPI(FakeAPI):
            def __init__(self):
                super().__init__(descendants=1)
                self.termination_attempts = 0
            def terminate_job(self, job):
                self.events.append('kill-job')
                self.termination_attempts += 1
                if self.termination_attempts == 1:
                    return False
                self.descendants = 0
                return True

        api = DeclineOnceAPI()
        with self.assertRaisesRegex(CheckRefused, 'job_termination_failed'):
            self.launch(api, terminate_descendants_after_exit=True)
        self.assertEqual(api.termination_attempts, 2)
        self.assertLess(api.events.index(('active', 0)), api.events.index(('close', 'job')))

    def test_opt_in_undrained_descendants_fail_closed(self):
        api = FakeAPI(descendants=1, kill_descendants=False)
        now = [0.0]
        def sleep(seconds): now[0] += seconds
        with self.assertRaisesRegex(CheckRefused, 'job_cleanup_failed'):
            self.launch(api, terminate_descendants_after_exit=True,
                        monotonic=lambda: now[0], sleep=sleep)
        self.assertGreaterEqual(api.events.count('kill-job'), 2)
        self.assertEqual(api.events.count(('active', 0)), 0)
        self.assertIn(('close', 'job'), api.events)

    def test_selected_grace_is_capped_by_overall_deadline(self):
        api = FakeAPI(descendants=1)
        now = [0.0]
        def sleep(seconds): now[0] += seconds
        with self.assertRaisesRegex(CheckRefused, 'job_did_not_drain'):
            self.launch(api, timeout_seconds=3, descendant_grace_seconds=10,
                        monotonic=lambda: now[0], sleep=sleep)
        self.assertEqual(now[0], 3)
        self.assertIn('kill-job', api.events)

    def test_invalid_descendant_grace_starts_nothing(self):
        for grace in (True, False, 0, -1, float('nan'), float('inf'), float('-inf'), 60.1):
            with self.subTest(grace=grace):
                api = FakeAPI()
                with self.assertRaisesRegex(CheckRefused, 'invalid_descendant_grace'):
                    self.launch(api, descendant_grace_seconds=grace)
                self.assertEqual(api.events, [])

    def test_partial_process_creation_is_cleaned_without_resume(self):
        api = FakeAPI(thread=None)
        with self.assertRaisesRegex(CheckRefused, 'process_create_failed'):
            self.launch(api)
        self.assertIn('kill-process', api.events)
        self.assertNotIn('resume', api.events)

    def test_native_resume_accepts_only_the_one_owned_suspension(self):
        from types import SimpleNamespace
        native = WindowsAPI.__new__(WindowsAPI)
        for count in (0, 1, 2, 0xFFFFFFFF):
            native.k32 = SimpleNamespace(ResumeThread=lambda handle: count)
            self.assertEqual(native.resume('thread'), count == 1)

    def test_consume_job_proof_opens_supervisor_duplicates_query_and_closes_before_return(self):
        import ctypes
        import os
        from unittest.mock import patch
        events = []
        expected_flags = (JOB_OBJECT_LIMIT_ACTIVE_PROCESS | JOB_OBJECT_LIMIT_JOB_MEMORY
                          | JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE)
        class Kernel:
            def OpenProcess(self, access, inherit, pid):
                events.append(('open-parent', access, inherit, pid, BOUNDED_JOB_QUERY_ENV in os.environ))
                return 10
            def GetProcessTimes(self, process, created, exited, kernel, user):
                created._obj.dwHighDateTime = 0
                created._obj.dwLowDateTime = 777
                return True
            def GetCurrentProcess(self): return -1
            def DuplicateHandle(self, source, source_handle, target, output, access, inherit, flags):
                events.append(('duplicate', source, getattr(source_handle, 'value', source_handle),
                               access, inherit, flags))
                output._obj.value = 33
                return True
            def IsProcessInJob(self, process, job, result):
                events.append(('membership', job.value))
                result._obj.value = True
                return True
            def QueryInformationJobObject(self, job, info, address, size, returned):
                self.assert_query = (job.value, info)
                limits = ctypes.cast(address, ctypes.POINTER(__import__(
                    'bounded_windows_job')._ExtendedLimits)).contents
                limits.BasicLimitInformation.LimitFlags = expected_flags
                limits.BasicLimitInformation.ActiveProcessLimit = 8
                limits.JobMemoryLimit = 2 * 1024**3
                return True
            def CloseHandle(self, handle):
                events.append(('close', getattr(handle, 'value', handle)))
                return True
        native = WindowsAPI.__new__(WindowsAPI)
        native.k32 = Kernel(); native.wintypes = ctypes.wintypes
        with patch.dict(os.environ, {BOUNDED_JOB_QUERY_ENV: '42:777:55'}):
            proof = native.consume_job_proof()
            self.assertNotIn(BOUNDED_JOB_QUERY_ENV, os.environ)
        self.assertEqual(proof, {'flags': expected_flags, 'memory_limit': 2 * 1024**3, 'process_limit': 8})
        self.assertIn(('open-parent', 0x1040, False, 42, False), events)
        self.assertIn(('duplicate', 10, 55, 0x0004, False, 0), events)
        self.assertEqual(events[-2:], [('close', 33), ('close', 10)])

    def test_consume_job_proof_refuses_missing_bad_parent_identity_and_nonmembership(self):
        import ctypes
        import os
        from unittest.mock import patch
        def make_native(*, open_parent=10, creation=777, member=True, query_ok=True):
            events = []
            class Kernel:
                def OpenProcess(self, *args): events.append('open'); return open_parent
                def GetProcessTimes(self, process, created, exited, kernel, user):
                    created._obj.dwHighDateTime = 0; created._obj.dwLowDateTime = creation
                    return True
                def GetCurrentProcess(self): return -1
                def DuplicateHandle(self, source, source_handle, target, output, access, inherit, flags):
                    output._obj.value = 33; return True
                def IsProcessInJob(self, process, job, result):
                    result._obj.value = member; return True
                def QueryInformationJobObject(self, *args): return query_ok
                def CloseHandle(self, handle): events.append(('close', getattr(handle, 'value', handle))); return True
            native = WindowsAPI.__new__(WindowsAPI)
            native.k32 = Kernel(); native.wintypes = ctypes.wintypes
            return native, events

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(BOUNDED_JOB_QUERY_ENV, None)
            native, events = make_native()
            with self.assertRaisesRegex(CheckRefused, 'job_proof_missing'):
                native.consume_job_proof()
            self.assertEqual(events, [])

            for value, expected in (('nope', 'job_proof_invalid'), ('42:777:55', 'job_proof_supervisor_changed'),
                                    ('42:777:55', 'job_proof_membership_failed'),
                                    ('42:777:55', 'job_proof_query_failed')):
                settings = {'creation': 778} if expected == 'job_proof_supervisor_changed' else {}
                if expected == 'job_proof_membership_failed': settings['member'] = False
                if expected == 'job_proof_query_failed': settings['query_ok'] = False
                native, events = make_native(**settings)
                with self.subTest(expected=expected), patch.dict(os.environ, {BOUNDED_JOB_QUERY_ENV: value}):
                    with self.assertRaisesRegex(CheckRefused, expected):
                        native.consume_job_proof()
                    self.assertNotIn(BOUNDED_JOB_QUERY_ENV, os.environ)
                if expected == 'job_proof_membership_failed':
                    self.assertEqual(events[-2:], [('close', 33), ('close', 10)])
                elif expected == 'job_proof_supervisor_changed':
                    self.assertEqual(events[-1], ('close', 10))
                elif expected == 'job_proof_query_failed':
                    self.assertEqual(events[-2:], [('close', 33), ('close', 10)])

            native, events = make_native(open_parent=0)
            with patch.dict(os.environ, {BOUNDED_JOB_QUERY_ENV: '42:777:55'}):
                with self.assertRaisesRegex(CheckRefused, 'job_proof_supervisor_unavailable'):
                    native.consume_job_proof()
            self.assertEqual(events, ['open'])

    def test_proof_launch_passes_only_nul_handle_during_startup(self):
        import ctypes
        import ctypes.wintypes
        events = []
        class Kernel:
            def GetCurrentProcess(self): return -1
            def GetCurrentProcessId(self): return 42
            def GetProcessTimes(self, process, created, exited, kernel, user):
                created._obj.dwHighDateTime = 0; created._obj.dwLowDateTime = 777
                return True
            def DuplicateHandle(self, source, handle, target, output, access, inherit, flags):
                events.append(('query-duplicate', access, inherit))
                output._obj.value = 55
                return True
            def CreateFileW(self, *args): return 7
            def InitializeProcThreadAttributeList(self, *args):
                args[-1]._obj.value = 128
                return True
            def UpdateProcThreadAttribute(self, *args):
                count = args[4] // ctypes.sizeof(ctypes.wintypes.HANDLE)
                values = ctypes.cast(args[3], ctypes.POINTER(ctypes.wintypes.HANDLE * count)).contents
                events.append(('inherited-handle-list', [item for item in values]))
                return True
            def DeleteProcThreadAttributeList(self, *args): pass
            def CreateProcessW(self, *args):
                events.append(('child-environment', ctypes.wstring_at(args[6])))
                pi = args[-1]._obj
                pi.hProcess = 11; pi.hThread = 12; pi.dwProcessId = 13
                return True
            def CloseHandle(self, handle): events.append(('close', handle)); return True
        native = WindowsAPI.__new__(WindowsAPI)
        native.k32 = Kernel(); native.wintypes = ctypes.wintypes
        native._pi_type = native._process_information_type()
        process, thread, pid, proof = native.create_suspended_proven(
            'python.exe', ['python.exe'], {'SystemRoot': 'C:\\Windows'}, 'C:\\synthetic', 'owned-job')
        self.assertEqual((process, thread, pid, proof), (11, 12, 13, 55))
        inherited = next(event[1] for event in events if isinstance(event, tuple)
                         and event[0] == 'inherited-handle-list')
        self.assertEqual(inherited, [7])
        env = next(event[1] for event in events if isinstance(event, tuple) and event[0] == 'child-environment')
        self.assertIn(f'{BOUNDED_JOB_QUERY_ENV}=42:777:55', env)
        self.assertIn(('query-duplicate', 0x0004, False), events)
        self.assertNotIn(('close', 55), events)  # Supervisor retains it through child proof consumption.
        native.close(proof)

    def test_native_close_failure_is_reported(self):
        from types import SimpleNamespace
        native = WindowsAPI.__new__(WindowsAPI)
        native.k32 = SimpleNamespace(CloseHandle=lambda handle: False)
        with self.assertRaisesRegex(CheckRefused, 'handle_close_failed'):
            native.close('job')

    def test_failed_proven_creation_closes_the_supervisor_query_and_reports_close_failure(self):
        import ctypes
        from types import SimpleNamespace
        def duplicate(source, handle, target, output, access, inherit, flags):
            output._obj.value = 55
            return True
        for close_fails in (False, True):
            events = []
            native = WindowsAPI.__new__(WindowsAPI)
            native.wintypes = ctypes.wintypes
            native.k32 = SimpleNamespace(GetCurrentProcess=lambda: -1, GetCurrentProcessId=lambda: 42,
                DuplicateHandle=duplicate)
            native._process_creation_time = lambda handle: 777
            def fail_create(*args): raise OSError('synthetic launch failure')
            native._create_suspended = fail_create
            def close(handle):
                events.append(handle.value)
                if close_fails: raise OSError('synthetic close failure')
            native.close = close
            with self.subTest(close_fails=close_fails):
                expected = CheckRefused if close_fails else OSError
                with self.assertRaises(expected):
                    native.create_suspended_proven('python.exe', ['python.exe'], {}, 'C:\\synthetic', 99)
                self.assertEqual(events, [55])

    def test_job_close_failure_cannot_be_reported_as_completed(self):
        api = FakeAPI()
        def close(handle):
            api.events.append(('close', handle))
            if handle == 'job':
                raise OSError('synthetic close failure')
        api.close = close
        with self.assertRaisesRegex(CheckRefused, 'job_cleanup_failed'):
            self.launch(api)

    def test_nul_close_failure_reclaims_created_handles_before_adapter_returns(self):
        import ctypes
        import ctypes.wintypes
        events = []
        class Kernel:
            def CreateFileW(self, *args): return 7
            def InitializeProcThreadAttributeList(self, *args):
                args[-1]._obj.value = 128
                return True
            def UpdateProcThreadAttribute(self, *args): return True
            def DeleteProcThreadAttributeList(self, *args): pass
            def CreateProcessW(self, *args):
                pi = args[-1]._obj
                pi.hProcess = 11; pi.hThread = 12; pi.dwProcessId = 13
                return True
            def CloseHandle(self, handle):
                events.append(('close', handle)); return handle != 7
            def TerminateProcess(self, handle, code):
                events.append(('terminate', handle)); return True
            def WaitForSingleObject(self, handle, milliseconds):
                events.append(('wait', handle)); return 0
        native = WindowsAPI.__new__(WindowsAPI)
        native.k32 = Kernel(); native.wintypes = ctypes.wintypes
        native._pi_type = native._process_information_type()
        with self.assertRaisesRegex(CheckRefused, 'process_create_cleanup_failed'):
            native.create_suspended('python.exe', ['python.exe'], {'SystemRoot':'C:\\Windows'}, 'C:\\synthetic')
        self.assertEqual(events, [('close', 7), ('terminate', 11), ('wait', 11), ('close', 12), ('close', 11)])

    def test_environment_is_sorted_unicode_and_terminated(self):
        self.assertEqual(environment_block({'z': '中文', 'a': '1'}), 'a=1\0z=中文\0\0')
        for env in ({}, {'a': '\0'}, {'a=b': 'x'}, {'TEMP': 'x', 'temp': 'y'}):
            with self.subTest(env=env), self.assertRaises(CheckRefused):
                environment_block(env)

    def test_database_guard_refuses_outside_paths_and_allows_synthetic_uri(self):
        root = Path.cwd().resolve()
        self.assertTrue(database_within(root / 'synthetic.sqlite', root))
        self.assertTrue(database_within('file:' + (root / 'synthetic.sqlite').as_posix() + '?mode=ro', root))
        self.assertTrue(database_within(':memory:', root))
        self.assertFalse(database_within(root.parent / 'outside.sqlite', root))
        guard = audit_guard(root)
        with self.assertRaisesRegex(RuntimeError, 'network_access_refused'):
            guard('socket.connect', (None, ('127.0.0.1', 1)))
        with self.assertRaisesRegex(RuntimeError, 'database_outside_candidate'):
            guard('sqlite3.connect', (str(root.parent / 'outside.sqlite'),))

    def test_windows_asyncio_socketpair_only_connects_to_its_ephemeral_listener(self):
        from types import SimpleNamespace
        allowance = SocketPairAllowance()
        guard = audit_guard(Path.cwd(), allowance)
        listener = SimpleNamespace(getsockname=lambda: ('127.0.0.1', 54321))
        with allowance.creating():
            guard('socket.bind', (listener, ('127.0.0.1', 0)))
            guard('socket.connect', (object(), ('127.0.0.1', 54321)))
            for target in [('127.0.0.1', 8002), ('192.0.2.1', 54321)]:
                with self.assertRaisesRegex(RuntimeError, 'network_access_refused'):
                    guard('socket.connect', (object(), target))
        with self.assertRaisesRegex(RuntimeError, 'network_access_refused'):
            guard('socket.connect', (object(), ('127.0.0.1', 54321)))

    def test_socketpair_exception_restores_denial_and_other_threads_cannot_reuse_allowance(self):
        import threading
        allowance = SocketPairAllowance()
        with self.assertRaises(ValueError):
            with allowance.creating():
                raise ValueError('synthetic failure')
        self.assertFalse(allowance.permits('socket.bind', (object(), ('127.0.0.1', 0))))
        result = []
        with allowance.creating():
            thread = threading.Thread(target=lambda: result.append(allowance.permits('socket.bind', (object(), ('127.0.0.1', 0)))))
            thread.start();thread.join()
        self.assertEqual(result, [False])


if __name__ == '__main__':
    unittest.main()
