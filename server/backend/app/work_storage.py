"""Admission for NEW development outputs; never relocates existing runtime data.

Windows bulk producers share a nonblocking per-volume lock. Receipts and partial
outputs are retained, including failures. This is admission, not a disk quota or
an OS sandbox for arbitrary programs.
"""
from __future__ import annotations

from contextlib import contextmanager, ExitStack
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import threading
import uuid

from .access.private_storage import require_private_directory, require_private_file

RESERVE = 1024**3
_leases = threading.local()
_process_lock = threading.RLock()  # TEMP and tempfile.tempdir are process-wide.


class StorageRefused(ValueError):
    pass


def direct(path):
    """Check every existing component before resolution can hide a junction."""
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts or any(ord(c) < 32 for c in str(path)):
        raise StorageRefused('absolute_direct_local_path_required')
    if os.name == 'nt':
        if str(path).startswith(('\\\\', '//')) or len(path.drive) != 2:
            raise StorageRefused('local_drive_required')
        for part in path.parts[1:]:
            if ':' in part or part.endswith(('.', ' ')) or Path(part).is_reserved():
                raise StorageRefused('unsafe_windows_path')
    for item in reversed((path, *path.parents)):
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise StorageRefused('reparse_path_refused')
    return path


def volume(path):
    path = direct(path)
    existing = path
    while not existing.exists():
        if existing == existing.parent:
            raise StorageRefused('volume_unavailable')
        existing = existing.parent
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        get_path = kernel.GetVolumePathNameW
        get_path.argtypes = (wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD)
        get_path.restype = wintypes.BOOL
        get_name = kernel.GetVolumeNameForVolumeMountPointW
        get_name.argtypes = (wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD)
        get_name.restype = wintypes.BOOL
        get_type = kernel.GetDriveTypeW
        get_type.argtypes = (wintypes.LPCWSTR,)
        get_type.restype = wintypes.UINT
        def identify(selected):
            mount, name = ctypes.create_unicode_buffer(1024), ctypes.create_unicode_buffer(1024)
            if not get_path(str(selected), mount, len(mount)) or get_type(mount.value) != 3:
                raise StorageRefused('fixed_local_volume_required')
            if not get_name(mount.value, name, len(name)):
                raise StorageRefused('volume_identity_unavailable')
            return name.value.lower(), Path(mount.value)
        identity, mount = identify(existing)
        system = ctypes.create_unicode_buffer(1024)
        get_system = kernel.GetSystemWindowsDirectoryW
        get_system.argtypes = (wintypes.LPWSTR, wintypes.UINT)
        get_system.restype = wintypes.UINT
        size = get_system(system, len(system))
        if not 0 < size < len(system):
            raise StorageRefused('system_volume_identity_unavailable')
        if identity == identify(system.value)[0]:
            raise StorageRefused('system_volume_refused')
        return identity, mount
    return existing.stat().st_dev, existing


def target(path):
    path = direct(path)
    volume(path)
    if os.path.lexists(path):
        raise StorageRefused('output_must_be_absent')
    if not path.parent.is_dir():
        raise StorageRefused('output_parent_unavailable')
    if os.name == 'nt':
        require_private_directory(path.parent)
    return path


def private_mkdir(path):
    path = direct(path)
    volume(path)
    # Native Python >=3.12.4 creates mode=0700 Windows directories with a
    # restricted DACL. Verify it rather than assuming chmod proves privacy.
    path.mkdir(mode=0o700)
    require_private_directory(path)
    return path


def work_root():
    configured = os.environ.get('PHOTOHOUSE_WORK_ROOT')
    if not configured and os.name != 'nt':
        raise StorageRefused('explicit_work_root_required')
    root = direct(configured or 'D:/PhotoHouseWork')
    volume(root)
    if not root.exists():
        private_mkdir(root)
    require_private_directory(root)
    return root


def new_run():
    root = work_root()
    runs = root / 'runs'
    if not runs.exists():
        private_mkdir(runs)
    require_private_directory(runs)
    return private_mkdir(runs / str(uuid.uuid4()))


def check_space(components, reserve=RESERVE):
    """Components are (destination, purpose, reviewed maximum bytes)."""
    if type(reserve) is not int or reserve < RESERVE:
        raise StorageRefused('invalid_safety_reserve')
    totals = {}
    for path, purpose, size in components:
        if type(size) is not int or size < 0 or not isinstance(purpose, str) or not purpose:
            raise StorageRefused('invalid_peak_budget')
        identity, mount = volume(path)
        previous = totals.get(identity, (mount, 0))
        totals[identity] = (mount, previous[1] + size)
    if not totals:
        raise StorageRefused('explicit_peak_budget_required')
    for mount, size in totals.values():
        if shutil.disk_usage(mount).free < size + reserve:
            raise StorageRefused('insufficient_peak_space')
    return totals


