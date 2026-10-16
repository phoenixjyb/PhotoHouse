"""Exact reviewed-query projection and composition contract tests."""
from dataclasses import replace
import hashlib
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]

from app.access.semantic_encoder import (JointSpaceBinding, SemanticInvalid,
                                         SemanticUnavailable, TextVector)
from app.access.visual_candidates import VectorSpaceIdentity, canonical_vector_checksum
from semantic_reviewed_projection import (
    ReviewedProjection,
    ReviewedSemanticProvider,
    composition_recipe,
    reviewed_document_sha256,
    validate_projection_binding,
)


ADAPTER_SHA = "f" * 64


def document(entries=None, reference="a" * 64):
    return {
        "schema": "photohouse.reviewed_scene_projection.v1",
        "policy": "exact_reviewed_only",
        "review": {"status": "operator_reviewed", "reference_sha256": reference},
        "entries": entries if entries is not None else [
            {"original": "原样 Original", "model_input": "a red circle"},
            {"original": "Exact Query", "model_input": "a red circle"},
            {"original": " exact Query ", "model_input": "a red circle"},
        ],
    }


def identities():
    image = VectorSpaceIdentity("1" * 64, "2" * 64, "shared-space", "image-v1", 512, "unit_l2")
    text = VectorSpaceIdentity("3" * 64, "4" * 64, "shared-space", "text-v1", 512, "unit_l2")
    return JointSpaceBinding(image, text, "5" * 64)


def projection(doc=None):
    doc = document() if doc is None else doc
    return ReviewedProjection(doc, expected_sha256=reviewed_document_sha256(doc))


def outer_binding(inner_binding, reviewed):
    recipe = composition_recipe(inner_binding, reviewed, ADAPTER_SHA)
    text = replace(inner_binding.text_identity,
                   preprocessing_sha256=recipe["recipe_sha256"])
    return JointSpaceBinding(inner_binding.image_identity, text, "6" * 64)


class InnerProvider:
    def __init__(self, binding):
        self.binding = binding
        self.calls = []
        self.mode = "ok"
        self.on_call = None

    def encode(self, query, *, check=lambda: None):
        self.calls.append(query)
        check()
        if self.on_call is not None:
            self.on_call()
        if self.mode == "raise":
            raise RuntimeError("private inner diagnostic")
        vector = (1.0,) + (0.0,) * 511
        checksum = canonical_vector_checksum(vector)
        result = TextVector(self.binding.binding_sha256,
                            hashlib.sha256(query.encode("utf-8")).hexdigest(),
                            vector, checksum)
        if self.mode == "bad_query":
            return replace(result, query_sha256="0" * 64)
        if self.mode == "bad_binding":
            return replace(result, binding_sha256="0" * 64)
        if self.mode == "bad_checksum":
            return replace(result, checksum_sha256="0" * 64)
        if self.mode == "bad_vector":
            return replace(result, vector=(0.0,) * 512)
        if self.mode == "bad_norm_valid_checksum":
            vector = (0.5,) * 512
            return replace(result, vector=vector,
                           checksum_sha256=canonical_vector_checksum(vector))
        return result


