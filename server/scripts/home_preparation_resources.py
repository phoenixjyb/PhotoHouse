"""Observe owned resources and emit sanitized worker failures.

Never manage unrelated processes or include private exception details in reports.
"""
import ctypes
from functools import lru_cache
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import time


class JobStopped(Exception):
    pass


# These are deliberately fixed identifiers. Exception text is never returned to
# a caller because it can contain paths, database details, provider output, or
# other private runtime state.
_REFUSAL_MESSAGES = {
    'Invalid worker arguments': 'invalid_arguments',
    'Explicit direct local path required': 'path_refused',
    'Explicit absolute local path required': 'path_refused',
    'Symlinked path component refused': 'path_refused',
    'Symlinked path refused': 'path_refused',
    'Path parent unavailable': 'path_unavailable',
    'Required path unavailable': 'path_unavailable',
    'Unexpected path type': 'path_refused',
    'Lock target changed': 'worker_lock_refused',
    'Worker lock target changed': 'worker_lock_refused',
    'Another approved CPU worker owns this database': 'worker_lock_busy',
    'Another approved image embedding worker owns this database': 'worker_lock_busy',
    'Supported migrated database required': 'unsupported_schema',
    'Required schema missing': 'unsupported_schema',
    'Required current schema columns missing': 'unsupported_schema',
    'Required tables missing': 'unsupported_schema',
    'Required columns missing': 'unsupported_schema',
    'Existing running media task requires inspection': 'task_state_requires_inspection',
    'Existing running embed task requires independent inspection': 'task_state_requires_inspection',
    'Stop file present': 'stop_requested',
    'Stop request already present': 'stop_requested',
    'Stop request arrived before startup': 'stop_requested',
    'Stop path must be separate': 'stop_path_refused',
    'Explicit supported image model required': 'unsupported_model',
    'Explicit model version required': 'unsupported_model',
    'Explicit CPU, cuda:0 or cuda:1 device required': 'unsupported_device',
    'GPU UUID must be omitted for CPU execution': 'gpu_identity_refused',
    'Explicit expected GPU UUID required for CUDA execution': 'gpu_identity_required',
    'Local checkpoint checksum mismatch': 'checkpoint_integrity',
    'Invalid local checkpoint identity': 'checkpoint_integrity',
    'Local checkpoint identity is invalid': 'checkpoint_integrity',
    'Provider preflight receipt too large': 'provider_receipt_invalid',
    'Strict image provider/device preflight did not match configuration': 'provider_preflight_mismatch',
    'Strict provider or device preflight mismatch': 'provider_preflight_mismatch',
    'Strict provider or device mismatch': 'provider_preflight_mismatch',
    'Worker target changed': 'worker_target_changed',
    'Fresh isolated CPU process required': 'isolated_process_required',
    'another_face_owner': 'worker_lock_busy',
    'model_checksum': 'checkpoint_integrity',
    'gpu_uuid_required': 'gpu_identity_required',
    'foreign_running_face_tasks': 'task_state_requires_inspection',
    'stop_requested': 'stop_requested',
    'stop_file_scope': 'stop_path_refused',
    'source_changed': 'source_changed',
    'source_or_model_changed': 'source_or_model_changed',
    'approval_or_claim_changed': 'approval_or_claim_changed',
    'claim_lost': 'claim_lost',
    'unsupported child model or device': 'unsupported_model_or_device',
    'receipt_invalid': 'receipt_invalid',
    'provider_receipt_invalid': 'provider_receipt_invalid',
    'source_scope': 'source_refused',
    'source_media_profile': 'source_refused',
    'crop_size': 'artifact_invalid',
    'receipt_source_mismatch': 'receipt_invalid',
    'detection_model_mismatch': 'model_mismatch',
    'detection_receipt_invalid': 'receipt_invalid',
    'detection_box_invalid': 'artifact_invalid',
    'landmarks_invalid': 'artifact_invalid',
    'crop_profile': 'artifact_invalid',
    'embedding_receipt_invalid': 'receipt_invalid',
    'vector_size': 'artifact_invalid',
    'vector_invalid': 'artifact_invalid',
    'unrecovered_journal': 'journal_requires_recovery',
    'journal_invalid': 'journal_invalid',
    'journal_task_mismatch': 'journal_invalid',
    'journal_ownership_mismatch': 'journal_invalid',
    'journal_path_invalid': 'journal_invalid',
    'journal_output_referenced': 'journal_conflict',
    'face_target_exists': 'output_conflict',
    'artifact_already_exists': 'output_conflict',
    'vector_target_exists': 'output_conflict',
    'model_changed': 'checkpoint_changed',
    'provider_probe_invalid': 'provider_preflight_mismatch',
    'unsupported_schema': 'unsupported_schema',
    'required_table_missing': 'unsupported_schema',
    'required_column_missing': 'unsupported_schema',
    'claim_requires_idle_connection': 'database_state_invalid',
    'verify_requires_transaction': 'database_state_invalid',
    'failure_requires_idle_connection': 'database_state_invalid',
    'recovery_requires_idle_connection': 'database_state_invalid',
}

