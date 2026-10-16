"""Generated stand-in checks for the reviewed-scene measurement branch."""
from contextlib import nullcontext
from dataclasses import replace
import hashlib
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]

import qualify_semantic_scenes as subject  # noqa: E402
from app.access.semantic_encoder import (  # noqa: E402
    JointSpaceBinding,
    SemanticUnavailable,
    TextVector,
)
from app.access.visual_candidates import (  # noqa: E402
    VectorSpaceIdentity,
    canonical_vector_checksum,
)
from semantic_reviewed_projection import (  # noqa: E402
    ReviewedProjection,
    ReviewedSemanticProvider,
    composition_recipe,
    reviewed_document_sha256,
)


ADAPTER_SHA256 = "f" * 64
LANGUAGES = ("en", "zh", "zh-en")


def _unit(index):
    return tuple(1.0 if offset == index else 0.0 for offset in range(512))


class _Tensor:
    shape = (1, 3, 224, 224)

    def unsqueeze(self, _dimension):
        return self

    def to(self, **_kwargs):
        return self


class _Output:
    shape = (1, 512)

    def __init__(self, values):
        self.values = values

    def detach(self):
        return self

    def to(self, **_kwargs):
        return self

    def __getitem__(self, _index):
        return self

    def tolist(self):
        return self.values


class _Model:
    """Bound fake inner encoder plus the same model's generated image tower."""

    def __init__(self, binding, *, checkpoint_sha256, vectors_by_text):
        self.binding = binding
        self._checkpoint_sha256 = checkpoint_sha256
        self._device = "cpu"
        self._pins = ()
        self._recipe = {"package_versions": {}}
        self._torch = SimpleNamespace(float32="float32", inference_mode=nullcontext)
        self._model = SimpleNamespace(
            visual=SimpleNamespace(preprocess_cfg={"size": 224}),
            encode_image=Mock(side_effect=[_Output(list(_unit(i))) for i in range(4)]),
        )
        self._vector = Mock(side_effect=lambda text, _check: vectors_by_text[text])
        self.encoded = []
        self.vectors_by_text = vectors_by_text

    def encode(self, query, *, check=lambda: None):
        self.encoded.append(query)
        check()
        vector = self.vectors_by_text[query]
        return TextVector(
            self.binding.binding_sha256,
            hashlib.sha256(query.encode("utf-8")).hexdigest(),
            vector,
            canonical_vector_checksum(vector),
        )

    def probe(self):
        return {"schema": "generated-bound-fake", "relevance_measured": False}


@pytest.fixture
def scene_case():
    images = [
        {"id": f"image-{index}", "path": f"/private/scenes/image-{index}.png",
         "sha256": f"{index:064x}"}
        for index in range(4)
    ]
    cases = []
    entries = []
    vectors_by_text = {}
    for case_index in range(2):
        queries = {
            "en": f"English scene {case_index}",
            "zh": f"中文场景 {case_index}",
            "zh-en": f"中文 scene {case_index}",
        }
        case_id = f"case-{case_index}"
        cases.append({"id": case_id, "relevant_images": [f"image-{case_index}"],
                      "queries": queries})
        for language, original in queries.items():
            model_input = f"described scene number {case_index} language {language}"
            entries.append({"original": original, "model_input": model_input})
            vectors_by_text[model_input] = _unit(case_index)
            vectors_by_text[original] = _unit(case_index)
    dataset = {
        "schema": "photohouse.semantic_scene_cases.v1",
        "review": {"natural_scenes": True, "labels_reviewed": True},
        "images": images,
        "cases": cases,
    }
    return SimpleNamespace(dataset=dataset, entries=entries,
                           vectors_by_text=vectors_by_text)


def _projection(entries):
    document = {
        "schema": "photohouse.reviewed_scene_projection.v1",
        "policy": "exact_reviewed_only",
        "review": {"status": "operator_reviewed", "reference_sha256": "a" * 64},
        "entries": entries,
    }
    return ReviewedProjection(document, expected_sha256=reviewed_document_sha256(document))


def _expected_recipe(dataset):
    # The measurement function adds these fields after observe_preprocessing.
    return {
        "schema": "generated-evaluation-recipe",
        "input_profile": "private_single_frame_jpeg_png_exif_rgb_v1",
        "dataset_sha256": subject.dataset_sha256(dataset),
    }