class ReviewedProjectionTests(unittest.TestCase):
    def test_canonical_digest_exact_lookup_and_hash_only_provenance(self):
        source = document()
        reviewed = projection(source)
        source["entries"][0]["model_input"] = "mutated after load"
        self.assertEqual(reviewed.project("原样 Original"), "a red circle")
        self.assertEqual(reviewed.project("Exact Query"), "a red circle")
        self.assertEqual(reviewed.project(" exact Query "), "a red circle")
        with self.assertRaises(SemanticUnavailable):
            reviewed.project("exact query")
        receipt = reviewed.provenance("原样 Original")
        self.assertEqual(set(receipt), {
            "original_query_sha256", "model_input_sha256", "projection_sha256"})
        self.assertEqual(receipt["original_query_sha256"],
                         hashlib.sha256("原样 Original".encode()).hexdigest())
        self.assertNotIn("原样 Original", repr(reviewed))
        self.assertNotIn("a red circle", repr(reviewed))
        self.assertEqual(reviewed.entry_count, 3)
        with self.assertRaises(TypeError):
            reviewed._entries["Exact Query"] = "changed"
        probe = reviewed.probe()
        probe["entry_count"] = 100
        self.assertEqual(reviewed.probe()["entry_count"], 3)
        self.assertFalse(reviewed.probe()["semantic_faithfulness_qualified"])

    def test_expected_digest_and_recipe_bind_all_review_inputs(self):
        base_doc = document()
        base = projection(base_doc)
        self.assertEqual(reviewed_document_sha256(base_doc), base.projection_sha256)
        with self.assertRaisesRegex(ValueError, "invalid_reviewed_projection_digest"):
            ReviewedProjection(base_doc, expected_sha256="0" * 64)
        inner = identities()
        recipe = composition_recipe(inner, base, ADAPTER_SHA)
        changed_mapping = projection(document(entries=[
            {"original": "原样 Original", "model_input": "a blue circle"}]))
        changed_review = projection(document(reference="b" * 64))
        self.assertNotEqual(recipe["recipe_sha256"],
                            composition_recipe(inner, changed_mapping, ADAPTER_SHA)["recipe_sha256"])
        self.assertNotEqual(recipe["recipe_sha256"],
                            composition_recipe(inner, changed_review, ADAPTER_SHA)["recipe_sha256"])
        self.assertNotEqual(recipe["recipe_sha256"],
                            composition_recipe(inner, base, "e" * 64)["recipe_sha256"])
        altered_inner = JointSpaceBinding(inner.image_identity,
            replace(inner.text_identity, artifact_sha256="7" * 64), inner.qualification_sha256)
        self.assertNotEqual(recipe["recipe_sha256"],
                            composition_recipe(altered_inner, base, ADAPTER_SHA)["recipe_sha256"])
        self.assertNotIn("原样 Original", repr(recipe))
        self.assertNotIn("a red circle", repr(recipe))

    def test_document_rejects_extra_duplicate_nonprimitive_and_invalid_text(self):
        base = document()
        variants = []
        extra = document(); extra["extra"] = True; variants.append(extra)
        extra_entry = document(); extra_entry["entries"][0]["label"] = "secret"; variants.append(extra_entry)
        duplicate = document(); duplicate["entries"].append(dict(duplicate["entries"][0])); variants.append(duplicate)
        for bad in ("has\nnewline", "has\x85control", "has\u2028separator", "\ud800", "a" * 513):
            variants.append(document(entries=[{"original": bad, "model_input": "an image"}]))
        for bad in ("nonascii café", "123 456", "has\nnewline", "\ud800", "a" * 513):
            variants.append(document(entries=[{"original": "valid", "model_input": bad}]))
        variants.extend([
            document(entries=[]),
            document(entries=[{"original": "valid", "model_input": "ok"} for _ in range(257)]),
            {**base, "review": {"status": "operator_reviewed", "reference_sha256": "A" * 64}},
            {**base, "policy": type("TextSubclass", (str,), {})("exact_reviewed_only")},
        ])
        for bad in variants:
            with self.subTest(document=repr(bad)[:80]):
                with self.assertRaises(ValueError):
                    reviewed_document_sha256(bad)

    def test_project_invalid_vs_unknown_and_does_not_normalize(self):
        reviewed = projection()
        for invalid in (None, 5, "", " \t ", "a\nquery", "a\x80query", "a\u2029query", "\ud800"):
            with self.subTest(query=type(invalid).__name__):
                with self.assertRaises(SemanticInvalid):
                    reviewed.project(invalid)
        for unknown in ("exact  Query", "Exact query", "Exact Query ", "Exact\tQuery"):
            expected = SemanticInvalid if "\t" in unknown else SemanticUnavailable
            with self.assertRaises(expected):
                reviewed.project(unknown)


