"""Hash-bound review and conservative semantic cue checks."""
import copy
import hashlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "backend"))

from semantic_scene_cases import dataset_sha256  # noqa: E402
from semantic_scene_translation import derive_dataset, translation_recipe  # noqa: E402
from semantic_scene_translation_fidelity import (  # noqa: E402
    REVIEW_SCHEMA, feature_mismatch,
)

PROVIDER = {
    "kind": "local_ollama", "model": "qwen3.5:9b",
    "model_manifest_sha256": "1" * 64, "provider_sha256": "2" * 64,
    "provider_version": "ollama-0.13.2",
}


def source_data():
    return {
        "schema": "photohouse.semantic_scene_cases.v1",
        "review": {"natural_scenes": True, "labels_reviewed": True},
        "images": [
            {"id": name, "path": f"/private/photos/{name}.jpg", "sha256": f"{i:064x}"}
            for i, name in enumerate(("img-a", "img-b", "img-c", "img-d"), 1)
        ],
        "cases": [
            {"id": "one", "relevant_images": ["img-a"],
             "queries": {"en": "A red house by a lake", "zh": "湖边的红房子",
                         "zh-en": "湖边的 red house"}},
            {"id": "two", "relevant_images": ["img-c"],
             "queries": {"en": "Children in a garden", "zh": "花园里的孩子",
                         "zh-en": "children in a garden"}},
        ],
    }


def outputs(source=None):
    source = source or source_data()
    return {f'{case["id"]}:{language}': "A red house by a lake"
            for case in source["cases"] for language in ("zh", "zh-en")}


def review_for(source, translations):
    pairs = {}
    for case in source["cases"]:
        for language in ("zh", "zh-en"):
            key = f'{case["id"]}:{language}'
            pairs[key] = {
                "source_text_sha256": hashlib.sha256(
                    case["queries"][language].encode("utf-8")).hexdigest(),
                "translation_text_sha256": hashlib.sha256(
                    translations[key].encode("utf-8")).hexdigest(),
                "decision": "faithful",
            }
    return {"schema": REVIEW_SCHEMA, "source_dataset_sha256": dataset_sha256(source),
            "reviewer_type": "assistant",
            "translation_recipe_sha256": translation_recipe(PROVIDER)["recipe_sha256"],
            "reviewed_pairs": pairs}


@pytest.mark.parametrize(("source", "translation", "category"), [
    ("滑雪者拿着滑雪板", "A snowboarder carries a single snowboard", "quantity"),
    ("两名儿童在院子里", "One child is in the yard", "quantity"),
    ("车辆仍在等候", "A vehicle is parked", "state"),
    ("独自收集葡萄", "Grapes are placed separately", "contrast"),
    ("没有积雪的田野", "A field covered with snow", "negation"),
    ("一个孩子在院子里", "A child is in the yard", "quantity"),
    ("vehicles waiting", "Vehicles are parked", "state"),
    ("停着等的交通工具", "Vehicles are parked", "state"),
    ("People are alone", "People are seated separately", "contrast"),
    ("窗户开着", "An open window is moving", "state"),
    ("no snow sports field", "A sports field with snow", "negation"),
    ("black coat and notebook", "A black coat and notebook", None),
    ("vehicles are waiting", "Vehicles are waiting and parked", "state"),
    ("物体不动", "The object is motionless", None),
    ("people are alone", "People are alone and separated", "contrast"),
])
def test_explicit_quantity_state_relation_and_negation_conflicts_are_rejected(
        source, translation, category):
    assert feature_mismatch(source, translation) == category


def test_mixed_language_counts_and_waiting_states_are_preserved():
    assert feature_mismatch("two children 停着等", "Two children are waiting") is None
    assert feature_mismatch("two children 停着等", "Two children are waiting in place") is None
    assert feature_mismatch("滑雪者拿着滑雪板", "A snowboarder carries one snowboard") == "quantity"


def test_ambiguous_snow_field_scope_is_rejected_until_rewritten_and_reviewed():
    source = "没有snow的sports field"
    assert feature_mismatch(source, "no snow sports field") == "negation_scope"
    assert feature_mismatch(source, "A sports field with no snow") is None


def test_faithful_review_must_bind_all_exact_source_and_output_pairs():
    source = source_data()
    source_before = copy.deepcopy(source)
    translated = outputs(source)
    review = review_for(source, translated)
    derived, receipt = derive_dataset(source, translated, PROVIDER, fidelity_review=review)
    assert source == source_before
    assert receipt["semantic_translation_reviewed"] is True
    assert receipt["translation_fidelity_review"]["reviewer_type"] == "assistant"
    assert receipt["translation_fidelity_review"]["reviewed_pair_count"] == 4
    assert derived["cases"][0]["queries"]["zh"] == translated["one:zh"]

    for mutate in (
        lambda x: x["reviewed_pairs"].pop("one:zh"),
        lambda x: x["reviewed_pairs"]["one:zh"].update(decision="uncertain"),
        lambda x: x.update(extra="not in v1 contract"),
        lambda x: x.update(source_dataset_sha256="0" * 64),
        lambda x: x.update(translation_recipe_sha256="0" * 64),
        lambda x: x["reviewed_pairs"]["one:zh"].update(source_text_sha256="0" * 64),
        lambda x: x["reviewed_pairs"]["one:zh"].update(translation_text_sha256="0" * 64),
    ):
        bad = copy.deepcopy(review)
        mutate(bad)
        with pytest.raises(ValueError, match="invalid_scene_translation_fidelity_review"):
            derive_dataset(source, translated, PROVIDER, fidelity_review=bad)

    human_review = copy.deepcopy(review)
    human_review["reviewer_type"] = "human"
    _, human_receipt = derive_dataset(source, translated, PROVIDER, fidelity_review=human_review)
    assert human_receipt["translation_fidelity_review"]["reviewer_type"] == "human"


@pytest.mark.parametrize(("source_text", "output_text"), [
    ("车辆仍在等候", "A vehicle is parked"),
    ("滑雪者拿着滑雪板", "A snowboarder carries one snowboard"),
    ("独自收集葡萄", "Grapes are placed separately"),
    ("没有积雪的田野", "A field covered with snow"),
])
def test_manual_attestation_cannot_qualify_detected_feature_mismatch(source_text, output_text):
    source = source_data()
    source["cases"][0]["queries"]["zh"] = source_text
    translated = outputs(source)
    translated["one:zh"] = output_text
    review = review_for(source, translated)
    with pytest.raises(ValueError, match="scene_translation_fidelity_feature_mismatch"):
        derive_dataset(source, translated, PROVIDER, fidelity_review=review)


def test_unreviewed_derivation_keeps_legacy_data_shape_and_cannot_qualify():
    source = source_data()
    derived, receipt = derive_dataset(source, outputs(source), PROVIDER)
    assert derived["cases"][0]["queries"]["zh"] == "A red house by a lake"
    assert receipt["semantic_translation_reviewed"] is False
    assert receipt["translation_fidelity_review"] is None


def test_current_recipe_pins_fidelity_guard_source():
    import hashlib
    guard = ROOT / "scripts" / "semantic_scene_translation_fidelity.py"
    assert translation_recipe(PROVIDER)["fidelity_guard_sha256"] == hashlib.sha256(
        guard.read_bytes()).hexdigest()
