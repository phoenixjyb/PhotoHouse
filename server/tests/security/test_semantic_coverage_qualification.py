"""Pure contract tests for reviewed omissions in a frozen semantic catalog."""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "backend"))

import semantic_coverage_qualification as coverage  # noqa: E402
from app.access.visual_candidates import VectorSpaceIdentity  # noqa: E402
from app.access.visual_vector_artifacts import (  # noqa: E402
    ImmutableVectorArtifact, identity_sha256,
)


def _sha(value):
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False).encode("ascii")


def _fixture(count=8, omitted_ids=()):
    omitted_ids = set(omitted_ids)
    image = VectorSpaceIdentity(
        artifact_sha256=_sha("model"), preprocessing_sha256=_sha("prep"),
        vector_space_id="siglip2-base-p16-256", model_version="v1",
        dimension=768, normalization="unit_l2")
    image_identity = asdict(image)
    identity_digest = identity_sha256(image)
    snapshot = {"schema": "photohouse.library_semantic_snapshot.v1",
        "library_id": "library-test", "assets": []}
    summaries, failures, records = [], [], []
    for number in range(1, count + 1):
        asset_id = str(number)
        source_digest = _sha(f"source-{number}")
        path = f"/originals/photo-{number}.jpg"
        snapshot["assets"].append({"asset_id": asset_id, "path": path,
            "sha256": source_digest, "mime": "image/jpeg", "width": 10, "height": 8})
        if number in omitted_ids:
            failures.append({"status": "failed", "asset_id": asset_id,
                "source_path": path,
                "code": "source_missing" if number % 2 else "preparation_unavailable",
                "source_sha256": None, "source_stat_identity": None})
            continue
        record_id = _sha(f"record-{number}")
        record = ImmutableVectorArtifact(record_id=record_id, asset_id=asset_id,
            source_sha256=source_digest, model_name="siglip2-base-p16-256",
            artifact_sha256=image.artifact_sha256,
            preprocessing_sha256=image.preprocessing_sha256,
            vector_space_id=image.vector_space_id, model_version=image.model_version,
            dimension=image.dimension, normalization=image.normalization,
            identity_sha256=identity_digest,
            relative_path=f"image-vectors/{identity_digest}/{record_id}.npy",
            file_sha256=_sha(f"file-{number}"), component_sha256=_sha(f"components-{number}"),
            created_at=1)
        records.append(record)
        summaries.append({"status": "ready", "asset_id": asset_id,
            "source_path": path, "source_sha256": source_digest,
            "source_stat_identity": {"fixture": number}, "derived_sha256": _sha(f"derived-{number}"),
            "preparation_recipe_sha256": _sha("recipe"), "observed_format": "JPEG",
            "observed_width": 10, "observed_height": 8, "orientation": 1,
            "prepared_width": 10, "prepared_height": 8, "record_id": record_id,
            "metadata_sha256": _sha(f"metadata-{number}")})
    snapshot_sha = coverage._snapshot_digest(snapshot)[0]
    receipt = {"schema": "fixture.receipt.v1"}
    manifest = {"schema": "photohouse.library_semantic_index.v1",
        "library_id": "library-test", "snapshot_sha256": snapshot_sha,
        "snapshot_asset_count": count, "image_identity": image_identity,
        "text_identity": {}, "model_receipt": receipt,
        "model_receipt_sha256": hashlib.sha256(_canonical(receipt)).hexdigest(),
        "records": summaries, "failures": failures,
        "record_count": len(summaries), "failure_count": len(failures),
        "processing_complete": True, "complete": not failures,
        "activation_approved": False, "relevance_accepted": False}
    index_sha = _sha("index bytes")
    return manifest, tuple(records), snapshot, index_sha


def test_complete_index_has_empty_review_roster_and_runtime_policy():
    manifest, records, snapshot, index_sha = _fixture()
    draft = coverage.omission_review_draft(manifest, records, snapshot,
        index_sha256=index_sha)
    assert draft == {"format_version": 1, "operator_reviewed": False,
        "index_sha256": index_sha, "snapshot_sha256": manifest["snapshot_sha256"],
        "omitted": []}
    with pytest.raises(coverage.CoverageQualificationRefused):
        coverage.validate_omission_review(draft, manifest, records, snapshot,
            index_sha256=index_sha)
    review = {**draft, "operator_reviewed": True}
    assert coverage.validate_omission_review(review, manifest, records, snapshot,
        index_sha256=index_sha) == ()
    policy = coverage.runtime_policy(review, manifest, records, snapshot,
        index_sha256=index_sha, binding_sha256=_sha("binding"), bulk_sha256=_sha("bulk"))
    assert policy["operator_reviewed"] is True
    assert len(policy["eligible"]) == len(records)
    assert policy["omitted"] == []
    assert policy["index_evidence_sha256"] == hashlib.sha256(_canonical(review)).hexdigest()


