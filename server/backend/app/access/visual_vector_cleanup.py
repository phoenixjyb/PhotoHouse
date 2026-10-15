"""Read-only planning for erasing vectors after an asset tombstone.

The caller must durably record an asset deletion before acting on this plan.
Artifact metadata remains immutable as provenance; this module never mutates
SQLite or removes files.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import sqlite3
import stat

from .visual_candidates import UNIT_NORM_TOLERANCE, canonical_vector_checksum
from .visual_vector_artifacts import ImmutableVectorArtifact, validate_artifact
from .visual_vector_loader import _checked_root, _is_reparse, _read_vector
from .visual_vector_schema import ARTIFACT_TABLE, sqlite_visual_vector_contract, verify_visual_vector_schema


MAX_CLEANUP_ARTIFACTS = 128
_COLUMNS = (
    "record_id,asset_id,source_sha256,model_name,artifact_sha256,preprocessing_sha256,"
    "vector_space_id,model_version,dimension,normalization,identity_sha256,relative_path,"
    "file_sha256,component_sha256,created_at,status"
)


class VectorCleanupRefused(ValueError):
    """Fixed, non-sensitive refusal for an unsafe or incomplete cleanup plan."""


@dataclass(frozen=True, slots=True)
class VectorCleanupItem:
    record_id: str
    relative_path: str
    file_sha256: str
    missing: bool


@dataclass(frozen=True, slots=True)
class VectorCleanupPlan:
    items: tuple[VectorCleanupItem, ...]


def _refuse():
    raise VectorCleanupRefused("Vector cleanup unavailable") from None


def plan_asset_vector_cleanup(db, root: Path, asset_id: int) -> VectorCleanupPlan:
    """Validate every versioned vector for an already-tombstoned asset.

    The caller owns the current transaction and is responsible for a durable
    deletion tombstone before it acts on the returned file list. The plan is
    read-only and idempotent: safely absent files are reported as ``missing``.
    """
    if (type(asset_id) is not int or not 1 <= asset_id <= 2**63 - 1
            or getattr(db, "in_transaction", None) is not True):
        _refuse()

    try:
        parent = db.execute("SELECT status FROM assets WHERE id=?", (asset_id,)).fetchone()
        if parent is None or type(parent[0]) is not str or parent[0] != "deleted":
            _refuse()

        # A wholly absent optional contract is a no-op. Orphaned/renamed
        # contract objects signal drift and must not be mistaken for absence.
        contract = sqlite_visual_vector_contract()
        expected_names = {name for _kind, name, _ddl in contract}
        objects = db.execute(
            "SELECT type,name FROM sqlite_master WHERE name IN (" +
            ",".join("?" for _ in expected_names) + ")",
            tuple(sorted(expected_names)),
        ).fetchall()
        if not objects:
            return VectorCleanupPlan(())
        if not verify_visual_vector_schema(db):
            _refuse()

        rows = db.execute(
            f"SELECT {_COLUMNS} FROM {ARTIFACT_TABLE} WHERE asset_id=? "
            "ORDER BY identity_sha256,record_id LIMIT ?",
            (asset_id, MAX_CLEANUP_ARTIFACTS + 1),
        ).fetchall()
        if len(rows) > MAX_CLEANUP_ARTIFACTS:
            _refuse()

        artifacts = tuple(_validated_artifact(row, asset_id) for row in rows)
        if not artifacts:
            return VectorCleanupPlan(())

        checked_root = _checked_root(root)
        if checked_root is None:
            _refuse()

        items = []
        for artifact in artifacts:
            target = _target_state(checked_root, artifact.relative_path)
            if target is None:
                items.append(VectorCleanupItem(
                    artifact.record_id, artifact.relative_path, artifact.file_sha256, True
                ))
                continue

            vector = _read_vector(checked_root, artifact)
            if vector is None:
                _refuse()
            try:
                checksum = canonical_vector_checksum(vector)
                norm = math.sqrt(math.fsum(float(value) * float(value) for value in vector))
            except (OverflowError, TypeError, ValueError):
                _refuse()
            if (checksum != artifact.component_sha256 or not math.isfinite(norm)
                    or norm == 0.0 or abs(norm - 1.0) > UNIT_NORM_TOLERANCE):
                _refuse()
            items.append(VectorCleanupItem(
                artifact.record_id, artifact.relative_path, artifact.file_sha256, False
            ))
        return VectorCleanupPlan(tuple(items))
    except VectorCleanupRefused:
        raise
    except (AttributeError, OSError, OverflowError, sqlite3.Error, TypeError, ValueError):
        _refuse()


def _validated_artifact(row, asset_id: int) -> ImmutableVectorArtifact:
    try:
        if len(row) != 16 or type(row[1]) is not int or row[1] != asset_id:
            _refuse()
        values = list(row)
        # SQLite INTEGER IDs must round-trip through the one canonical decimal
        # representation accepted by the pure artifact validator.
        values[1] = str(values[1])
        artifact = ImmutableVectorArtifact(*values)
    except (TypeError, ValueError):
        _refuse()
    if artifact.asset_id != str(asset_id) or not validate_artifact(artifact):
        _refuse()
    return artifact


def _target_state(root: Path, relative_path: str) -> bool | None:
    """Return False for a safe regular file, None if safely absent, else refuse."""
    relative = Path(relative_path)
    if (relative.is_absolute() or ".." in relative.parts or len(relative.parts) != 3
            or relative.as_posix() != relative_path):
        _refuse()

    parent = root
    try:
        for part in relative.parts[:-1]:
            parent = parent / part
            try:
                info = parent.lstat()
            except FileNotFoundError:
                return None
            if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)
                    or _is_reparse(info)):
                _refuse()
        target = parent / relative.parts[-1]
        try:
            info = target.lstat()
        except FileNotFoundError:
            return None
        if (not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode)
                or _is_reparse(info) or info.st_nlink != 1):
            _refuse()
        return False
    except OSError:
        _refuse()
