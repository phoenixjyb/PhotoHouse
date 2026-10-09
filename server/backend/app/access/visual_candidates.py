"""Pure, bounded ranking of already-authorized image vectors.

This module deliberately has no database, filesystem, provider, model or runtime
integration. Callers must build an authorization snapshot and candidate cohort
from their current library transaction before calling the ranker.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import re
import struct
from typing import Literal


MAX_SEEDS = 24
MAX_CANDIDATES = 512
MAX_DIMENSION = 4096
MAX_RESULTS = 20
UNIT_NORM_TOLERANCE = 1e-3

_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z", re.ASCII)
_ASSET_ID = re.compile(r"[1-9][0-9]{0,18}\Z", re.ASCII)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_CHECKSUM_PREFIX = b"photohouse-visual-vector-v1\0"


@dataclass(frozen=True)
class AuthorizationSnapshot:
    """A small allowlist of photos authorized and filtered before ranking.

    This value records a caller's authorization result; it does not prove that
    authorization occurred. The integration must create it inside the current
    ``library.read`` transaction, after checking active status and membership.
    The bounded cohort contains seed IDs and the exact candidate IDs to score,
    not every asset in a potentially large library.
    """

    library_id: str
    photo_ids: frozenset[str]

    def __post_init__(self) -> None:
        values = self.photo_ids
        if type(values) not in (set, frozenset, list, tuple):
            object.__setattr__(self, "photo_ids", frozenset())
            return
        if len(values) > MAX_SEEDS + MAX_CANDIDATES:
            object.__setattr__(self, "photo_ids", frozenset())
            return
        if any(type(value) is not str for value in values):
            object.__setattr__(self, "photo_ids", frozenset())
            return
        object.__setattr__(self, "photo_ids", frozenset(values))


@dataclass(frozen=True)
class VectorSpaceIdentity:
    """Exact identity required for every seed and candidate vector."""

    artifact_sha256: str
    preprocessing_sha256: str
    vector_space_id: str
    model_version: str
    dimension: int
    normalization: Literal["unit_l2"]


@dataclass(frozen=True)
class VectorRecord:
    """Immutable vector record; checksum covers canonical float32 components."""

    asset_id: str
    identity: VectorSpaceIdentity | None
    vector: tuple[float, ...]
    checksum_sha256: str

    def __post_init__(self) -> None:
        # Take an immutable copy so later caller mutation cannot change the
        # scoring input. Oversized/malformed values become invalid and are
        # refused by rank_visual_candidates without unbounded copying.
        try:
            if type(self.vector) not in (tuple, list) or len(self.vector) > MAX_DIMENSION:
                object.__setattr__(self, "vector", ())
            else:
                object.__setattr__(self, "vector", tuple(self.vector))
        except (TypeError, ValueError):
            object.__setattr__(self, "vector", ())


@dataclass(frozen=True)
class VisualCandidate:
    """A proposal linked to the selected photo that scored it highest."""

    asset_id: str
    matched_seed_asset_id: str


@dataclass(frozen=True)
class RankingResult:
    status: Literal["ready", "unavailable"]
    candidates: tuple[VisualCandidate, ...]


UNAVAILABLE = RankingResult("unavailable", ())


def canonical_vector_checksum(vector: tuple[float, ...] | list[float]) -> str:
    """Hash a dimension-tagged, big-endian IEEE-754 float32 vector.

    This canonical component checksum is intentionally distinct from a hash of
    an ``.npy`` container. It is stable across hosts and independent of file
    headers. Invalid shapes or values raise the fixed ``ValueError`` code for
    fixture construction; the ranker converts the same conditions to its fixed
    unavailable result.
    """
    packed = _packed_vector(vector)
    return hashlib.sha256(_CHECKSUM_PREFIX + struct.pack(">I", len(vector)) + packed).hexdigest()


def _packed_vector(vector: tuple[float, ...] | list[float]) -> bytes:
    if type(vector) not in (tuple, list) or not 1 <= len(vector) <= MAX_DIMENSION:
        raise ValueError("invalid_vector")
    values = []
    for component in vector:
        if type(component) not in (int, float):
            raise ValueError("invalid_vector")
        try:
            value = float(component)
        except OverflowError:
            raise ValueError("invalid_vector") from None
        if not math.isfinite(value):
            raise ValueError("invalid_vector")
        values.append(value)
    try:
        packed = struct.pack(f">{len(values)}f", *values)
    except (OverflowError, struct.error):
        raise ValueError("invalid_vector") from None
    if any(not math.isfinite(value) for value in struct.unpack(f">{len(values)}f", packed)):
        raise ValueError("invalid_vector")
    return packed


def _canonical_components(record: VectorRecord, identity: VectorSpaceIdentity) -> tuple[float, ...]:
    if (type(record) is not VectorRecord or type(record.identity) is not VectorSpaceIdentity
            or record.identity != identity or type(record.checksum_sha256) is not str
            or _SHA256.fullmatch(record.checksum_sha256) is None
            or type(record.vector) is not tuple or len(record.vector) != identity.dimension):
        raise ValueError("invalid_vector_record")
    packed = _packed_vector(record.vector)
    checksum = hashlib.sha256(
        _CHECKSUM_PREFIX + struct.pack(">I", len(record.vector)) + packed
    ).hexdigest()
    if checksum != record.checksum_sha256:
        raise ValueError("invalid_vector_record")
    values = struct.unpack(f">{len(record.vector)}f", packed)
    norm = math.sqrt(math.fsum(value * value for value in values))
    if (not math.isfinite(norm) or norm == 0.0
            or abs(norm - 1.0) > UNIT_NORM_TOLERANCE):
        raise ValueError("invalid_vector_record")
    # Scoring uses unit-normalized canonical components. Keep the checksum
    # bound to the original float32 bytes above, before normalization.
    return tuple(value / norm for value in values)


def _valid_identity(identity: object) -> bool:
    return (type(identity) is VectorSpaceIdentity
            and type(identity.artifact_sha256) is str
            and _SHA256.fullmatch(identity.artifact_sha256) is not None
            and type(identity.preprocessing_sha256) is str
            and _SHA256.fullmatch(identity.preprocessing_sha256) is not None
            and type(identity.vector_space_id) is str
            and _ID.fullmatch(identity.vector_space_id) is not None
            and type(identity.model_version) is str
            and _ID.fullmatch(identity.model_version) is not None
            and type(identity.dimension) is int
            and 1 <= identity.dimension <= MAX_DIMENSION
            and type(identity.normalization) is str
            and identity.normalization == "unit_l2")


def _asset_id(value: object) -> bool:
    return (type(value) is str and _ASSET_ID.fullmatch(value) is not None
            and int(value) <= 2**63 - 1)


def _score(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    """Cosine score over canonical, unit-normalized float32 components."""
    return math.fsum(a * b for a, b in zip(left, right))


def rank_visual_candidates(
    authorization: AuthorizationSnapshot,
    *,
    seed_ids: tuple[str, ...] | list[str],
    seed_vectors: tuple[VectorRecord, ...] | list[VectorRecord],
    candidate_ids: tuple[str, ...] | list[str],
    candidate_vectors: tuple[VectorRecord, ...] | list[VectorRecord],
    expected_identity: VectorSpaceIdentity,
) -> RankingResult:
    """Return a bounded deterministic ranking or one fixed refusal value.

    ``candidate_ids`` is the complete bounded cohort already selected from the
    authorized active-photo query, including each candidate for which a vector
    is expected. The vectors must cover that cohort exactly. Authorization is
    checked before any vector is read or scored; an unlisted ID refuses the
    whole cohort. Seeds may also appear in the candidate cohort, but are
    validated and excluded from output.
    """
    try:
        if (type(authorization) is not AuthorizationSnapshot
                or type(authorization.library_id) is not str
                or not _ID.fullmatch(authorization.library_id)
                or type(authorization.photo_ids) is not frozenset
                or len(authorization.photo_ids) > MAX_SEEDS + MAX_CANDIDATES
                or not 1 <= len(seed_ids) <= MAX_SEEDS
                or type(seed_ids) not in (tuple, list)
                or len(candidate_ids) > MAX_CANDIDATES
                or type(candidate_ids) not in (tuple, list)
                or type(seed_vectors) not in (tuple, list)
                or type(candidate_vectors) not in (tuple, list)
                or len(seed_vectors) > MAX_SEEDS
                or len(candidate_vectors) > MAX_CANDIDATES
                or not _valid_identity(expected_identity)):
            return UNAVAILABLE

        if (any(not _asset_id(item) for item in seed_ids)
                or any(not _asset_id(item) for item in candidate_ids)
                or len(set(seed_ids)) != len(seed_ids)
                or len(set(candidate_ids)) != len(candidate_ids)):
            return UNAVAILABLE

        # Authorization is deliberately resolved before checking vector
        # metadata or entering the scoring loop.
        if (any(not _asset_id(item) for item in authorization.photo_ids)
                or not set(seed_ids).issubset(authorization.photo_ids)
                or not set(candidate_ids).issubset(authorization.photo_ids)
                or authorization.photo_ids != frozenset(seed_ids) | frozenset(candidate_ids)):
            return UNAVAILABLE

        seed_records = tuple(seed_vectors)
        candidate_records = tuple(candidate_vectors)
        if (any(type(record) is not VectorRecord or not _asset_id(record.asset_id)
                for record in seed_records + candidate_records)
                or any(record.asset_id not in authorization.photo_ids
                       for record in seed_records + candidate_records)):
            return UNAVAILABLE

        seed_by_id = {record.asset_id: record for record in seed_records}
        candidate_by_id = {record.asset_id: record for record in candidate_records}
        if (len(seed_by_id) != len(seed_records) or len(candidate_by_id) != len(candidate_records)
                or set(seed_by_id) != set(seed_ids)
                or set(candidate_by_id) != set(candidate_ids)):
            return UNAVAILABLE

        seeds = {asset_id: _canonical_components(seed_by_id[asset_id], expected_identity)
                 for asset_id in seed_ids}
        candidates = {asset_id: _canonical_components(candidate_by_id[asset_id], expected_identity)
                      for asset_id in candidate_ids}

        # If a seed is repeated in the candidate cohort, it still denotes one
        # underlying asset and must not carry a conflicting vector record.
        for asset_id in seeds.keys() & candidates.keys():
            seed_record = seed_by_id[asset_id]
            candidate_record = candidate_by_id[asset_id]
            if (seed_record.identity != candidate_record.identity
                    or seed_record.checksum_sha256 != candidate_record.checksum_sha256):
                return UNAVAILABLE

        ranked = []
        for candidate_id, vector in candidates.items():
            if candidate_id in seeds:
                continue
            best_score = None
            best_seed = None
            for seed_id, seed_vector in seeds.items():
                score = _score(seed_vector, vector)
                if (best_score is None or score > best_score
                        or score == best_score and int(seed_id) < int(best_seed)):
                    best_score, best_seed = score, seed_id
            ranked.append((best_score, int(candidate_id), candidate_id, best_seed))

        ranked.sort(key=lambda item: (-item[0], item[1]))
        return RankingResult("ready", tuple(
            VisualCandidate(asset_id, seed_id)
            for _score_value, _numeric_id, asset_id, seed_id in ranked[:MAX_RESULTS]
        ))
    except (TypeError, ValueError, OverflowError, RecursionError):
        return UNAVAILABLE
