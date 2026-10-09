"""Bounded Windows child jobs for explicitly authorized offline qualification.

The module has no CLI and does not launch on import. Callers supply the executable,
argv, clean environment and private working directory. Native acceptance requires
an independent Windows canary; portable fake tests qualify the controller only.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import hashlib
import subprocess
import sys
import time
from typing import Any, Protocol

WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 258
CREATE_SUSPENDED = 0x00000004
CREATE_NO_WINDOW = 0x08000000
CREATE_UNICODE_ENVIRONMENT = 0x00000400
EXTENDED_STARTUPINFO_PRESENT = 0x00080000
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION = 1
JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x00000008
JOB_OBJECT_LIMIT_JOB_MEMORY = 0x00000200
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000

class CheckRefused(RuntimeError):
    pass


class NativeAPI(Protocol):
    def free_ram(self) -> int: ...
    def create_job(self, memory_limit: int, process_limit: int) -> Any: ...
    def create_suspended(self, executable: str, argv: list[str], environment: dict[str, str], cwd: str) -> tuple[Any, Any, int]: ...
    def assign(self, job: Any, process: Any) -> bool: ...
    def resume(self, thread: Any) -> bool: ...
    def wait_process(self, process: Any, milliseconds: int) -> str: ...
    def exit_code(self, process: Any) -> int: ...
    def terminate_process(self, process: Any) -> bool: ...
    def terminate_job(self, job: Any) -> bool: ...
    def active_processes(self, job: Any) -> int: ...
    def close(self, handle: Any) -> None: ...


def environment_block(environment: dict[str, str]) -> str:
    if not environment or any(type(k) is not str or type(v) is not str or not k or
                              '=' in k or '\0' in k or '\0' in v for k, v in environment.items()):
        raise CheckRefused('invalid_environment')
    if len({k.upper() for k in environment}) != len(environment):
        raise CheckRefused('duplicate_environment_key')
    return '\0'.join(k + '=' + v for k, v in sorted(environment.items(), key=lambda item: item[0].upper())) + '\0\0'


def run_bounded(api: NativeAPI, executable: str, argv: list[str], environment: dict[str, str], cwd: str,
                *, timeout_seconds: float, memory_limit: int = 2 * 1024**3,
                process_limit: int = 16, minimum_free_ram: int = 8 * 1024**3,
                monotonic=time.monotonic, sleep=time.sleep) -> int:
    """Start suspended, assign before resume, retain the Job until descendants drain."""
    if not executable or not cwd or not argv or argv[0] != executable or not 0 < timeout_seconds <= 900:
        raise CheckRefused('invalid_launch')
    if memory_limit <= 0 or process_limit <= 0 or minimum_free_ram < 0:
        raise CheckRefused('invalid_limits')
    environment_block(environment)
    if api.free_ram() < minimum_free_ram:
        raise CheckRefused('free_ram_below_minimum')
    deadline = monotonic() + timeout_seconds
    job = process = thread = None
    assigned = completed = False
    def drain(until):
        while True:
            count = api.active_processes(job)
            if type(count) is not int or count < 0:
                raise CheckRefused('job_inventory_invalid')
            if count == 0:
                return
            remaining = until - monotonic()
            if remaining <= 0:
                raise CheckRefused('job_did_not_drain')
            sleep(min(0.05, remaining))
    try:
        job = api.create_job(memory_limit, process_limit)
        if not job:
            raise CheckRefused('job_create_failed')
        process, thread, _ = api.create_suspended(executable, argv, environment, cwd)
        if not process or not thread:
            raise CheckRefused('process_create_failed')
        if not api.assign(job, process):
            raise CheckRefused('job_assignment_failed')
        assigned = True
        if not api.resume(thread):
            raise CheckRefused('process_resume_failed')
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise CheckRefused('process_timeout')
        outcome = api.wait_process(process, int(remaining * 1000))
        if outcome != 'exited':
            raise CheckRefused('process_timeout' if outcome == 'timeout' else 'process_wait_failed')
        code = api.exit_code(process)
        drain(min(deadline, monotonic() + 5))
        completed = True
        return code
    finally:
        cleanup_ok = True
        if process and not completed:
            try:
                if assigned:
                    cleanup_ok = bool(api.terminate_job(job))
                else:
                    cleanup_ok = bool(api.terminate_process(process))
                cleanup_ok = api.wait_process(process, 5000) == 'exited' and cleanup_ok
                if assigned:
                    drain(monotonic() + 5)
            except BaseException:
                cleanup_ok = False
        for handle in (thread, process, job):
            if handle:
                try:
                    api.close(handle)
                except BaseException:
                    cleanup_ok = False
        if not cleanup_ok:
            raise CheckRefused('job_cleanup_failed') from None


class _MemoryStatus(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


class _BasicLimits(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", ctypes.c_ulong), ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", ctypes.c_ulong),
        ("Affinity", ctypes.c_size_t), ("PriorityClass", ctypes.c_ulong), ("SchedulingClass", ctypes.c_ulong),
    ]


class _IOCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimits), ("IoInfo", _IOCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class _Accounting(ctypes.Structure):
    _fields_ = [
        ("TotalUserTime", ctypes.c_longlong), ("TotalKernelTime", ctypes.c_longlong),
        ("ThisPeriodTotalUserTime", ctypes.c_longlong), ("ThisPeriodTotalKernelTime", ctypes.c_longlong),
        ("TotalPageFaultCount", ctypes.c_ulong), ("TotalProcesses", ctypes.c_ulong),
        ("ActiveProcesses", ctypes.c_ulong), ("TotalTerminatedProcesses", ctypes.c_ulong),
    ]


class WindowsAPI:
    """Small Win32 adapter; all process creation starts suspended in a Job."""
    def __init__(self):
        if sys.platform != "win32":
            raise CheckRefused("windows_required")
        self.ctypes = ctypes
        self.wintypes = ctypes.wintypes
        self.k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k, w = self.k32, self.wintypes
        k.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
        k.CreateJobObjectW.restype = w.HANDLE
        k.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
        k.SetInformationJobObject.restype = w.BOOL
        k.QueryInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD)]
        k.QueryInformationJobObject.restype = w.BOOL
        k.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
        k.AssignProcessToJobObject.restype = w.BOOL
        k.ResumeThread.argtypes = [w.HANDLE]
        k.ResumeThread.restype = w.DWORD
        k.TerminateJobObject.argtypes = [w.HANDLE, w.UINT]
        k.TerminateJobObject.restype = w.BOOL
        k.TerminateProcess.argtypes = [w.HANDLE, w.UINT]
        k.TerminateProcess.restype = w.BOOL
        k.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
        k.WaitForSingleObject.restype = w.DWORD
        k.GetExitCodeProcess.argtypes = [w.HANDLE, ctypes.POINTER(w.DWORD)]
        k.GetExitCodeProcess.restype = w.BOOL
        k.CloseHandle.argtypes = [w.HANDLE]
        k.CloseHandle.restype = w.BOOL
        k.CreateProcessW.argtypes = [w.LPCWSTR, w.LPWSTR, ctypes.c_void_p, ctypes.c_void_p,
                                     w.BOOL, w.DWORD, ctypes.c_void_p, w.LPCWSTR,
                                     ctypes.c_void_p, ctypes.c_void_p]
        k.CreateProcessW.restype = w.BOOL
        k.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, ctypes.c_void_p,
                                  w.DWORD, w.DWORD, w.HANDLE]
        k.CreateFileW.restype = w.HANDLE
        k.GlobalMemoryStatusEx.argtypes = [ctypes.c_void_p]
        k.GlobalMemoryStatusEx.restype = w.BOOL
        k.InitializeProcThreadAttributeList.argtypes = [ctypes.c_void_p, w.DWORD, w.DWORD, ctypes.POINTER(ctypes.c_size_t)]
        k.InitializeProcThreadAttributeList.restype = w.BOOL
        k.UpdateProcThreadAttribute.argtypes = [ctypes.c_void_p, w.DWORD, ctypes.c_size_t, ctypes.c_void_p,
                                              ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p]
        k.UpdateProcThreadAttribute.restype = w.BOOL
        k.DeleteProcThreadAttributeList.argtypes = [ctypes.c_void_p]
        k.DeleteProcThreadAttributeList.restype = None
        self._pi_type = self._process_information_type()

    @staticmethod
    def _process_information_type():
        class PROCESS_INFORMATION(ctypes.Structure):
            _fields_ = [("hProcess", ctypes.wintypes.HANDLE), ("hThread", ctypes.wintypes.HANDLE),
                        ("dwProcessId", ctypes.wintypes.DWORD), ("dwThreadId", ctypes.wintypes.DWORD)]
        return PROCESS_INFORMATION

    @staticmethod
    def _startup_info_type():
        class STARTUPINFO(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.wintypes.DWORD), ("lpReserved", ctypes.wintypes.LPWSTR),
                ("lpDesktop", ctypes.wintypes.LPWSTR), ("lpTitle", ctypes.wintypes.LPWSTR),
                ("dwX", ctypes.wintypes.DWORD), ("dwY", ctypes.wintypes.DWORD),
                ("dwXSize", ctypes.wintypes.DWORD), ("dwYSize", ctypes.wintypes.DWORD),
                ("dwXCountChars", ctypes.wintypes.DWORD), ("dwYCountChars", ctypes.wintypes.DWORD),
                ("dwFillAttribute", ctypes.wintypes.DWORD), ("dwFlags", ctypes.wintypes.DWORD),
                ("wShowWindow", ctypes.wintypes.WORD), ("cbReserved2", ctypes.wintypes.WORD),
                ("lpReserved2", ctypes.POINTER(ctypes.c_ubyte)),
                ("hStdInput", ctypes.wintypes.HANDLE), ("hStdOutput", ctypes.wintypes.HANDLE),
                ("hStdError", ctypes.wintypes.HANDLE),
            ]
        return STARTUPINFO

    def free_ram(self) -> int:
        status = _MemoryStatus()
        status.dwLength = ctypes.sizeof(status)
        if not self.k32.GlobalMemoryStatusEx(ctypes.byref(status)):
            raise CheckRefused("ram_inventory_failed")
        return int(status.ullAvailPhys)

    def sha256_file(self, path: str, deadline: float | None = None) -> str:
        digest = hashlib.sha256()
        total = 0
        with open(path, "rb", buffering=0) as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                total += len(chunk)
                if total > 1024**3:
                    raise ValueError("pinned file size limit")
                if deadline is not None and time.monotonic() > deadline:
                    raise CheckRefused("preflight_timeout")
                digest.update(chunk)
        return digest.hexdigest()

    def create_job(self, memory_limit: int, process_limit: int):
        job = self.k32.CreateJobObjectW(None, None)
        if not job:
            return None
        limits = _ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = (
            JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE | JOB_OBJECT_LIMIT_JOB_MEMORY | JOB_OBJECT_LIMIT_ACTIVE_PROCESS)
        limits.BasicLimitInformation.ActiveProcessLimit = process_limit
        limits.JobMemoryLimit = memory_limit
        if not self.k32.SetInformationJobObject(job, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                                                  ctypes.byref(limits), ctypes.sizeof(limits)):
            self.close(job)
            return None
        observed = _ExtendedLimits()
        if (not self.k32.QueryInformationJobObject(job, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                    ctypes.byref(observed), ctypes.sizeof(observed), None)
                or observed.BasicLimitInformation.LimitFlags != limits.BasicLimitInformation.LimitFlags
                or observed.BasicLimitInformation.ActiveProcessLimit != process_limit
                or observed.JobMemoryLimit != memory_limit):
            self.close(job)
            raise CheckRefused('job_limits_not_verified')
        return job

    def create_suspended(self, executable: str, argv: list[str], environment: dict[str, str], cwd: str):
        si_type = self._startup_info_type()
        class STARTUPINFOEX(ctypes.Structure):
            _fields_ = [('StartupInfo', si_type), ('lpAttributeList', ctypes.c_void_p)]
        extended = STARTUPINFOEX()
        si = extended.StartupInfo
        si.cb = ctypes.sizeof(extended)
        pi = self._pi_type()
        cmd = ctypes.create_unicode_buffer(subprocess.list2cmdline(argv))
        class SECURITY_ATTRIBUTES(ctypes.Structure):
            _fields_ = [("nLength", self.wintypes.DWORD), ("lpSecurityDescriptor", ctypes.c_void_p),
                        ("bInheritHandle", self.wintypes.BOOL)]
        security = SECURITY_ATTRIBUTES(ctypes.sizeof(SECURITY_ATTRIBUTES), None, True)
        nul = self.k32.CreateFileW("NUL", 0xC0000000, 1 | 2, ctypes.byref(security), 3, 0x80, None)
        if nul in (0, self.wintypes.HANDLE(-1).value):
            return None, None, 0
        si.dwFlags = 0x00000100  # STARTF_USESTDHANDLES
        si.hStdInput = nul
        si.hStdOutput = nul
        si.hStdError = nul
        # Pass only the NUL standard handle; never inherit the caller's other handles.
        size = ctypes.c_size_t()
        self.k32.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(size))
        attributes = ctypes.create_string_buffer(size.value)
        initialized = False
        created = False
        try:
            if not self.k32.InitializeProcThreadAttributeList(attributes, 1, 0, ctypes.byref(size)):
                raise CheckRefused('attribute_list_failed')
            initialized = True
            handles = (self.wintypes.HANDLE * 1)(nul)
            if not self.k32.UpdateProcThreadAttribute(attributes, 0, 0x00020002,
                                                       ctypes.byref(handles), ctypes.sizeof(handles), None, None):
                raise CheckRefused('handle_list_failed')
            extended.lpAttributeList = ctypes.cast(attributes, ctypes.c_void_p)
            flags = CREATE_SUSPENDED | CREATE_UNICODE_ENVIRONMENT | CREATE_NO_WINDOW | EXTENDED_STARTUPINFO_PRESENT
            env = ctypes.create_unicode_buffer(environment_block(environment))
            ok = self.k32.CreateProcessW(executable, cmd, None, None, True, flags, env, cwd,
                                         ctypes.byref(extended), ctypes.byref(pi))
            if not ok:
                return None, None, 0
            created = True
            return pi.hProcess, pi.hThread, int(pi.dwProcessId)
        finally:
            if initialized:
                self.k32.DeleteProcThreadAttributeList(attributes)
            try:
                self.close(nul)
            except BaseException:
                # A successful CreateProcess has not returned its handles yet.
                # Do not lose an unassigned suspended child on NUL-close failure.
                if created:
                    self.terminate_process(pi.hProcess)
                    self.wait_process(pi.hProcess, 5000)
                    for handle in (pi.hThread, pi.hProcess):
                        try:
                            self.close(handle)
                        except BaseException:
                            pass
                raise CheckRefused('process_create_cleanup_failed') from None

    def assign(self, job, process) -> bool:
        return bool(self.k32.AssignProcessToJobObject(job, process))

    def resume(self, thread) -> bool:
        # One suspension was created by CREATE_SUSPENDED; any other prior count
        # cannot prove this thread is now running solely under our owned Job.
        return self.k32.ResumeThread(thread) == 1

    def wait_process(self, process, milliseconds: int) -> str:
        result = self.k32.WaitForSingleObject(process, max(0, milliseconds))
        if result == WAIT_OBJECT_0:
            return "exited"
        if result == WAIT_TIMEOUT:
            return "timeout"
        return "failed"

    def exit_code(self, process) -> int:
        code = self.wintypes.DWORD()
        if not self.k32.GetExitCodeProcess(process, ctypes.byref(code)):
            raise CheckRefused("process_exit_code_unavailable")
        return int(code.value)

    def terminate_process(self, process) -> bool:
        return bool(self.k32.TerminateProcess(process, 1))

    def terminate_job(self, job) -> bool:
        return bool(self.k32.TerminateJobObject(job, 1))

    def active_processes(self, job) -> int:
        value = _Accounting()
        if not self.k32.QueryInformationJobObject(job, JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION,
                                                   ctypes.byref(value), ctypes.sizeof(value), None):
            raise CheckRefused("job_inventory_unavailable")
        return int(value.ActiveProcesses)

    def close(self, handle) -> None:
        if handle and not self.k32.CloseHandle(handle):
            raise CheckRefused('handle_close_failed')
