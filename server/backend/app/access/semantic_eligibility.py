"""Pinned, private eligibility policy for the semantic image-search pilot.

This module only validates an operator-authored policy. It does not build or
review one, and never places local paths in its public descriptor.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Callable

from .private_storage import require_private_directory, require_private_file, stable_stat_identity
from .visual_vector_artifacts import ImmutableVectorArtifact


MAX_POLICY_BYTES = 16 * 1024 * 1024
MAX_ENTRIES = 100_000
READ_CHUNK = 64 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_LIBRARY = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z", re.ASCII)
_ASSET = re.compile(r"[1-9][0-9]{0,18}\Z", re.ASCII)
_REASONS = frozenset(("preparation_unavailable", "source_missing"))
_FIELDS = frozenset(("format_version", "operator_reviewed", "library_id", "binding_sha256",
                     "bulk_sha256", "index_evidence_sha256", "eligible", "omitted"))


class SemanticEligibilityUnavailable(ValueError):
    """Fixed refusal for invalid, stale, or unsafe eligibility data."""

    def __init__(self):
        super().__init__("semantic_eligibility_unavailable")


class _CallbackFailure(Exception):
    def __init__(self, error):
        self.error = error


def _unavailable():
    raise SemanticEligibilityUnavailable() from None


def _check(check: Callable[[], None]):
    if not callable(check):
        _unavailable()
    try:
        check()
    except BaseException as error:
        raise _CallbackFailure(error) from None


def _charge(charge, amount: int):
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


def _safe_path(path) -> bool:
    return (isinstance(path, Path) and path.is_absolute() and ".." not in path.parts
            and str(path) == os.path.normpath(str(path)))


def _valid_hash(value) -> bool:
    return type(value) is str and _SHA256.fullmatch(value) is not None


def _valid_asset(value) -> bool:
    return (type(value) is str and _ASSET.fullmatch(value) is not None
            and int(value) <= 2**63 - 1)


def _valid_record(value) -> bool:
    # The current immutable artifact schema constrains record_id to lowercase
    # SHA-256 text (64 characters), within the policy's 128-character ceiling.
    return _valid_hash(value)


def _outside_source(policy_path: Path, source_root: Path) -> bool:
    # A policy anywhere inside the source tree, or an ancestor containing it,
    # would let an application checkout replace or shadow the policy file.
    try:
        policy_path.relative_to(source_root)
        return False
    except ValueError:
        pass
    try:
        source_root.relative_to(policy_path)
        return False
    except ValueError:
        return True


def _reparse(info) -> bool:
    return bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _ancestor_snapshot(directory: Path):
    """Snapshot each lexical directory ancestor and refuse aliases."""
    current = directory.anchor
    observed = []
    try:
        for part in directory.parts[1:]:
            current = os.path.join(current, part)
            info = os.lstat(current)
            if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)
                    or _reparse(info)):
                return None
            observed.append((current, stable_stat_identity(info), info.st_mode))
        return tuple(observed)
    except (OSError, ValueError, TypeError):
        return None


def _same_identity(left, right) -> bool:
    try:
        return stable_stat_identity(left) == stable_stat_identity(right)
    except (AttributeError, OSError, ValueError):
        return False


def _strict_json(raw: bytes):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    def reject_constant(_value):
        raise ValueError("non-finite number")

    try:
        return json.loads(raw.decode("utf-8", errors="strict"), object_pairs_hook=pairs,
                          parse_constant=reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError):
        _unavailable()


def _read_private(path: Path, expected_sha256: str, check, charge) -> bytes:
    if (not _safe_path(path) or not _valid_hash(expected_sha256)
            or path.name in ("", ".", "..")):
        _unavailable()
    parent_snapshot = _ancestor_snapshot(path.parent)
    if parent_snapshot is None:
        _unavailable()
    descriptor = None
    try:
        require_private_directory(path.parent)
        before = os.lstat(path)
        require_private_file(path)
        if (not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode)
                or _reparse(before) or before.st_nlink != 1
                or before.st_size < 1 or before.st_size > MAX_POLICY_BYTES):
            _unavailable()
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
        _check(check)
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        if (not _same_identity(before, opened) or not stat.S_ISREG(opened.st_mode)
                or _reparse(opened) or opened.st_nlink != 1 or opened.st_size != before.st_size):
            _unavailable()
        chunks, total = [], 0
        while total < opened.st_size:
            _check(check)
            requested = min(READ_CHUNK, opened.st_size - total)
            _charge(charge, requested)
            chunk = os.read(descriptor, requested)
            if not chunk:
                _unavailable()
            chunks.append(chunk)
            total += len(chunk)
        raw = b"".join(chunks)
        after_fd = os.fstat(descriptor)
        require_private_directory(path.parent)
        require_private_file(path)
        # Stat after the path ACL check so a replacement or metadata change
        # during that check cannot be hidden by an earlier pathname snapshot.
        after_path = os.lstat(path)
        if (len(raw) != opened.st_size or not stat.S_ISREG(after_fd.st_mode)
                or _reparse(after_fd) or after_fd.st_nlink != 1
                or not stat.S_ISREG(after_path.st_mode) or stat.S_ISLNK(after_path.st_mode)
                or _reparse(after_path) or after_path.st_nlink != 1
                or not _same_identity(opened, after_fd) or not _same_identity(opened, after_path)
                or _ancestor_snapshot(path.parent) != parent_snapshot):
            _unavailable()
    except _CallbackFailure:
        raise
    except SemanticEligibilityUnavailable:
        raise
    except (OSError, TypeError, ValueError):
        _unavailable()
    finally:
        if descriptor is not None:
            os.close(descriptor)
    _check(check)
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        _unavailable()
    return raw


@dataclass(frozen=True, slots=True)
class SemanticEligibilityPolicy:
    policy_sha256: str
    library_id: str
    eligible_ids: frozenset[str]
    omitted_ids: frozenset[str]

    def coverage(self, matched_omitted_images: int) -> dict:
        if (type(matched_omitted_images) is not int
                or not 0 <= matched_omitted_images <= len(self.omitted_ids)):
            _unavailable()
        return {
            "version": 1,
            "policy_sha256": self.policy_sha256,
            "state": "partial" if self.omitted_ids else "complete",
            "catalog_images": len(self.eligible_ids) + len(self.omitted_ids),
            "searchable_images": len(self.eligible_ids),
            "omitted_images": len(self.omitted_ids),
            "matched_omitted_images": matched_omitted_images,
        }


@dataclass(frozen=True, slots=True)
class SemanticEligibilityStore:
    """Hash-pinned operator policy configuration; filesystem checks are per read."""

    path: Path
    file_sha256: str
    library_id: str
    binding_sha256: str
    bulk_sha256: str
    source_root: Path

    def __post_init__(self):
        if (not _safe_path(self.path) or not _safe_path(self.source_root)
                or not _outside_source(self.path, self.source_root)
                or not _valid_hash(self.file_sha256) or not _valid_hash(self.binding_sha256)
                or not _valid_hash(self.bulk_sha256)
                or type(self.library_id) is not str
                or _LIBRARY.fullmatch(self.library_id) is None):
            _unavailable()

    @property
    def descriptor(self) -> dict:
        return {"policy_sha256": self.file_sha256, "library_id": self.library_id,
                "binding_sha256": self.binding_sha256, "bulk_sha256": self.bulk_sha256}

    @_unwrap_callbacks
    def read_and_validate(self, source_hashes: dict[str, str],
                          artifacts: dict[str, ImmutableVectorArtifact], *,
                          library_id: str, check=lambda: None, charge=lambda _size: None):
        _check(check)
        if (library_id != self.library_id or type(library_id) is not str
                or type(source_hashes) is not dict or type(artifacts) is not dict
                or len(source_hashes) > MAX_ENTRIES or len(artifacts) > MAX_ENTRIES):
            _unavailable()
        for asset_id, digest in source_hashes.items():
            _check(check)
            if not _valid_asset(asset_id) or not _valid_hash(digest):
                _unavailable()
        source_snapshot = _ancestor_snapshot(self.source_root)
        if source_snapshot is None:
            _unavailable()
        raw = _read_private(self.path, self.file_sha256, check, charge)
        if _ancestor_snapshot(self.source_root) != source_snapshot:
            _unavailable()
        document = _strict_json(raw)
        if (type(document) is not dict or set(document) != _FIELDS
                or type(document.get("format_version")) is not int or document["format_version"] != 1
                or type(document.get("operator_reviewed")) is not bool
                or document["operator_reviewed"] is not True
                or document.get("library_id") != self.library_id
                or document.get("binding_sha256") != self.binding_sha256
                or document.get("bulk_sha256") != self.bulk_sha256
                or not _valid_hash(document.get("index_evidence_sha256"))):
            _unavailable()
        eligible, omitted = document["eligible"], document["omitted"]
        if (type(eligible) is not list or type(omitted) is not list
                or not 1 <= len(eligible) <= MAX_ENTRIES
                or len(eligible) + len(omitted) > MAX_ENTRIES):
            _unavailable()
        eligible_ids, omitted_ids = set(), set()
        expected_artifacts, record_ids = {}, set()
        for item in eligible:
            _check(check)
            if (type(item) is not dict or set(item) != {"asset_id", "source_sha256", "record_id"}
                    or not _valid_asset(item.get("asset_id"))
                    or not _valid_hash(item.get("source_sha256"))
                    or not _valid_record(item.get("record_id"))):
                _unavailable()
            asset_id = item["asset_id"]
            if asset_id in eligible_ids:
                _unavailable()
            if item["record_id"] in record_ids:
                _unavailable()
            eligible_ids.add(asset_id)
            record_ids.add(item["record_id"])
            expected_artifacts[asset_id] = (item["source_sha256"], item["record_id"])
        for item in omitted:
            _check(check)
            if (type(item) is not dict or set(item) != {"asset_id", "source_sha256", "reason"}
                    or not _valid_asset(item.get("asset_id"))
                    or not _valid_hash(item.get("source_sha256"))
                    or type(item.get("reason")) is not str or item["reason"] not in _REASONS):
                _unavailable()
            asset_id = item["asset_id"]
            if asset_id in omitted_ids or asset_id in eligible_ids:
                _unavailable()
            omitted_ids.add(asset_id)
        if eligible_ids | omitted_ids != set(source_hashes):
            _unavailable()
        for asset_id, (digest, _record_id) in expected_artifacts.items():
            if source_hashes.get(asset_id) != digest:
                _unavailable()
        for item in omitted:
            if source_hashes.get(item["asset_id"]) != item["source_sha256"]:
                _unavailable()
        if set(artifacts) != eligible_ids:
            _unavailable()
        for asset_id, artifact in artifacts.items():
            _check(check)
            source_sha256, record_id = expected_artifacts[asset_id]
            if (type(artifact) is not ImmutableVectorArtifact or artifact.asset_id != asset_id
                    or artifact.source_sha256 != source_sha256 or artifact.record_id != record_id
                    or artifact.status != "ready"):
                _unavailable()
        _check(check)
        return SemanticEligibilityPolicy(self.file_sha256, self.library_id,
                                         frozenset(eligible_ids), frozenset(omitted_ids))
