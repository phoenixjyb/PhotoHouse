"""Default-off selected-story generation bound to a private owned worker.

One bounded file exchange per exact scope; no HTTP endpoint, provider discovery,
model installation, source lookup, automatic retry or default app binding.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace
import math
import hashlib
import json
import ntpath
import os
from pathlib import Path
import stat
import tempfile

from .memory_narrative import (
    MAX_OUTPUT_BYTES, MAX_PROVIDER_BYTES, _generation_payload, _json_bytes,
    _strict_loads, _validate_bundle, validate_narrative,
)
from .host_inference_admission import HostAdmissionError, HostInferenceAdmission
from .private_storage import require_private_directory, require_private_file
from .selected_story_local import _MODEL
from .selected_story_native import NativeStoryLaunch, NativeStoryOwnerError, NativeStoryProcessOwner
from .selected_story_operations import PreparationScope

REQUEST_ENV = 'PHOTOHOUSE_NATIVE_STORY_REQUEST'
RESPONSE_ENV = 'PHOTOHOUSE_NATIVE_STORY_RESPONSE'
MAX_REQUEST_BYTES = 128 * 1024


class ProcessSelectedStoryError(RuntimeError):
    def __init__(self, category):
        self.category = category if category in {
            'disabled', 'closed', 'busy', 'invalid_input', 'cancelled',
            'worker', 'invalid_response', 'cleanup',
        } else 'worker'
        super().__init__('Process selected-story provider unavailable')


@dataclass(repr=False)
class _Exchange:
    scope: PreparationScope
    exchange_root: Path | None = None
    parent_identity: tuple | None = None
    directory: Path | None = None
    identity: tuple | None = None
    owner: NativeStoryProcessOwner | None = None
    host_permit: object = None
    setup: asyncio.Task | None = None
    reading: asyncio.Task | None = None
    cleanup: asyncio.Task | None = None
    disposal: asyncio.Task | None = None
    settled: asyncio.Event = field(default_factory=asyncio.Event)


def _regular(path):
    value = path.lstat()
    if (not stat.S_ISREG(value.st_mode) or value.st_nlink != 1
            or hasattr(os, 'getuid') and value.st_uid != os.getuid()
            or getattr(value, 'st_file_attributes', 0) & 0x400):
        raise ValueError('Invalid exchange file')
    if os.name == 'nt':
        require_private_file(path)
    return value


def _directory(call):
    value = call.directory.lstat()
    if (not stat.S_ISDIR(value.st_mode) or stat.S_ISLNK(value.st_mode)
            or getattr(value, 'st_file_attributes', 0) & 0x400
            or (value.st_dev, value.st_ino) != call.identity
            or os.name == 'posix' and (value.st_uid != os.getuid() or value.st_mode & 0o077)):
        raise ValueError('Invalid exchange directory')
    require_private_directory(call.directory)
    if call.exchange_root is not None:
        _private_exchange_root(call)
        if call.directory.parent != call.exchange_root:
            raise ValueError('Invalid exchange parent')


def _exchange_root_path(value):
    """Validate an explicit root's spelling without touching the filesystem."""
    if not isinstance(value, (str, Path)) or not value:
        raise ValueError('Invalid exchange root')
    raw = os.fspath(value)
    if (type(raw) is not str or not raw or raw.startswith(('\\\\', '//'))
            or any(ord(character) < 32 for character in raw)):
        raise ValueError('Invalid exchange root')
    path = Path(raw)
    if (not path.is_absolute() or path == Path(path.anchor) or '..' in path.parts
            or ntpath.splitdrive(raw)[0].startswith('\\\\')):
        raise ValueError('Invalid exchange root')
    return path


def _private_exchange_root(call):
    """Require the same private, canonical configured parent on every use."""
    root = call.exchange_root
    if root is None:
        return None
    try:
        info = root.lstat()
        resolved = root.resolve(strict=True)
    except (OSError, RuntimeError):
        raise ValueError('Invalid exchange root') from None
    if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)
            or getattr(info, 'st_file_attributes', 0) & 0x400
            or os.path.normcase(os.path.abspath(str(resolved))) !=
               os.path.normcase(os.path.abspath(str(root)))):
        raise ValueError('Invalid exchange root')
    require_private_directory(root)
    identity = (info.st_dev, info.st_ino)
    if call.parent_identity is None:
        call.parent_identity = identity
    elif call.parent_identity != identity:
        raise ValueError('Changed exchange root')
    return identity


