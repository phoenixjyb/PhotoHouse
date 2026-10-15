from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from semantic_pair_cases import case_plan, evaluate, plan_sha256  # noqa: E402


def vectors():
    plan = case_plan()
    basis = {}
    for index, image in enumerate(plan["images"]):
        value = [0.0] * 512
        value[index] = 1.0
        basis[image["id"]] = value
    texts = {
        query["id"]: list(basis[query["expected_image"]])
        for query in plan["queries"]
    }
    return basis, texts


def test_plan_is_fixed_fresh_and_hashes_canonical_content():
    first = case_plan()
    second = case_plan()
    assert first == second
    assert first["schema"] == "photohouse.semantic_pair_cases.v2"
    assert len(first["images"]) == 4
    assert len(first["queries"]) == 12
    assert [query["language"] for query in first["queries"]] == ["en"] * 4 + ["zh"] * 4 + ["zh-en"] * 4
    assert first["dialect_relevance_measured"] is False
    assert first["rendering"] == {
        "background_rgb": [255, 255, 255], "canvas_px": [256, 256],
        "geometry_xyxy_px": [64, 64, 192, 192], "jpeg_quality": 95,
        "jpeg_subsampling": 0,
    }
    assert first["images"] == [
        {"id": "red-circle", "color": [220, 20, 20], "shape": "circle"},
        {"id": "blue-circle", "color": [20, 40, 220], "shape": "circle"},
        {"id": "red-square", "color": [220, 20, 20], "shape": "square"},
        {"id": "blue-square", "color": [20, 40, 220], "shape": "square"},
    ]
    assert first["queries"][:8] == [
        {"id": "en-red-circle", "language": "en", "text": "a red circle on a white background", "expected_image": "red-circle"},
        {"id": "en-blue-circle", "language": "en", "text": "a blue circle on a white background", "expected_image": "blue-circle"},
        {"id": "en-red-square", "language": "en", "text": "a red square on a white background", "expected_image": "red-square"},
        {"id": "en-blue-square", "language": "en", "text": "a blue square on a white background", "expected_image": "blue-square"},
        {"id": "zh-red-circle", "language": "zh", "text": "白色背景上的红色圆形", "expected_image": "red-circle"},
        {"id": "zh-blue-circle", "language": "zh", "text": "白色背景上的蓝色圆形", "expected_image": "blue-circle"},
        {"id": "zh-red-square", "language": "zh", "text": "白色背景上的红色方形", "expected_image": "red-square"},
        {"id": "zh-blue-square", "language": "zh", "text": "白色背景上的蓝色方形", "expected_image": "blue-square"},
    ]
    assert [(query["id"], query["text"], query["expected_image"])
            for query in first["queries"][8:]] == [
        ("zh-en-red-circle", "白色背景上的red circle", "red-circle"),
        ("zh-en-blue-circle", "a blue circle，白色背景", "blue-circle"),
        ("zh-en-red-square", "白色背景上的red square", "red-square"),
        ("zh-en-blue-square", "a blue square，白色背景", "blue-square"),
    ]
    assert plan_sha256() == "abd45ca17c022de3875324a9ebda8c747a98c590e3cacb858e0bbad3fafc4fa4"
    assert plan_sha256() != "6380eb66df9262f173b1cece62a5b0cc749ba64bcf941ea221eba840d4750d5f"
    first["images"][0]["color"][0] = 0
    first["queries"].clear()
    first["rendering"]["canvas_px"][0] = 1
    assert case_plan() == second


def test_perfect_synthetic_pairing_ranks_every_expected_image_first():
    images, texts = vectors()
    report = evaluate(images, texts)
    assert report["schema"] == "photohouse.semantic_pair_evaluation.v2"
    assert len(report["cases"]) == 12
    assert all(row["rank"] == 1 and row["score_margin"] == pytest.approx(1.0)
               for row in report["cases"])
    assert report["languages"] == {
        language: {"cases": 4, "top1": 4, "top2": 4, "mean_reciprocal_rank": 1.0}
        for language in ("en", "zh", "zh-en")
    }
    assert report["overall"] == {"cases": 12, "top1": 12, "top2": 12, "mean_reciprocal_rank": 1.0}
    assert report["dialect_relevance_measured"] is False
    assert all(report[key] is False for key in (
        "family_relevance_measured", "human_reviewed", "activation_approved",
        "legacy_vectors_qualified"))
    assert report["synthetic_only"] is True
    assert all("text" not in row and "vector" not in row for row in report["cases"])


def test_all_tied_vectors_receive_pessimistic_last_rank():
    images, texts = vectors()
    tied = [1.0] + [0.0] * 511
    report = evaluate({key: tied for key in images}, {key: tied for key in texts})
    assert {row["rank"] for row in report["cases"]} == {4}
    assert all(row["score_margin"] == pytest.approx(0.0) for row in report["cases"])
    assert report["overall"]["cases"] == 12
    assert all(metrics["top1"] == 0 and metrics["top2"] == 0
               and metrics["cases"] == 4
               and metrics["mean_reciprocal_rank"] == pytest.approx(0.25)
               for metrics in report["languages"].values())


def test_mixed_cohort_failure_remains_visible_beside_english_and_chinese():
    images, texts = vectors()
    plan = case_plan()
    image_ids = [image["id"] for image in plan["images"]]
    for query in plan["queries"]:
        if query["language"] == "zh-en":
            wrong = next(image_id for image_id in image_ids
                         if image_id != query["expected_image"])
            texts[query["id"]] = list(images[wrong])

    report = evaluate(images, texts)
    assert report["languages"]["en"]["top1"] == 4
    assert report["languages"]["zh"]["top1"] == 4
    assert report["languages"]["zh-en"]["top1"] == 0
    assert report["overall"]["top1"] == 8
    assert all(row["rank"] > 1 for row in report["cases"] if row["language"] == "zh-en")


@pytest.mark.parametrize("side,change", [
    ("image", "missing"), ("image", "extra"), ("text", "missing"), ("text", "extra"),
    ("image", "short"), ("text", "short"), ("image", "nonfinite"),
    ("text", "boolean"), ("image", "zero"), ("text", "nonunit"),
    ("image", "overflow"),
])
def test_invalid_coverage_or_vectors_are_refused_with_fixed_error(side, change):
    images, texts = vectors()
    selected = images if side == "image" else texts
    key = next(iter(selected))
    if change == "missing":
        del selected[key]
    elif change == "extra":
        selected["unexpected"] = selected[key]
    elif change == "short":
        selected[key] = [1.0]
    elif change == "nonfinite":
        selected[key] = [float("nan")] + [0.0] * 511
    elif change == "boolean":
        selected[key] = [True] + [0.0] * 511
    elif change == "zero":
        selected[key] = [0.0] * 512
    elif change == "nonunit":
        selected[key] = [2.0] + [0.0] * 511
    elif change == "overflow":
        selected[key] = [10**10000] + [0.0] * 511
    with pytest.raises(ValueError, match="^invalid_semantic_pair_vectors$"):
        evaluate(images, texts)


def test_mixed_dimensions_are_refused():
    images, texts = vectors()
    images[next(iter(images))] = [1.0] * 511
    with pytest.raises(ValueError, match="^invalid_semantic_pair_vectors$"):
        evaluate(images, texts)