def _private_child(parent, name):
    path = direct(parent / name)
    if not path.exists():
        try:
            private_mkdir(path)
        except FileExistsError:
            pass
    require_private_directory(path)
    return path


@contextmanager
def _volume_lock(mount):
    held = getattr(_leases, 'held', {})
    key = str(mount).lower()
    if key in held:
        yield held[key]
        return
    base = _private_child(mount, 'PhotoHouseWork')
    admission = _private_child(base, 'admission')
    path = direct(admission / 'volume.lock')
    with path.open('a+b') as stream:
        require_private_file(path)
        if stream.seek(0, 2) == 0:
            stream.write(b'0'); stream.flush()
        stream.seek(0)
        import msvcrt
        try:
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise StorageRefused('volume_operation_busy') from None
        try:
            held[key] = admission
            _leases.held = held
            yield admission
        finally:
            held.pop(key, None)
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def _bytes(paths):
    total = 0
    for path in paths:
        path = direct(path)
        if path.is_file():
            total += path.stat().st_size
        elif path.is_dir():
            for parent, directories, files in os.walk(path, followlinks=False):
                for name in (*directories, *files):
                    item = direct(Path(parent) / name)
                    if item.is_file():
                        total += item.stat().st_size
    return total


@contextmanager
def operation(outputs, components):
    """Admit before data writes and redirect this process's temporary files.

    On Windows the lock is held through verification/closure; unmanaged writers
    still require a later free-space recheck. POSIX keeps portable caller checks
    but does not claim Windows volume-lock enforcement.
    """
    outputs = [target(p) for p in outputs]
    if not outputs or len(set(outputs)) != len(outputs):
        raise StorageRefused('distinct_outputs_required')
    if any(left != right and left.is_relative_to(right) for left in outputs for right in outputs):
        raise StorageRefused('overlapping_outputs_refused')
    components = list(components)
    totals = check_space(components)
    if any(volume(path)[0] not in totals for path in outputs):
        raise StorageRefused('unbudgeted_output_volume')
    with _process_lock, ExitStack() as stack:
        admissions = []
        if os.name == 'nt':
            for identity in sorted(totals):
                admissions.append(stack.enter_context(_volume_lock(totals[identity][0])))
            check_space(components)
            # Parent identity/privacy can change while acquiring a lock.
            for path in outputs:
                target(path)
            receipt_root = private_mkdir(admissions[0] / str(uuid.uuid4()))
        else:
            receipt_root = private_mkdir(outputs[0].parent / ('.work-' + str(uuid.uuid4())))
        temporary = private_mkdir(receipt_root / 'temporary')
        env_keys = ('TEMP', 'TMP', 'TMPDIR', 'SQLITE_TMPDIR')
        before = {key: os.environ.get(key) for key in env_keys}
        previous_temp = tempfile.tempdir
        os.environ.update({key: str(temporary) for key in env_keys})
        tempfile.tempdir = str(temporary)
        record = {'version': 1, 'operation_id': receipt_root.name, 'state': 'running',
                  'outputs': [str(p) for p in outputs],
                  'planned_bytes': sum(size for _, _, size in components),
                  'components': [{'purpose': purpose, 'bytes': size} for _, purpose, size in components],
                  'reserve_per_volume': RESERVE, 'actual_bytes': None}
        receipt = receipt_root / 'receipt.json'
        def save():
            direct(receipt)
            if receipt.exists():
                require_private_file(receipt)
            flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
            with os.fdopen(os.open(receipt, flags, 0o600), 'w', encoding='utf-8') as stream:
                json.dump(record, stream, sort_keys=True); stream.write('\n')
                stream.flush(); os.fsync(stream.fileno())
            require_private_file(receipt)
        try:
            save()
            yield temporary
        except BaseException:
            record['state'] = 'failed_uncertain'
            raise
        else:
            record['state'] = 'closed'
        finally:
            for key, value in before.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            tempfile.tempdir = previous_temp
            try:
                sidecars = [Path(str(p) + suffix) for p in outputs
                            for suffix in ('-wal', '-shm', '-journal')]
                record['actual_bytes'] = _bytes([*outputs, *sidecars, temporary])
            except (OSError, ValueError):
                record['state'] = 'failed_uncertain'
            exceeded = (record['actual_bytes'] is not None and
                        record['actual_bytes'] > record['planned_bytes'] and record['state'] == 'closed')
            if exceeded:
                record['state'] = 'failed_uncertain'
            save()
            if exceeded:
                raise StorageRefused('declared_work_budget_exceeded')
