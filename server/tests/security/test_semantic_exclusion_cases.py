"""Pure scorecard tests for explicit semantic exclusion candidates."""
from __future__ import annotations

import copy
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from semantic_exclusion_cases import dataset_sha256, evaluate, validate_dataset  # noqa: E402


def dataset():
    return {
        "schema": "photohouse.semantic_exclusion_cases.v1",
        "images": ["wanted", "excluded", "other-a", "other-b"],
        "cases": [{
            "id": "absence-one",
            "relevant_images": ["wanted"],
            "forbidden_images": ["excluded"],
            "queries": {"en": "A dog on grass, without a boat",
                        "zh": "草地上的狗，不要船",
                        "zh-en": "草地上的 dog without a boat"},
        }],
    }


def basis(index, dimension=512):
    value = [0.0] * dimension
    value[index] = 1.0
    return value


def image_vectors(*, forbidden_score=0.5):
    return {
        "wanted": basis(0),
        "excluded": [forbidden_score, math.sqrt(1 - forbidden_score ** 2)] + [0.0] * 510,
        "other-a": basis(2),
        "other-b": basis(3),
    }


def text_vectors(per_language=None):
    per_language = per_language or {"en": basis(0), "zh": basis(0), "zh-en": basis(0)}
    return {f"absence-one:{language}": vector for language, vector in per_language.items()}


