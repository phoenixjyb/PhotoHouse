from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from semantic_scene_cases import dataset_sha256, evaluate, validate_dataset  # noqa: E402


def dataset():
    return {
        "schema": "photohouse.semantic_scene_cases.v1",
        "review": {"natural_scenes": True, "labels_reviewed": True},
        "images": [
            {"id": name, "path": f"/private/photos/{name}.jpg", "sha256": f"{index:064x}"}
            for index, name in enumerate(("img-a", "img-b", "img-c", "img-d"), 1)
        ],
        "cases": [
            {"id": "scene-one", "relevant_images": ["img-a", "img-b"],
             "queries": {"en": "A red house beside a lake", "zh": "湖边的红房子",
                         "zh-en": "湖边的 red house"}},
            {"id": "scene-two", "relevant_images": ["img-c"],
             "queries": {"en": "Two children in a garden", "zh": "花园里的两个孩子",
                         "zh-en": "花园里的 two children"}},
        ],
    }


def vectors(value=None):
    value = value or dataset()
    image_vectors = {}
    for index, image in enumerate(value["images"]):
        vector = [0.0] * 512
        vector[index] = 1.0
        image_vectors[image["id"]] = vector
    text_vectors = {}
    for case in value["cases"]:
        for language in ("en", "zh", "zh-en"):
            text_vectors[f'{case["id"]}:{language}'] = list(
                image_vectors[case["relevant_images"][0]])
    return image_vectors, text_vectors


def eight_image_dataset():
    value = dataset()
    for index, name in enumerate(("img-e", "img-f", "img-g", "img-h"), 5):
        value["images"].append({"id": name, "path": f"/private/photos/{name}.jpg",
                                "sha256": f"{index:064x}"})
    return value


def test_validation_returns_fresh_primitive_dataset_and_fingerprint_ignores_paths():
    source = dataset()
    normalized = validate_dataset(source)
    assert normalized == source
    normalized["cases"][0]["relevant_images"].clear()
    assert source["cases"][0]["relevant_images"] == ["img-a", "img-b"]

    first_hash = dataset_sha256(source)
    relocated = copy.deepcopy(source)
    for image in relocated["images"]:
        image["path"] = f'/relocated/{image["id"]}.jpg'
    assert dataset_sha256(relocated) == first_hash

    changed_label = copy.deepcopy(source)
    changed_label["cases"][0]["relevant_images"] = ["img-a"]
    assert dataset_sha256(changed_label) != first_hash
    changed_query = copy.deepcopy(source)
    changed_query["cases"][0]["queries"]["zh"] += "。"
    assert dataset_sha256(changed_query) != first_hash
    changed_review = copy.deepcopy(source)
    changed_review["review"]["labels_reviewed"] = False
    assert dataset_sha256(changed_review) != first_hash


@pytest.mark.parametrize("mutate", [
    lambda d: d.update(extra=True),
    lambda d: d.update(schema="wrong"),
    lambda d: d["images"][0].update(path="relative.jpg"),
    lambda d: d["images"][0].update(path="/photos/../secret.jpg"),
    lambda d: d["images"][0].update(sha256="A" * 64),
    lambda d: d["images"][1].update(sha256=d["images"][0]["sha256"]),
    lambda d: d["images"][1].update(id=d["images"][0]["id"]),
    lambda d: d["cases"][0].update(relevant_images=["missing"]),
    lambda d: d["cases"][0].update(relevant_images=["img-a", "img-a"]),
    lambda d: d["cases"][0].update(relevant_images=["img-a", "img-b", "img-c", "img-d"]),
    lambda d: d["cases"][0]["queries"].update(extra="query"),
    lambda d: d["cases"][0]["queries"].update(zh=" has leading whitespace"),
    lambda d: d["cases"][0]["queries"].update(en="two\nlines"),
    lambda d: d["cases"][0]["queries"].update(zh="\ud800"),
    lambda d: d["cases"][0]["queries"].update(en="é" * 257),
    lambda d: d["review"].update(natural_scenes=1),
])
def test_invalid_dataset_shapes_and_values_are_refused(mutate):
    value = dataset()
    mutate(value)
    with pytest.raises(ValueError, match="^invalid_semantic_scene_dataset$"):
        validate_dataset(value)


def test_perfect_retrieval_has_language_metrics_multirelevant_recall_and_private_report():
    value = dataset()
    images, texts = vectors(value)
    report = evaluate(value, images, texts)
    assert report["schema"] == "photohouse.semantic_scene_evaluation.v1"
    assert report["candidate_count"] == 4
    assert report["matched_case_count"] == 2
    assert report["top_k"] == 5
    assert report["effective_top_k"] == 4
    assert report["overall"] == {
        "queries": 6, "top1": 6, "top5": 6,
        "mean_reciprocal_rank": 1.0, "recall_at_5": 1.0,
    }
    assert set(report["languages"]) == {"en", "zh", "zh-en"}
    assert all(metrics["top1"] == 2 and metrics["top5"] == 2
               for metrics in report["languages"].values())
    assert report["cases"] == [
        {"case_id": "scene-one", "ranks": {"en": 1, "zh": 1, "zh-en": 1},
         "all_languages_top1": True, "worst_language_rank": 1},
        {"case_id": "scene-two", "ranks": {"en": 1, "zh": 1, "zh-en": 1},
         "all_languages_top1": True, "worst_language_rank": 1},
    ]
    assert all(report[key] is False for key in (
        "dialect_relevance_measured", "family_relevance_measured", "activation_approved"))
    serialized = repr(report)
    assert "/private/photos" not in serialized
    assert all(query not in serialized for case in value["cases"]
               for query in case["queries"].values())
    assert "vector" not in serialized


