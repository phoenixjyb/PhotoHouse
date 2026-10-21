"""Pure offline scoring for explicitly labeled semantic exclusion cases.

This module accepts caller-provided image and text vectors. It performs no file,
model, provider, service, or configuration IO and never approves activation.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any

from semantic_scene_cases import _relevant_ranks, _vectors


_DATASET_SCHEMA = "photohouse.semantic_exclusion_cases.v1"
_REPORT_SCHEMA = "photohouse.semantic_exclusion_evaluation.v1"
_LANGUAGES = ("en", "zh", "zh-en")
_DIMENSIONS = (512, 768)
_TIE_EPSILON = 1e-7
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z", re.ASCII)
_INVALID_DATASET = "invalid_semantic_exclusion_dataset"
_INVALID_VECTORS = "invalid_semantic_exclusion_vectors"


def _bad_dataset() -> None:
    raise ValueError(_INVALID_DATASET)


def _bad_vectors() -> None:
    raise ValueError(_INVALID_VECTORS)


def _query_text(value: object) -> bool:
    if type(value) is not str or not value or value != value.strip():
        return False
    try:
        encoded = value.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        return False
    return len(encoded) <= 512 and not any(
        ord(char) < 32 or 0x7F <= ord(char) <= 0x9F or char in "\u2028\u2029"
        for char in value
    )


def validate_dataset(value: object) -> dict[str, Any]:
    """Validate and normalize the closed exclusion diagnostic schema."""
    if (type(value) is not dict or set(value) != {"schema", "images", "cases"}
            or value["schema"] != _DATASET_SCHEMA):
        _bad_dataset()
    raw_images, raw_cases = value["images"], value["cases"]
    if type(raw_images) is not list or not 4 <= len(raw_images) <= 64:
        _bad_dataset()
    if type(raw_cases) is not list or not 1 <= len(raw_cases) <= 64:
        _bad_dataset()

    image_ids: list[str] = []
    seen_images: set[str] = set()
    for image_id in raw_images:
        if (type(image_id) is not str or not _ID.fullmatch(image_id)
                or image_id in seen_images):
            _bad_dataset()
        seen_images.add(image_id)
        image_ids.append(image_id)
    known_images = set(image_ids)

    cases: list[dict[str, Any]] = []
    seen_cases: set[str] = set()
    for case in raw_cases:
        if (type(case) is not dict or set(case) != {
                "id", "relevant_images", "forbidden_images", "queries"}):
            _bad_dataset()
        case_id = case["id"]
        relevant, forbidden, queries = (
            case["relevant_images"], case["forbidden_images"], case["queries"])
        if (type(case_id) is not str or not _ID.fullmatch(case_id)
                or case_id in seen_cases or type(relevant) is not list
                or type(forbidden) is not list or not relevant or not forbidden
                or any(type(item) is not str or item not in known_images
                       for item in relevant + forbidden)
                or len(set(relevant)) != len(relevant)
                or len(set(forbidden)) != len(forbidden)
                or set(relevant) & set(forbidden)
                or type(queries) is not dict or set(queries) != set(_LANGUAGES)
                or any(not _query_text(queries[language]) for language in _LANGUAGES)):
            _bad_dataset()
        seen_cases.add(case_id)
        cases.append({
            "id": case_id,
            "relevant_images": list(relevant),
            "forbidden_images": list(forbidden),
            "queries": {language: queries[language] for language in _LANGUAGES},
        })
    return {"schema": _DATASET_SCHEMA, "images": image_ids, "cases": cases}


def dataset_sha256(dataset: object) -> str:
    """Fingerprint exact schema, IDs, labels and query bytes; paths are absent."""
    normalized = validate_dataset(dataset)
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _dot(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    return math.fsum(a * b for a, b in zip(left, right))


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(rows)
    ahead = sum(row["forbidden_ahead_or_tied"] for row in rows)
    included = sum(row["forbidden_in_top_k"] for row in rows)
    return {
        "queries": count,
        "forbidden_ahead_or_tied": ahead,
        "forbidden_ahead_or_tied_rate": ahead / count,
        "forbidden_in_top_k": included,
        "forbidden_in_top_k_rate": included / count,
    }


def evaluate(dataset: object, image_vectors: object, text_vectors: object,
             *, dimension: int, top_k: int = 5) -> dict[str, Any]:
    """Score explicit forbidden candidates for all English/Chinese/mixed queries.

    Relevant ranks use the established pessimistic scene policy. A forbidden
    image is "ahead or tied" if it scores within 1e-7 of the best relevant
    image. A forbidden image is counted in top-k if fewer than k candidates are
    strictly above it by more than 1e-7; ties therefore count as possible
    inclusion, which is conservative for an exclusion diagnostic.
    """
    normalized = validate_dataset(dataset)
    if type(dimension) is not int or dimension not in _DIMENSIONS:
        _bad_vectors()
    if type(top_k) is not int or not 1 <= top_k <= 64:
        _bad_vectors()
    image_ids = set(normalized["images"])
    text_ids = {f'{case["id"]}:{language}'
                for case in normalized["cases"] for language in _LANGUAGES}
    try:
        images = _vectors(image_vectors, image_ids, dimension)
        texts = _vectors(text_vectors, text_ids, dimension)
    except (TypeError, ValueError, OverflowError):
        _bad_vectors()

    effective_top_k = min(top_k, len(image_ids))
    language_rows: dict[str, list[dict[str, Any]]] = {
        language: [] for language in _LANGUAGES}
    case_rows: list[dict[str, Any]] = []
    for case in normalized["cases"]:
        per_language = {}
        for language in _LANGUAGES:
            query_id = f'{case["id"]}:{language}'
            query = texts[query_id]
            scores = {image_id: _dot(query, vector)
                      for image_id, vector in images.items()}
            relevant = set(case["relevant_images"])
            forbidden = set(case["forbidden_images"])
            relevant_ranks = _relevant_ranks(scores, relevant)
            best_rank = min(relevant_ranks.values())
            best_relevant_score = max(scores[image_id] for image_id in relevant)
            forbidden_ahead_or_tied = any(
                scores[image_id] >= best_relevant_score - _TIE_EPSILON
                for image_id in forbidden)
            forbidden_in_top_k = any(
                sum(other_score > scores[image_id] + _TIE_EPSILON
                    for other_id, other_score in scores.items() if other_id != image_id)
                < effective_top_k
                for image_id in forbidden)
            row = {
                "case_id": case["id"],
                "language": language,
                "best_relevant_rank": best_rank,
                "forbidden_ahead_or_tied": forbidden_ahead_or_tied,
                "forbidden_in_top_k": forbidden_in_top_k,
            }
            language_rows[language].append(row)
            per_language[language] = {
                "best_relevant_rank": best_rank,
                "forbidden_ahead_or_tied": forbidden_ahead_or_tied,
                "forbidden_in_top_k": forbidden_in_top_k,
            }
        case_rows.append({"case_id": case["id"], "languages": per_language})

    all_rows = [row for language in _LANGUAGES for row in language_rows[language]]
    return {
        "schema": _REPORT_SCHEMA,
        "dataset_sha256": dataset_sha256(normalized),
        "candidate_count": len(image_ids),
        "case_count": len(normalized["cases"]),
        "top_k": top_k,
        "effective_top_k": effective_top_k,
        "overall": _summary(all_rows),
        "languages": {language: _summary(language_rows[language])
                      for language in _LANGUAGES},
        "cases": case_rows,
        "activation_approved": False,
    }