def test_full_65_omission_roster_is_catalog_bound_and_numeric_sorted():
    missing = set(range(1, 66))
    manifest, records, snapshot, index_sha = _fixture(100, missing)
    draft = coverage.omission_review_draft(manifest, records, snapshot,
        index_sha256=index_sha)
    assert [row["asset_id"] for row in draft["omitted"]] == [str(n) for n in range(1, 66)]
    assert len(records) == 35
    # The source_missing observer had no hash; qualification pins the catalog hash.
    assert draft["omitted"][0]["source_sha256"] == snapshot["assets"][0]["sha256"]
    review = {**draft, "operator_reviewed": True}
    approved = coverage.validate_omission_review(review, manifest, records, snapshot,
        index_sha256=index_sha)
    assert isinstance(approved, tuple) and len(approved) == 65
    with pytest.raises(AttributeError):
        approved[0].asset_id = "999"
    policy = coverage.runtime_policy(review, manifest, records, snapshot,
        index_sha256=index_sha, binding_sha256=_sha("binding"), bulk_sha256=_sha("bulk"))
    assert len(policy["eligible"]) == 35 and len(policy["omitted"]) == 65


@pytest.mark.parametrize("mutate", [
    lambda review: review.update(operator_reviewed=False),
    lambda review: review.update(format_version=True),
    lambda review: review.update(index_sha256=_sha("stale index")),
    lambda review: review.update(snapshot_sha256=_sha("stale snapshot")),
    lambda review: review["omitted"].append(review["omitted"][0]),
    lambda review: review["omitted"].pop(),
    lambda review: review["omitted"].reverse(),
    lambda review: review.update(extra="not closed"),
])
def test_review_must_be_exact_and_closed(mutate):
    manifest, records, snapshot, index_sha = _fixture(5, {2, 5})
    draft = coverage.omission_review_draft(manifest, records, snapshot,
        index_sha256=index_sha)
    review = {**draft, "operator_reviewed": True,
        "omitted": [dict(row) for row in draft["omitted"]]}
    mutate(review)
    with pytest.raises(coverage.CoverageQualificationRefused):
        coverage.validate_omission_review(review, manifest, records, snapshot,
            index_sha256=index_sha)


def test_unaccounted_catalog_unknown_failure_and_null_catalog_hash_refuse():
    manifest, records, snapshot, index_sha = _fixture(5, {5})
    review = coverage.omission_review_draft(manifest, records, snapshot,
        index_sha256=index_sha)
    review["operator_reviewed"] = True
    changed = json.loads(json.dumps(manifest))
    changed["failures"].clear()
    changed["failure_count"] = 0
    changed["complete"] = True
    with pytest.raises(coverage.CoverageQualificationRefused):
        coverage.omission_review_draft(changed, records, snapshot,
            index_sha256=index_sha)
    changed = json.loads(json.dumps(manifest))
    changed["failures"][0]["code"] = "source_not_approved"
    with pytest.raises(coverage.CoverageQualificationRefused):
        coverage.omission_review_draft(changed, records, snapshot,
            index_sha256=index_sha)
    no_catalog_hash = json.loads(json.dumps(snapshot))
    no_catalog_hash["assets"][-1]["sha256"] = None
    repinned = {**manifest, 'snapshot_sha256': hashlib.sha256(_canonical(no_catalog_hash)).hexdigest()}
    with pytest.raises(coverage.CoverageQualificationRefused):
        coverage.omission_review_draft(repinned, records, no_catalog_hash,
            index_sha256=index_sha)


def test_duplicate_record_source_drift_or_incomplete_processing_refuse():
    manifest, records, snapshot, index_sha = _fixture(5, {5})
    duplicated = (records[0],) + records[1:] + (records[0],)
    with pytest.raises(coverage.CoverageQualificationRefused):
        coverage.omission_review_draft(manifest, duplicated, snapshot,
            index_sha256=index_sha)
    changed = json.loads(json.dumps(manifest))
    changed["processing_complete"] = False
    with pytest.raises(coverage.CoverageQualificationRefused):
        coverage.omission_review_draft(changed, records, snapshot,
            index_sha256=index_sha)
    changed = json.loads(json.dumps(manifest))
    changed["records"][0]["source_sha256"] = _sha("changed")
    with pytest.raises(coverage.CoverageQualificationRefused):
        coverage.omission_review_draft(changed, records, snapshot,
            index_sha256=index_sha)
