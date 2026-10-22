"""Pure planner for complete multilingual image-library coverage.

This module validates a collector-supplied snapshot and partitions eligible
images into bounded unpublished batches. It performs no filesystem, database,
model, network, or provider work. A plan is not a reviewed or builder-accepted
cohort and makes no claim that source hashes were checked against file bytes.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any, Mapping, Sequence


SNAPSHOT_SCHEMA = "photohouse.multilingual_library_snapshot.v1"
PLAN_SCHEMA = "photohouse.multilingual_library_coverage_plan.v1"
MAX_BATCH_IMAGES = 512
MAX_BATCH_BYTES = 256 * 1024 * 1024
MAX_IMAGE_BYTES = 32 * 1024 * 1024
MAX_IMAGE_PIXELS = 16 * 1024 * 1024
MAX_IMAGE_DIMENSION = 8192
MAX_SNAPSHOT_ASSETS = 100_000
MAX_PATH_LENGTH = 32_767
MAX_SQLITE_ID = 2**63 - 1

_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_LIBRARY_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z", re.ASCII)
_IDENTIFIER = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z", re.ASCII)
_STATUSES = {"available", "missing", "outside_roots", "unsafe_path", "unreadable"}
_SUPPORTED_MIME = {"image/jpeg", "image/png"}
_SNAPSHOT_FIELDS = {"schema", "library_id", "source_revision_sha256", "assets"}
_ASSET_FIELDS = {
    "asset_id", "path", "db_source_sha256", "mime", "width", "height", "bytes", "file_status",
}
_IDENTITY_FIELDS = {
    "artifact_sha256", "preprocessing_sha256", "vector_space_id", "model_version",
    "dimension", "normalization",
}


class CoverageInputError(ValueError):
    """Raised when a closed snapshot or plan has malformed structure."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _fail(reason: str) -> None:
    raise CoverageInputError(reason)


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError):
        _fail("invalid_json_value")


def _sha(value: object) -> bool:
    return type(value) is str and _SHA256.fullmatch(value) is not None


def _path_is_canonical_file(value: object) -> bool:
    if type(value) is not str or not value or any(ord(char) < 32 or ord(char) == 127 for char in value):
        return False
    if len(value) > MAX_PATH_LENGTH:
        return False
    try:
        return (os.path.isabs(value) and os.path.normpath(value) == value
                and bool(os.path.basename(value)))
    except (OSError, ValueError):
        # Avoid probing the filesystem: path shape alone is all this planner checks.
        return False


def validate_snapshot(snapshot: object) -> dict[str, Any]:
    """Validate and canonically order a collector-supplied private snapshot.

    Paths and source hashes are metadata supplied by the scoped collector. This
    function intentionally does not open paths or verify hashes against bytes.
    """
    if type(snapshot) is not dict or set(snapshot) != _SNAPSHOT_FIELDS:
        _fail("snapshot_schema")
    if snapshot["schema"] != SNAPSHOT_SCHEMA:
        _fail("snapshot_schema")
    if (type(snapshot["library_id"]) is not str
            or _LIBRARY_ID.fullmatch(snapshot["library_id"]) is None):
        _fail("library_id")
    if not _sha(snapshot["source_revision_sha256"]):
        _fail("source_revision_sha256")
    assets = snapshot["assets"]
    if type(assets) is not list or not assets or len(assets) > MAX_SNAPSHOT_ASSETS:
        _fail("assets")

    normalized: list[dict[str, Any]] = []
    seen: set[int] = set()
    for row in assets:
        if type(row) is not dict or set(row) != _ASSET_FIELDS:
            _fail("asset_schema")
        asset_id = row["asset_id"]
        if type(asset_id) is not int or not 1 <= asset_id <= MAX_SQLITE_ID:
            _fail("asset_id")
        if asset_id in seen:
            _fail("duplicate_asset_id")
        seen.add(asset_id)
        if not _path_is_canonical_file(row["path"]):
            _fail("asset_path")
        if not _sha(row["db_source_sha256"]):
            _fail("db_source_sha256")
        if (type(row["mime"]) is not str or not row["mime"]
                or len(row["mime"]) > 128 or any(ord(c) < 33 or ord(c) > 126 for c in row["mime"])):
            _fail("mime")
        for key in ("width", "height"):
            if type(row[key]) is not int or row[key] < 0:
                _fail(key)
        if type(row["bytes"]) is not int or row["bytes"] < 0:
            _fail("bytes")
        if type(row["file_status"]) is not str or row["file_status"] not in _STATUSES:
            _fail("file_status")
        normalized.append({key: row[key] for key in sorted(_ASSET_FIELDS)})

    normalized.sort(key=lambda item: item["asset_id"])
    return {
        "schema": SNAPSHOT_SCHEMA,
        "library_id": snapshot["library_id"],
        "source_revision_sha256": snapshot["source_revision_sha256"],
        "assets": normalized,
    }


