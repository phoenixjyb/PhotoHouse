"""Pure validation for immutable image-vector artifact metadata.

This module never opens files or databases and never asserts that an artifact
was produced by an approved provider. A producer must separately verify the
checkpoint, source bytes, and journaled file publication before inserting a
record.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re

from .visual_candidates import MAX_DIMENSION, VectorSpaceIdentity


_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_IDENTIFIER = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z", re.ASCII)
_ASSET_ID = re.compile(r"[1-9][0-9]{0,18}\Z", re.ASCII)
_IDENTITY_VERSION = "photohouse-image-vector-identity-v1"


@dataclass(frozen=True, slots=True)
class ImmutableVectorArtifact:
    """Completed vector artifact metadata using the SQLite column names."""

    record_id: str
    asset_id: str
    source_sha256: str
    model_name: str
    artifact_sha256: str
    preprocessing_sha256: str
    vector_space_id: str
    model_version: str
    dimension: int
    normalization: str
    identity_sha256: str
    relative_path: str
    file_sha256: str
    component_sha256: str
    created_at: int
    status: str = "ready"


def _valid_identity(identity: object) -> bool:
    return (
        type(identity) is VectorSpaceIdentity
        and type(identity.artifact_sha256) is str
        and _SHA256.fullmatch(identity.artifact_sha256) is not None
        and type(identity.preprocessing_sha256) is str
        and _SHA256.fullmatch(identity.preprocessing_sha256) is not None
        and type(identity.vector_space_id) is str
        and _IDENTIFIER.fullmatch(identity.vector_space_id) is not None
        and type(identity.model_version) is str
        and _IDENTIFIER.fullmatch(identity.model_version) is not None
        and type(identity.dimension) is int
        and 1 <= identity.dimension <= MAX_DIMENSION
        and type(identity.normalization) is str
        and identity.normalization == "unit_l2"
    )


def identity_sha256(identity: VectorSpaceIdentity) -> str:
    """Hash a versioned, canonical representation of vector-space identity."""
    if not _valid_identity(identity):
        raise ValueError("invalid_vector_identity") from None
    payload = {
        "artifact_sha256": identity.artifact_sha256,
        "dimension": identity.dimension,
        "model_version": identity.model_version,
        "normalization": identity.normalization,
        "preprocessing_sha256": identity.preprocessing_sha256,
        "vector_space_id": identity.vector_space_id,
        "version": _IDENTITY_VERSION,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("ascii")).hexdigest()


def validate_artifact(
    record: ImmutableVectorArtifact,
    expected_identity: VectorSpaceIdentity | None = None,
) -> bool:
    """Return whether metadata is canonical and bound to one vector identity."""
    try:
        if type(record) is not ImmutableVectorArtifact:
            return False
        if (type(record.asset_id) is not str or _ASSET_ID.fullmatch(record.asset_id) is None
                or int(record.asset_id) > 2**63 - 1):
            return False
        if type(record.model_name) is not str or _IDENTIFIER.fullmatch(record.model_name) is None:
            return False
        if any(type(value) is not str or _SHA256.fullmatch(value) is None
               for value in (record.record_id, record.source_sha256, record.artifact_sha256,
                             record.preprocessing_sha256, record.identity_sha256,
                             record.file_sha256, record.component_sha256)):
            return False
        if (type(record.vector_space_id) is not str
                or _IDENTIFIER.fullmatch(record.vector_space_id) is None
                or type(record.model_version) is not str
                or _IDENTIFIER.fullmatch(record.model_version) is None
                or type(record.dimension) is not int
                or not 1 <= record.dimension <= MAX_DIMENSION
                or type(record.normalization) is not str
                or record.normalization != "unit_l2"
                or type(record.created_at) is not int
                or record.created_at < 0
                or type(record.status) is not str
                or record.status != "ready"):
            return False

        identity = VectorSpaceIdentity(
            artifact_sha256=record.artifact_sha256,
            preprocessing_sha256=record.preprocessing_sha256,
            vector_space_id=record.vector_space_id,
            model_version=record.model_version,
            dimension=record.dimension,
            normalization=record.normalization,
        )
        if not _valid_identity(identity) or record.identity_sha256 != identity_sha256(identity):
            return False
        if expected_identity is not None:
            if not _valid_identity(expected_identity) or identity != expected_identity:
                return False

        expected_path = f"image-vectors/{record.identity_sha256}/{record.record_id}.npy"
        return type(record.relative_path) is str and record.relative_path == expected_path
    except (AttributeError, OverflowError, TypeError, ValueError):
        return False