def process_launch_digest(launch, *, exchange_root=None):
    """Pin the launch recipe and, when explicit, its private IPC parent."""
    if type(launch) is not NativeStoryLaunch:
        raise ValueError('Invalid process launch')
    value = {key: getattr(launch, key) for key in (
        'executable', 'executable_sha256', 'argv', 'cwd', 'memory_limit',
        'process_limit', 'minimum_free_ram')}
    value['environment'] = dict(launch.environment)
    if exchange_root is not None:
        value['exchange_root'] = str(_exchange_root_path(exchange_root))
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
        separators=(',', ':')).encode('utf-8')).hexdigest()


class ProcessSelectedStoryProvider:
    """Trusted worker code must execute inference inside its owned containment.

    File protocol binding is not native Windows, model locality, dependency,
    filesystem ACL/quota, image identity or GPU qualification.
    """
    proof_domain = 'owned_story_exchange'

    def __init__(self, launch, model, *, kernel_factory, enabled=False, timeout=45,
                 cleanup_seconds=5, host_admission=None, exchange_root=None):
        if (type(launch) is not NativeStoryLaunch or not callable(kernel_factory)
                or type(model) is not str or not _MODEL.fullmatch(model) or '://' in model
                or type(enabled) is not bool or type(timeout) not in (int, float)
                or not math.isfinite(timeout) or not 0 < timeout <= 60
                or len(launch.environment) > 62
                or {REQUEST_ENV, RESPONSE_ENV} & {k.upper() for k in launch.environment}):
            raise ValueError('Invalid process selected-story configuration')
        selected_root = None if exchange_root is None else _exchange_root_path(exchange_root)
        if host_admission is not None and (type(host_admission) is not HostInferenceAdmission
                or host_admission.profile.launch_sha256 != process_launch_digest(
                    launch, exchange_root=selected_root)):
            raise ValueError('Host admission launch binding mismatch')
        self.host_admission = host_admission
        # Validate cleanup configuration without constructing a native kernel.
        NativeStoryProcessOwner(launch, kernel_factory=kernel_factory,
                                cleanup_seconds=cleanup_seconds)
        self.launch, self.model, self.kernel_factory = launch, model, kernel_factory
        self.exchange_root = selected_root
        self.enabled, self.timeout, self.cleanup_seconds = enabled, float(timeout), cleanup_seconds
        self._loop = self._active = self._last_settled_scope = None
        self._closed = False

    def _bind(self):
        loop = asyncio.get_running_loop()
        if self._loop is None:
            self._loop = loop
        elif self._loop is not loop:
            raise ProcessSelectedStoryError('worker')

    @staticmethod
    def _check(scope):
        if scope.cancelled():
            raise ProcessSelectedStoryError('cancelled')

    def _setup(self, call, payload):
        self._check(call.scope)
        if self.host_admission is not None:
            call.host_permit = self.host_admission.acquire(call.scope.operation_id)
        self._check(call.scope)
        # Recorded immediately; retained task owns all setup even if waiter leaves.
        call.exchange_root = self.exchange_root
        if call.exchange_root is None:
            call.directory = Path(tempfile.mkdtemp(prefix='photohouse-story-'))
        else:
            _private_exchange_root(call)
            call.directory = Path(tempfile.mkdtemp(prefix='photohouse-story-',
                                                   dir=str(call.exchange_root)))
        value = call.directory.lstat()
        call.identity = (value.st_dev, value.st_ino)
        os.chmod(call.directory, 0o700)
        _directory(call)
        request = call.directory / 'request.json'
        descriptor = os.open(request, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'wb') as stream:
            _regular(request)  # Verify inherited Windows DACL before source words.
            stream.write(payload)
        environment = dict(self.launch.environment)
        environment.update({REQUEST_ENV: str(request),
                            RESPONSE_ENV: str(call.directory / 'response.json')})
        spec = replace(self.launch, environment=environment)
        call.owner = NativeStoryProcessOwner(spec, kernel_factory=self.kernel_factory,
                                            enabled=True, cleanup_seconds=self.cleanup_seconds)

    @staticmethod
    def _read(call):
        _directory(call)
        path = call.directory / 'response.json'
        before = _regular(path)
        if before.st_size > MAX_PROVIDER_BYTES:
            raise ValueError('Response limit')
        flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, 'rb') as stream:
            opened = os.fstat(stream.fileno())
            if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1
                    or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)):
                raise ValueError('Response identity')
            data = stream.read(MAX_PROVIDER_BYTES + 1)
        if len(data) > MAX_PROVIDER_BYTES:
            raise ValueError('Response limit')
        return data

    async def prepare(self, bundle, scope):
        self._bind()
        if not self.enabled:
            raise ProcessSelectedStoryError('disabled')
        if self._closed:
            raise ProcessSelectedStoryError('closed')
        if type(scope) is not PreparationScope:
            raise ProcessSelectedStoryError('invalid_input')
        if self._active is not None:
            raise ProcessSelectedStoryError('busy')
        try:
            self._check(scope)
            clean = _validate_bundle(bundle, allow_draft=True)
            if (clean['version'] != 3 or clean['target']['id'] != scope.operation_id
                    or self._last_settled_scope is not None and
                    self._last_settled_scope.operation_id == scope.operation_id):
                raise ValueError('Invalid scope')
            payload = _json_bytes({'version': 1, 'operation_id': scope.operation_id,
                'generation': _generation_payload(clean, 'narrative', self.model)},
                'process generation request', MAX_REQUEST_BYTES)
            remaining = min(self.timeout, scope.deadline_monotonic - scope._clock())
            if not math.isfinite(remaining) or remaining <= 0:
                raise ProcessSelectedStoryError('cancelled')
        except ProcessSelectedStoryError:
            raise
        except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
            raise ProcessSelectedStoryError('invalid_input') from None
        call = _Exchange(scope)
        self._active = call
        try:
            async with asyncio.timeout(remaining):
                call.setup = asyncio.create_task(asyncio.to_thread(self._setup, call, payload))
                await asyncio.shield(call.setup)
                self._check(scope)
                await call.owner.begin(scope)
                await call.owner.wait_for_exit(scope)
                if await call.owner.stop_and_reconcile(scope) is not True:
                    raise ProcessSelectedStoryError('cleanup')
                self._check(scope)
                call.reading = asyncio.create_task(asyncio.to_thread(self._read, call))
                body = await asyncio.shield(call.reading)
                response = _strict_loads(body)
                if (type(response) is not dict or set(response) != {'version', 'operation_id', 'model', 'result'}
                        or type(response['version']) is not int or response['version'] != 1
                        or response['operation_id'] != scope.operation_id or response['model'] != self.model):
                    raise ValueError('Response binding')
                _json_bytes(response['result'], 'worker result', MAX_OUTPUT_BYTES)
                result = validate_narrative(response['result'], clean)
                self._check(scope)
                return result
        except (ProcessSelectedStoryError, HostAdmissionError):
            raise
        except TimeoutError:
            raise ProcessSelectedStoryError('cancelled') from None
        except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
            raise ProcessSelectedStoryError('invalid_response') from None
        except NativeStoryOwnerError as error:
            raise ProcessSelectedStoryError('cancelled' if error.category == 'cancelled' else 'worker') from None
        except Exception:
            raise ProcessSelectedStoryError('worker') from None
        finally:
            call.settled.set()

    @staticmethod
    def _dispose(call):
        if call.directory is None:
            return True
        try:
            _directory(call)
            entries = set()
            with os.scandir(call.directory) as listing:
                for entry in listing:
                    if entry.name not in {'request.json', 'response.json'} or len(entries) >= 2:
                        return False
                    entries.add(call.directory / entry.name)
            for path in entries:
                _regular(path)
            for path in entries:
                if call.exchange_root is not None:
                    _directory(call)
                path.unlink()
            if call.exchange_root is not None:
                _directory(call)
            call.directory.rmdir()
            call.directory = None
            return True
        except Exception:
            return False

    async def _reconcile(self, call):
        await call.settled.wait()
        for task in (call.setup, call.reading):
            if task is not None:
                try:
                    await asyncio.shield(task)
                except Exception:
                    pass
        if call.owner is not None and await call.owner.close() is not True:
            return False
        if call.disposal is None or call.disposal.done() and call.disposal.result() is not True:
            call.disposal = asyncio.create_task(asyncio.to_thread(self._dispose, call))
        proof = await asyncio.shield(call.disposal)
        if proof is True and call.host_permit is not None:
            try:
                proof = await asyncio.to_thread(call.host_permit.finish, reconciled=True)
            except Exception:
                proof = False  # Durable claim stays occupied on uncertain settlement.
        if proof is True and self._active is call:
            self._active = None
            self._last_settled_scope = call.scope
        return proof is True

    async def stop_and_reconcile(self, scope):
        self._bind()
        if type(scope) is not PreparationScope:
            return False
        call = self._active
        if call is None or self._last_settled_scope is scope:
            return True
        if call.scope is not scope:
            return False
        if (call.cleanup is None or call.cleanup.cancelled() or
                call.cleanup.done() and (call.cleanup.exception() is not None or call.cleanup.result() is not True)):
            call.cleanup = asyncio.create_task(self._reconcile(call))
        return await asyncio.shield(call.cleanup)

    async def close(self):
        self._bind()
        self._closed = True
        call = self._active
        if call is None:
            return True
        # Caller must first fence/cancel active prepare through operation lifecycle.
        return await self.stop_and_reconcile(call.scope)