def test_language_failure_and_multirelevant_recall_are_visible_per_case():
    value = dataset()
    images, texts = vectors(value)
    texts["scene-one:zh"] = list(images["img-d"])
    texts["scene-one:zh-en"] = list(images["img-b"])
    report = evaluate(value, images, texts)
    assert report["languages"]["en"]["top1"] == 2
    assert report["languages"]["zh"]["top1"] == 1
    assert report["languages"]["zh-en"]["top1"] == 2
    assert report["cases"][0] == {
        "case_id": "scene-one", "ranks": {"en": 1, "zh": 3, "zh-en": 1},
        "all_languages_top1": False, "worst_language_rank": 3,
    }
    # Querying for the second relevant image still puts both relevant images in
    # the top five; recall is over all labels, not only the first match.
    texts["scene-one:zh-en"] = list(images["img-b"])
    report = evaluate(value, images, texts)
    assert report["languages"]["zh-en"]["recall_at_5"] == 1.0


def test_constant_vectors_treat_all_nonrelevant_ties_as_ahead():
    value = dataset()
    tied = [1.0] + [0.0] * 511
    images = {image["id"]: list(tied) for image in value["images"]}
    texts = {f'{case["id"]}:{language}': list(tied)
             for case in value["cases"] for language in ("en", "zh", "zh-en")}
    report = evaluate(value, images, texts)
    assert report["languages"]["en"]["top1"] == 0
    assert report["languages"]["en"]["top5"] == 2
    assert report["languages"]["en"]["recall_at_5"] == 1.0
    assert report["cases"][0]["ranks"]["en"] == 3
    assert report["cases"][1]["worst_language_rank"] == 4


def test_eight_candidates_expose_relevant_recall_outside_top_five():
    value = eight_image_dataset()
    images, texts = vectors(value)
    # For this query img-a scores first. The second relevant image img-b ties
    # six nonrelevant candidates, all of which count ahead under the policy.
    texts["scene-one:en"] = list(images["img-a"])
    report = evaluate(value, images, texts)
    assert report["candidate_count"] == 8
    assert report["effective_top_k"] == 5
    assert report["languages"]["en"]["recall_at_5"] == pytest.approx(0.75)
    assert report["languages"]["en"]["top5"] == 2


def test_constant_vectors_with_eight_candidates_get_no_top_five_credit():
    value = eight_image_dataset()
    tied = [1.0] + [0.0] * 511
    images = {image["id"]: list(tied) for image in value["images"]}
    texts = {f'{case["id"]}:{language}': list(tied)
             for case in value["cases"] for language in ("en", "zh", "zh-en")}
    report = evaluate(value, images, texts)
    assert report["candidate_count"] == 8
    assert report["matched_case_count"] == 2
    assert report["all_languages_top1_cases"] == 0
    assert report["languages"]["en"]["top1"] == 0
    assert report["languages"]["en"]["top5"] == 0
    assert report["languages"]["en"]["recall_at_5"] == 0.0


def test_nonrelevant_candidate_within_epsilon_counts_ahead_despite_id_order():
    value = dataset()
    images, texts = vectors(value)
    near_one = 1.0 - 0.5e-7
    images["img-a"] = [near_one, (1.0 - near_one * near_one) ** 0.5] + [0.0] * 510
    images["img-c"] = [1.0] + [0.0] * 511
    texts["scene-two:en"] = list(images["img-c"])
    report = evaluate(value, images, texts)
    assert report["languages"]["en"]["queries"] == 2
    scene_two = next(case for case in report["cases"] if case["case_id"] == "scene-two")
    assert scene_two["ranks"]["en"] == 2


@pytest.mark.parametrize("side,change", [
    ("image", "missing"), ("image", "extra"), ("text", "missing"), ("text", "extra"),
    ("image", "dimension"), ("text", "dimension"), ("image", "boolean"),
    ("text", "nonnumeric"), ("image", "nonfinite"), ("text", "unnormalized"),
    ("image", "overflow"),
])
def test_incomplete_or_invalid_vector_maps_are_refused(side, change):
    images, texts = vectors()
    selected = images if side == "image" else texts
    key = next(iter(selected))
    if change == "missing":
        del selected[key]
    elif change == "extra":
        selected["unexpected"] = selected[key]
    elif change == "dimension":
        selected[key] = [1.0]
    elif change == "boolean":
        selected[key] = [True] + [0.0] * 511
    elif change == "nonnumeric":
        selected[key] = ["1"] + [0.0] * 511
    elif change == "nonfinite":
        selected[key] = [float("inf")] + [0.0] * 511
    elif change == "unnormalized":
        selected[key] = [2.0] + [0.0] * 511
    elif change == "overflow":
        selected[key] = [10**10000] + [0.0] * 511
    with pytest.raises(ValueError, match="^invalid_semantic_scene_vectors$"):
        evaluate(dataset(), images, texts)