class SemanticExclusionCasesTests(unittest.TestCase):
    def test_fingerprint_binds_schema_ids_labels_and_exact_query_bytes(self):
        original = dataset()
        baseline = dataset_sha256(original)
        self.assertEqual(validate_dataset(original), original)
        for mutate in (
            lambda value: value["images"].reverse(),
            lambda value: value["cases"][0]["relevant_images"].append("other-a"),
            lambda value: value["cases"][0]["forbidden_images"].append("other-b"),
            lambda value: value["cases"][0]["queries"].update(zh="改动"),
        ):
            changed = copy.deepcopy(original)
            mutate(changed)
            self.assertNotEqual(dataset_sha256(changed), baseline)
        changed_schema = copy.deepcopy(original)
        changed_schema["schema"] = "photohouse.semantic_exclusion_cases.v2"
        with self.assertRaises(ValueError):
            validate_dataset(changed_schema)

    def test_forbidden_below_best_is_still_reported_in_requested_top_k(self):
        report = evaluate(dataset(), image_vectors(), text_vectors(), dimension=512, top_k=2)
        self.assertEqual(report["effective_top_k"], 2)
        self.assertEqual(report["overall"]["forbidden_ahead_or_tied"], 0)
        self.assertEqual(report["overall"]["forbidden_in_top_k"], 3)
        self.assertEqual(report["languages"]["en"], {
            "queries": 1, "forbidden_ahead_or_tied": 0,
            "forbidden_ahead_or_tied_rate": 0.0,
            "forbidden_in_top_k": 1, "forbidden_in_top_k_rate": 1.0,
        })
        self.assertFalse(report["activation_approved"])

    def test_forbidden_ahead_and_tied_candidates_are_detected(self):
        ahead_images = image_vectors()
        ahead_images["wanted"] = [0.5, 0.0, 0.0, 0.0, math.sqrt(0.75)] + [0.0] * 507
        ahead_images["excluded"] = basis(0)
        ahead = evaluate(dataset(), ahead_images, text_vectors(), dimension=512, top_k=1)
        self.assertTrue(ahead["cases"][0]["languages"]["en"]["forbidden_ahead_or_tied"])
        self.assertTrue(ahead["cases"][0]["languages"]["en"]["forbidden_in_top_k"])

        tied_images = image_vectors(forbidden_score=1.0)
        tied_images["wanted"] = basis(0)
        tied = evaluate(dataset(), tied_images, text_vectors(), dimension=512, top_k=1)
        self.assertTrue(tied["overall"]["forbidden_ahead_or_tied"])
        self.assertTrue(tied["overall"]["forbidden_in_top_k"])

    def test_language_regressions_and_top_k_clamping_are_visible(self):
        vectors = text_vectors({"en": basis(0), "zh": basis(1), "zh-en": basis(0)})
        report = evaluate(dataset(), image_vectors(), vectors, dimension=512, top_k=64)
        self.assertEqual(report["effective_top_k"], 4)
        self.assertFalse(report["languages"]["en"]["forbidden_ahead_or_tied"])
        self.assertTrue(report["languages"]["zh"]["forbidden_ahead_or_tied"])
        self.assertFalse(report["languages"]["zh-en"]["forbidden_ahead_or_tied"])
        self.assertEqual(report["overall"]["forbidden_ahead_or_tied"], 1)
        self.assertEqual(report["overall"]["queries"], 3)

    def test_collapsed_vectors_conservatively_fail_exclusion(self):
        collapsed = {image_id: basis(0) for image_id in dataset()["images"]}
        report = evaluate(dataset(), collapsed, text_vectors(), dimension=512, top_k=1)
        self.assertEqual(report["overall"]["forbidden_ahead_or_tied"], 3)
        self.assertEqual(report["overall"]["forbidden_in_top_k"], 3)

    def test_forbidden_outside_top_k_and_epsilon_boundary(self):
        report = evaluate(dataset(), image_vectors(), text_vectors(), dimension=512, top_k=1)
        self.assertEqual(report["overall"]["forbidden_in_top_k"], 0)
        self.assertEqual(report["cases"][0]["languages"]["en"]["best_relevant_rank"], 1)
        near_tie = evaluate(dataset(), image_vectors(forbidden_score=1 - 5e-8),
                            text_vectors(), dimension=512, top_k=1)
        self.assertEqual(near_tie["overall"]["forbidden_ahead_or_tied"], 3)
        self.assertEqual(near_tie["overall"]["forbidden_in_top_k"], 3)
        outside = evaluate(dataset(), image_vectors(forbidden_score=1 - 2e-7),
                           text_vectors(), dimension=512, top_k=1)
        self.assertEqual(outside["overall"]["forbidden_ahead_or_tied"], 0)
        self.assertEqual(outside["overall"]["forbidden_in_top_k"], 0)

    def test_768_dimensions_and_multiple_relevant_and_forbidden_labels(self):
        labeled = dataset()
        labeled["cases"][0]["relevant_images"].append("other-a")
        labeled["cases"][0]["forbidden_images"].append("other-b")
        images = {key: vector + [0.0] * 256 for key, vector in image_vectors().items()}
        texts = {key: vector + [0.0] * 256 for key, vector in text_vectors().items()}
        report = evaluate(labeled, images, texts, dimension=768, top_k=2)
        self.assertEqual(report["overall"]["queries"], 3)
        self.assertEqual(report["overall"]["forbidden_ahead_or_tied"], 0)
        self.assertEqual(report["overall"]["forbidden_in_top_k"], 3)

    def test_rejects_bad_vectors_dimensions_and_top_k(self):
        good_images, good_texts = image_vectors(), text_vectors()
        with self.assertRaisesRegex(ValueError, "^invalid_semantic_exclusion_vectors$"):
            evaluate(dataset(), {**good_images, "extra": basis(4)}, good_texts, dimension=512)
        bad = copy.deepcopy(good_images)
        bad["wanted"] = [0.0] * 512
        with self.assertRaisesRegex(ValueError, "^invalid_semantic_exclusion_vectors$"):
            evaluate(dataset(), bad, good_texts, dimension=512)
        bad = copy.deepcopy(good_texts)
        bad["absence-one:zh"] = [float("nan")] + [0.0] * 511
        with self.assertRaisesRegex(ValueError, "^invalid_semantic_exclusion_vectors$"):
            evaluate(dataset(), good_images, bad, dimension=512)
        with self.assertRaisesRegex(ValueError, "^invalid_semantic_exclusion_vectors$"):
            evaluate(dataset(), good_images, good_texts, dimension=256)
        with self.assertRaisesRegex(ValueError, "^invalid_semantic_exclusion_vectors$"):
            evaluate(dataset(), good_images, good_texts, dimension=512, top_k=True)

    def test_rejects_invalid_schema_labels_ids_and_query_bounds(self):
        mutations = (
            lambda value: value["cases"][0].update(extra=True),
            lambda value: value["images"].append("wanted"),
            lambda value: value["cases"][0].update(relevant_images=["missing"]),
            lambda value: value["cases"][0].update(forbidden_images=["wanted"]),
            lambda value: value["cases"][0].update(forbidden_images=["excluded", "excluded"]),
            lambda value: value["cases"][0]["queries"].update(fr="bonjour"),
            lambda value: value["cases"][0]["queries"].update(zh=" bad\nquery"),
            lambda value: value["cases"][0]["queries"].update(en="x" * 513),
            lambda value: value.update(paths=["/not-part-of-this-contract"]),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                changed = copy.deepcopy(dataset())
                mutate(changed)
                with self.assertRaisesRegex(ValueError, "^invalid_semantic_exclusion_dataset$"):
                    validate_dataset(changed)


if __name__ == "__main__":
    unittest.main()