_RUNTIME_CODES = {
    'operator_stop': 'stop_requested',
    'worker_stop_requested': 'stop_requested',
    'task_time_limit': 'task_time_limit',
    'run_time_limit': 'task_time_limit',
    'disk_reserve': 'resource_limit',
    'disk_pressure': 'resource_limit',
    'resource_observation_failed': 'resource_observation_failed',
    'resource_observation_unsupported': 'resource_observation_failed',
    'memory_budget': 'resource_limit',
    'memory_floor': 'resource_limit',
    'memory_pressure': 'resource_limit',
    'owned_memory_limit': 'resource_limit',
    'gpu_memory_floor': 'resource_limit',
    'gpu_device_unverifiable': 'provider_preflight_mismatch',
    'hard_child_memory_cap_unavailable': 'resource_limit',
    'checkpoint_changed': 'checkpoint_changed',
    'publish_target_or_stop_request': 'publish_or_stop_refused',
    'Strict provider or device mismatch': 'provider_preflight_mismatch',
    'Strict provider or device preflight mismatch': 'provider_preflight_mismatch',
    'Effective model device could not be verified': 'provider_preflight_mismatch',
    'Invalid strict image vector': 'invalid_worker_output',
    'Unsupported strict image embedding dimension': 'invalid_worker_output',
    'Invalid frame embedding': 'invalid_worker_output',
    'Frame embedding dimensions differ': 'invalid_worker_output',
    'Invalid video embedding': 'invalid_worker_output',
}


def _failure_code(error, refused_types=()):
    """Return a safe, fixed failure identifier for a terminal CLI exception."""
    if isinstance(error, KeyboardInterrupt):
        return 'interrupted'
    if isinstance(error, sqlite3.Error):
        code = getattr(error, 'sqlite_errorcode', None)
        if type(code) is int and (code & 0xff) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
            return 'database_busy'
        return 'database_error'
    if isinstance(error, PermissionError):
        return 'permission_denied'
    if isinstance(error, FileNotFoundError):
        return 'file_missing'
    if isinstance(error, OSError):
        return 'io_error'
    if isinstance(error, JobStopped):
        return _RUNTIME_CODES.get(str(error), 'unexpected_failure')
    if refused_types and isinstance(error, refused_types):
        return _REFUSAL_MESSAGES.get(str(error), 'refused')
    if isinstance(error, RuntimeError):
        return _RUNTIME_CODES.get(str(error), 'unexpected_failure')
    return 'unexpected_failure'


def emit_worker_failure(error, *, refused_types=(), face_pipeline=False):
    """Write one sanitized terminal report and return the legacy CLI exit code."""
    code = _failure_code(error, refused_types)
    if face_pipeline:
        report = {'face_pipeline': 'refused', 'phase': 'worker_entry', 'reason': code}
    else:
        report = {'worker': 'refused-or-interrupted', 'inspect_task_state': True,
                  'phase': 'worker_entry', 'failure': code}
    print(json.dumps(report, sort_keys=True), file=sys.stderr, flush=True)
    return 2


@lru_cache(maxsize=1)
def _windows_memory_api():
    # ctypes retains pointer types. Rebuilding these structures per sample leaks
    # their type graphs through that cache, even after garbage collection.
    from ctypes import wintypes as w
    class Status(ctypes.Structure):
        _fields_ = [('length',w.DWORD),('load',w.DWORD)]+[(n,ctypes.c_ulonglong) for n in
            ('total','available','page_total','page_available','virtual_total','virtual_available','extended')]
    class Counters(ctypes.Structure):
        _fields_ = [('cb',w.DWORD),('faults',w.DWORD)]+[(n,ctypes.c_size_t) for n in
            ('peak','rss','quota_peak_paged','quota_paged','quota_peak_nonpaged','quota_nonpaged','page','peak_page')]
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.GlobalMemoryStatusEx.argtypes=[ctypes.POINTER(Status)]
    kernel.GetCurrentProcess.restype=w.HANDLE
    kernel.K32GetProcessMemoryInfo.argtypes=[w.HANDLE,ctypes.POINTER(Counters),w.DWORD]
    return kernel,Status,Counters


