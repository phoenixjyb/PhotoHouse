"""Deterministic synthetic image/text cases for joint-space qualification."""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any


_SCHEMA = "photohouse.semantic_pair_cases.v2"
_DIMENSION = 512
_TIE_EPSILON = 1e-7
_INVALID = "invalid_semantic_pair_vectors"


def case_plan() -> dict[str, Any]:
    """Return a fresh primitive-only plan for fixed synthetic color/shape pairs."""
    images = [
        {"id": "red-circle", "color": [220, 20, 20], "shape": "circle"},
        {"id": "blue-circle", "color": [20, 40, 220], "shape": "circle"},
        {"id": "red-square", "color": [220, 20, 20], "shape": "square"},
        {"id": "blue-square", "color": [20, 40, 220], "shape": "square"},
    ]
    words = (
        ("red-circle", "a red circle on a white background", "白色背景上的红色圆形"),
        ("blue-circle", "a blue circle on a white background", "白色背景上的蓝色圆形"),
        ("red-square", "a red square on a white background", "白色背景上的红色方形"),
        ("blue-square", "a blue square on a white background", "白色背景上的蓝色方形"),
    )
    # Preserve the v1 English and Chinese cohorts exactly. The mixed-script
    # cohort is separate so its performance remains visible in evaluation.
    queries = [
        {"id": f"{language}-{image_id}", "language": language,
         "text": text, "expected_image": image_id}
        for language, index in (("en", 1), ("zh", 2))
        for image_id, *texts in words
        for text in (texts[index - 1],)
    ]
    queries.extend(
        {"id": f"zh-en-{image_id}", "language": "zh-en", "text": text,
         "expected_image": image_id}
        for image_id, text in (
            ("red-circle", "白色背景上的red circle"),
            ("blue-circle", "a blue circle，白色背景"),
            ("red-square", "白色背景上的red square"),
            ("blue-square", "a blue square，白色背景"),
        )
    )
    return {
        "schema": _SCHEMA,
        "dialect_relevance_measured": False,
        "rendering": {
            "background_rgb": [255, 255, 255],
            "canvas_px": [256, 256],
            "geometry_xyxy_px": [64, 64, 192, 192],
            "jpeg_quality": 95,
            "jpeg_subsampling": 0,
        },
        "images": images,
        "queries": queries,
    }


def plan_sha256() -> str:
    """Hash the canonical ASCII JSON representation of the case plan."""
    encoded = json.dumps(case_plan(), sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _vectors(value: object, expected_ids: set[str]) -> dict[str, tuple[float, ...]]:
    if type(value) is not dict or set(value) != expected_ids:
        raise ValueError(_INVALID)
    result = {}
    for key, raw in value.items():
        if type(raw) not in (list, tuple) or len(raw) != _DIMENSION:
            raise ValueError(_INVALID)
        if any(type(component) not in (int, float) for component in raw):
            raise ValueError(_INVALID)
        try:
            vector = tuple(float(component) for component in raw)
        except (OverflowError, TypeError, ValueError):
            raise ValueError(_INVALID) from None
        if not all(math.isfinite(component) for component in vector):
            raise ValueError(_INVALID)
        norm = math.sqrt(math.fsum(component * component for component in vector))
        if not math.isfinite(norm) or norm == 0.0 or abs(norm - 1.0) > 1e-3:
            raise ValueError(_INVALID)
        result[key] = vector
    return result


def evaluate(image_vectors: object, text_vectors: object) -> dict[str, Any]:
    """Score every planned query against all images with pessimistic tie ranks.

    Inputs map image IDs and query IDs to finite, unit-L2 512-component vectors.
    A tie within ``1e-7`` is counted against the expected image.
    """
    plan = case_plan()
    image_ids = {item["id"] for item in plan["images"]}
    query_ids = {item["id"] for item in plan["queries"]}
    images = _vectors(image_vectors, image_ids)
    queries = _vectors(text_vectors, query_ids)
    cases = []
    language_order = list(dict.fromkeys(query["language"] for query in plan["queries"]))
    by_language = {language: [] for language in language_order}
    for query in plan["queries"]:
        vector = queries[query["id"]]
        scores = {
            image_id: math.fsum(a * b for a, b in zip(vector, image_vector))
            for image_id, image_vector in images.items()
        }
        expected_score = scores[query["expected_image"]]
        competitors = [score for image_id, score in scores.items()
                       if image_id != query["expected_image"]]
        rank = 1 + sum(score >= expected_score - _TIE_EPSILON for score in competitors)
        margin = expected_score - max(competitors)
        result = {"id": query["id"], "language": query["language"],
                  "expected_image": query["expected_image"], "rank": rank,
                  "score_margin": margin}
        cases.append(result)
        by_language[query["language"]].append(result)
    def summarize(rows):
        return {
            "cases": len(rows),
            "top1": sum(row["rank"] == 1 for row in rows),
            "top2": sum(row["rank"] <= 2 for row in rows),
            "mean_reciprocal_rank": math.fsum(1.0 / row["rank"] for row in rows) / len(rows),
        }

    languages = {language: summarize(rows) for language, rows in by_language.items()}
    return {
        "schema": "photohouse.semantic_pair_evaluation.v2",
        "plan_sha256": plan_sha256(),
        "cases": cases,
        "overall": summarize(cases),
        "languages": languages,
        "dialect_relevance_measured": False,
        "family_relevance_measured": False,
        "human_reviewed": False,
        "activation_approved": False,
        "legacy_vectors_qualified": False,
        "synthetic_only": True,
    }