def _block_reason(asset: Mapping[str, Any]) -> str | None:
    status = asset["file_status"]
    if status != "available":
        return {
            "missing": "file_missing",
            "outside_roots": "outside_roots",
            "unsafe_path": "unsafe_path",
            "unreadable": "unreadable",
        }[status]
    if asset["bytes"] == 0:
        return "empty_image"
    if asset["mime"] not in _SUPPORTED_MIME:
        return "unsupported_mime"
    if asset["bytes"] > MAX_IMAGE_BYTES:
        return "image_byte_limit"
    if asset["width"] <= 0 or asset["height"] <= 0:
        return "invalid_dimensions"
    if asset["width"] > MAX_IMAGE_DIMENSION or asset["height"] > MAX_IMAGE_DIMENSION:
        return "image_dimension_limit"
    if asset["width"] * asset["height"] > MAX_IMAGE_PIXELS:
        return "image_pixel_limit"
    return None


def _plan_body(snapshot: dict[str, Any]) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    for asset in snapshot["assets"]:
        reason = _block_reason(asset)
        if reason is None:
            candidates.append(asset)
        else:
            blockers.append({"asset_id": asset["asset_id"], "reason": reason})

    batches: list[dict[str, Any]] = []
    current_ids: list[int] = []
    current_bytes = 0
    for asset in candidates:
        if current_ids and (len(current_ids) >= MAX_BATCH_IMAGES
                            or current_bytes + asset["bytes"] > MAX_BATCH_BYTES):
            batches.append({"batch_number": len(batches) + 1,
                            "asset_ids": current_ids, "bytes": current_bytes})
            current_ids, current_bytes = [], 0
        current_ids.append(asset["asset_id"])
        current_bytes += asset["bytes"]
    if current_ids:
        batches.append({"batch_number": len(batches) + 1,
                        "asset_ids": current_ids, "bytes": current_bytes})

    content = {
        "schema": PLAN_SCHEMA,
        "snapshot": snapshot,
        "asset_count": len(snapshot["assets"]),
        "candidate_count": len(candidates),
        "candidate_asset_ids": [asset["asset_id"] for asset in candidates],
        "blocker_count": len(blockers),
        "blockers": blockers,
        "batches": batches,
        "reviewed": False,
        "source_hashes_verified": False,
        "builder_accepted_cohort": False,
        "production_coverage": False,
        "activation_performed": False,
    }
    content["snapshot_digest_sha256"] = hashlib.sha256(_canonical(content)).hexdigest()
    return content


def plan_snapshot(snapshot: object) -> dict[str, Any]:
    """Return a deterministic bounded plan; never imply review or activation."""
    return _plan_body(validate_snapshot(snapshot))


def _validated_identity(value: object) -> dict[str, Any] | None:
    if type(value) is not dict or set(value) != _IDENTITY_FIELDS:
        return None
    if (not _sha(value["artifact_sha256"]) or not _sha(value["preprocessing_sha256"])
            or type(value["vector_space_id"]) is not str
            or _IDENTIFIER.fullmatch(value["vector_space_id"]) is None
            or type(value["model_version"]) is not str
            or _IDENTIFIER.fullmatch(value["model_version"]) is None
            or type(value["dimension"]) is not int or value["dimension"] != 768
            or value["normalization"] != "unit_l2"):
        return None
    return {key: value[key] for key in sorted(_IDENTITY_FIELDS)}


def _validated_plan(plan: object) -> dict[str, Any]:
    if type(plan) is not dict or type(plan.get("snapshot")) is not dict:
        _fail("plan_schema")
    expected = plan_snapshot(plan["snapshot"])
    if plan != expected:
        _fail("plan_digest_or_contents")
    return expected