class ReviewedSemanticProviderTests(unittest.TestCase):
    def setUp(self):
        self.inner_binding = identities()
        self.reviewed = projection()
        self.outer = outer_binding(self.inner_binding, self.reviewed)
        self.inner = InnerProvider(self.inner_binding)
        self.provider = ReviewedSemanticProvider(self.inner, self.reviewed, self.outer,
                                                 adapter_source_sha256=ADAPTER_SHA)

    def test_validates_composition_and_distinguishes_original_query_digests(self):
        recipe = validate_projection_binding(self.inner_binding, self.reviewed, self.outer, ADAPTER_SHA)
        self.assertEqual(recipe, composition_recipe(self.inner_binding, self.reviewed, ADAPTER_SHA))
        first = self.provider.encode("Exact Query")
        second = self.provider.encode(" exact Query ")
        self.assertEqual(self.inner.calls, ["a red circle", "a red circle"])
        self.assertEqual(first.binding_sha256, self.outer.binding_sha256)
        self.assertEqual(first.query_sha256, hashlib.sha256(b"Exact Query").hexdigest())
        self.assertEqual(second.query_sha256, hashlib.sha256(b" exact Query ").hexdigest())
        self.assertEqual(first.vector, second.vector)
        self.assertEqual(first.checksum_sha256, second.checksum_sha256)
        self.assertNotEqual(first.query_sha256, second.query_sha256)
        self.assertEqual(self.provider.binding, self.outer)
        self.assertEqual(self.inner.binding, self.inner_binding)
        self.assertFalse(self.provider.probe()["activation_approved"])

    def test_success_checks_and_source_pins_run_on_both_sides(self):
        check_calls = []
        source_calls = []
        provider = ReviewedSemanticProvider(
            self.inner, self.reviewed, self.outer, adapter_source_sha256=ADAPTER_SHA,
            source_check=lambda: source_calls.append("source"))
        result = provider.encode("Exact Query", check=lambda: check_calls.append("check"))
        self.assertEqual(result.binding_sha256, self.outer.binding_sha256)
        # The fake inner calls the supplied check once; the adapter adds its
        # own pre/post checks around the complete composition.
        self.assertEqual(check_calls, ["check", "check", "check"])
        self.assertEqual(source_calls, ["source", "source"])

    def test_unknown_and_invalid_queries_never_call_inner(self):
        with self.assertRaises(SemanticUnavailable):
            self.provider.encode("not reviewed")
        with self.assertRaises(SemanticInvalid):
            self.provider.encode("bad\nquery")
        self.assertEqual(self.inner.calls, [])

    def test_outer_binding_mismatch_is_rejected_before_provider_creation(self):
        wrong_image = replace(self.outer.image_identity, artifact_sha256="8" * 64)
        wrong_qual = replace(self.outer, image_identity=wrong_image)
        with self.assertRaises(ValueError):
            validate_projection_binding(self.inner_binding, self.reviewed, wrong_qual, ADAPTER_SHA)
        same_qual = replace(self.outer,
                            qualification_sha256=self.inner_binding.qualification_sha256)
        with self.assertRaises(ValueError):
            ReviewedSemanticProvider(self.inner, self.reviewed, same_qual,
                                     adapter_source_sha256=ADAPTER_SHA)
        changed_text = replace(self.outer.text_identity, model_version="other-text-v1")
        with self.assertRaises(ValueError):
            validate_projection_binding(self.inner_binding, self.reviewed,
                replace(self.outer, text_identity=changed_text), ADAPTER_SHA)

    def test_inner_vector_query_binding_checksum_and_unit_norm_are_checked(self):
        for mode in ("bad_query", "bad_binding", "bad_checksum", "bad_vector",
                     "bad_norm_valid_checksum", "raise"):
            with self.subTest(mode=mode):
                self.inner.mode = mode
                before = len(self.inner.calls)
                with self.assertRaises(SemanticUnavailable) as raised:
                    self.provider.encode("Exact Query")
                self.assertEqual(str(raised.exception), "semantic_unavailable")
                self.assertEqual(len(self.inner.calls), before + 1)
        self.inner.mode = "ok"
        self.assertEqual(self.provider.encode("Exact Query").binding_sha256,
                         self.outer.binding_sha256)

    def test_inner_binding_change_before_or_during_call_is_refused(self):
        self.inner.binding = replace(self.inner_binding, qualification_sha256="9" * 64)
        with self.assertRaises(SemanticUnavailable):
            self.provider.encode("Exact Query")
        self.assertEqual(self.inner.calls, [])
        self.inner.binding = self.inner_binding
        self.inner.on_call = lambda: setattr(
            self.inner, "binding", replace(self.inner_binding, qualification_sha256="9" * 64))
        with self.assertRaises(SemanticUnavailable):
            self.provider.encode("Exact Query")
        self.assertEqual(len(self.inner.calls), 1)
        self.inner.on_call = None
        self.inner.binding = self.inner_binding
        self.assertEqual(self.provider.encode("Exact Query").binding_sha256,
                         self.outer.binding_sha256)

    def test_checks_reentry_failures_and_lease_recovery(self):
        reentered = []
        def reenter():
            try:
                self.provider.encode("Exact Query")
            except SemanticUnavailable:
                reentered.append(True)
        self.inner.on_call = reenter
        self.assertEqual(self.provider.encode("Exact Query").binding_sha256,
                         self.outer.binding_sha256)
        self.assertEqual(reentered, [True])
        self.inner.on_call = None
        with self.assertRaises(SemanticUnavailable):
            self.provider.encode("Exact Query", check=lambda: (_ for _ in ()).throw(RuntimeError("secret")))
        self.assertEqual(len(self.inner.calls), 1)
        with self.assertRaises(SemanticUnavailable):
            ReviewedSemanticProvider(self.inner, self.reviewed, self.outer,
                adapter_source_sha256=ADAPTER_SHA, source_check=lambda: (_ for _ in ()).throw(
                    RuntimeError("private source detail"))).encode("Exact Query")
        self.assertEqual(len(self.inner.calls), 1)
        self.assertEqual(self.provider.encode("Exact Query").binding_sha256,
                         self.outer.binding_sha256)

    def test_probe_repr_and_failures_do_not_disclose_query_or_inner_errors(self):
        raw = "Exact Query"
        self.assertNotIn(raw, repr(self.provider))
        self.assertNotIn("a red circle", repr(self.provider))
        probe = self.provider.probe()
        self.assertNotIn(raw, repr(probe))
        self.assertNotIn("a red circle", repr(probe))
        self.inner.mode = "raise"
        with self.assertRaises(SemanticUnavailable) as raised:
            self.provider.encode(raw)
        self.assertEqual(str(raised.exception), "semantic_unavailable")
        self.assertNotIn(raw, str(raised.exception))
        self.assertNotIn("private inner diagnostic", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
