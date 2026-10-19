#!/usr/bin/env python3
"""Qualify one image worker memory Job across repeated synthetic child launches.

Windows only. This launches model-free Python children with no database, media,
network, or filesystem output. The parent proves each child belongs to the exact
active Job before releasing it to make progress.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import run_approved_image_embed_worker as image_worker

DEFAULT_CHILDREN = 120
MAX_CHILDREN = 128
MAX_SECONDS = 180
EXPECTED_LIMIT_BYTES = 4 * 1024**3
EXPECTED_LIMIT_FLAGS = 0x200
CHILD_COMMAND = (
    "import sys,time; token=sys.stdin.buffer.read(1); "
    "sys.exit(31) if token != b'\\x01' else None; "
    "time.sleep(0.2); sys.stdout.buffer.write(b'image-worker-memory-child-ok\\n'); "
    "sys.stdout.buffer.flush()"
)
CHILD_OUTPUT = b"image-worker-memory-child-ok\n"


def _child_environment() -> dict[str, str]:
    result = {}
    for name in ('SystemRoot', 'WINDIR'):
        value = os.environ.get(name)
        if value:
            result[name] = value
    return result


class QualificationRefused(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class Parser(argparse.ArgumentParser):
    def error(self, _message):
        raise QualificationRefused('invalid_arguments')


def _is_process_in_job(process_handle, job_handle) -> bool:
    if sys.platform != 'win32':
        raise QualificationRefused('windows_required')
    try:
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        check = kernel32.IsProcessInJob
        check.argtypes = (wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL))
        check.restype = wintypes.BOOL
        in_job = wintypes.BOOL()
        if not check(process_handle, job_handle, ctypes.byref(in_job)):
            raise QualificationRefused('job_membership_query_failed')
        return bool(in_job.value)
    except QualificationRefused:
        raise
    except Exception:
        raise QualificationRefused('job_membership_query_failed') from None


def _terminate_owned(process):
    """Stop only the child returned by the just-created Popen call."""
    try:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
    except Exception:
        # The caller still reports the proof failure without exposing details.
        pass
    try:
        if process.stdin is not None:
            process.stdin.close()
    except Exception:
        pass
    try:
        if process.stdout is not None:
            process.stdout.close()
    except Exception:
        pass


class _AttestedLaunches:
    """Temporarily attest each actual child Popen before unblocking its stdin."""

    def __init__(self, job, expected_children: int):
        self.job = job
        self.expected_children = expected_children
        self.launched = 0
        self.original_popen = None

    def __enter__(self):
        self.original_popen = subprocess.Popen

        def launch(*args, **kwargs):
            if self.launched >= self.expected_children:
                raise QualificationRefused('unexpected_child_launch')
            command = args[0] if args else kwargs.get('args')
            expected = [sys.executable, '-I', '-B', '-c', CHILD_COMMAND]
            if (command != expected or kwargs.get('cwd') != image_worker.ROOT
                    or kwargs.get('env') != _child_environment()):
                raise QualificationRefused('unexpected_child_configuration')
            # The child is held at stdin until membership in this exact Job is
            # established. Popen is restored even if proof or release fails.
            child_kwargs = dict(kwargs)
            child_kwargs['stdin'] = subprocess.PIPE
            process = self.original_popen(*args, **child_kwargs)
            try:
                if not _is_process_in_job(process._handle, self.job.handle):
                    raise QualificationRefused('child_job_membership_failed')
                if process.stdin is None:
                    raise QualificationRefused('child_gate_unavailable')
                process.stdin.write(b'\x01')
                process.stdin.flush()
                process.stdin.close()
                self.launched += 1
                return process
            except BaseException:
                _terminate_owned(process)
                raise

        subprocess.Popen = launch
        return self

    def __exit__(self, _exc_type, _exc, _traceback):
        subprocess.Popen = self.original_popen
        return False


def _install_counted_job_factory():
    original = image_worker.WindowsJob
    state = {'created': 0}

    def create(memory_mib):
        state['created'] += 1
        if state['created'] > 1:
            raise QualificationRefused('multiple_job_objects_created')
        return original(memory_mib)

    image_worker.WindowsJob = create
    return original, state


def qualify(children: int = DEFAULT_CHILDREN) -> dict:
    if sys.platform != 'win32':
        raise QualificationRefused('windows_required')
    if type(children) is not int or not 1 <= children <= MAX_CHILDREN:
        raise QualificationRefused('invalid_child_count')
    if image_worker._ACTIVE_WINDOWS_JOB is not None:
        raise QualificationRefused('worker_envelope_already_active')

    started = time.monotonic()
    deadline = started + MAX_SECONDS
    original_factory, factory_state = _install_counted_job_factory()
    launch_proof = None
    try:
        with image_worker.worker_memory_envelope():
            job = image_worker._require_active_windows_job()
            policy = job.summary()
            if (type(policy) is not dict
                    or policy.get('limit_bytes') != EXPECTED_LIMIT_BYTES
                    or policy.get('limit_flags') != EXPECTED_LIMIT_FLAGS
                    or factory_state['created'] != 1):
                raise QualificationRefused('job_policy_mismatch')
            launch_proof = _AttestedLaunches(job, children)
            with launch_proof:
                for _ in range(children):
                    if time.monotonic() >= deadline:
                        raise QualificationRefused('runtime_limit')
                    output = image_worker.run_supervised(
                        [sys.executable, '-I', '-B', '-c', CHILD_COMMAND],
                        env=_child_environment(), derived=image_worker.ROOT, deadline=deadline,
                        capture_stdout=True)
                    if output != CHILD_OUTPUT:
                        raise QualificationRefused('child_result_mismatch')
            if launch_proof.launched != children:
                raise QualificationRefused('child_count_mismatch')
        elapsed = time.monotonic() - started
        if elapsed > MAX_SECONDS:
            raise QualificationRefused('runtime_limit')
        if image_worker._ACTIVE_WINDOWS_JOB is not None:
            raise QualificationRefused('worker_envelope_not_released')
        return {
            'status': 'pass',
            'children': launch_proof.launched,
            'job_objects_created': factory_state['created'],
            'job_memory_limit_bytes': EXPECTED_LIMIT_BYTES,
            'job_limit_flags': EXPECTED_LIMIT_FLAGS,
            'max_runtime_seconds': MAX_SECONDS,
            'elapsed_seconds': round(elapsed, 3),
        }
    finally:
        image_worker.WindowsJob = original_factory


def main(argv=None) -> int:
    parser = Parser(description=__doc__)
    parser.add_argument('--children', type=int, default=DEFAULT_CHILDREN)
    parser.add_argument('--execute', action='store_true')
    try:
        args = parser.parse_args(argv)
        if not args.execute:
            raise QualificationRefused('execute_required')
        result = qualify(args.children)
    except QualificationRefused as error:
        result = {'status': 'refused', 'reason': error.reason}
        print(json.dumps(result, sort_keys=True, separators=(',', ':')))
        return 2
    except BaseException:
        print(json.dumps({'status': 'failed', 'reason': 'qualification_failed'},
                         sort_keys=True, separators=(',', ':')))
        return 1
    print(json.dumps(result, sort_keys=True, separators=(',', ':')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
