"""Default-off Windows capacity reads and explicit external-owner clearance.

No discovery, service control, model loading, receipt creation or admission
activation. A native-call duration bound is checked on completion; a stuck
native call cannot be interrupted safely by Python and retains its caller.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import threading
import time
import uuid

from .host_inference_admission import (
    HostAdmissionError, HostCapacity, HostResourceProfile, resource_profile_digest,
)
from .private_storage import require_private_directory, require_private_file

SHA = re.compile(r'[0-9a-f]{64}\Z')
OWNER = re.compile(r'[a-z][a-z0-9_-]{0,47}\Z')
GPU = re.compile(r'gpu:[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z')
MAX_RECEIPT_BYTES = 8192


def _uuid(value):
    return type(value) is str and str(uuid.UUID(value)) == value


def _digest(value):
    return type(value) is str and SHA.fullmatch(value) is not None


def _read_pinned(path, digest, *, limit, private, expected_links=1):
    if not path.is_absolute() or path.resolve(strict=True) != path:
        raise ValueError('Unqualified file')
    if private:
        require_private_directory(path.parent)
        require_private_file(path)
    before = path.lstat()
    if (not stat.S_ISREG(before.st_mode) or before.st_nlink != expected_links
            or getattr(before, 'st_file_attributes', 0) & 0x400
            or not 0 < before.st_size <= limit):
        raise ValueError('Unqualified file')
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
    with os.fdopen(os.open(path, flags), 'rb') as stream:
        opened = os.fstat(stream.fileno())
        key = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
        if key(opened) != key(before):
            raise ValueError('Changed file')
        data = stream.read(limit + 1)
        if key(os.fstat(stream.fileno())) != key(before) or key(path.lstat()) != key(before):
            raise ValueError('Changed file')
    if len(data) > limit or hashlib.sha256(data).hexdigest() != digest:
        raise ValueError('Unqualified file')
    return data


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate field')
        result[key] = value
    return result


@dataclass(frozen=True, repr=False)
class NvmlSelection:
    dll_file: str
    dll_sha256: str
    resource_id: str
    dll_link_count: int = 1

    def __post_init__(self):
        if (type(self.dll_file) is not str or not Path(self.dll_file).is_absolute()
                or not _digest(self.dll_sha256) or type(self.resource_id) is not str
                or GPU.fullmatch(self.resource_id) is None
                or type(self.dll_link_count) is not int or not 1 <= self.dll_link_count <= 16):
            raise ValueError('Invalid explicit GPU selection')


@dataclass(frozen=True, repr=False)
class WindowsProbeIdentity:
    host_id: str
    principal_sid: str
    volume_id: str

    def __post_init__(self):
        try:
            valid = (type(self.host_id) is str and re.fullmatch(r'[a-z0-9][a-z0-9_.-]{0,126}', self.host_id)
                and type(self.principal_sid) is str and len(self.principal_sid) <= 184
                and re.fullmatch(r'S-1-(?:[0-9]+-)*[0-9]+', self.principal_sid)
                and _uuid(self.volume_id))
        except (ValueError, TypeError, AttributeError):
            valid = False
        if not valid:
            raise ValueError('Invalid explicit Windows identity')


def windows_probe_binding(identity, directory, receipt, required_owners, clearance_id, nvml=None):
    if type(identity) is not WindowsProbeIdentity:
        raise ValueError('Explicit Windows identity required')
    value = {'version': 1, 'identity': vars(identity), 'directory': str(Path(directory)),
             'receipt': str(Path(receipt)), 'owners': sorted(required_owners), 'clearance_id': clearance_id,
             'nvml': vars(nvml) if nvml is not None else None}
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                                    separators=(',', ':')).encode()).hexdigest()


def windows_probe_digest(identity, directory, receipt, required_owners, clearance_id,
                         clearance_sha256, nvml=None):
    binding = windows_probe_binding(identity, directory, receipt, required_owners, clearance_id, nvml)
    return hashlib.sha256((binding + ':' + clearance_sha256).encode('ascii')).hexdigest()


@dataclass(frozen=True, repr=False)
class NativeCapacity:
    resource_id: str
    free_ram: int
    free_disk: int
    free_vram: int = 0
    host_id: str = ''
    principal_sid: str = ''
    volume_id: str = ''
    uptime_seconds: float = 0


class WindowsCapacityMetrics:
    """Read only native OS/NVML counters; never select a backend GPU ordinal."""
    def __init__(self, *, nvml=None):
        if nvml is not None and type(nvml) is not NvmlSelection:
            raise ValueError('Invalid NVML selection')
        self.nvml, self._failed = nvml, False

    def capture(self, resource_id, directory):
        if os.name != 'nt' or self._failed:
            raise HostAdmissionError()
        if ((resource_id == 'cpu' and self.nvml is not None)
                or resource_id != 'cpu' and (self.nvml is None or self.nvml.resource_id != resource_id)):
            raise HostAdmissionError()
        try:
            import ctypes
            from ctypes import wintypes as w
            if ctypes.sizeof(ctypes.c_void_p) != 8:
                raise ValueError('Unsupported native ABI')
            root = Path(directory)
            require_private_directory(root)
            if root.resolve(strict=True) != root:
                raise ValueError('Noncanonical capacity path')
            k = ctypes.WinDLL('kernel32', use_last_error=True, winmode=0x800)
            mount = ctypes.create_unicode_buffer(4096)
            k.GetVolumePathNameW.argtypes, k.GetVolumePathNameW.restype = [w.LPCWSTR, w.LPWSTR, w.DWORD], w.BOOL
            if not k.GetVolumePathNameW(str(root), mount, len(mount)) or not mount.value:
                raise ValueError('Capacity mount unavailable')
            k.GetDriveTypeW.argtypes, k.GetDriveTypeW.restype = [w.LPCWSTR], w.UINT
            if k.GetDriveTypeW(mount.value) != 3:  # DRIVE_FIXED; refuse mapped/network/removable paths.
                raise ValueError('Unqualified capacity volume')
            host = ctypes.create_unicode_buffer(128); length = w.DWORD(len(host))
            k.GetComputerNameW.argtypes, k.GetComputerNameW.restype = [w.LPWSTR, ctypes.POINTER(w.DWORD)], w.BOOL
            if not k.GetComputerNameW(host, ctypes.byref(length)):
                raise ValueError('Host identity unavailable')
            volume = ctypes.create_unicode_buffer(64)
            k.GetVolumeNameForVolumeMountPointW.argtypes = [w.LPCWSTR, w.LPWSTR, w.DWORD]
            k.GetVolumeNameForVolumeMountPointW.restype = w.BOOL
            if not k.GetVolumeNameForVolumeMountPointW(mount.value, volume, len(volume)):
                raise ValueError('Volume identity unavailable')
            matched = re.fullmatch(r'\\\\\?\\Volume\{([0-9a-fA-F-]{36})\}\\', volume.value)
            if matched is None or not _uuid(matched[1].lower()):
                raise ValueError('Volume identity unavailable')
            k.GetTickCount64.argtypes, k.GetTickCount64.restype = [], ctypes.c_ulonglong
            uptime = k.GetTickCount64() / 1000
            principal = self._principal(k, ctypes)
            class Status(ctypes.Structure):
                _fields_ = [('length', w.DWORD), ('load', w.DWORD)] + [
                    (name, ctypes.c_ulonglong) for name in ('total', 'available', 'page_total',
                    'page_available', 'virtual_total', 'virtual_available', 'extended')]
            status = Status(); status.length = ctypes.sizeof(status)
            k.GlobalMemoryStatusEx.argtypes, k.GlobalMemoryStatusEx.restype = [ctypes.POINTER(Status)], w.BOOL
            if not k.GlobalMemoryStatusEx(ctypes.byref(status)) or not 0 <= status.available <= status.total:
                raise ValueError('RAM unavailable')
            available, total, free = (ctypes.c_ulonglong() for _ in range(3))
            k.GetDiskFreeSpaceExW.argtypes = [w.LPCWSTR] + [ctypes.POINTER(ctypes.c_ulonglong)] * 3
            k.GetDiskFreeSpaceExW.restype = w.BOOL
            if (not k.GetDiskFreeSpaceExW(str(root), ctypes.byref(available), ctypes.byref(total), ctypes.byref(free))
                    or not 0 <= available.value <= total.value):
                raise ValueError('Disk unavailable')
            vram = 0 if resource_id == 'cpu' else self._gpu_memory()
            return NativeCapacity(resource_id, int(status.available), int(available.value), vram,
                                  host.value.lower(), principal, matched[1].lower(), uptime)
        except Exception:
            self._failed = True  # No automatic fallback/retry after uncertain native state.
            raise HostAdmissionError() from None

    @staticmethod
    def _principal(kernel, ctypes):
        from ctypes import wintypes as w
        security = ctypes.WinDLL('advapi32', use_last_error=True, winmode=0x800)
        security.OpenProcessToken.argtypes, security.OpenProcessToken.restype = [w.HANDLE, w.DWORD, ctypes.POINTER(w.HANDLE)], w.BOOL
        security.GetTokenInformation.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD)]
        security.GetTokenInformation.restype = w.BOOL
        security.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(w.LPWSTR)]
        security.ConvertSidToStringSidW.restype = w.BOOL
        kernel.GetCurrentProcess.argtypes, kernel.GetCurrentProcess.restype = [], w.HANDLE
        kernel.CloseHandle.argtypes, kernel.CloseHandle.restype = [w.HANDLE], w.BOOL
        kernel.LocalFree.argtypes, kernel.LocalFree.restype = [ctypes.c_void_p], ctypes.c_void_p
        token = w.HANDLE(); text = w.LPWSTR()
        try:
            if not security.OpenProcessToken(kernel.GetCurrentProcess(), 8, ctypes.byref(token)):
                raise ValueError('Principal unavailable')
            size = w.DWORD()
            security.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
            if not ctypes.sizeof(ctypes.c_void_p) <= size.value <= 65536:
                raise ValueError('Principal unavailable')
            data = ctypes.create_string_buffer(size.value)
            if not security.GetTokenInformation(token, 1, data, size.value, ctypes.byref(size)):
                raise ValueError('Principal unavailable')
            sid = ctypes.c_void_p.from_buffer(data)
            if not security.ConvertSidToStringSidW(sid, ctypes.byref(text)) or not text.value:
                raise ValueError('Principal unavailable')
            return text.value
        finally:
            failed = False
            if text:
                failed = bool(kernel.LocalFree(ctypes.cast(text, ctypes.c_void_p)))
            if token:
                failed = not kernel.CloseHandle(token) or failed
            if failed:
                raise ValueError('Principal cleanup unavailable')

    def _gpu_memory(self):
        import ctypes
        selection = self.nvml
        path = Path(selection.dll_file)
        # System driver DLLs are public-readable; write protection and dependencies
        # require separate qualification. This is a file preflight, not mapped-image proof.
        _read_pinned(path, selection.dll_sha256, limit=64 * 1024**2, private=False, expected_links=selection.dll_link_count)
        api = ctypes.CDLL(str(path), winmode=0x100 | 0x800)  # DLL_LOAD_DIR | SYSTEM32 only.
        # Track the DLL reference until explicit FreeLibrary succeeds.
        self._loaded = api
        try:
            kernel = ctypes.WinDLL('kernel32', use_last_error=True, winmode=0x800)
            kernel.GetModuleFileNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint]
            kernel.GetModuleFileNameW.restype = ctypes.c_uint
            loaded = ctypes.create_unicode_buffer(4096)
            count = kernel.GetModuleFileNameW(api._handle, loaded, len(loaded))
            if not 0 < count < len(loaded) or Path(loaded.value).resolve(strict=True) != path:
                raise ValueError('Loaded NVML path mismatch')
            _read_pinned(path, selection.dll_sha256, limit=64 * 1024**2, private=False, expected_links=selection.dll_link_count)
            def bind(name, args):
                call = getattr(api, name); call.argtypes, call.restype = args, ctypes.c_int
                return call
            init = bind('nvmlInit_v2', [])
            shutdown = bind('nvmlShutdown', [])
            select = bind('nvmlDeviceGetHandleByUUID', [ctypes.c_char_p, ctypes.POINTER(ctypes.c_void_p)])
            identity = bind('nvmlDeviceGetUUID', [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint])
            class Memory(ctypes.Structure):
                _fields_ = [(name, ctypes.c_ulonglong) for name in ('total', 'free', 'used')]
            memory = bind('nvmlDeviceGetMemoryInfo', [ctypes.c_void_p, ctypes.POINTER(Memory)])
            if init() != 0:
                raise ValueError('NVML unavailable')
            try:
                expected = ('GPU-' + selection.resource_id[4:]).encode('ascii')
                device = ctypes.c_void_p()
                if select(expected, ctypes.byref(device)) != 0 or not device.value:
                    raise ValueError('GPU unavailable')
                actual = ctypes.create_string_buffer(96)
                info = Memory()
                if identity(device, actual, len(actual)) != 0 or memory(device, ctypes.byref(info)) != 0:
                    raise ValueError('GPU counters unavailable')
                if (actual.value.decode('ascii').lower() != expected.decode('ascii').lower()
                        or not 0 < info.total <= 1024**5 or info.free > info.total or info.used > info.total):
                    raise ValueError('GPU identity/capacity mismatch')
                return int(info.free)
            finally:
                if shutdown() != 0:
                    raise ValueError('NVML shutdown unavailable')
        finally:
            import _ctypes
            _ctypes.FreeLibrary(api._handle)
            self._loaded = None



@dataclass(frozen=True, repr=False)
class _ProbeConfig:
    profile: HostResourceProfile
    directory: Path
    receipt: Path
    digest: str
    clearance_id: str
    owners: tuple
    identity: WindowsProbeIdentity
    nvml: NvmlSelection | None


class WindowsStoryCapacityProbe:
    def __init__(self, profile, directory, clearance_file, clearance_sha256, clearance_id,
                 required_owners, *, identity=None, enabled=False, nvml=None, metrics_factory=None,
                 monotonic=time.monotonic, wall_clock=time.time):
        try:
            valid = (type(profile) is HostResourceProfile and _digest(clearance_sha256)
                and _uuid(clearance_id) and type(required_owners) is tuple
                and 1 <= len(required_owners) <= 16 and len(set(required_owners)) == len(required_owners)
                and all(type(owner) is str and OWNER.fullmatch(owner) for owner in required_owners)
                and type(identity) is WindowsProbeIdentity
                and type(enabled) is bool and callable(monotonic) and callable(wall_clock)
                and profile.capacity_sha256 == windows_probe_digest(identity, directory, clearance_file, required_owners, clearance_id, clearance_sha256, nvml)
                and (metrics_factory is None or callable(metrics_factory))
                and (nvml is None if profile.resource_id == 'cpu' else
                     type(nvml) is NvmlSelection and nvml.resource_id == profile.resource_id))
        except (ValueError, TypeError, AttributeError):
            valid = False
        if not valid:
            raise ValueError('Invalid Windows capacity configuration')
        self._config = _ProbeConfig(profile, Path(directory), Path(clearance_file),
            clearance_sha256, clearance_id, required_owners, identity, nvml)
        self.enabled, self.clock, self.wall_clock = enabled, monotonic, wall_clock
        self._factory = metrics_factory or (lambda: WindowsCapacityMetrics(nvml=nvml))
        self._metrics, self._last_wall = None, None
        self._lock = threading.Lock()

    @property
    def profile(self):
        return self._config.profile

    @property
    def directory(self):
        return self._config.directory

    @property
    def receipt(self):
        return self._config.receipt

    @property
    def digest(self):
        return self._config.digest

    @property
    def clearance_id(self):
        return self._config.clearance_id

    @property
    def owners(self):
        return self._config.owners

    @property
    def identity(self):
        return self._config.identity

    @property
    def _nvml(self):
        return self._config.nvml

    def _clearance(self):
        if self.profile.capacity_sha256 != windows_probe_digest(self.identity, self.directory,
                self.receipt, self.owners, self.clearance_id, self.digest, self._nvml):
            raise ValueError('Probe configuration changed')
        raw = _read_pinned(self.receipt, self.digest, limit=MAX_RECEIPT_BYTES, private=True)
        receipt = json.loads(raw, object_pairs_hook=_object)
        now = self.wall_clock()
        if (type(now) not in (int, float) or not math.isfinite(now)
                or self._last_wall is not None and now < self._last_wall):
            raise ValueError('Clock unavailable')
        self._last_wall = now
        if (type(receipt) is not dict or set(receipt) != {'version', 'clearance_id', 'profile_sha256',
                'issued_unix', 'expires_unix', 'owners', 'probe_sha256'} or type(receipt['version']) is not int
                or receipt['version'] != 1 or receipt['clearance_id'] != self.clearance_id
                or receipt['profile_sha256'] != resource_profile_digest(replace(self.profile, capacity_sha256=None))
                or receipt['probe_sha256'] != windows_probe_binding(self.identity, self.directory,
                    self.receipt, self.owners, self.clearance_id, self._nvml)
                or type(receipt['issued_unix']) is not int or type(receipt['expires_unix']) is not int
                or not 0 < receipt['expires_unix'] - receipt['issued_unix'] <= 300
                or not receipt['issued_unix'] <= now <= receipt['expires_unix'] - 60
                or type(receipt['owners']) is not list or len(receipt['owners']) != len(self.owners)):
            raise ValueError('Clearance unavailable')
        seen = set()
        for owner in receipt['owners']:
            if (type(owner) is not dict or set(owner) != {'id', 'state', 'evidence_sha256'}
                    or type(owner['id']) is not str or owner['id'] not in self.owners
                    or owner['id'] in seen or owner['state'] != 'clear' or not _digest(owner['evidence_sha256'])):
                raise ValueError('External owner unavailable')
            seen.add(owner['id'])

    def __call__(self):
        if not self.enabled:
            raise HostAdmissionError('disabled')
        if not self._lock.acquire(blocking=False):
            raise HostAdmissionError('busy')
        try:
            started = self.clock()
            require_private_directory(self.directory)
            self._clearance()
            if self._metrics is None:
                self._metrics = self._factory()
            sample = self._metrics.capture(self.profile.resource_id, self.directory)
            if (type(sample) is not NativeCapacity or sample.resource_id != self.profile.resource_id
                    or any(type(value) is not int or value < 0 for value in
                           (sample.free_ram, sample.free_disk, sample.free_vram))):
                raise ValueError('Capacity unavailable')
            if (sample.host_id != self.identity.host_id or sample.principal_sid != self.identity.principal_sid
                    or sample.volume_id != self.identity.volume_id
                    or type(sample.uptime_seconds) not in (int, float)
                    or not math.isfinite(sample.uptime_seconds) or sample.uptime_seconds <= 0):
                raise ValueError('Native host binding mismatch')
            # A receipt issued before this boot must never authorize a new start.
            issued = json.loads(_read_pinned(self.receipt, self.digest,
                limit=MAX_RECEIPT_BYTES, private=True), object_pairs_hook=_object)['issued_unix']
            if self.wall_clock() - issued > sample.uptime_seconds:
                raise ValueError('Clearance predates boot')
            self._clearance()  # Revocation, replacement, expiry or drift during measurement refuses.
            if not 0 <= self.clock() - started <= 0.5:
                raise ValueError('Capacity probe too slow')
            return HostCapacity(sample.resource_id, self.clearance_id, started,
                                sample.free_ram, sample.free_disk, False, sample.free_vram)
        except HostAdmissionError:
            raise
        except Exception:
            raise HostAdmissionError() from None
        finally:
            self._lock.release()
