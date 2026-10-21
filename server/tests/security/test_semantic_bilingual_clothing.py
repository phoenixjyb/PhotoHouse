"""Generated coverage for the bounded bilingual clothing normalizer/provider."""
from dataclasses import replace
import hashlib
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]

from app.access.semantic_encoder import (
    JointSpaceBinding,
    SemanticInvalid,
    SemanticUnavailable,
    SemanticUnsupported,
    TextVector,
)
from app.access.visual_candidates import VectorSpaceIdentity, canonical_vector_checksum
from semantic_bilingual_clothing import (
    BilingualClothingProvider,
    composition_recipe,
    model_input,
)


ADAPTER_SHA = "f" * 64
COLORS = {
    "红色": "red", "蓝色": "blue", "绿色": "green", "紫色": "purple",
    "黄色": "yellow", "黑色": "black", "白色": "white", "粉色": "pink",
    "橙色": "orange", "棕色": "brown", "灰色": "gray",
}
GARMENTS = {
    "衣服": ("clothing", False), "服装": ("clothing", False),
    "连衣裙": ("dress", True), "外套": ("coat", True),
    "衬衫": ("shirt", True), "T恤": ("t-shirt", True),
    "裤子": ("trousers", False), "戏服": ("costume", True),
    "戏装": ("costume", True),
}
WEARERS = {
    "孩子": "child", "小孩": "child", "儿童": "child", "女人": "woman",
    "男人": "man", "人": "person", "女孩": "girl", "男孩": "boy",
}


def bindings():
    image = VectorSpaceIdentity("1" * 64, "2" * 64, "shared-space", "image-v1", 512, "unit_l2")
    text = VectorSpaceIdentity("3" * 64, "4" * 64, "shared-space", "text-v1", 512, "unit_l2")
    return JointSpaceBinding(image, text, "5" * 64)


def outer_binding(inner):
    recipe = composition_recipe(inner, ADAPTER_SHA)
    text = replace(inner.text_identity, preprocessing_sha256=recipe["recipe_sha256"])
    return JointSpaceBinding(inner.image_identity, text, "6" * 64)


class InnerProvider:
    def __init__(self, binding):
        self.binding = binding
        self.calls = []
        self.mode = "ok"

    def encode(self, query, *, check=lambda: None):
        check()
        self.calls.append(query)
        vector = (1.0,) + (0.0,) * 511
        result = TextVector(
            self.binding.binding_sha256,
            hashlib.sha256(query.encode("utf-8")).hexdigest(),
            vector,
            canonical_vector_checksum(vector),
        )
        if self.mode == "bad_binding":
            return replace(result, binding_sha256="0" * 64)
        if self.mode == "bad_query":
            return replace(result, query_sha256="0" * 64)
        if self.mode == "bad_checksum":
            return replace(result, checksum_sha256="0" * 64)
        return result


