"""Pure, bounded proposals for photos near explicitly selected memories.

Callers resolve membership, active status, vectors, and recorded capture times
inside their current authorized read. This module performs no I/O and returns
only candidate IDs, anchor IDs, and a narrowly stated time reason.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import math
import re
from typing import Literal

from .visual_candidates import (
    MAX_CANDIDATES,
    MAX_RESULTS,
    MAX_SEEDS,
    AuthorizationSnapshot,
    VectorRecord,
    VectorSpaceIdentity,
    _ID,
    _asset_id,
    _canonical_components,
    _score,
    _valid_identity,
)


_CAPTURE_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z", re.ASCII)
_CAPTURE_DATETIME = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9]{2}:[0-9]{2}"
    r"(?::[0-9]{2}(?:\.[0-9]{1,6})?)?"
    r"(?:Z|[+-][0-9]{2}:?[0-9]{2})?\Z",
    re.ASCII,
)
_MAX_EXCLUSIONS = 512


@dataclass(frozen=True)
class GroupCandidate:
    asset_id: str
    matched_seed_asset_id: str
    time_reason: Literal["same_recorded_day", "within_recorded_window"]


@dataclass(frozen=True)
class GroupProposal:
    status: Literal["ready", "unavailable"]
    candidates: tuple[GroupCandidate, ...]


UNAVAILABLE = GroupProposal("unavailable", ())


def _recorded_time(value: object):
    """Parse only bounded ISO capture metadata; preserve date precision."""
    if type(value) is not str or len(value) > 128:
        return None
    try:
        if _CAPTURE_DATE.fullmatch(value):
            return ("date", date.fromisoformat(value))
        if _CAPTURE_DATETIME.fullmatch(value):
            parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
            return ("datetime", parsed)
    except (ValueError, OverflowError):
        return None
    return None


def _time_match(left, right, max_gap_seconds: int):
    if left is None or right is None:
        return None
    left_kind, left_value = left
    right_kind, right_value = right
    if left_kind == "date" or right_kind == "date":
        left_day = left_value.date() if left_kind == "datetime" else left_value
        right_day = right_value.date() if right_kind == "datetime" else right_value
        if left_day != right_day:
            return None
        return "same_recorded_day"
    left_aware = left_value.utcoffset() is not None
    right_aware = right_value.utcoffset() is not None
    if left_aware != right_aware:
        return None
    if left_aware:
        left_value = left_value.astimezone(timezone.utc)
        right_value = right_value.astimezone(timezone.utc)
    try:
        gap = abs((left_value - right_value).total_seconds())
    except (OverflowError, TypeError):
        return None
    return "within_recorded_window" if gap <= max_gap_seconds else None


def _bounded_ids(values, maximum, *, allow_set=False):
    allowed = (tuple, list, frozenset, set) if allow_set else (tuple, list)
    if type(values) not in allowed or len(values) > maximum:
        return None
    try:
        items = tuple(values)
    except (TypeError, ValueError, RecursionError):
        return None
    if any(not _asset_id(item) for item in items) or len(set(items)) != len(items):
        return None
    return items


def propose_memory_group(
    authorization,
    *,
    seed_ids,
    seed_vectors,
    candidate_ids,
    candidate_vectors,
    expected_identity,
    capture_times,
    excluded_ids=(),
    minimum_similarity=0.9,
    max_gap_seconds=21600,
) -> GroupProposal:
    """Return a deterministic, anchor-only group proposal or fixed refusal.

    Vector and authorization validation covers the whole supplied cohort before
    any cosine scoring. Temporal eligibility is applied before scoring and
    before the twenty-result cap, so an older high-scoring candidate cannot
    displace a time-eligible result.
    """
    try:
        seeds = _bounded_ids(seed_ids, MAX_SEEDS)
        candidates = _bounded_ids(candidate_ids, MAX_CANDIDATES)
        exclusions = _bounded_ids(excluded_ids, _MAX_EXCLUSIONS, allow_set=True)
        if (seeds is None or not seeds or candidates is None or exclusions is None
                or set(seeds) & set(exclusions)
                or type(seed_vectors) not in (tuple, list)
                or len(seed_vectors) > MAX_SEEDS
                or type(candidate_vectors) not in (tuple, list)
                or len(candidate_vectors) > MAX_CANDIDATES
                or not _valid_identity(expected_identity)
                or type(minimum_similarity) not in (int, float)
                or not math.isfinite(float(minimum_similarity))
                or not 0 < float(minimum_similarity) <= 1
                or type(max_gap_seconds) is not int
                or not 1 <= max_gap_seconds <= 172800
                or type(capture_times) is not dict
                or len(capture_times) > MAX_SEEDS + MAX_CANDIDATES):
            return UNAVAILABLE

        cohort = set(seeds) | set(candidates)
        if (len(cohort) > MAX_SEEDS + MAX_CANDIDATES
                or type(authorization) is not AuthorizationSnapshot
                or type(authorization.library_id) is not str
                or not _ID.fullmatch(authorization.library_id)
                or type(authorization.photo_ids) is not frozenset
                or any(not _asset_id(item) for item in authorization.photo_ids)
                or authorization.photo_ids != frozenset(cohort)
                or set(capture_times) != cohort
                or any(type(key) is not str or not _asset_id(key) for key in capture_times)
                or any(value is not None and (type(value) is not str or len(value) > 128)
                       for value in capture_times.values())):
            return UNAVAILABLE

        parsed_times = {asset_id: _recorded_time(capture_times[asset_id])
                        for asset_id in cohort}
        if type(seed_vectors) not in (tuple, list) or type(candidate_vectors) not in (tuple, list):
            return UNAVAILABLE
        seed_records = tuple(seed_vectors)
        candidate_records = tuple(candidate_vectors)
        if (any(type(record) is not VectorRecord or not _asset_id(record.asset_id)
                or record.asset_id not in cohort for record in seed_records + candidate_records)):
            return UNAVAILABLE
        seed_by_id = {record.asset_id: record for record in seed_records}
        candidate_by_id = {record.asset_id: record for record in candidate_records}
        if (len(seed_by_id) != len(seed_records) or len(candidate_by_id) != len(candidate_records)
                or set(seed_by_id) != set(seeds) or set(candidate_by_id) != set(candidates)):
            return UNAVAILABLE
        # As in the visual ranker, duplicate seed membership is allowed only
        # when both cohort entries refer to the same exact vector record.
        for asset_id in seed_by_id.keys() & candidate_by_id.keys():
            left, right = seed_by_id[asset_id], candidate_by_id[asset_id]
            if left.identity != right.identity or left.checksum_sha256 != right.checksum_sha256:
                return UNAVAILABLE

        # Canonicalize every supplied vector before scoring any pair. This
        # binds scores to validated checksums, identity, dimension, and norm.
        canonical_seeds = {asset_id: _canonical_components(seed_by_id[asset_id], expected_identity)
                           for asset_id in seeds}
        canonical_candidates = {
            asset_id: _canonical_components(candidate_by_id[asset_id], expected_identity)
            for asset_id in candidates
        }
        eligible = []
        for candidate_id in candidates:
            if candidate_id in seed_by_id or candidate_id in exclusions:
                continue
            matches = []
            for seed_id in seeds:
                reason = _time_match(parsed_times[seed_id], parsed_times[candidate_id], max_gap_seconds)
                if reason is not None:
                    matches.append((seed_id, reason))
            if matches:
                eligible.append((candidate_id, matches))

        ranked = []
        for candidate_id, matches in eligible:
            best_score = None
            best_seed = None
            best_reason = None
            for seed_id, reason in matches:
                score = _score(canonical_seeds[seed_id], canonical_candidates[candidate_id])
                if (score >= minimum_similarity and
                        (best_score is None or score > best_score or
                         score == best_score and int(seed_id) < int(best_seed))):
                    best_score, best_seed, best_reason = score, seed_id, reason
            if best_seed is not None:
                ranked.append((best_score, int(candidate_id), candidate_id, best_seed, best_reason))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        limit = min(MAX_RESULTS, max(0, 24 - len(seeds)))
        result = tuple(GroupCandidate(asset_id, seed_id, reason)
                       for _score_value, _numeric_id, asset_id, seed_id, reason in ranked[:limit])
        return GroupProposal("ready", result)
    except (TypeError, ValueError, OverflowError, RecursionError, AttributeError):
        return UNAVAILABLE