def _binding_and_provider(dataset, entries, *, image_preprocessing=None,
                          image_artifact="b" * 64, dimension=512,
                          source_check=lambda: None):
    projection = _projection(entries)
    image_identity = VectorSpaceIdentity(
        image_artifact,
        image_preprocessing or subject.recipe_sha256(_expected_recipe(dataset)),
        "scene-test-space", "image-test-v1", dimension, "unit_l2",
    )
    inner_text = VectorSpaceIdentity(
        "b" * 64, "c" * 64, "scene-test-space", "text-test-v1", dimension, "unit_l2",
    )
    inner_binding = JointSpaceBinding(image_identity, inner_text, "d" * 64)
    recipe = composition_recipe(inner_binding, projection, ADAPTER_SHA256)
    outer_text = replace(inner_text, preprocessing_sha256=recipe["recipe_sha256"])
    outer_binding = JointSpaceBinding(image_identity, outer_text, "e" * 64)
    model = _Model(inner_binding, checkpoint_sha256="b" * 64,
                   vectors_by_text={**{entry["model_input"]: _unit(i // 3)
                                      for i, entry in enumerate(entries)},
                                    **{entry["original"]: _unit(i // 3)
                                       for i, entry in enumerate(entries)}})
    provider = ReviewedSemanticProvider(
        model, projection, outer_binding, adapter_source_sha256=ADAPTER_SHA256,
        source_check=source_check,
    )
    return model, provider, projection


def _measure(dataset, model, *, reviewed_provider=None, observed=None, deadline=float("inf")):
    transform = SimpleNamespace(
        __file__=__file__,
        PreprocessCfg=lambda **kwargs: kwargs,
        image_transform_v2=Mock(return_value=lambda _image: _Tensor()),
    )
    original_import = subject.importlib.import_module

    def import_module(name):
        if name == "open_clip.transform":
            return transform
        if name.startswith(("torchvision.", "PIL.")):
            return SimpleNamespace(__file__=__file__)
        return original_import(name)

    if observed is None:
        observed = {"schema": "generated-evaluation-recipe"}
    with patch.object(subject, "version", return_value="1.2.3"), \
         patch.object(subject.importlib, "import_module", side_effect=import_module), \
         patch.object(subject, "_source_pin", return_value=SimpleNamespace(sha256="c" * 64)), \
         patch.object(subject, "_current"), \
         patch.object(subject, "verify_checkpoint"), \
         patch.object(subject, "observe_preprocessing", return_value=observed), \
         patch.object(subject, "decode_image", side_effect=lambda _pin: SimpleNamespace(close=Mock())):
        record = subject.measure(
            model, dataset,
            {image["id"]: object() for image in dataset["images"]},
            {name: "1.2.3" for name in subject.IMAGE_PACKAGES},
            deadline, reviewed_provider=reviewed_provider,
        )
    return record, transform


def test_reviewed_measurement_encodes_exact_projected_inputs_and_keeps_hash_receipts(scene_case):
    model, provider, projection = _binding_and_provider(
        scene_case.dataset, scene_case.entries,
    )
    # This same observed recipe is independently assembled by measure().
    model._model.encode_image = Mock(side_effect=[_Output(list(_unit(i))) for i in range(4)])
    record, _ = _measure(scene_case.dataset, model, reviewed_provider=provider)

    originals = [case["queries"][language]
                 for case in scene_case.dataset["cases"] for language in LANGUAGES]
    derived = [projection.project(query) for query in originals]
    assert model.encoded == derived
    model._vector.assert_not_called()
    assert record["schema"] == "photohouse.reviewed_scene_measurement.v1"
    assert record["metrics"]["overall"]["top1"] == 6
    assert record["reviewed_provider"]["projection_sha256"] == projection.projection_sha256
    assert record["image_identity_matched"] is True
    assert record["serving_transport_measured"] is False
    assert record["semantic_faithfulness_automatically_verified"] is False
    assert record["pair_binding_created"] is False
    assert record["activation_performed"] is False

    for case in scene_case.dataset["cases"]:
        for language in LANGUAGES:
            key = f'{case["id"]}:{language}'
            query = case["queries"][language]
            expected = projection.provenance(query)
            receipt = record["query_receipts"][key]
            assert receipt["original_query_sha256"] == expected["original_query_sha256"]
            assert receipt["vector_checksum_sha256"] == canonical_vector_checksum(_unit(
                scene_case.dataset["cases"].index(case)))
    serialized = repr(record)
    assert all(query not in serialized for query in originals + derived)
    assert all(image["path"] not in serialized for image in scene_case.dataset["images"])
    assert "vector\"" not in serialized


def test_reviewed_and_unbound_paths_keep_identical_image_recipe_and_vector_checksums(scene_case):
    model, provider, _projection_value = _binding_and_provider(
        scene_case.dataset, scene_case.entries,
    )
    model._model.encode_image = Mock(side_effect=[_Output(list(_unit(i))) for i in range(4)])
    reviewed, _ = _measure(scene_case.dataset, model, reviewed_provider=provider)

    direct_model = _Model(None, checkpoint_sha256="b" * 64,
                          vectors_by_text=scene_case.vectors_by_text)
    direct_model._model.encode_image = Mock(side_effect=[_Output(list(_unit(i))) for i in range(4)])
    direct, _ = _measure(scene_case.dataset, direct_model)

    assert reviewed["image_preprocessing_sha256"] == direct["image_preprocessing_sha256"]
    assert reviewed["image_preprocessing_recipe"] == direct["image_preprocessing_recipe"]
    assert reviewed["images"] == direct["images"]
    assert reviewed["image_identity"]["preprocessing_sha256"] == reviewed[
        "image_preprocessing_sha256"]
    assert reviewed["image_identity"]["artifact_sha256"] == "b" * 64


@pytest.mark.parametrize("mismatch", ["preprocessing", "artifact", "dimension"])
def test_reviewed_image_identity_mismatch_refuses_before_any_tower_call(scene_case, mismatch):
    kwargs = {}
    if mismatch == "preprocessing":
        kwargs["image_preprocessing"] = "9" * 64
    elif mismatch == "artifact":
        kwargs["image_artifact"] = "9" * 64
    else:
        kwargs["dimension"] = 256
    model, provider, _ = _binding_and_provider(scene_case.dataset, scene_case.entries, **kwargs)
    model._model.encode_image = Mock()
    with pytest.raises(ValueError, match="semantic_scene_measurement_unavailable"):
        _measure(scene_case.dataset, model, reviewed_provider=provider)
    model._model.encode_image.assert_not_called()
    model.encode = Mock()
    assert model.encoded == []


def test_reviewed_measurement_requires_exact_provider_and_identical_inner_binding(scene_case):
    model, provider, _ = _binding_and_provider(scene_case.dataset, scene_case.entries)
    with pytest.raises(ValueError, match="semantic_scene_measurement_unavailable"):
        _measure(scene_case.dataset, model, reviewed_provider=object())

    other, _valid_provider, _ = _binding_and_provider(scene_case.dataset, scene_case.entries)
    with pytest.raises(ValueError, match="semantic_scene_measurement_unavailable"):
        _measure(scene_case.dataset, other, reviewed_provider=provider)
    model._model.encode_image.assert_not_called()


@pytest.mark.parametrize("field", ["binding_sha256", "query_sha256", "checksum_sha256"])
def test_tampered_provider_vector_is_refused_before_ranking(scene_case, field):
    model, provider, _ = _binding_and_provider(scene_case.dataset, scene_case.entries)
    original_encode = ReviewedSemanticProvider.encode

    def tampered(self, query, *, check=lambda: None):
        result = original_encode(self, query, check=check)
        if field == "binding_sha256":
            return replace(result, binding_sha256="0" * 64)
        if field == "query_sha256":
            return replace(result, query_sha256="0" * 64)
        return replace(result, checksum_sha256="0" * 64)

    with patch.object(ReviewedSemanticProvider, "encode", tampered):
        with pytest.raises(ValueError):
            _measure(scene_case.dataset, model, reviewed_provider=provider)


def test_reviewed_source_and_deadline_failures_are_fixed_and_do_not_emit_query_text(scene_case):
    original = scene_case.dataset["cases"][0]["queries"]["en"]
    model, provider, _ = _binding_and_provider(
        scene_case.dataset, scene_case.entries,
        source_check=lambda: (_ for _ in ()).throw(RuntimeError("private source diagnostic")),
    )
    with pytest.raises(SemanticUnavailable) as failure:
        _measure(scene_case.dataset, model, reviewed_provider=provider)
    assert str(failure.value) == "semantic_unavailable"
    assert original not in str(failure.value)

    model, provider, _ = _binding_and_provider(scene_case.dataset, scene_case.entries)
    with pytest.raises(ValueError) as failure:
        _measure(scene_case.dataset, model, reviewed_provider=provider,
                 deadline=float("-inf"))
    model._model.encode_image.assert_not_called()
    assert str(failure.value) == "semantic_scene_measurement_unavailable"
    assert original not in str(failure.value)