class BilingualClothingTests(unittest.TestCase):
    def test_generated_chinese_color_garment_wearer_matrix(self):
        for color, english_color in COLORS.items():
            for garment, (english_garment, article) in GARMENTS.items():
                for wearer, english_wearer in WEARERS.items():
                    with self.subTest(color=color, garment=garment, wearer=wearer):
                        expected_garment = f"{english_color} {english_garment}"
                        if article:
                            expected_garment = f"a {expected_garment}"
                        expected = f"a {english_wearer} wearing {expected_garment}"
                        self.assertEqual(
                            model_input(f"穿{color}{garment}的{wearer}"), expected
                        )
                        self.assertEqual(
                            model_input(f"穿着{color}{garment}的{wearer}"), expected
                        )

    def test_mixed_and_english_phrases_normalize_case_and_articles(self):
        self.assertEqual(model_input("穿purple costume的孩子"),
                         "a child wearing a purple costume")
        self.assertEqual(model_input("穿着PURPLE T-SHIRT的女孩"),
                         "a girl wearing a purple t-shirt")
        self.assertEqual(model_input("A CHILD wearing Purple Costume"),
                         "a child wearing a purple costume")
        self.assertEqual(model_input("child wearing a purple costume"),
                         "a child wearing a purple costume")
        self.assertEqual(model_input("a person wearing gray clothing"),
                         "a person wearing gray clothing")

    def test_unknown_or_partial_phrases_are_preserved_whole(self):
        cases = (
            "穿紫色服装的孩子在公园",
            "穿银色服装的孩子",
            "穿紫色盔甲的孩子",
            "穿紫色裙子的孩子",  # skirt/dress is ambiguous; do not narrow it.
            "穿紫色服装的孩子和女人",
            "children wearing purple costumes",
            "a child wearing a purple costume outside",
            "穿purple  costume的孩子",
            " a child ",
        )
        for query in cases:
            with self.subTest(query=query):
                self.assertEqual(model_input(query), query)

    def test_invalid_originals_refuse_without_truncation(self):
        for query in ("", "  ", "a\nchild", "a\x85child",
                      "a\u2028child", "a" * 513, "\ud800"):
            with self.subTest(query=repr(query)):
                with self.assertRaises(SemanticInvalid):
                    model_input(query)

    def test_normalizer_does_no_filesystem_work(self):
        with patch.object(Path, "read_bytes", side_effect=AssertionError("unexpected file read")):
            self.assertEqual(model_input("穿紫色服装的孩子"),
                             "a child wearing purple clothing")

    def test_recipe_and_outer_binding_change_text_identity_only(self):
        inner = bindings()
        recipe = composition_recipe(inner, ADAPTER_SHA)
        self.assertEqual(recipe["policy"], "photohouse.bilingual_clothing_normalization.v1")
        self.assertEqual(len(recipe["module_sha256"]), 64)
        self.assertNotIn("purple costume", repr(recipe))
        outer = outer_binding(inner)
        provider = BilingualClothingProvider(InnerProvider(inner), outer,
                                             adapter_source_sha256=ADAPTER_SHA)
        self.assertEqual(provider.binding.image_identity, inner.image_identity)
        self.assertNotEqual(provider.binding.text_identity, inner.text_identity)
        self.assertEqual(provider.recipe["recipe_sha256"],
                         outer.text_identity.preprocessing_sha256)

    def test_provider_preserves_original_digest_and_binds_projected_encoder_result(self):
        inner_binding = bindings()
        inner = InnerProvider(inner_binding)
        checks = []
        provider = BilingualClothingProvider(
            inner, outer_binding(inner_binding), adapter_source_sha256=ADAPTER_SHA,
            source_check=lambda: checks.append("source"),
        )
        query = "穿紫色服装的孩子"
        result = provider.encode(query, check=lambda: checks.append("request"))
        self.assertEqual(inner.calls, ["a child wearing purple clothing"])
        self.assertEqual(result.binding_sha256, provider.binding.binding_sha256)
        self.assertEqual(result.query_sha256, hashlib.sha256(query.encode()).hexdigest())
        self.assertEqual(result.checksum_sha256, canonical_vector_checksum(result.vector))
        self.assertEqual(checks, [
            "source", "request", "source", "request", "request", "source", "request",
        ])

    def test_exclusion_guard_runs_before_inner_for_normalized_and_fallback_text(self):
        inner_binding = bindings()
        inner = InnerProvider(inner_binding)
        provider = BilingualClothingProvider(
            inner, outer_binding(inner_binding), adapter_source_sha256=ADAPTER_SHA,
        )
        for query in ("a child without purple clothing", "no silver costume"):
            with self.subTest(query=query):
                with self.assertRaises(SemanticUnsupported):
                    provider.encode(query)
        self.assertEqual(inner.calls, [])

    def test_inner_identity_and_response_are_checked(self):
        inner_binding = bindings()
        inner = InnerProvider(inner_binding)
        provider = BilingualClothingProvider(
            inner, outer_binding(inner_binding), adapter_source_sha256=ADAPTER_SHA,
        )
        for mode in ("bad_binding", "bad_query", "bad_checksum"):
            inner.mode = mode
            with self.subTest(mode=mode), self.assertRaises(SemanticUnavailable):
                provider.encode("穿紫色服装的孩子")

        inner.mode = "ok"
        inner.binding = bindings()
        with self.assertRaises(SemanticUnavailable):
            provider.encode("穿紫色服装的孩子")

    def test_construction_rejects_incompatible_binding_or_source_digest(self):
        inner = bindings()
        outer = outer_binding(inner)
        altered = JointSpaceBinding(
            replace(outer.image_identity, preprocessing_sha256="7" * 64),
            outer.text_identity,
            "8" * 64,
        )
        with self.assertRaises(ValueError):
            BilingualClothingProvider(InnerProvider(inner), altered,
                                      adapter_source_sha256=ADAPTER_SHA)
        with self.assertRaises(ValueError):
            BilingualClothingProvider(InnerProvider(inner), outer,
                                      adapter_source_sha256="not-a-digest")


if __name__ == "__main__":
    unittest.main()


def test_provider_v2_configuration_binds_text_normalizer_before_model_loading(tmp_path, monkeypatch):
    import json
    from dataclasses import asdict
    import serve_multilingual_semantic_text as serving
    from semantic_bilingual_clothing import POLICY
    inner = bindings()
    inner = JointSpaceBinding(replace(inner.image_identity, dimension=768),
        replace(inner.text_identity, dimension=768), inner.qualification_sha256)
    recipe = serving.bilingual_recipe(inner)
    outer = JointSpaceBinding(inner.image_identity, replace(inner.text_identity,
        preprocessing_sha256=recipe['recipe_sha256']), 'a' * 64)
    doc = {'schema': 'photohouse.multilingual_text_provider.v2',
        'model_directory': str(tmp_path / 'model'),
        'artifacts': serving.qualification.OFFICIAL_ARTIFACTS,
        'package_versions': serving.qualification.EXPECTED_PACKAGES,
        'binding': asdict(outer), 'inner_binding': asdict(inner),
        'normalization_policy': POLICY, 'credential_file': None, 'port': 43871}
    monkeypatch.setattr(serving, '_load_private_document', lambda *_a, **_k: doc)
    loaded, binding, token = serving.configuration(tmp_path / 'unused.json')
    assert binding == outer and token is None
    for change in ({'normalization_policy': 'automatic_translation'},
                   {'binding': asdict(inner)}, {'unexpected': True}):
        bad = {**doc, **change}
        monkeypatch.setattr(serving, '_load_private_document', lambda *_a, _doc=bad, **_k: _doc)
        with __import__('pytest').raises(ValueError):
            serving.configuration(tmp_path / 'unused.json')
