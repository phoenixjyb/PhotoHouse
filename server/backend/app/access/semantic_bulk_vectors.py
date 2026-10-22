"""Explicit, bounded immutable bulk snapshots for semantic vector ranking.

This module is a storage primitive only. It has no provider, model, database,
configuration, or activation behavior. Callers must select it explicitly and
must supply the complete current ready-artifact cohort on every snapshot.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import math
import operator
import os
from pathlib import Path
import re
import stat
import struct
import threading
from typing import Callable

from .private_storage import require_private_directory, require_private_file
from .visual_candidates import MAX_DIMENSION, VectorRecord, VectorSpaceIdentity, _canonical_components
from .visual_vector_artifacts import ImmutableVectorArtifact, identity_sha256, validate_artifact
from .visual_vector_loader import _checked_root, _is_reparse, _read_vector, _root_snapshot, _same_file


MAX_BULK_BYTES = 128 * 1024 * 1024
MAX_HEADER_BYTES = 32 * 1024 * 1024
MAX_CACHE_BYTES = 256 * 1024 * 1024
MAX_CANDIDATES = 100_000
_MAGIC = b"PHVSBULK1\0"
_LIBRARY = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z", re.ASCII)
_ASSET_ID = re.compile(r"[1-9][0-9]{0,18}\Z", re.ASCII)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_READ_CHUNK = 1024 * 1024
_CACHE_BLOCK_BYTES = 4 * 1024 * 1024
_ARTIFACT_COHORT_FIELDS = (
    "record_id", "asset_id", "source_sha256", "model_name", "artifact_sha256",
    "preprocessing_sha256", "vector_space_id", "model_version", "dimension",
    "normalization", "identity_sha256", "relative_path", "file_sha256",
    "component_sha256", "created_at", "status",
)


class BulkVectorUnavailable(ValueError):
    """Fixed refusal for invalid, stale, or unsafe bulk vector data."""

    def __init__(self):
        super().__init__("bulk_vectors_unavailable")


class _CallbackFailure(Exception):
    def __init__(self, error):
        self.error = error


def _unavailable():
    raise BulkVectorUnavailable() from None


def _check_callback(check: Callable[[], None]) -> None:
    if not callable(check):
        _unavailable()
    try:
        check()
    except BaseException as error:
        raise _CallbackFailure(error) from None


def _call_charge(charge, amount):
    if not callable(charge):
        _unavailable()
    try:
        charge(amount)
    except BaseException as error:
        raise _CallbackFailure(error) from None


def _unwrap_callbacks(function):
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except _CallbackFailure as failure:
            raise failure.error
        except (MemoryError, RecursionError, OverflowError):
            _unavailable()
    return wrapped


def _valid_library(library_id: object) -> bool:
    return type(library_id) is str and _LIBRARY.fullmatch(library_id) is not None


def _valid_artifact_cohort(artifacts, identity, library_id, check):
    if type(artifacts) is not tuple or len(artifacts) > MAX_CANDIDATES:
        _unavailable()
    if not _valid_library(library_id) or type(identity) is not VectorSpaceIdentity:
        _unavailable()
    try:
        identity_digest = identity_sha256(identity)
    except (AttributeError, TypeError, ValueError):
        _unavailable()
    seen_ids, seen_records = set(), set()
    for artifact in artifacts:
        _check_callback(check)
        if type(artifact) is not ImmutableVectorArtifact or not validate_artifact(artifact, identity):
            _unavailable()
        if artifact.asset_id in seen_ids or artifact.record_id in seen_records:
            _unavailable()
        seen_ids.add(artifact.asset_id)
        seen_records.add(artifact.record_id)
    ordered = tuple(sorted(artifacts, key=lambda item: (int(item.asset_id), item.record_id)))
    return identity_digest, ordered


def _canonical_json(value) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                          allow_nan=False).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError, OverflowError):
        _unavailable()


def _cohort_digest(artifacts, check) -> str:
    digest = hashlib.sha256()
    for artifact in artifacts:
        _check_callback(check)
        encoded = _canonical_json(asdict(artifact))
        digest.update(struct.pack(">I", len(encoded)))
        digest.update(encoded)
    return digest.hexdigest()


def _artifact_cohort_key(artifacts, check):
    """Copy validated cohort metadata into immutable primitive tuples."""
    rows = []
    for artifact in artifacts:
        _check_callback(check)
        if type(artifact) is not ImmutableVectorArtifact:
            _unavailable()
        # Cold callers validate grammar before this copy. Warm callers rely on
        # exact primitive types plus equality with the prior validated rows.
        # Store values rather than frozen dataclass references: object.__setattr__
        # can still mutate a retained dataclass instance after this snapshot.
        row = tuple(getattr(artifact, name) for name in _ARTIFACT_COHORT_FIELDS)
        if any(type(value) is not (int if name in ("dimension", "created_at") else str)
               for name, value in zip(_ARTIFACT_COHORT_FIELDS, row)):
            _unavailable()
        rows.append(row)
    return tuple(rows)


def _warm_artifact_cohort_key(artifacts, cached, check):
    """Copy current fields for comparison with one prior validated cohort."""
    if (type(artifacts) is not tuple or len(artifacts) > MAX_CANDIDATES
            or type(cached) is not tuple or len(cached) != 3
            or type(cached[0]) is not tuple or len(cached[0]) != 4
            or type(cached[1]) is not tuple or len(cached[1]) != len(artifacts)):
        return None
    # The cached rows came from a complete validation and are immutable builtin
    # primitives. A warm hit still copies and type-checks every current field;
    # equality can therefore reuse only the prior grammar/cohort proof.
    return _artifact_cohort_key(artifacts, check)


def _private_artifact_copies(cohort_key, check):
    """Detach downstream work from caller-owned artifact instances."""
    copies = []
    for row in cohort_key:
        _check_callback(check)
        if type(row) is not tuple or len(row) != len(_ARTIFACT_COHORT_FIELDS):
            _unavailable()
        copies.append(ImmutableVectorArtifact(*row))
    return tuple(copies)


def _safe_file_parent(path: Path):
    if (not isinstance(path, Path) or not path.is_absolute() or ".." in path.parts
            or path.name in ("", ".", "..")):
        _unavailable()
    snapshot = _root_snapshot(path.parent)
    if snapshot is None:
        _unavailable()
    return snapshot


def _write_all(fd: int, data: bytes, check: Callable[[], None]) -> None:
    offset = 0
    while offset < len(data):
        _check_callback(check)
        wrote = os.write(fd, data[offset:offset + _READ_CHUNK])
        if wrote <= 0:
            _unavailable()
        offset += wrote


@_unwrap_callbacks
def write_bulk_vectors(destination, vector_root, artifacts, identity, library_id,
                       check=lambda: None) -> "BulkVectorStore":
    """Build and atomically publish an immutable bulk file without overwrite."""
    _check_callback(check)
    identity_digest, artifacts = _valid_artifact_cohort(artifacts, identity, library_id, check)
    if not isinstance(vector_root, Path) or _checked_root(vector_root) is None:
        _unavailable()
    if (not isinstance(destination, Path) or not destination.is_absolute()
            or ".." in destination.parts):
        _unavailable()
    parent_snapshot = _safe_file_parent(destination)
    try:
        require_private_directory(destination.parent)
    except (OSError, ValueError, TypeError):
        _unavailable()
    header = {
        "schema": 1,
        "library_id": library_id,
        "identity": asdict(identity),
        "identity_sha256": identity_digest,
        "cohort_sha256": _cohort_digest(artifacts, check),
        "count": len(artifacts),
        "asset_ids": [item.asset_id for item in artifacts],
    }
    header_bytes = _canonical_json(header)
    if len(header_bytes) > MAX_HEADER_BYTES:
        _unavailable()
    raw_prefix = _MAGIC + struct.pack(">I", len(header_bytes)) + header_bytes
    if len(raw_prefix) > MAX_BULK_BYTES:
        _unavailable()
    temp = destination.with_name(f".{destination.name}.{os.urandom(16).hex()}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    fd = None
    owned_temp = None
    try:
        _check_callback(check)
        fd = os.open(temp, flags, 0o600)
        created = os.fstat(fd)
        owned_temp = (created.st_dev, created.st_ino)
        try:
            require_private_file(temp)
        except (OSError, ValueError, TypeError):
            _unavailable()
        _write_all(fd, raw_prefix, check)
        payload_bytes = len(artifacts) * identity.dimension * 4
        if len(raw_prefix) + payload_bytes > MAX_BULK_BYTES:
            _unavailable()
        for artifact in artifacts:
            _check_callback(check)
            vector = _read_vector(vector_root, artifact)
            _check_callback(check)
            if vector is None:
                _unavailable()
            record = VectorRecord(artifact.asset_id, identity, vector, artifact.component_sha256)
            try:
                _canonical_components(record, identity)
                packed = struct.pack(f">{identity.dimension}f", *vector)
            except (ValueError, TypeError, OverflowError, struct.error):
                _unavailable()
            _write_all(fd, packed, check)
        os.fsync(fd)
        os.close(fd)
        fd = None
        _check_callback(check)
        if _root_snapshot(destination.parent) != parent_snapshot:
            _unavailable()
        # A hard link publishes the complete inode atomically and refuses an
        # existing final name. Temp and final remain in the same directory.
        os.link(temp, destination, follow_symlinks=False)
        os.unlink(temp)
        temp = None
        try:
            require_private_file(destination)
        except (OSError, ValueError, TypeError):
            _unavailable()
        if _root_snapshot(destination.parent) != parent_snapshot:
            _unavailable()
        raw_hash = _hash_published(destination, check)
        return BulkVectorStore(destination, raw_hash, library_id, identity)
    except BulkVectorUnavailable:
        raise
    except (OSError, TypeError, OverflowError, MemoryError):
        _unavailable()
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        if temp is not None and owned_temp is not None:
            try:
                info = os.lstat(temp)
                if (_root_snapshot(destination.parent) == parent_snapshot
                        and stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode)
                        and not _is_reparse(info) and info.st_nlink == 1
                        and (info.st_dev, info.st_ino) == owned_temp):
                    os.unlink(temp)
            except OSError:
                pass


def _hash_published(path, check):
    raw, _ = _read_secure_file(path, None, check, None)
    return hashlib.sha256(raw).hexdigest()


def _read_secure_file(path: Path, expected_sha: str | None, check, charge):
    parent_snapshot = _safe_file_parent(path)
    try:
        require_private_directory(path.parent)
        before = os.lstat(path)
        require_private_file(path)
        if (not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode)
                or _is_reparse(before) or before.st_nlink != 1
                or before.st_size > MAX_BULK_BYTES or before.st_size < len(_MAGIC) + 4):
            _unavailable()
        if os.name != "nt" and before.st_mode & 0o077:
            _unavailable()
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
        try:
            opened = os.fstat(descriptor)
            if (not _same_file(before, opened) or not stat.S_ISREG(opened.st_mode)
                    or opened.st_nlink != 1 or opened.st_size != before.st_size):
                _unavailable()
            chunks, total = [], 0
            while total < opened.st_size:
                _check_callback(check)
                requested = min(_READ_CHUNK, opened.st_size - total)
                if charge is not None:
                    _call_charge(charge, requested)
                chunk = os.read(descriptor, requested)
                if not chunk:
                    _unavailable()
                chunks.append(chunk)
                total += len(chunk)
            raw = b"".join(chunks)
            after_fd, after_path = os.fstat(descriptor), os.lstat(path)
            require_private_directory(path.parent)
            require_private_file(path)
            if (len(raw) != opened.st_size or not stat.S_ISREG(after_fd.st_mode)
                    or after_fd.st_nlink != 1 or _is_reparse(after_fd)
                    or not stat.S_ISREG(after_path.st_mode) or after_path.st_nlink != 1
                    or _is_reparse(after_path) or not _same_file(opened, after_fd)
                    or not _same_file(opened, after_path)
                    or _root_snapshot(path.parent) != parent_snapshot):
                _unavailable()
        finally:
            os.close(descriptor)
    except BulkVectorUnavailable:
        raise
    except (OSError, ValueError, TypeError):
        _unavailable()
    _check_callback(check)
    if expected_sha is not None and hashlib.sha256(raw).hexdigest() != expected_sha:
        _unavailable()
    return raw, parent_snapshot


class BulkVectorStore:
    """Pinned bulk file descriptor with a single immutable verified cache."""

    __slots__ = ('path', 'file_sha256', 'library_id', 'identity', '_cache', '_cache_lock')

    def __init__(self, path, file_sha256, library_id, identity):
        if (not isinstance(path, Path) or not path.is_absolute() or ".." in path.parts
                or path.name in ("", ".", "..") or type(file_sha256) is not str
                or _SHA256.fullmatch(file_sha256) is None or not _valid_library(library_id)
                or type(identity) is not VectorSpaceIdentity):
            _unavailable()
        try:
            identity_sha256(identity)
        except (AttributeError, TypeError, ValueError):
            _unavailable()
        object.__setattr__(self, "path", path)
        object.__setattr__(self, "file_sha256", file_sha256)
        object.__setattr__(self, "library_id", library_id)
        object.__setattr__(self, "identity", identity)
        object.__setattr__(self, "_cache", None)
        object.__setattr__(self, "_cache_lock", threading.Lock())

    def __setattr__(self, name, value):
        raise AttributeError("immutable_bulk_store")

    @property
    def descriptor(self):
        return {"path": str(self.path), "file_sha256": self.file_sha256,
                "library_id": self.library_id, "identity_sha256": identity_sha256(self.identity)}

    @_unwrap_callbacks
    def snapshot(self, artifacts, *, library_id, check=lambda: None, charge=lambda size: None):
        _check_callback(check)
        cached = self._cache
        identity_digest = None
        cohort_key = None
        warm_hit = False
        if (library_id == self.library_id and _valid_library(library_id)
                and type(self.identity) is VectorSpaceIdentity):
            try:
                identity_digest = identity_sha256(self.identity)
            except (AttributeError, TypeError, ValueError):
                _unavailable()
            if (type(cached) is tuple and len(cached) == 3
                    and type(cached[0]) is tuple and len(cached[0]) == 4
                    and cached[0][0] == self.file_sha256
                    and cached[0][2] == library_id
                    and cached[0][3] == identity_digest):
                current_key = _warm_artifact_cohort_key(artifacts, cached, check)
                if current_key is not None and current_key == cached[1]:
                    cohort_key = current_key
                    warm_hit = True
        if not warm_hit:
            identity_digest, artifacts = _valid_artifact_cohort(
                artifacts, self.identity, library_id, check,
            )
            try:
                current_identity_digest = identity_sha256(self.identity)
            except (AttributeError, TypeError, ValueError):
                _unavailable()
            if library_id != self.library_id or identity_digest != current_identity_digest:
                _unavailable()
            cohort_key = _artifact_cohort_key(artifacts, check)
        # Every downstream operation receives artifacts reconstructed from the
        # complete typed primitive copy. Callbacks and caller-held references
        # can mutate the originals without changing this coherent snapshot.
        artifacts = _private_artifact_copies(cohort_key, check)
        try:
            current_identity_digest = identity_sha256(self.identity)
        except (AttributeError, TypeError, ValueError):
            _unavailable()
        if identity_digest != current_identity_digest:
            _unavailable()
        # Reuse only the digest for an exact copy of the freshly validated
        # primitive fields; never retain mutable artifact objects in the cache.
        cohort_digest = (cached[0][1] if cached is not None and cached[1] == cohort_key
                         else _cohort_digest(artifacts, check))
        raw, _ = _read_secure_file(self.path, self.file_sha256, check, charge)
        header, payload = _decode_container(raw)
        expected_header = {"schema": 1, "library_id": library_id, "identity": asdict(self.identity),
                           "identity_sha256": identity_digest, "cohort_sha256": cohort_digest,
                           "count": len(artifacts), "asset_ids": [item.asset_id for item in artifacts]}
        if header != expected_header:
            _unavailable()
        key = (self.file_sha256, cohort_digest, library_id, identity_digest)
        cached = self._cache
        if cached is not None and cached[0] == key and cached[1] == cohort_key:
            canonical_matrix = cached[2]
        else:
            # One lock owns cold verification and cache publication. Waiters
            # remain cancellable, and no partial cache is ever visible.
            while not self._cache_lock.acquire(timeout=0.05):
                _check_callback(check)
            try:
                _check_callback(check)
                cached = self._cache
                if cached is not None and cached[0] == key and cached[1] == cohort_key:
                    canonical_matrix = cached[2]
                else:
                    canonical_matrix = _canonical_matrix(payload, artifacts, self.identity, check)
                    _check_callback(check)
                    object.__setattr__(self, "_cache", (key, cohort_key, canonical_matrix))
            finally:
                self._cache_lock.release()
        return BulkVectorSnapshot(artifacts, self.identity, canonical_matrix)


class BulkVectorSnapshot:
    __slots__ = ("_artifacts", "identity", "_matrix", "_ids", "_sealed")

    def __init__(self, artifacts, identity, matrix):
        object.__setattr__(self, "_artifacts", artifacts)
        object.__setattr__(self, "identity", identity)
        object.__setattr__(self, "_matrix", matrix)
        object.__setattr__(self, "_ids", frozenset(a.asset_id for a in artifacts))
        object.__setattr__(self, "_sealed", True)

    def __setattr__(self, name, value):
        if getattr(self, "_sealed", False):
            raise AttributeError("immutable_bulk_snapshot")
        object.__setattr__(self, name, value)

    @property
    def count(self):
        return len(self._artifacts)

    @_unwrap_callbacks
    def rank(self, query, asset_ids, *, check=lambda: None):
        _check_callback(check)
        if (type(query) is not tuple or len(query) != self.identity.dimension
                or any(type(value) not in (float, int) or not math.isfinite(value) for value in query)
                or type(asset_ids) is not tuple or len(asset_ids) > self.count
                or any(type(value) is not str or _ASSET_ID.fullmatch(value) is None for value in asset_ids)
                or len(set(asset_ids)) != len(asset_ids) or not set(asset_ids) <= self._ids):
            _unavailable()
        wanted = set(asset_ids)
        width = self.identity.dimension * 8
        ranked = []
        blocks, rows_per_block = self._matrix
        for index, artifact in enumerate(self._artifacts):
            _check_callback(check)
            if artifact.asset_id not in wanted:
                continue
            block = blocks[index // rows_per_block]
            block_index = index % rows_per_block
            vector = struct.unpack_from(f">{self.identity.dimension}d", block, block_index * width)
            score = math.fsum(map(operator.mul, query, vector))
            ranked.append((artifact.asset_id, score))
        if len(ranked) != len(asset_ids):
            _unavailable()
        return tuple(sorted(ranked, key=lambda item: (-item[1], int(item[0]))))


def _decode_container(raw):
    try:
        if len(raw) < len(_MAGIC) + 4 or raw[:len(_MAGIC)] != _MAGIC:
            _unavailable()
        header_size = struct.unpack_from(">I", raw, len(_MAGIC))[0]
        start = len(_MAGIC) + 4
        end = start + header_size
        if header_size > MAX_HEADER_BYTES or end > len(raw):
            _unavailable()
        encoded = raw[start:end]
        header = json.loads(encoded.decode("ascii"))
        if (type(header) is not dict or type(header.get('schema')) is not int
                or header.get('schema') != 1 or _canonical_json(header) != encoded):
            _unavailable()
        identity = header.get("identity")
        count, asset_ids = header.get("count"), header.get("asset_ids")
        if (type(count) is not int or not 0 <= count <= MAX_CANDIDATES
                or type(asset_ids) is not list or len(asset_ids) != count
                or type(identity) is not dict):
            _unavailable()
        dimension = identity.get("dimension")
        if type(dimension) is not int or not 1 <= dimension <= MAX_DIMENSION:
            _unavailable()
        expected_data = count * dimension * 4
        if end + expected_data != len(raw):
            _unavailable()
        return header, memoryview(raw)[end:]
    except BulkVectorUnavailable:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError, OverflowError, MemoryError):
        _unavailable()


def _canonical_matrix(payload, artifacts, identity, check):
    row_bytes = identity.dimension * 4
    canonical_row_bytes = identity.dimension * 8
    required = len(artifacts) * identity.dimension * 8
    if required > MAX_CACHE_BYTES:
        _unavailable()
    rows_per_block = max(1, _CACHE_BLOCK_BYTES // canonical_row_bytes)
    blocks = []
    try:
        for block_start in range(0, len(artifacts), rows_per_block):
            block_count = min(rows_per_block, len(artifacts) - block_start)
            matrix = bytearray(block_count * canonical_row_bytes)
            for offset in range(block_count):
                index = block_start + offset
                artifact = artifacts[index]
                _check_callback(check)
                raw_values = struct.unpack_from(f">{identity.dimension}f", payload, index * row_bytes)
                record = VectorRecord(artifact.asset_id, identity, tuple(raw_values), artifact.component_sha256)
                canonical = _canonical_components(record, identity)
                struct.pack_into(f">{identity.dimension}d", matrix, offset * canonical_row_bytes, *canonical)
            blocks.append(bytes(matrix))
        _check_callback(check)
        return (tuple(blocks), rows_per_block)
    except _CallbackFailure:
        raise
    except (ValueError, TypeError, OverflowError, struct.error, MemoryError):
        _unavailable()
