"""Default-off persistent CPU policy, fresh native capacity and known conflicts.

Separate from experimental receipt/owner-clearance contracts. The policy UUID
is a persistent operator activation identity, never host-global clearance.
No process control, automatic activation, receipt renewal or claim reclamation.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import ntpath
import os
from pathlib import Path
import re
import threading
import time
import uuid

from .host_inference_admission import HostAdmissionError, HostCapacity, HostResourceProfile
from .private_storage import require_private_directory
from .windows_story_capacity import NativeCapacity, WindowsCapacityMetrics, WindowsProbeIdentity

_DRIVE = re.compile(r'[A-Za-z]:\Z')


def _images(images):
    if (type(images) is not tuple or not 1 <= len(images) <= 16
            or any(type(p) is not str or not 0 < len(p) <= 4096
                or not ntpath.isabs(p) or _DRIVE.fullmatch(ntpath.splitdrive(p)[0]) is None
                or ntpath.normpath(p) != p or not p.lower().endswith('.exe')
                or any(ord(c) < 32 for c in p)
                or any(part.endswith(('.', ' ')) or ':' in part
                    for part in p[3:].split('\\')) for p in images)
            or len(set(p.casefold() for p in images)) != len(images)):
        raise ValueError('Explicit known conflict images required')
    return tuple(sorted(p.casefold() for p in images))


def windows_service_probe_digest(identity, directory, policy_id, conflict_images):
    """Pin an operator policy and its limited configured-conflict scope."""
    if (type(identity) is not WindowsProbeIdentity or type(policy_id) is not str
            or str(uuid.UUID(policy_id)) != policy_id or not Path(directory).is_absolute()):
        raise ValueError('Explicit service policy binding required')
    value = {'version': 1, 'mode': 'persistent_cpu_operator_policy',
             'identity': vars(identity), 'directory': str(Path(directory)),
             'policy_id': policy_id, 'known_conflict_images': _images(conflict_images)}
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


@dataclass(frozen=True, repr=False)
class WindowsStoryConflictSample:
    observed_monotonic: float
    busy: bool


class WindowsStoryProcessConflicts:
    """Read only configured images, conservatively refusing ambiguous matches.

    All processes sharing a matching image are busy, including this service if
    misconfigured to match itself. No command-line guessing or self/PID exclusion.
    This is not an inventory, host-global exclusion or a stop permission.
    """
    def __init__(self, *, monotonic=time.monotonic):
        self.clock, self._failed = monotonic, False

    def capture(self, images):
        wanted = set(_images(images))
        names = {ntpath.basename(p) for p in wanted}
        if os.name != 'nt' or self._failed:
            raise HostAdmissionError()
        try:
            import ctypes as c
            if c.sizeof(c.c_void_p) != 8:
                raise ValueError('Unsupported native ABI')
            # Fixed-width Win32 fields also keep synthetic ABI tests meaningful.
            # https://learn.microsoft.com/windows/win32/api/tlhelp32/ns-tlhelp32-processentry32w
            class Entry(c.Structure):
                _fields_ = [('size', c.c_uint32), ('usage', c.c_uint32), ('pid', c.c_uint32),
                    ('heap', c.c_size_t), ('module', c.c_uint32), ('threads', c.c_uint32),
                    ('parent', c.c_uint32), ('priority', c.c_int32), ('flags', c.c_uint32),
                    ('image', c.c_uint16 * 260)]
            if c.sizeof(Entry) != 568:
                raise ValueError('Unsupported process ABI')
            api = c.WinDLL('kernel32', use_last_error=True, winmode=0x800)
            api.CreateToolhelp32Snapshot.argtypes, api.CreateToolhelp32Snapshot.restype = [c.c_uint32, c.c_uint32], c.c_void_p
            for fn in (api.Process32FirstW, api.Process32NextW):
                fn.argtypes, fn.restype = [c.c_void_p, c.POINTER(Entry)], c.c_int
            api.OpenProcess.argtypes, api.OpenProcess.restype = [c.c_uint32, c.c_int, c.c_uint32], c.c_void_p
            api.QueryFullProcessImageNameW.argtypes = [c.c_void_p, c.c_uint32, c.c_wchar_p, c.POINTER(c.c_uint32)]
            api.QueryFullProcessImageNameW.restype = c.c_int
            api.CloseHandle.argtypes, api.CloseHandle.restype = [c.c_void_p], c.c_int
            started = self.clock()
            snapshot = api.CreateToolhelp32Snapshot(2, 0)  # TH32CS_SNAPPROCESS, noninheritable.
            if not snapshot or snapshot == c.c_void_p(-1).value:
                raise ValueError('Process snapshot unavailable')
            count, busy = 0, False
            try:
                entry = Entry(); entry.size = c.sizeof(entry)
                more = api.Process32FirstW(snapshot, c.byref(entry))
                while more:
                    count += 1
                    if count > 4096 or not 0 <= self.clock() - started <= 0.25:
                        raise ValueError('Process observation limit')
                    end = next((i for i, value in enumerate(entry.image) if value == 0), None)
                    if end is None or end == 0:
                        raise ValueError('Truncated process identity')
                    name = bytes(entry.image)[:2 * end].decode('utf-16-le', errors='strict').casefold()
                    if name in names:
                        process = api.OpenProcess(0x1000, False, entry.pid)  # QUERY_LIMITED_INFORMATION only.
                        if not process:
                            raise ValueError('Matching process unavailable')
                        try:
                            image = c.create_unicode_buffer(4096); size = c.c_uint32(len(image))
                            if (not api.QueryFullProcessImageNameW(process, 0, image, c.byref(size))
                                    or not 0 < size.value < len(image)
                                    or len(image.value.encode('utf-16-le')) // 2 != size.value
                                    or ntpath.basename(image.value).casefold() != name):
                                raise ValueError('Matching process image unavailable')
                            actual = _images((image.value,))[0]
                            if actual in wanted:
                                busy = True
                        finally:
                            if not api.CloseHandle(process):
                                raise ValueError('Process handle cleanup unavailable')
                    more = api.Process32NextW(snapshot, c.byref(entry))
                if c.get_last_error() != 18 or not count:  # ERROR_NO_MORE_FILES is the only complete end.
                    raise ValueError('Incomplete process observation')
            finally:
                if not api.CloseHandle(snapshot):
                    raise ValueError('Snapshot cleanup unavailable')
            if not 0 <= self.clock() - started <= 0.25:
                raise ValueError('Process observation too slow')
            return WindowsStoryConflictSample(started, busy)
        except Exception:
            self._failed = True
            raise HostAdmissionError() from None


class WindowsStoryServiceCapacityProbe:
    """Fresh resources under an explicitly activated persistent CPU policy.

    HostInferenceAdmission retains activation/revocation and the durable claim.
    No service startup side effect enables policy. Every acquisition checks real
    metrics and configured conflicts before/after; stale/unknown observations
    refuse. The complete probe must finish within the existing 0.5 second limit.
    A stuck native call retains its caller; Python cannot safely interrupt it.
    """
    def __init__(self, profile, directory, policy_id, conflict_images, *, identity,
                 enabled=False, metrics_factory=None, conflicts_factory=None,
                 monotonic=time.monotonic):
        if (type(profile) is not HostResourceProfile or profile.resource_id != 'cpu'
                or type(enabled) is not bool or not callable(monotonic)
                or metrics_factory is not None and not callable(metrics_factory)
                or conflicts_factory is not None and not callable(conflicts_factory)
                or profile.capacity_sha256 != windows_service_probe_digest(
                    identity, directory, policy_id, conflict_images)):
            raise ValueError('Invalid persistent CPU capacity configuration')
        self.profile, self.directory, self.policy_id = profile, Path(directory), policy_id
        self.identity, self.images = identity, _images(conflict_images)
        self.enabled, self.clock = enabled, monotonic
        self._metrics_factory = metrics_factory or WindowsCapacityMetrics
        self._conflicts_factory = conflicts_factory or WindowsStoryProcessConflicts
        self._metrics = self._conflicts = None
        self._lock = threading.Lock()

    def __call__(self):
        if not self.enabled:
            raise HostAdmissionError('disabled')
        if not self._lock.acquire(blocking=False):
            raise HostAdmissionError('busy')
        try:
            started = self.clock()
            if self.profile.capacity_sha256 != windows_service_probe_digest(
                    self.identity, self.directory, self.policy_id, self.images):
                raise ValueError('Policy configuration changed')
            require_private_directory(self.directory)
            if self.directory.resolve(strict=True) != self.directory:
                raise ValueError('Noncanonical capacity directory')
            if self._metrics is None:
                self._metrics = self._metrics_factory()
            if self._conflicts is None:
                self._conflicts = self._conflicts_factory()
            before = self._conflicts.capture(self.images)
            first = self._metrics.capture('cpu', self.directory)
            sample = self._metrics.capture('cpu', self.directory)
            after = self._conflicts.capture(self.images)
            now = self.clock()
            if (not math.isfinite(started) or not math.isfinite(now) or not 0 <= now - started <= 0.5
                    or any(type(s) is not WindowsStoryConflictSample or type(s.busy) is not bool
                        or type(s.observed_monotonic) not in (int, float)
                        or not math.isfinite(s.observed_monotonic)
                        or not started <= s.observed_monotonic <= now for s in (before, after))
                    or before.observed_monotonic > after.observed_monotonic):
                raise ValueError('Conflict observation unavailable')
            if before.busy or after.busy:
                raise HostAdmissionError('busy')
            if any(type(s) is not NativeCapacity or s.resource_id != 'cpu'
                    or any(type(v) is not int or v < 0 for v in (s.free_ram, s.free_disk, s.free_vram))
                    or s.free_vram != 0 or s.host_id != self.identity.host_id
                    or s.principal_sid != self.identity.principal_sid or s.volume_id != self.identity.volume_id
                    or type(s.uptime_seconds) not in (int, float)
                    or not math.isfinite(s.uptime_seconds) or s.uptime_seconds <= 0 for s in (first, sample)):
                raise ValueError('Native capacity binding unavailable')
            if first.uptime_seconds > sample.uptime_seconds:
                raise ValueError('Native boot observation changed')
            # The legacy field name carries operator policy here, not an owner-clearance receipt.
            return HostCapacity('cpu', self.policy_id, started,
                min(first.free_ram, sample.free_ram), min(first.free_disk, sample.free_disk), False)
        except HostAdmissionError:
            raise
        except Exception:
            raise HostAdmissionError() from None
        finally:
            self._lock.release()
