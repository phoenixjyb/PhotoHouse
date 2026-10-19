"""Validation and offline ranking metrics for reviewed natural-scene cases.

This module reads no files and performs no model or service work. A caller owns
filesystem checks for the image paths before it supplies vectors.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any


_DATASET_SCHEMA = "photohouse.semantic_scene_cases.v1"
_REPORT_SCHEMA = "photohouse.semantic_scene_evaluation.v1"
_DIMENSION = 512
_TIE_EPSILON = 1e-7
_INVALID_DATASET = "invalid_semantic_scene_dataset"
_INVALID_VECTORS = "invalid_semantic_scene_vectors"
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z", re.ASCII)
_DIGEST = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_LANGUAGES = ("en", "zh", "zh-en")


def _bad_dataset() -> None:
    raise ValueError(_INVALID_DATASET)


def _path_is_absolute_without_parent(path: str) -> bool:
    # Accept either local path convention, while checking components lexically
    # so this remains independent of the host running the pure validator.
    if "\x00" in path:
        return False
    if PurePosixPath(path).is_absolute():
        return ".." not in PurePosixPath(path).parts
    if PureWindowsPath(path).is_absolute():
        return ".." not in PureWindowsPath(path).parts
    return False


def _single_line_text(value: object) -> bool:
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
    """Validate and return a fresh primitive-only normalized dataset.

    Exact keys are required throughout. Paths are checked lexically only; the
    caller must establish that each file exists and matches its declared hash.
    """
    if type(value) is not dict or set(value) != {"schema", "review", "images", "cases"}:
        _bad_dataset()
    if value["schema"] != _DATASET_SCHEMA:
        _bad_dataset()
    review = value["review"]
    if (type(review) is not dict or set(review) != {"natural_scenes", "labels_reviewed"}
            or type(review["natural_scenes"]) is not bool
            or type(review["labels_reviewed"]) is not bool):
        _bad_dataset()

    raw_images = value["images"]
    raw_cases = value["cases"]
    if type(raw_images) is not list or not 4 <= len(raw_images) <= 64:
        _bad_dataset()
    if type(raw_cases) is not list or not 2 <= len(raw_cases) <= 32:
        _bad_dataset()

    images: list[dict[str, str]] = []
    image_ids: set[str] = set()
    paths: set[str] = set()
    hashes: set[str] = set()
    for image in raw_images:
        if type(image) is not dict or set(image) != {"id", "path", "sha256"}:
            _bad_dataset()
        image_id, path, digest = image["id"], image["path"], image["sha256"]
        if (type(image_id) is not str or not _ID.fullmatch(image_id)
                or type(path) is not str or not _path_is_absolute_without_parent(path)
                or type(digest) is not str or not _DIGEST.fullmatch(digest)
                or image_id in image_ids or path in paths or digest in hashes):
            _bad_dataset()
        image_ids.add(image_id)
        paths.add(path)
        hashes.add(digest)
        images.append({"id": image_id, "path": path, "sha256": digest})

    cases: list[dict[str, Any]] = []
    case_ids: set[str] = set()
    for case in raw_cases:
        if type(case) is not dict or set(case) != {"id", "relevant_images", "queries"}:
            _bad_dataset()
        case_id = case["id"]
        relevant = case["relevant_images"]
        queries = case["queries"]
        if (type(case_id) is not str or not _ID.fullmatch(case_id)
                or case_id in case_ids or type(relevant) is not list
                or not 1 <= len(relevant) < len(images)
                or any(type(item) is not str or item not in image_ids for item in relevant)
                or len(set(relevant)) != len(relevant)
                or type(queries) is not dict or set(queries) != set(_LANGUAGES)
                or any(not _single_line_text(queries[language]) for language in _LANGUAGES)):
            _bad_dataset()
        case_ids.add(case_id)
        cases.append({
            "id": case_id,
            "relevant_images": list(relevant),
            "queries": {language: queries[language] for language in _LANGUAGES},
        })

    return {
        "schema": _DATASET_SCHEMA,
        "review": {"natural_scenes": review["natural_scenes"],
                   "labels_reviewed": review["labels_reviewed"]},
        "images": images,
        "cases": cases,
    }


def dataset_sha256(dataset: object) -> str:
    """Hash canonical dataset content while excluding local image paths."""
    normalized = validate_dataset(dataset)
    fingerprint = {
        "schema": normalized["schema"],
        "review": normalized["review"],
        "images": [{"id": image["id"], "sha256": image["sha256"]}
                   for image in normalized["images"]],
        "cases": normalized["cases"],
    }
    encoded = json.dumps(fingerprint, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _vectors(value: object, expected_ids: set[str], dimension: int) -> dict[str, tuple[float, ...]]:
    if type(value) is not dict or set(value) != expected_ids:
        raise ValueError(_INVALID_VECTORS)
    result: dict[str, tuple[float, ...]] = {}
    for key, raw in value.items():
        if type(raw) not in (list, tuple) or len(raw) != dimension:
            raise ValueError(_INVALID_VECTORS)
        if any(type(component) not in (int, float) for component in raw):
            raise ValueError(_INVALID_VECTORS)
        try:
            vector = tuple(float(component) for component in raw)
        except (OverflowError, TypeError, ValueError):
            raise ValueError(_INVALID_VECTORS) from None
        if not all(math.isfinite(component) for component in vector):
            raise ValueError(_INVALID_VECTORS)
        norm = math.sqrt(math.fsum(component * component for component in vector))
        if not math.isfinite(norm) or norm == 0.0 or abs(norm - 1.0) > 1e-3:
            raise ValueError(_INVALID_VECTORS)
        result[key] = vector
    return result


def _relevant_ranks(scores: dict[str, float], relevant: set[str]) -> dict[str, int]:
    """Return deterministic pessimistic one-based ranks for relevant images.

    Every nonrelevant image within 1e-7 of a relevant image is counted ahead.
    Relevant near-ties use image ID order. Computing each relevant rank directly
    avoids a non-transitive sort comparator around the epsilon boundary.
    """
    ranks = {}
    for candidate in relevant:
        score = scores[candidate]
        ahead = 0
        for other, other_score in scores.items():
            if other == candidate:
                continue
            if other not in relevant:
                ahead += other_score >= score - _TIE_EPSILON
            else:
                ahead += (other_score > score + _TIE_EPSILON
                          or (abs(other_score - score) <= _TIE_EPSILON and other < candidate))
        ranks[candidate] = 1 + ahead
    return ranks


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "queries": len(rows),
        "top1": sum(row["rank"] == 1 for row in rows),
        "top5": sum(row["rank"] <= 5 for row in rows),
        "mean_reciprocal_rank": math.fsum(1.0 / row["rank"] for row in rows) / len(rows),
        "recall_at_5": math.fsum(row["recall_at_5"] for row in rows) / len(rows),
    }


def evaluate(dataset: object, image_vectors: object, text_vectors: object,
             *, dimension: int = _DIMENSION) -> dict[str, Any]:
    """Evaluate exact image/query vector maps; return metrics without private inputs.

    Text vector keys are ``<case-id>:<language>``. Ranking uses dot products of
    validated unit vectors. ``recall_at_5`` averages per-query relevant-image
    recall, counting a nonrelevant image within 1e-7 of a relevant result ahead.
    No score threshold or activation decision is applied. ``matched_case_count``
    counts cases whose three language queries all rank a relevant image first.
    """
    if type(dimension) is not int or dimension not in (_DIMENSION, 768):
        raise ValueError(_INVALID_VECTORS)
    normalized = validate_dataset(dataset)
    image_ids = {image["id"] for image in normalized["images"]}
    query_ids = {f'{case["id"]}:{language}'
                 for case in normalized["cases"] for language in _LANGUAGES}
    images = _vectors(image_vectors, image_ids, dimension)
    texts = _vectors(text_vectors, query_ids, dimension)
    languages: dict[str, list[dict[str, Any]]] = {language: [] for language in _LANGUAGES}
    case_metrics: list[dict[str, Any]] = []

    for case in normalized["cases"]:
        language_ranks: dict[str, int] = {}
        for language in _LANGUAGES:
            key = f'{case["id"]}:{language}'
            vector = texts[key]
            scores = {
                image_id: math.fsum(a * b for a, b in zip(vector, image_vector))
                for image_id, image_vector in images.items()
            }
            relevant = set(case["relevant_images"])
            relevant_ranks_by_image = _relevant_ranks(scores, relevant)
            relevant_ranks = list(relevant_ranks_by_image.values())
            first_rank = min(relevant_ranks)
            recall = sum(rank <= 5 for rank in relevant_ranks) / len(relevant)
            row = {"case_id": case["id"], "language": language,
                   "rank": first_rank, "recall_at_5": recall}
            languages[language].append(row)
            language_ranks[language] = first_rank
        case_metrics.append({
            "case_id": case["id"],
            "ranks": language_ranks,
            "all_languages_top1": all(rank == 1 for rank in language_ranks.values()),
            "worst_language_rank": max(language_ranks.values()),
        })

    flattened = [row for language in _LANGUAGES for row in languages[language]]
    all_languages_top1_cases = sum(case["all_languages_top1"] for case in case_metrics)
    candidate_count = len(normalized["images"])
    return {
        "schema": _REPORT_SCHEMA,
        "dataset_sha256": dataset_sha256(normalized),
        "candidate_count": candidate_count,
        "matched_case_count": len(case_metrics),
        "all_languages_top1_cases": all_languages_top1_cases,
        "top_k": 5,
        "effective_top_k": min(5, candidate_count),
        "overall": _summary(flattened),
        "languages": {language: _summary(languages[language]) for language in _LANGUAGES},
        "cases": case_metrics,
        "review_declarations": dict(normalized["review"]),
        "dialect_relevance_measured": False,
        "family_relevance_measured": False,
        "activation_approved": False,
    }
