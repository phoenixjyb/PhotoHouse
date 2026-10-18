import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import qualify_image_worker_memory_lifetime as qualifier
import run_approved_image_embed_worker as worker


class FakeJob:
    def __init__(self, memory_mib):
        self.memory_mib = memory_mib
        self.handle = object()
        self.closed = 0

    def summary(self):
        return {'limit_bytes': self.memory_mib * 1024**2, 'limit_flags': 0x200}

    def close(self):
        self.closed += 1


class FakeProcess:
    def __init__(self, *, returncode=0):
        self._handle = object()
        self.stdin = FakeInput()
        self.stdout = io.BytesIO(qualifier.CHILD_OUTPUT)
        self.returncode = returncode
        self.killed = False
        self.waited = False

    def poll(self):
        if self.killed:
            return -9
        return self.returncode if self.stdin.closed and self.stdin.value == b'\x01' else None

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        self.waited = True
        return self.returncode


class FakeInput:
    def __init__(self):
        self.value = b''
        self.closed = False

    def write(self, value):
        self.value += value

    def flush(self):
        pass

    def close(self):
        self.closed = True


class ImageWorkerMemoryLifetimeQualificationTests(unittest.TestCase):
    def setUp(self):
        self.jobs = []
        self.processes = []

        def create_job(memory_mib):
            job = FakeJob(memory_mib)
            self.jobs.append(job)
            return job

        def popen(*_args, **_kwargs):
            process = FakeProcess()
            self.processes.append(process)
            return process

        self.create_job = create_job
        self.popen = popen

    def windows_patches(self, membership):
        return (
            patch.object(qualifier.sys, 'platform', 'win32'),
            patch.object(worker, 'WindowsJob', side_effect=self.create_job),
            patch.object(worker, 'observe_memory', return_value=(16 * 1024**3, 0)),
            patch.object(subprocess, 'Popen', side_effect=self.popen),
            patch.object(subprocess, 'CREATE_NO_WINDOW', 0x08000000, create=True),
            patch.object(subprocess, 'BELOW_NORMAL_PRIORITY_CLASS', 0x4000, create=True),
            patch.object(qualifier, '_is_process_in_job', side_effect=membership),
        )

    def enter_patches(self, patches):
        entered = []
        for item in patches:
            entered.append(item.__enter__())
        self.addCleanup(lambda: [item.__exit__(None, None, None) for item in reversed(patches)])
        return entered

    def test_qualifier_uses_one_four_gib_job_for_all_children(self):
        children = 4
        observed_pairs = []

        def membership(process_handle, job_handle):
            observed_pairs.append((process_handle, job_handle))
            return process_handle is self.processes[-1]._handle and job_handle is self.jobs[0].handle

        self.enter_patches(self.windows_patches(membership))
        original_popen = subprocess.Popen
        result = qualifier.qualify(children)

        self.assertEqual(result['status'], 'pass')
        self.assertEqual(result['children'], children)
        self.assertEqual(result['job_objects_created'], 1)
        self.assertEqual(result['job_memory_limit_bytes'], 4 * 1024**3)
        self.assertEqual(result['job_limit_flags'], 0x200)
        self.assertEqual(len(self.jobs), 1)
        self.assertEqual(self.jobs[0].memory_mib, 4096)
        self.assertEqual(self.jobs[0].closed, 1)
        self.assertEqual(len(self.processes), children)
        self.assertEqual(len(observed_pairs), children)
        self.assertTrue(all(p.stdin.closed and p.stdin.value == b'\x01' for p in self.processes))
        self.assertIs(subprocess.Popen, original_popen)
        self.assertIsNone(worker._ACTIVE_WINDOWS_JOB)

    def test_failed_membership_kills_owned_child_and_restores_popen_and_job_factory(self):
        self.enter_patches(self.windows_patches(lambda _process, _job: False))
        original_popen = subprocess.Popen
        original_job_factory = worker.WindowsJob

        with self.assertRaisesRegex(qualifier.QualificationRefused, 'child_job_membership_failed'):
            qualifier.qualify(1)

        self.assertEqual(len(self.processes), 1)
        self.assertTrue(self.processes[0].killed)
        self.assertTrue(self.processes[0].waited)
        self.assertEqual(self.jobs[0].closed, 1)
        self.assertIs(subprocess.Popen, original_popen)
        self.assertIs(worker.WindowsJob, original_job_factory)
        self.assertIsNone(worker._ACTIVE_WINDOWS_JOB)

    def test_child_count_validation_and_non_windows_refusal(self):
        with patch.object(qualifier.sys, 'platform', 'win32'):
            with self.assertRaisesRegex(qualifier.QualificationRefused, 'invalid_child_count'):
                qualifier.qualify(129)
            with self.assertRaisesRegex(qualifier.QualificationRefused, 'invalid_child_count'):
                qualifier.qualify(0)

        with patch.object(qualifier.sys, 'platform', 'darwin'), patch.object(sys, 'stdout', io.StringIO()):
            result = qualifier.main(['--execute'])
        self.assertEqual(result, 2)

    def test_cli_emits_fixed_json_on_argument_errors(self):
        output = io.StringIO()
        with patch.object(qualifier.sys, 'stdout', output):
            result = qualifier.main(['--execute', '--children', 'many'])
        self.assertEqual(result, 2)
        self.assertEqual(json.loads(output.getvalue()),
                         {'status': 'refused', 'reason': 'invalid_arguments'})

    def test_actual_synthetic_child_accepts_only_the_release_token(self):
        command = [sys.executable, '-I', '-B', '-c', qualifier.CHILD_COMMAND]
        accepted = subprocess.run(command, input=b'\x01', cwd=worker.ROOT,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  timeout=5, check=False)
        self.assertEqual(accepted.returncode, 0)
        self.assertEqual(accepted.stdout, qualifier.CHILD_OUTPUT)
        self.assertEqual(accepted.stderr, b'')

        refused = subprocess.run(command, input=b'\x00', cwd=worker.ROOT,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 timeout=5, check=False)
        self.assertEqual(refused.returncode, 31)
        self.assertEqual(refused.stdout, b'')
        self.assertEqual(refused.stderr, b'')


@unittest.skipUnless(
    sys.platform == 'win32' and os.environ.get('PHOTOHOUSE_RUN_WINDOWS_LIFETIME_QUALIFICATION') == '1',
    'opt-in Windows integration; run in a dedicated subprocess',
)
class WindowsImageWorkerMemoryLifetimeIntegrationTests(unittest.TestCase):
    def test_dedicated_qualifier_subprocess_proves_one_lifetime_job(self):
        script = ROOT / 'scripts' / 'qualify_image_worker_memory_lifetime.py'
        result = subprocess.run(
            [sys.executable, '-I', '-B', str(script), '--execute', '--children', '120'],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=qualifier.MAX_SECONDS + 5, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout[:512])
        payload = json.loads(result.stdout)
        self.assertEqual(payload['status'], 'pass')
        self.assertEqual(payload['children'], 120)
        self.assertEqual(payload['job_objects_created'], 1)
        self.assertEqual(payload['job_memory_limit_bytes'], 4 * 1024**3)
        self.assertEqual(payload['job_limit_flags'], 0x200)
        self.assertLessEqual(payload['elapsed_seconds'], qualifier.MAX_SECONDS)
        self.assertEqual(result.stderr, b'')


if __name__ == '__main__':
    unittest.main()
