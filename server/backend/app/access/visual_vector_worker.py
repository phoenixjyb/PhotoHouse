"""Guarded adapter from an approved image task to vector publication.

This module validates task claims and artifact bytes. It has no provider,
NumPy, migration, schema installation, or database transaction ownership.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3

from .visual_candidates import VectorSpaceIdentity, canonical_vector_checksum
from .visual_vector_artifacts import ImmutableVectorArtifact, identity_sha256, validate_artifact
from .visual_vector_loader import _decode_npy
from .visual_vector_publication import VectorPublicationStore


_SHA = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_NAME = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z", re.ASCII)
_MAX_SOURCE_BYTES = 256 * 1024**2
_MAX_VECTOR_BYTES = 64 * 1024
_CLAIM_VERSION = "photohouse-approved-image-claim-v1"
_RECORD_VERSION = "photohouse-approved-image-vector-record-v1"


def _fail():
    raise ValueError("approved_image_claim_unavailable") from None


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _positive_int(value, maximum=2**63 - 1):
    return type(value) is int and 1 <= value <= maximum


def _payload(raw, asset_id):
    if type(raw) is not str or len(raw) > 4096:
        return False
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate_key")
            result[key] = value
        return result
    try:
        value = json.loads(raw, object_pairs_hook=unique_object,
                           parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("constant")))
    except (TypeError, ValueError, RecursionError):
        return False
    return (type(value) is dict and set(value) == {"asset_id", "modality"}
            and type(value["asset_id"]) is int and value["asset_id"] == asset_id
            and type(value["modality"]) is str and value["modality"] == "image")


def _timestamp_epoch(value):
    if type(value) is not str or len(value) != 19:
        _fail()
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        _fail()
    if parsed.strftime("%Y-%m-%d %H:%M:%S") != value:
        _fail()
    return int(parsed.timestamp())


@dataclass(frozen=True, slots=True)
class ApprovedImageClaim:
    task_id: int
    asset_id: int
    path: str
    sha256: str
    bytes: int
    mime: str
    library_id: str
    claimed_payload_json: str
    claim_started_at: str
    claim_retry_count: int

    @classmethod
    def from_candidate(cls, candidate):
        try:
            values = {name: candidate[name] for name in (
                "task_id", "asset_id", "path", "sha256", "bytes", "mime", "library_id",
                "claimed_payload_json", "claim_started_at", "claim_retry_count")}
        except (KeyError, TypeError):
            _fail()
        if (not _positive_int(values["task_id"]) or not _positive_int(values["asset_id"])
                or type(values["path"]) is not str or not values["path"]
                or len(values["path"]) > 4096 or "\x00" in values["path"]
                or any(ord(char) < 32 for char in values["path"])
                or not Path(values["path"]).is_absolute() or ".." in Path(values["path"]).parts
                or type(values["sha256"]) is not str or _SHA.fullmatch(values["sha256"]) is None
                or not _positive_int(values["bytes"], _MAX_SOURCE_BYTES)
                or values["mime"] not in ("image/jpeg", "image/png")
                or type(values["mime"]) is not str
                or type(values["library_id"]) is not str or not _NAME.fullmatch(values["library_id"])
                or not _payload(values["claimed_payload_json"], values["asset_id"])
                or type(values["claim_retry_count"]) is not int
                or not 0 <= values["claim_retry_count"] <= 2**31 - 1):
            _fail()
        _timestamp_epoch(values["claim_started_at"])
        return cls(**values)


def claim_sha256(claim: ApprovedImageClaim) -> str:
    if type(claim) is not ApprovedImageClaim:
        _fail()
    value = {
        "asset_id": claim.asset_id, "bytes": claim.bytes,
        "claim_retry_count": claim.claim_retry_count,
        "claim_started_at": claim.claim_started_at,
        "claimed_payload_json": claim.claimed_payload_json,
        "library_id": claim.library_id, "mime": claim.mime,
        "path": claim.path, "sha256": claim.sha256, "task_id": claim.task_id,
        "version": _CLAIM_VERSION,
    }
    # Revalidate instances constructed directly, bypassing from_candidate.
    if ApprovedImageClaim.from_candidate(value) != claim:
        _fail()
    return hashlib.sha256(_canonical(value).encode("ascii")).hexdigest()


def publication_record_id(claim: ApprovedImageClaim, identity: VectorSpaceIdentity) -> str:
    digest = claim_sha256(claim)
    identity_digest = identity_sha256(identity)
    payload = {"claim_sha256": digest, "identity_sha256": identity_digest,
               "version": _RECORD_VERSION}
    return hashlib.sha256(_canonical(payload).encode("ascii")).hexdigest()


def build_artifact(claim: ApprovedImageClaim, identity: VectorSpaceIdentity,
                   model_name: str, raw_npy_bytes: bytes) -> ImmutableVectorArtifact:
    claim_sha256(claim)
    if (not validate_artifact_identity(identity) or type(model_name) is not str
            or _NAME.fullmatch(model_name) is None or type(raw_npy_bytes) is not bytes
            or not 0 < len(raw_npy_bytes) <= _MAX_VECTOR_BYTES):
        _fail()
    vector = _decode_npy(raw_npy_bytes, identity.dimension)
    if (vector is None or abs(math.sqrt(math.fsum(x*x for x in vector)) - 1.0) > 1e-3):
        _fail()
    try:
        component_digest = canonical_vector_checksum(vector)
    except (TypeError, ValueError, OverflowError):
        _fail()
    ident = identity_sha256(identity)
    record_id = publication_record_id(claim, identity)
    record = ImmutableVectorArtifact(
        record_id=record_id, asset_id=str(claim.asset_id), source_sha256=claim.sha256,
        model_name=model_name, artifact_sha256=identity.artifact_sha256,
        preprocessing_sha256=identity.preprocessing_sha256,
        vector_space_id=identity.vector_space_id, model_version=identity.model_version,
        dimension=identity.dimension, normalization=identity.normalization,
        identity_sha256=ident,
        relative_path=f"image-vectors/{ident}/{record_id}.npy",
        file_sha256=hashlib.sha256(raw_npy_bytes).hexdigest(),
        component_sha256=component_digest, created_at=_timestamp_epoch(claim.claim_started_at),
    )
    if not validate_artifact(record, identity):
        _fail()
    return record


def validate_artifact_identity(identity):
    try:
        identity_sha256(identity)
        return type(identity) is VectorSpaceIdentity
    except (AttributeError, TypeError, ValueError):
        return False


def approved_vector_store(db, root, claim, identity, *, model_name, source_is_current):
    """Bind publication callbacks to one claimed task and its current approval."""
    digest = claim_sha256(claim)
    if (not isinstance(root, Path) or not validate_artifact_identity(identity)
            or type(model_name) is not str or _NAME.fullmatch(model_name) is None
            or not callable(source_is_current)):
        _fail()

    def guard(connection, record, intent_claim):
        if (intent_claim != digest or record.record_id != publication_record_id(claim, identity)
                or record.asset_id != str(claim.asset_id) or record.source_sha256 != claim.sha256
                or record.identity_sha256 != identity_sha256(identity)
                or record.model_name != model_name):
            return False
        task = connection.execute(
            "SELECT type,state,cancel_requested,payload_json,started_at,retry_count "
            "FROM tasks WHERE id=?", (claim.task_id,)).fetchone()
        if task is None or (task[0] != "embed" or task[2] != 0
                or task[3] != claim.claimed_payload_json or task[4] != claim.claim_started_at
                or task[5] != claim.claim_retry_count):
            return False
        intent = connection.execute(
            "SELECT state,asset_id,claim_sha256 FROM image_vector_publications WHERE record_id=?",
            (record.record_id,)).fetchone()
        task_state_ok = task[1] == "running" or (
            task[1] == "finished" and intent == ("committed", claim.asset_id, digest))
        if not task_state_ok:
            return False
        asset = connection.execute(
            "SELECT a.path,a.hash_sha256,a.file_size,a.mime,a.status,u.state,u.sha256,u.bytes "
            "FROM assets a JOIN access_uploads u ON u.asset_id=a.id WHERE a.id=?",
            (claim.asset_id,)).fetchall()
        mappings = connection.execute(
            "SELECT m.library_id,l.state FROM access_asset_libraries m "
            "LEFT JOIN access_libraries l ON l.id=m.library_id WHERE m.asset_id=?",
            (claim.asset_id,)).fetchall()
        legacy = connection.execute(
            "SELECT count(*) FROM embeddings WHERE asset_id=? AND modality='image'",
            (claim.asset_id,)).fetchone()
        if (len(asset) != 1 or asset[0] != (claim.path, claim.sha256, claim.bytes, claim.mime,
                "active", "assigned", claim.sha256, claim.bytes)
                or len(mappings) != 1 or mappings[0] != (claim.library_id, "active")
                or legacy is None or legacy[0] != 0):
            return False
        # Invoke the trusted root-owned source verifier only after the DB claim,
        # upload receipt, library and legacy-row checks have succeeded.
        try:
            return source_is_current() is True
        except Exception:
            return False

    def finalize(connection, record, intent_claim):
        if intent_claim != digest or record.record_id != publication_record_id(claim, identity):
            _fail()
        changed = connection.execute(
            "UPDATE tasks SET state='finished',finished_at=CURRENT_TIMESTAMP,last_error=NULL "
            "WHERE id=? AND type='embed' AND state='running' AND cancel_requested=0 "
            "AND payload_json=? AND started_at=? AND retry_count=?",
            (claim.task_id, claim.claimed_payload_json, claim.claim_started_at,
             claim.claim_retry_count)).rowcount
        if changed != 1:
            _fail()

    return VectorPublicationStore(db, root, identity, guard=guard, finalize=finalize)
