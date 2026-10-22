"""Durable, bounded progress checkpoints for semantic qualification.

The journal contains timing and work counters only. Its status is diagnostic
progress and never represents relevance acceptance or activation approval.
No model, database, or provider module is imported by this module.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import math
import os
from pathlib import Path
import re
import secrets
import stat
import threading
import time


SCHEMA = "photohouse.semantic_qualification_progress.v1"
CHECKPOINT_SCHEMA = "photohouse.semantic_qualification_checkpoint.v1"
PHASES = (
    "initial_audit", "artifact_validation", "initial_vector_hashes",
    "review_validation", "bulk_vectors", "fixture", "source_projection",
    "eligibility", "model_bind_verify", "canary", "final_model_verify",
    "final_vector_hashes", "final_audit", "final_review_validation", "report",
)
OPERATIONS = (
    "audit_json", "audit_source_stat", "audit_vector_read", "audit_checkpoint_verify",
    "bulk_cohort", "bulk_vector_read", "bulk_components", "bulk_write",
    "bulk_published_hash", "fixture_build", "scoped_source", "source_digest",
    "coverage_inputs", "coverage_review", "coverage_policy", "file_hash",
)
_PHASE_SET = frozenset(PHASES)
_OPERATION_SET = frozenset(OPERATIONS)
_MAX_RECORDS = 512
_MAX_RECORD_BYTES = 16 * 1024
_MAX_TOTAL_BYTES = 8 * 1024 * 1024
_MAX_UNITS = 2**53 - 1
_CHECKPOINT_NAME = re.compile(r"checkpoint-([0-9]{6})\.json\Z", re.ASCII)
_TEMP_NAME = re.compile(r"\.checkpoint-[0-9]{6}\.json\.[0-9a-f]{32}\.tmp\Z", re.ASCII)
_FIELDS = frozenset(("schema", "diagnostic_only", "qualification_passed",
    "sequence", "event", "status", "phase", "elapsed_ms", "completed_units",
    "dropped_records", "operations"))
_EVENTS = frozenset(("phase_started", "phase_completed", "phase_failed", "progress", "closed"))
_STATUSES = frozenset(("running", "failed", "completed"))


class QualificationJournalError(ValueError):
    """Fixed refusal for invalid or unsafe journal state."""

    def __init__(self):
        super().__init__("semantic_qualification_journal_unavailable")


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False).encode("ascii")


def _private_storage():
    # Import only when a journal is used, keeping module import free of project
    # or model initialization side effects.
    from app.access.private_storage import (require_private_directory,
        require_private_file, sync_directory)
    return require_private_directory, require_private_file, sync_directory


def _parent_identity(path: Path) -> tuple[int, int]:
    info = path.lstat()
    if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)
            or getattr(info, "st_file_attributes", 0) & 0x400):
        raise QualificationJournalError()
    return info.st_dev, info.st_ino


def _elapsed_ms(start: float, now: float) -> int:
    if type(now) not in (int, float) or not math.isfinite(now):
        raise QualificationJournalError()
    elapsed = max(0, int((now - start) * 1000))
    if elapsed > _MAX_UNITS:
        raise QualificationJournalError()
    return elapsed


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise QualificationJournalError()
        result[key] = value
    return result


def _decode_record(raw: bytes, expected_sequence: int) -> dict:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda _value: (_ for _ in ()).throw(QualificationJournalError()))
        if (type(value) is not dict or set(value) != _FIELDS
                or value["schema"] != CHECKPOINT_SCHEMA
                or value["diagnostic_only"] is not True
                or value["qualification_passed"] is not False
                or type(value["sequence"]) is not int or value["sequence"] != expected_sequence
                or value["event"] not in _EVENTS or value["status"] not in _STATUSES
                or (value["phase"] is not None and value["phase"] not in _PHASE_SET)
                or type(value["elapsed_ms"]) not in (int, float)
                or not math.isfinite(value["elapsed_ms"])
                or not 0 <= value["elapsed_ms"] <= _MAX_UNITS
                or type(value["completed_units"]) is not int
                or not 0 <= value["completed_units"] <= _MAX_UNITS
                or type(value["dropped_records"]) is not int
                or not 0 <= value["dropped_records"] <= _MAX_UNITS
                or type(value["operations"]) is not dict
                or set(value["operations"]) != _OPERATION_SET):
            raise QualificationJournalError()
        for item in value["operations"].values():
            if (type(item) is not dict or set(item) != {"calls", "errors", "inclusive_ms", "max_ms"}
                    or any(type(item[key]) is not int or item[key] < 0
                        for key in ("calls", "errors"))
                    or any(type(item[key]) not in (int, float) or not math.isfinite(item[key])
                        or not 0 <= item[key] <= _MAX_UNITS
                        for key in ("inclusive_ms", "max_ms"))
                    or item["errors"] > item["calls"]
                    or item["max_ms"] > item["inclusive_ms"]):
                raise QualificationJournalError()
        return value
    except QualificationJournalError:
        raise
    except Exception:
        raise QualificationJournalError() from None


def _read_bytes(path: Path) -> bytes:
    require_private_directory, require_private_file, _sync_directory = _private_storage()
    require_private_file(path)
    before = path.lstat()
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        identity = (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
        if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1
                or identity != (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                or opened.st_size > _MAX_RECORD_BYTES):
            raise QualificationJournalError()
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            raw = stream.read(_MAX_RECORD_BYTES + 1)
        after = path.lstat()
        if (len(raw) > _MAX_RECORD_BYTES or
                (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != identity[:4]):
            raise QualificationJournalError()
        require_private_directory(path.parent)
        return raw
    finally:
        os.close(descriptor)


class QualificationJournal:
    """Write private progress checkpoints to a newly-created directory."""

    def __init__(self, directory, *, clock=time.monotonic):
        if not callable(clock):
            raise QualificationJournalError()
        try:
            from qualify_semantic_pair import output_target
            target = output_target(Path(directory))
            require_private_directory, _require_private_file, _sync_directory = _private_storage()
            parent_identity = _parent_identity(target.parent)
            require_private_directory(target.parent)
            target.mkdir(mode=0o700)
            require_private_directory(target)
            if _parent_identity(target.parent) != parent_identity:
                raise QualificationJournalError()
        except QualificationJournalError:
            raise
        except Exception:
            raise QualificationJournalError() from None
        self.directory = target
        self._parent_identity = parent_identity
        self._clock = clock
        self._lock = threading.RLock()
        self._started = clock()
        if type(self._started) not in (int, float) or not math.isfinite(self._started):
            raise QualificationJournalError()
        self._last_clock = self._started
        self._last_pulse_clock = self._started
        self._sequence = 0
        self._bytes = 0
        self._current_phase = None
        self._phase_started = None
        self._completed_units = 0
        self._status = "running"
        self._closed = False
        self._report_completed = False
        self._failed = False
        self._dropped_records = 0
        self._totals = {name: {"calls": 0, "errors": 0, "inclusive_ms": 0}
            for name in PHASES}
        self._operations = {name: {"calls": 0, "errors": 0,
            "inclusive_ms": 0.0, "max_ms": 0.0, "_compensation": 0.0}
            for name in OPERATIONS}
        self._directory_identity = _parent_identity(self.directory)
        _require_private_directory, _require_private_file, sync_directory = _private_storage()
        sync_directory(self.directory.parent)

    def _now(self) -> float:
        value = self._clock()
        if type(value) not in (int, float) or not math.isfinite(value):
            raise QualificationJournalError()
        self._last_clock = max(self._last_clock, value)
        return self._last_clock

    def _progress_snapshot(self, now: float | None = None) -> dict:
        now = self._now() if now is None else now
        phases = {name: dict(values) for name, values in self._totals.items()}
        active_elapsed = None
        if self._current_phase is not None:
            active_elapsed = _elapsed_ms(self._phase_started, now)
        return {
            "schema": SCHEMA,
            "diagnostic_only": True,
            "qualification_passed": False,
            "elapsed_ms": _elapsed_ms(self._started, now),
            "sequence": self._sequence,
            "status": self._status,
            "current_phase": self._current_phase,
            "completed_units": self._completed_units,
            "active_elapsed_ms": active_elapsed,
            "dropped_records": self._dropped_records,
            "phases": phases,
            "operations": {name: {key: value for key, value in values.items()
                if key != "_compensation"} for name, values in self._operations.items()},
        }

    def snapshot(self) -> dict:
        """Return a detached JSON-shaped progress view."""
        with self._lock:
            value = self._progress_snapshot()
            return json.loads(_canonical(value).decode("ascii"))

    def _record(self, event: str, phase: str | None, *, final=False, now=None) -> bool:
        with self._lock:
            if self._closed and not final:
                raise QualificationJournalError()
            if event not in _EVENTS or (phase is not None and phase not in _PHASE_SET):
                raise QualificationJournalError()
            now = self._now() if now is None else now
            next_sequence = self._sequence + 1
            record = {
            "schema": CHECKPOINT_SCHEMA,
            "diagnostic_only": True,
            "qualification_passed": False,
            "sequence": next_sequence,
            "event": event,
            "status": self._status,
            "phase": phase,
            "elapsed_ms": _elapsed_ms(self._started, now),
            "completed_units": self._completed_units,
            "dropped_records": self._dropped_records,
            "operations": {name: {key: value for key, value in values.items()
                if key != "_compensation"} for name, values in self._operations.items()},
            }
            raw = _canonical(record) + b"\n"
            if len(raw) > _MAX_RECORD_BYTES:
                raise QualificationJournalError()
            max_count = _MAX_RECORDS if final else _MAX_RECORDS - 1
            max_bytes = _MAX_TOTAL_BYTES if final else _MAX_TOTAL_BYTES - _MAX_RECORD_BYTES
            if next_sequence > max_count or self._bytes + len(raw) > max_bytes:
                self._dropped_records += 1
                return False
            require_private_directory, require_private_file, sync_directory = _private_storage()
            if _parent_identity(self.directory.parent) != self._parent_identity:
                raise QualificationJournalError()
            require_private_directory(self.directory)
            temp = self.directory / f".checkpoint-{next_sequence:06d}.json.{secrets.token_hex(16)}.tmp"
            final_path = self.directory / f"checkpoint-{next_sequence:06d}.json"
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
            descriptor = None
            owned = None
            try:
                descriptor = os.open(temp, flags, 0o600)
                opened = os.fstat(descriptor)
                owned = (opened.st_dev, opened.st_ino)
                require_private_file(temp)
                with os.fdopen(descriptor, "wb", closefd=False) as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(descriptor)
                # Windows CRT descriptors do not grant delete sharing. Close
                # before linking/unlinking, as in the bulk-vector publisher.
                os.close(descriptor)
                descriptor = None
                info = temp.lstat()
                if (not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode)
                        or getattr(info, "st_file_attributes", 0) & 0x400
                        or info.st_nlink != 1 or info.st_size != len(raw)
                        or (info.st_dev, info.st_ino) != owned):
                    raise QualificationJournalError()
                if _parent_identity(self.directory) != self._directory_identity:
                    raise QualificationJournalError()
                if _parent_identity(self.directory.parent) != self._parent_identity:
                    raise QualificationJournalError()
                os.link(temp, final_path, follow_symlinks=False)
                os.unlink(temp)
                temp = None
                require_private_file(final_path)
                sync_directory(self.directory)
                require_private_directory(self.directory)
                if _parent_identity(self.directory.parent) != self._parent_identity:
                    raise QualificationJournalError()
                self._sequence = next_sequence
                self._bytes += len(raw)
                return True
            except FileExistsError:
                raise QualificationJournalError() from None
            except QualificationJournalError:
                raise
            except Exception:
                raise QualificationJournalError() from None
            finally:
                if descriptor is not None:
                    try:
                        os.close(descriptor)
                    except OSError:
                        pass
                if temp is not None and owned is not None:
                    try:
                        info = temp.lstat()
                        if (info.st_dev, info.st_ino) == owned:
                            temp.unlink()
                    except OSError:
                        pass

    @contextmanager
    def phase(self, name: str):
        with self._lock:
            if (self._closed or self._current_phase is not None or type(name) is not str
                    or name not in _PHASE_SET):
                raise QualificationJournalError()
            now = self._now()
            if self._totals[name]["calls"] >= _MAX_UNITS:
                raise QualificationJournalError()
            self._current_phase = name
            self._phase_started = now
            self._completed_units = 0
            self._totals[name]["calls"] += 1
            self._record("phase_started", name, now=now)
        try:
            yield self
        except BaseException:
            with self._lock:
                ended = self._now()
                elapsed = _elapsed_ms(now, ended)
                self._totals[name]["errors"] += 1
                self._totals[name]["inclusive_ms"] += elapsed
                self._status = "failed"
                self._failed = True
                self._current_phase = None
                self._phase_started = None
                try:
                    self._record("phase_failed", name, now=ended)
                except BaseException:
                    # Keep the operation's original exception as the primary error.
                    pass
            raise
        else:
            with self._lock:
                ended = self._now()
                elapsed = _elapsed_ms(now, ended)
                self._totals[name]["inclusive_ms"] += elapsed
                self._current_phase = None
                self._phase_started = None
                self._record("phase_completed", name, now=ended)
                if name == "report":
                    self._report_completed = True
                    self._status = "failed" if self._failed else "completed"

    def pulse(self, units: int = 1) -> None:
        with self._lock:
            if (self._closed or self._current_phase is None or type(units) is not int
                    or not 1 <= units <= _MAX_UNITS
                    or self._completed_units > _MAX_UNITS - units):
                raise QualificationJournalError()
            self._completed_units += units
            now = self._now()
            if now - self._last_pulse_clock >= 5.0:
                self._last_pulse_clock = now
                self._record("progress", self._current_phase, now=now)

    def record_operation(self, name: str, elapsed_ms: int | float, error: bool = False) -> None:
        """Aggregate one bounded operation without retaining caller data."""
        with self._lock:
            if (self._closed or type(name) is not str or name not in _OPERATION_SET
                    or type(elapsed_ms) not in (int, float) or not math.isfinite(elapsed_ms)
                    or elapsed_ms < 0 or elapsed_ms > _MAX_UNITS or type(error) is not bool):
                raise QualificationJournalError()
            duration = float(elapsed_ms)
            totals = self._operations[name]
            if (totals["calls"] >= _MAX_UNITS or totals["errors"] >= _MAX_UNITS
                    or totals["inclusive_ms"] > _MAX_UNITS - duration):
                raise QualificationJournalError()
            totals["calls"] += 1
            totals["errors"] += int(error)
            adjusted = duration - totals["_compensation"]
            new_total = totals["inclusive_ms"] + adjusted
            totals["_compensation"] = (new_total - totals["inclusive_ms"]) - adjusted
            totals["inclusive_ms"] = new_total
            totals["max_ms"] = max(totals["max_ms"], duration)
            if self._current_phase is not None:
                self.pulse()

    def close(self, success: bool = False) -> None:
        with self._lock:
            if type(success) is not bool or self._closed:
                raise QualificationJournalError()
            if self._current_phase is not None:
                self._status = "failed"
                self._failed = True
            elif not success:
                self._status = "failed"
                self._failed = True
            elif self._failed or not self._report_completed or self._totals["report"]["errors"]:
                self._status = "failed"
            else:
                self._status = "completed"
            self._closed = True
            self._record("closed", None, final=True)


def read_checkpoints(directory) -> tuple[dict, ...]:
    """Read validated checkpoint records; bounded temp remnants are ignored."""
    try:
        path = Path(directory)
        require_private_directory, require_private_file, _sync_directory = _private_storage()
        require_private_directory(path)
        parent_identity = _parent_identity(path)
        entries = list(path.iterdir())
        if len(entries) > _MAX_RECORDS * 2:
            raise QualificationJournalError()
        published = {}
        temps = 0
        for entry in entries:
            match = _CHECKPOINT_NAME.fullmatch(entry.name)
            if match:
                sequence = int(match.group(1))
                if sequence in published or not 1 <= sequence <= _MAX_RECORDS:
                    raise QualificationJournalError()
                published[sequence] = entry
                continue
            if _TEMP_NAME.fullmatch(entry.name):
                temps += 1
                if temps > _MAX_RECORDS:
                    raise QualificationJournalError()
                require_private_file(entry)
                if entry.stat().st_size > _MAX_RECORD_BYTES:
                    raise QualificationJournalError()
                continue
            raise QualificationJournalError()
        if len(published) > _MAX_RECORDS or set(published) != set(range(1, len(published) + 1)):
            raise QualificationJournalError()
        total = 0
        records = []
        for sequence in range(1, len(published) + 1):
            raw = _read_bytes(published[sequence])
            total += len(raw)
            if total > _MAX_TOTAL_BYTES:
                raise QualificationJournalError()
            records.append(_decode_record(raw, sequence))
        if _parent_identity(path) != parent_identity:
            raise QualificationJournalError()
        return tuple(records)
    except QualificationJournalError:
        raise
    except Exception:
        raise QualificationJournalError() from None


__all__ = ("OPERATIONS", "PHASES", "QualificationJournal", "QualificationJournalError",
    "read_checkpoints")
