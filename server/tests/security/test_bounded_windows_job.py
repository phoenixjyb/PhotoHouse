"""Portable controller checks; these do not claim Win32 ABI acceptance."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from bounded_windows_job import CheckRefused, WindowsAPI, environment_block, run_bounded
from run_editorial_rehearsal_group import SocketPairAllowance, audit_guard, database_within


class FakeAPI:
    def __init__(self, **changes):
        self.events = []
        self.ram = 16 * 1024**3
        self.assignment = self.resumption = self.termination = True
        self.wait = 'exited'
        self.code = 0
        self.descendants = 0
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
        self.events.append('kill-job'); self.descendants = 0; return self.termination
    def active_processes(self, job):
        self.events.append(('active', self.descendants)); return self.descendants
    def close(self, handle): self.events.append(('close', handle))


class WindowsJobControllerTests(unittest.TestCase):
    def launch(self, api, **kwargs):
        timeout_seconds = kwargs.pop('timeout_seconds', 2)
        return run_bounded(api, 'python.exe', ['python.exe', '-I', '-B', 'fixture.py'],
                           {'SystemRoot': 'C:\\Windows', 'TEMP': 'C:\\synthetic'},
                           'C:\\synthetic', timeout_seconds=timeout_seconds, **kwargs)

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

    def test_native_close_failure_is_reported(self):
        from types import SimpleNamespace
        native = WindowsAPI.__new__(WindowsAPI)
        native.k32 = SimpleNamespace(CloseHandle=lambda handle: False)
        with self.assertRaisesRegex(CheckRefused, 'handle_close_failed'):
            native.close('job')

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
