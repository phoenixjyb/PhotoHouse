"""Explicit large-cohort budgets and bounded-vector-memory semantic ranking.

Metadata and ID/score results remain bounded by the configured candidate limit.
Only a single batch of image vectors is retained; no approximate/truncated
candidate selection is used. Runtime callers own current scope and file checks.
"""
from copy import copy
from dataclasses import dataclass
import math
import struct

from .semantic_encoder import (JointSpaceBinding, TextVector, SemanticUnavailable,
    _checked, _CheckFailure)
from .visual_candidates import (VectorRecord, _SHA256, _asset_id,
    _canonical_components, _score)

MAX_LIBRARY_CANDIDATES = 100000
VECTOR_BATCH_SIZE = 128
MAX_VECTOR_READ_BYTES = 256 * 1024**2


@dataclass(frozen=True, slots=True)
class SemanticServingLimits:
    candidate_limit: int
    source_rows: int
    source_bytes: int
    search_seconds: float

    def __post_init__(self):
        if (type(self.candidate_limit) is not int
                or not 513 <= self.candidate_limit <= MAX_LIBRARY_CANDIDATES
                or type(self.source_rows) is not int or not 1 <= self.source_rows <= 1000000
                or type(self.source_bytes) is not int or not 1 <= self.source_bytes <= 256 * 1024**2
                or type(self.search_seconds) not in (int, float)
                or not math.isfinite(self.search_seconds) or not 0 < self.search_seconds <= 120):
            raise ValueError('Invalid semantic serving limits')

    def budget(self, original):
        # Retain the exact same semaphore/admission pool, not a second pool.
        view = copy(original)
        view.rows = self.source_rows
        view.source_bytes = view.search_source_bytes = self.source_bytes
        view.seconds = view.search_seconds = self.search_seconds
        return view


def rank_semantic_batches(query_vector, binding, candidate_batches, *,
                          expected_count, candidate_limit, check=lambda: None):
    """Rank every validated batch, refusing duplicates, corrupt tails or omissions.

    A batch has at most 128 vectors. Only IDs/scores survive each batch. The
    caller must verify eligible metadata and files before model execution and
    re-authorize after this function returns; this pure function grants no scope.
    """
    try:
        _checked(check)
        if (type(binding) is not JointSpaceBinding or type(query_vector) is not TextVector
                or type(candidate_limit) is not int or not 513 <= candidate_limit <= MAX_LIBRARY_CANDIDATES
                or type(expected_count) is not int or not 0 <= expected_count <= candidate_limit
                or query_vector.binding_sha256 != binding.binding_sha256
                or type(query_vector.query_sha256) is not str
                or _SHA256.fullmatch(query_vector.query_sha256) is None
                or type(query_vector.checksum_sha256) is not str
                or _SHA256.fullmatch(query_vector.checksum_sha256) is None):
            raise SemanticUnavailable()
        query = _canonical_components(VectorRecord('1', binding.text_identity,
            query_vector.vector, query_vector.checksum_sha256), binding.text_identity)
        ranked, seen = [], set()
        for batch in candidate_batches:
            _checked(check)
            if type(batch) is not tuple or not 1 <= len(batch) <= VECTOR_BATCH_SIZE:
                raise SemanticUnavailable()
            if len(seen) + len(batch) > expected_count:
                raise SemanticUnavailable()
            for record in batch:
                _checked(check)
                if (type(record) is not VectorRecord or not _asset_id(record.asset_id)
                        or record.asset_id in seen):
                    raise SemanticUnavailable()
                vector = _canonical_components(record, binding.image_identity)
                seen.add(record.asset_id)
                ranked.append((record.asset_id, _score(query, vector)))
                _checked(check)
            # Release the consumed batch before requesting the next one from a
            # producer that builds it incrementally.
            del record, vector, batch
        if len(seen) != expected_count:
            raise SemanticUnavailable()
        ranked.sort(key=lambda item: (-item[1], int(item[0])))
        _checked(check)
        return tuple(ranked)
    except SemanticUnavailable:
        raise
    except _CheckFailure as failure:
        raise failure.error
    except (TypeError, ValueError, OverflowError, RecursionError, struct.error):
        raise SemanticUnavailable() from None
