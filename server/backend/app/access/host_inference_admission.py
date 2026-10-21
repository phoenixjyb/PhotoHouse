"""Default-off, cooperating-process story admission; no service or model control.

The private local SQLite claim survives process loss. Never reclaim it by age,
PID inspection or maintenance clearance. Recovery is an offline operator task.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import math
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time
import uuid

from .private_storage import require_private_directory, require_private_file


class HostAdmissionError(RuntimeError):
    def __init__(self, reason='unavailable'):
        self.reason = reason if reason in {'busy', 'disabled', 'maintenance', 'unavailable'} else 'unavailable'
        super().__init__('Host story admission unavailable')


def _uuid(value):
    return type(value) is str and str(uuid.UUID(value)) == value


def _resource(value):
    return type(value) is str and (value == 'cpu' or re.fullmatch(
        r'gpu:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', value) is not None)


@dataclass(frozen=True, repr=False)
class HostResourceProfile:
    resource_id: str
    launch_sha256: str
    minimum_free_ram: int
    minimum_free_disk: int
    minimum_free_vram: int = 0

    def __post_init__(self):
        if (not _resource(self.resource_id) or type(self.launch_sha256) is not str
                or re.fullmatch(r'[0-9a-f]{64}', self.launch_sha256) is None
                or type(self.minimum_free_ram) is not int
                or not 0 < self.minimum_free_ram <= 256 * 1024**3
                or type(self.minimum_free_disk) is not int
                or not 0 < self.minimum_free_disk <= 1024**4
                or type(self.minimum_free_vram) is not int
                or (self.resource_id == 'cpu' and self.minimum_free_vram != 0)
                or (self.resource_id != 'cpu' and not 0 < self.minimum_free_vram <= 96 * 1024**3)):
            raise ValueError('Invalid host resource profile')


@dataclass(frozen=True, repr=False)
class HostCapacity:
    """Trusted probe evidence, not an inventory or GPU qualification mechanism."""
    resource_id: str
    clearance_id: str
    observed_monotonic: float
    free_ram: int
    free_disk: int
    external_busy: bool
    free_vram: int = 0


class HostPermit:
    def __init__(self, coordinator, operation_id, owner_id):
        self._coordinator, self._operation, self._owner = coordinator, operation_id, owner_id
        self._finished = False

    def finish(self, *, reconciled):
        if type(reconciled) is not bool:
            raise ValueError('Explicit reconciliation required')
        if not reconciled:
            return False
        if not self._finished:
            self._coordinator._release(self)
            self._finished = True
        return True


class HostInferenceAdmission:
    """One host claim, immediate busy, explicit maintenance and fresh capacity.

    Every cooperating process must use the same protected local directory.
    This does not govern external Windows/WSL jobs or prevent privileged writes.
    The injected probe must attest their agreed clearance and resource profile.
    """
    def __init__(self, directory, profile, *, capacity_probe, enabled=False,
                 monotonic=time.monotonic):
        if (type(profile) is not HostResourceProfile or not callable(capacity_probe)
                or type(enabled) is not bool or not callable(monotonic)):
            raise ValueError('Invalid host admission configuration')
        self.directory = Path(directory)
        self.profile, self.probe, self.enabled, self.clock = profile, capacity_probe, enabled, monotonic
        self.path = self.directory / 'host-story.sqlite3'
        self._identity = None

    def _profile_digest(self):
        return hashlib.sha256(json.dumps(vars(self.profile), sort_keys=True).encode()).hexdigest()

    def _storage(self):
        require_private_directory(self.directory)
        if self.directory.resolve(strict=True) != self.directory:
            raise HostAdmissionError()
        require_private_file(self.path)
        info = self.path.stat()
        identity = info.st_dev, info.st_ino
        if not info.st_ino or self._identity is not None and identity != self._identity:
            raise HostAdmissionError()
        self._identity = identity
        for suffix in ('-journal', '-wal', '-shm'):
            p = Path(str(self.path) + suffix)
            if p.exists() or p.is_symlink():
                require_private_file(p)

    @contextmanager
    def _transaction(self):
        if not self.enabled:
            raise HostAdmissionError('disabled')
        db = None
        try:
            self._storage()
            db = sqlite3.connect(self.path.as_uri() + '?mode=rw', uri=True, timeout=0,
                                 isolation_level=None)
            db.execute('PRAGMA synchronous=FULL')
            db.execute('BEGIN IMMEDIATE')
            self._storage()
            row = db.execute('SELECT version FROM control WHERE id=1').fetchone()
            if row != (1,):
                raise HostAdmissionError()
            yield db
            self._storage()
            db.commit()
        except HostAdmissionError:
            raise
        except sqlite3.OperationalError as error:
            reason = 'busy' if getattr(error, 'sqlite_errorcode', None) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED) else 'unavailable'
            raise HostAdmissionError(reason) from None
        except Exception:
            raise HostAdmissionError() from None
        finally:
            if db is not None:
                db.close()  # Roll back any uncommitted transaction.

    def set_maintenance(self, blocked, *, clearance_id=None):
        """Trusted operator seam, not an HTTP/model tool. No claim deletion."""
        if type(blocked) is not bool:
            raise ValueError('Explicit maintenance decision required')
        try:
            if not blocked and not _uuid(clearance_id):
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise ValueError('Explicit clearance identity required') from None
        with self._transaction() as db:
            if not blocked and db.execute('SELECT 1 FROM claim').fetchone() is not None:
                raise HostAdmissionError('busy')
            db.execute('UPDATE control SET maintenance=?, resource=?, clearance=?, profile=? WHERE id=1',
                       (int(blocked), self.profile.resource_id, None if blocked else clearance_id, self._profile_digest()))

    def acquire(self, operation_id):
        try:
            if not _uuid(operation_id):
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise ValueError('Invalid host operation identity') from None
        with self._transaction() as db:
            maintenance, resource, clearance, profile = db.execute(
                'SELECT maintenance, resource, clearance, profile FROM control WHERE id=1').fetchone()
            if maintenance != 0 or resource != self.profile.resource_id or not _uuid(clearance):
                raise HostAdmissionError('maintenance')
            if profile != self._profile_digest():
                raise HostAdmissionError()
            if db.execute('SELECT 1 FROM claim').fetchone() is not None:
                raise HostAdmissionError('busy')
            started = self.clock()
            sample = self.probe()
            now = self.clock()
            if (type(sample) is not HostCapacity or sample.resource_id != resource
                    or sample.clearance_id != clearance or type(sample.external_busy) is not bool
                    or sample.external_busy or type(sample.observed_monotonic) not in (int, float)
                    or not math.isfinite(now) or not 0 <= now - started <= 0.5
                    or not math.isfinite(sample.observed_monotonic)
                    or not 0 <= now - sample.observed_monotonic <= 2
                    or type(sample.free_ram) is not int or sample.free_ram < self.profile.minimum_free_ram
                    or type(sample.free_disk) is not int or sample.free_disk < self.profile.minimum_free_disk
                    or type(sample.free_vram) is not int or sample.free_vram < self.profile.minimum_free_vram):
                raise HostAdmissionError()
            permit = HostPermit(self, operation_id, str(uuid.uuid4()))
            db.execute('INSERT INTO claim VALUES (1, ?, ?, ?, ?)',
                       (permit._operation, permit._owner, resource, self.profile.launch_sha256))
        return permit

    def _release(self, permit):
        if type(permit) is not HostPermit or permit._coordinator is not self:
            raise HostAdmissionError()
        with self._transaction() as db:
            removed = db.execute('DELETE FROM claim WHERE id=1 AND operation=? AND owner=? AND resource=? AND launch=?',
                (permit._operation, permit._owner, self.profile.resource_id, self.profile.launch_sha256)).rowcount
            if removed != 1:
                raise HostAdmissionError()


def initialize_host_admission(directory, *, enabled=False):
    """Create a fresh private synthetic/operator store BLOCKED; never overwrite."""
    if enabled is not True:
        raise HostAdmissionError('disabled')
    root = Path(directory)
    require_private_directory(root)
    if root.resolve(strict=True) != root or any(root.iterdir()):
        raise HostAdmissionError()
    path = root / 'host-story.sqlite3'
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(descriptor)
    require_private_file(path)
    db = sqlite3.connect(path.as_uri() + '?mode=rw', uri=True)
    try:
        db.executescript('''PRAGMA synchronous=FULL;
            CREATE TABLE control (id INTEGER PRIMARY KEY CHECK(id=1), version INTEGER NOT NULL,
                maintenance INTEGER NOT NULL, resource TEXT, clearance TEXT, profile TEXT);
            CREATE TABLE claim (id INTEGER PRIMARY KEY CHECK(id=1), operation TEXT NOT NULL,
                owner TEXT NOT NULL, resource TEXT NOT NULL, launch TEXT NOT NULL);
            INSERT INTO control VALUES (1, 1, 1, NULL, NULL, NULL);''')
        db.commit()
    finally:
        db.close()
