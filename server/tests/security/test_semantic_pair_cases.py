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
    assert len(first["images"]) == 4
    assert len(first["queries"]) == 8
    assert {query["language"] for query in first["queries"]} == {"en", "zh"}
    assert len(plan_sha256()) == 64
    first["images"][0]["color"][0] = 0
    first["queries"].clear()
    first["rendering"]["canvas_px"][0] = 1
    assert case_plan() == second


def test_perfect_synthetic_pairing_ranks_every_expected_image_first():
    images, texts = vectors()
    report = evaluate(images, texts)
    assert len(report["cases"]) == 8
    assert all(row["rank"] == 1 and row["score_margin"] == pytest.approx(1.0)
               for row in report["cases"])
    assert report["languages"] == {
        language: {"cases": 4, "top1": 4, "top2": 4, "mean_reciprocal_rank": 1.0}
        for language in ("en", "zh")
    }
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
    assert all(metrics["top1"] == 0 and metrics["top2"] == 0
               and metrics["mean_reciprocal_rank"] == pytest.approx(0.25)
               for metrics in report["languages"].values())


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
