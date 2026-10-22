"""Pure qualification for an explicitly reviewed partial semantic index.

This module consumes an already inspected index and frozen catalog snapshot.
It never reads original media, loads a model, or creates operator approval.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re

from app.access.visual_candidates import VectorSpaceIdentity
from app.access.visual_vector_artifacts import ImmutableVectorArtifact, validate_artifact


MAX_ASSETS = 100_000
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_ASSET_ID = re.compile(r"[1-9][0-9]{0,18}\Z", re.ASCII)
_LIBRARY_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z", re.ASCII)
_REVIEW_FIELDS = frozenset(("format_version", "operator_reviewed", "index_sha256",
                             "snapshot_sha256", "omitted"))
_INDEX_FIELDS = frozenset(("schema", "library_id", "snapshot_sha256",
    "snapshot_asset_count", "image_identity", "text_identity", "model_receipt",
    "model_receipt_sha256", "records", "failures", "record_count", "failure_count",
    "processing_complete", "complete", "activation_approved", "relevance_accepted"))
_SNAPSHOT_FIELDS = frozenset(("schema", "library_id", "assets"))
_ASSET_FIELDS = frozenset(("asset_id", "path", "sha256", "mime", "width", "height"))
_RECORD_FIELDS = frozenset(("record_id", "asset_id", "source_sha256", "model_name",
    "artifact_sha256", "preprocessing_sha256", "vector_space_id", "model_version",
    "dimension", "normalization", "identity_sha256", "relative_path", "file_sha256",
    "component_sha256", "created_at", "status"))
_SUMMARY_FIELDS = frozenset(("status", "asset_id", "source_path", "source_sha256",
    "source_stat_identity", "derived_sha256", "preparation_recipe_sha256",
    "observed_format", "observed_width", "observed_height", "orientation",
    "prepared_width", "prepared_height", "record_id", "metadata_sha256"))
_FAILURE_FIELDS = frozenset(("status", "asset_id", "source_path", "code",
                              "source_sha256", "source_stat_identity"))
_ELIGIBILITY_REASONS = frozenset(("source_missing", "preparation_unavailable"))


class CoverageQualificationRefused(ValueError):
    """Fixed refusal for an unpinned, incomplete, or unreviewed catalog."""

    def __init__(self):
        super().__init__("semantic_coverage_qualification_refused")


@dataclass(frozen=True, slots=True)
class OmittedAsset:
    asset_id: str
    source_sha256: str
    reason: str


def _require(condition):
    if not condition:
        raise CoverageQualificationRefused() from None


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False).encode("ascii")


def _valid_hash(value) -> bool:
    return type(value) is str and _SHA256.fullmatch(value) is not None


def _snapshot_digest(snapshot):
    _require(type(snapshot) is dict and set(snapshot) == _SNAPSHOT_FIELDS
        and snapshot.get("schema") == "photohouse.library_semantic_snapshot.v1"
        and type(snapshot.get("library_id")) is str
        and _LIBRARY_ID.fullmatch(snapshot["library_id"]) is not None
        and type(snapshot.get("assets")) is list
        and len(snapshot["assets"]) <= MAX_ASSETS)
    seen = set()
    normalized = []
    for asset in snapshot["assets"]:
        _require(type(asset) is dict and set(asset) == _ASSET_FIELDS
            and type(asset.get("asset_id")) is str
            and _ASSET_ID.fullmatch(asset["asset_id"]) is not None
            and int(asset["asset_id"]) <= 2**63 - 1
            and asset["asset_id"] not in seen
            and type(asset.get("path")) is str and len(asset["path"]) <= 32_768)
        digest = asset.get("sha256")
        _require(_valid_hash(digest))
        mime = asset.get("mime")
        _require(mime is None or (type(mime) is str and 1 <= len(mime) <= 128
            and all(0x20 <= ord(char) <= 0x7e for char in mime)))
        for name in ("width", "height"):
            value = asset.get(name)
            _require(value is None or (type(value) is int and -(2**31) <= value < 2**31))
        seen.add(asset["asset_id"])
        # library_semantic_index.validate_snapshot canonicalizes path lexically
        # via pathlib.Path, without touching the filesystem.
        from pathlib import Path
        path = Path(asset["path"])
        _require(path.is_absolute() and ".." not in path.parts and path != Path(path.anchor))
        normalized.append({**asset, "path": str(path)})
    canonical_snapshot = {"schema": snapshot["schema"], "library_id": snapshot["library_id"],
                          "assets": normalized}
    return hashlib.sha256(_canonical(canonical_snapshot)).hexdigest(), canonical_snapshot


def _identity(raw):
    _require(type(raw) is dict and set(raw) == {
        "artifact_sha256", "preprocessing_sha256", "vector_space_id", "model_version",
        "dimension", "normalization"})
    try:
        result = VectorSpaceIdentity(**raw)
        # validate_artifact below enforces the identity contract. Here ensure the
        # record metadata can be checked against this exact manifest identity.
        _require(type(result.dimension) is int)
        return result
    except Exception:
        raise CoverageQualificationRefused() from None


def _validate_inputs(manifest, records, snapshot, index_sha256):
    _require(_valid_hash(index_sha256))
    snapshot_digest, normalized_snapshot = _snapshot_digest(snapshot)
    _require(type(manifest) is dict and set(manifest) == _INDEX_FIELDS
        and manifest.get("schema") == "photohouse.library_semantic_index.v1"
        and type(manifest.get("library_id")) is str
        and _LIBRARY_ID.fullmatch(manifest["library_id"]) is not None
        and manifest["library_id"] == normalized_snapshot["library_id"]
        and _valid_hash(manifest.get("snapshot_sha256"))
        and manifest["snapshot_sha256"] == snapshot_digest
        and type(manifest.get("snapshot_asset_count")) is int
        and manifest["snapshot_asset_count"] == len(normalized_snapshot["assets"])
        and type(manifest.get("processing_complete")) is bool
        and manifest["processing_complete"] is True
        and type(manifest.get("activation_approved")) is bool
        and manifest["activation_approved"] is False
        and type(manifest.get("relevance_accepted")) is bool
        and manifest["relevance_accepted"] is False
        and type(manifest.get("records")) is list and type(manifest.get("failures")) is list
        and len(manifest["records"]) + len(manifest["failures"])
            == manifest["snapshot_asset_count"]
        and type(manifest.get("record_count")) is int
        and manifest["record_count"] == len(manifest["records"])
        and type(manifest.get("failure_count")) is int
        and manifest["failure_count"] == len(manifest["failures"])
        and type(manifest.get("complete")) is bool
        and manifest["complete"] is (manifest["failure_count"] == 0)
        and _valid_hash(manifest.get("model_receipt_sha256"))
        and hashlib.sha256(_canonical(manifest.get("model_receipt"))).hexdigest()
            == manifest["model_receipt_sha256"])

    catalog = {row["asset_id"]: row for row in normalized_snapshot["assets"]}
    _require(len(catalog) == len(normalized_snapshot["assets"]))
    summaries = manifest["records"]
    failures = manifest["failures"]
    _require(type(records) in (tuple, list) and len(records) == len(summaries))
    image_identity = _identity(manifest["image_identity"])
    record_by_id, record_ids, all_processed = {}, set(), set()
    for summary, record in zip(summaries, records):
        _require(type(summary) is dict and set(summary) == _SUMMARY_FIELDS
            and summary.get("status") == "ready"
            and type(summary.get("asset_id")) is str
            and _ASSET_ID.fullmatch(summary["asset_id"]) is not None
            and summary["asset_id"] in catalog
            and summary["asset_id"] not in all_processed
            and _valid_hash(summary.get("source_sha256"))
            and _valid_hash(summary.get("record_id")))
        asset = catalog[summary["asset_id"]]
        _require(summary["source_path"] == asset["path"]
            and summary["source_sha256"] == asset["sha256"]
            and type(record) is ImmutableVectorArtifact
            and set(record.__dataclass_fields__) == _RECORD_FIELDS
            and validate_artifact(record, image_identity)
            and record.asset_id == summary["asset_id"]
            and record.source_sha256 == asset["sha256"]
            and record.record_id == summary["record_id"]
            and record.status == "ready"
            and record.record_id not in record_ids)
        all_processed.add(summary["asset_id"])
        record_ids.add(record.record_id)
        record_by_id[summary["asset_id"]] = record

    omitted = []
    for failure in failures:
        _require(type(failure) is dict and set(failure) == _FAILURE_FIELDS
            and failure.get("status") == "failed"
            and type(failure.get("asset_id")) is str
            and _ASSET_ID.fullmatch(failure["asset_id"]) is not None
            and failure["asset_id"] in catalog
            and failure["asset_id"] not in all_processed
            and failure.get("code") in _ELIGIBILITY_REASONS)
        asset = catalog[failure["asset_id"]]
        _require(failure["source_path"] == asset["path"]
            and (failure["source_sha256"] is None
                or failure["source_sha256"] == asset["sha256"]))
        # Failure receipts can have no observed hash. The frozen catalog hash
        # remains the source identity pinned into the omission policy.
        omitted.append(OmittedAsset(failure["asset_id"], asset["sha256"], failure["code"]))
        all_processed.add(failure["asset_id"])
    _require(len(all_processed) == len(catalog) and len(record_by_id) >= 1)
    omitted.sort(key=lambda row: int(row.asset_id))
    return snapshot_digest, normalized_snapshot, record_by_id, tuple(omitted)


def _omission_doc(index_sha256, snapshot_digest, omitted, reviewed):
    return {"format_version": 1, "operator_reviewed": reviewed,
        "index_sha256": index_sha256, "snapshot_sha256": snapshot_digest,
        "omitted": [{"asset_id": row.asset_id, "source_sha256": row.source_sha256,
                     "reason": row.reason} for row in omitted]}


def omission_review_draft(manifest, records, snapshot, *, index_sha256):
    """Return the complete frozen-catalog omission roster for operator review."""
    try:
        snapshot_digest, _snapshot, _ready, omitted = _validate_inputs(
            manifest, records, snapshot, index_sha256)
        return _omission_doc(index_sha256, snapshot_digest, omitted, False)
    except CoverageQualificationRefused:
        raise
    except Exception:
        raise CoverageQualificationRefused() from None


def validate_omission_review(review, manifest, records, snapshot, *, index_sha256):
    """Accept only an exact, explicitly reviewed roster bound to this index."""
    try:
        snapshot_digest, _snapshot, _ready, omitted = _validate_inputs(
            manifest, records, snapshot, index_sha256)
        expected = _omission_doc(index_sha256, snapshot_digest, omitted, True)
        _require(type(review) is dict and set(review) == _REVIEW_FIELDS
            and type(review.get("format_version")) is int
            and review["format_version"] == 1
            and type(review.get("operator_reviewed")) is bool
            and review["operator_reviewed"] is True
            and _valid_hash(review.get("index_sha256"))
            and _valid_hash(review.get("snapshot_sha256"))
            and review == expected)
        return omitted
    except CoverageQualificationRefused:
        raise
    except Exception:
        raise CoverageQualificationRefused() from None


def runtime_policy(review, manifest, records, snapshot, *, index_sha256,
                   binding_sha256, bulk_sha256):
    """Build SemanticEligibilityStore's policy document after explicit review."""
    try:
        omitted = validate_omission_review(review, manifest, records, snapshot,
            index_sha256=index_sha256)
        _require(_valid_hash(binding_sha256) and _valid_hash(bulk_sha256))
        _snapshot_digest_value, _normalized_snapshot, ready, _expected_omitted = _validate_inputs(
            manifest, records, snapshot, index_sha256)
        return {"format_version": 1, "operator_reviewed": True,
            "library_id": manifest["library_id"], "binding_sha256": binding_sha256,
            "bulk_sha256": bulk_sha256,
            "index_evidence_sha256": hashlib.sha256(_canonical(review)).hexdigest(),
            "eligible": [{"asset_id": record.asset_id,
                "source_sha256": record.source_sha256, "record_id": record.record_id}
                for record in sorted(ready.values(), key=lambda value: int(value.asset_id))],
            "omitted": [{"asset_id": row.asset_id,
                "source_sha256": row.source_sha256, "reason": row.reason} for row in omitted]}
    except CoverageQualificationRefused:
        raise
    except Exception:
        raise CoverageQualificationRefused() from None