def coverage_summary(
    plan: object,
    verified_artifact_rows: object,
    image_identity: object | None = None,
) -> dict[str, Any]:
    """Summarize candidate and whole-library vector coverage.

    Artifact rows are metadata supplied by a separate verifier; this function
    does not prove file bytes or vector contents. Rows have exactly
    ``asset_id`` and ``source_sha256``, plus an optional ``image_identity``.
    If identities are omitted from every row, the caller must provide the
    explicit identity parameter. Mixed row shapes are refused.
    """
    checked_plan = _validated_plan(plan)
    rows = verified_artifact_rows
    if type(rows) not in (list, tuple):
        _fail("artifact_rows")
    expected_identity = _validated_identity(image_identity) if image_identity is not None else None
    if image_identity is not None and expected_identity is None:
        _fail("image_identity")

    candidate_ids = set(checked_plan["candidate_asset_ids"])
    candidate_sources = {
        asset["asset_id"]: asset["db_source_sha256"]
        for asset in checked_plan["snapshot"]["assets"]
        if asset["asset_id"] in candidate_ids
    }
    seen: set[int] = set()
    identities: list[dict[str, Any]] = []
    present: dict[int, str] = {}
    issues: list[dict[str, Any]] = []
    row_shape: frozenset[str] | None = None
    for row in rows:
        if type(row) is not dict:
            _fail("artifact_row_schema")
        keys = frozenset(row)
        if keys not in (frozenset({"asset_id", "source_sha256"}),
                        frozenset({"asset_id", "source_sha256", "image_identity"})):
            _fail("artifact_row_schema")
        if row_shape is None:
            row_shape = keys
        elif row_shape != keys:
            _fail("artifact_row_schema")
        asset_id = row["asset_id"]
        if type(asset_id) is not int or not 1 <= asset_id <= MAX_SQLITE_ID:
            _fail("artifact_asset_id")
        if asset_id in seen:
            present.pop(asset_id, None)
            issues.append({"asset_id": asset_id, "reason": "duplicate_artifact"})
            continue
        seen.add(asset_id)
        if asset_id not in candidate_sources:
            issues.append({"asset_id": asset_id, "reason": "foreign_artifact"})
            continue
        if not _sha(row["source_sha256"]) or row["source_sha256"] != candidate_sources[asset_id]:
            issues.append({"asset_id": asset_id, "reason": "stale_source"})
            continue
        present[asset_id] = row["source_sha256"]
        if "image_identity" in row:
            identity = _validated_identity(row["image_identity"])
            if identity is None:
                issues.append({"asset_id": asset_id, "reason": "invalid_image_identity"})
                present.pop(asset_id, None)
            else:
                identities.append(identity)

    if row_shape == frozenset({"asset_id", "source_sha256"}) and expected_identity is None and rows:
        _fail("image_identity_required")
    if row_shape == frozenset({"asset_id", "source_sha256", "image_identity"}) and expected_identity is not None:
        if any(identity != expected_identity for identity in identities):
            issues.append({"reason": "foreign_image_identity"})
            present.clear()
    if identities:
        first_identity = identities[0]
        if any(identity != first_identity for identity in identities[1:]):
            issues.append({"reason": "mixed_image_identity"})
            present.clear()
        elif expected_identity is not None and first_identity != expected_identity:
            issues.append({"reason": "foreign_image_identity"})
            present.clear()
        elif expected_identity is None:
            expected_identity = first_identity

    missing = sorted(set(candidate_sources) - set(present))
    issues.extend({"asset_id": asset_id, "reason": "missing_artifact"} for asset_id in missing)
    candidate_complete = not missing and not any(
        issue["reason"] in {"duplicate_artifact", "foreign_artifact", "stale_source",
                            "invalid_image_identity", "foreign_image_identity", "mixed_image_identity"}
        for issue in issues
    ) and expected_identity is not None
    whole_library_complete = candidate_complete and checked_plan["blocker_count"] == 0
    return {
        "schema": "photohouse.multilingual_library_coverage_summary.v1",
        "plan_digest_sha256": checked_plan["snapshot_digest_sha256"],
        "candidate_count": checked_plan["candidate_count"],
        "candidate_covered_count": len(present),
        "candidate_coverage": candidate_complete,
        "blocker_count": checked_plan["blocker_count"],
        "whole_library_coverage": whole_library_complete,
        "image_identity": expected_identity,
        "issues": sorted(issues, key=lambda item: (item.get("asset_id", -1), item["reason"])),
        "reviewed": False,
        "production_coverage": False,
        "activation_performed": False,
    }