def memory(process=None):
    """Available physical memory and owned RSS. Sampling is not a hard OS quota."""
    if sys.platform == 'win32':
        kernel,Status,Counters=_windows_memory_api()
        status=Status();status.length=ctypes.sizeof(status)
        counters=Counters();counters.cb=ctypes.sizeof(counters)
        handle=int(process._handle) if process is not None else kernel.GetCurrentProcess()
        if not kernel.GlobalMemoryStatusEx(ctypes.byref(status)) or not kernel.K32GetProcessMemoryInfo(handle,ctypes.byref(counters),counters.cb):
            if process is not None and process.poll() is not None:return status.available,0
            raise OSError(ctypes.get_last_error(),'Cannot measure owned memory')
        return status.available,counters.rss
    pid=process.pid if process is not None else os.getpid()
    if sys.platform.startswith('linux'):
        values=dict(re.findall(r'^(\w+):\s+(\d+)',Path('/proc/meminfo').read_text(),re.M))
        try:status=Path(f'/proc/{pid}/status').read_text()
        except FileNotFoundError:
            if process is not None and process.poll() is not None:return int(values['MemAvailable'])*1024,0
            raise
        return int(values['MemAvailable'])*1024,int(re.search(r'^VmRSS:\s+(\d+)',status,re.M)[1])*1024
    if sys.platform == 'darwin':
        raw=subprocess.check_output(['/usr/bin/vm_stat'],text=True,timeout=2)
        page=int(re.search(r'page size of (\d+) bytes',raw)[1])
        values=dict(re.findall(r'^([^:]+):\s+(\d+)\.',raw,re.M))
        available=sum(int(values[k]) for k in ('Pages free','Pages inactive','Pages speculative'))*page
        result=subprocess.run(['/bin/ps','-o','rss=','-p',str(pid)],capture_output=True,text=True,timeout=2)
        if result.returncode and process is not None and process.poll() is not None:return available,0
        result.check_returncode()
        return available,int(result.stdout.strip())*1024
    raise OSError('Memory observation is unavailable on this platform')


class Guard:
    def __init__(self, workspace, reserve_bytes, minimum_ram=4*1024**3, maximum_rss=1024**3,
                 max_seconds=None, observe=memory):
        self.workspace=workspace;self.reserve=reserve_bytes;self.minimum_ram=minimum_ram
        self.maximum_rss=maximum_rss;self.observe=observe;self.started=time.monotonic()
        self.max_seconds=max_seconds;self.last=-float('inf');self.peak=0;self.ram_floor=None;self.samples=0
        self.last_child=None

    def __call__(self, process=None, force=False, extra_disk=0):
        now=time.monotonic()
        if (self.workspace/'stop.flag').exists():raise JobStopped('operator_stop')
        if self.max_seconds is not None and now-self.started>=self.max_seconds:raise JobStopped('run_time_limit')
        if shutil.disk_usage(self.workspace).free < self.reserve+extra_disk:raise JobStopped('disk_pressure')
        new_child=process is not None and process is not self.last_child
        if not force and not new_child and now-self.last<1:return
        self.last=now
        if process is not None:self.last_child=process
        try:
            available,parent_rss=self.observe(None)
            child_rss=0
            if process is not None:
                child_available,child_rss=self.observe(process);available=min(available,child_available)
        except (OSError,ValueError,KeyError,AttributeError) as error:
            raise JobStopped('resource_observation_failed') from error
        self.peak=max(self.peak,parent_rss,child_rss);self.samples+=1
        self.ram_floor=available if self.ram_floor is None else min(available,self.ram_floor)
        if available<self.minimum_ram:raise JobStopped('memory_pressure')
        if max(parent_rss,child_rss)>self.maximum_rss:raise JobStopped('owned_memory_limit')

    def summary(self):
        return {'samples':self.samples,'observed_peak_rss':self.peak,'observed_minimum_available_ram':self.ram_floor}
