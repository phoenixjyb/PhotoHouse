"""Exact field-order and type guards for tuple-based artifact extraction."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.access import semantic_bulk_vectors as bulk
from app.access import semantic_search as search
from app.access.visual_vector_artifacts import ImmutableVectorArtifact


def artifact(**overrides):
    values = {
        "record_id": "a" * 64,
        "asset_id": "7",
        "source_sha256": "b" * 64,
        "model_name": "model-v1",
        "artifact_sha256": "c" * 64,
        "preprocessing_sha256": "d" * 64,
        "vector_space_id": "space-v1",
        "model_version": "version-v1",
        "dimension": 768,
        "normalization": "unit_l2",
        "identity_sha256": "e" * 64,
        "relative_path": "vectors/item.npy",
        "file_sha256": "f" * 64,
        "component_sha256": "0" * 64,
        "created_at": 123456,
        "status": "ready",
    }
    values.update(overrides)
    return ImmutableVectorArtifact(**values)


class ArtifactFieldExtractionTests(unittest.TestCase):
    def test_bulk_extraction_preserves_all_sixteen_fields_and_order(self):
        value = artifact()
        calls = []
        rows = bulk._artifact_cohort_key((value,), lambda: calls.append("check"))
        expected = tuple(getattr(value, name) for name in bulk._ARTIFACT_COHORT_FIELDS)
        self.assertEqual(rows, (expected,))
        self.assertEqual(len(rows[0]), 16)
        self.assertEqual(calls, ["check"])
        self.assertEqual(bulk._ARTIFACT_COHORT_FIELDS[8], "dimension")
        self.assertEqual(bulk._ARTIFACT_COHORT_FIELDS[14], "created_at")

    def test_semantic_freeze_preserves_all_sixteen_fields_and_order(self):
        value = artifact()
        calls = []
        frozen = search._freeze_artifacts({"7": value}, lambda: calls.append("check"))
        expected = tuple(getattr(value, name) for name in search._ARTIFACT_FIELDS)
        self.assertEqual(frozen, (("7", expected),))
        self.assertEqual(len(frozen[0][1]), 16)
        self.assertEqual(search._ARTIFACT_FIELDS, bulk._ARTIFACT_COHORT_FIELDS)
        self.assertEqual(calls, ["check"])

    def test_bulk_exact_type_gate_rejects_bool_float_and_subclass_values(self):
        class StringSubclass(str):
            pass

        class SpoofingTypeMeta(type):
            def __eq__(self, other):
                return True

            __hash__ = type.__hash__

        class SpoofedStringSubclass(str, metaclass=SpoofingTypeMeta):
            pass

        for bad in (
            artifact(dimension=True),
            artifact(created_at=False),
            artifact(dimension=768.0),
            artifact(created_at=1.0),
            artifact(status=StringSubclass("ready")),
            artifact(status=SpoofedStringSubclass("ready")),
        ):
            with self.subTest(value=bad), self.assertRaises(bulk.BulkVectorUnavailable):
                bulk._artifact_cohort_key((bad,), lambda: None)

    def test_missing_attribute_keeps_attribute_error_semantics(self):
        bulk_value = artifact()
        object.__delattr__(bulk_value, "status")
        with self.assertRaises(AttributeError):
            bulk._artifact_cohort_key((bulk_value,), lambda: None)

        freeze_value = artifact()
        object.__delattr__(freeze_value, "status")
        with self.assertRaises(AttributeError):
            search._freeze_artifacts({"7": freeze_value}, lambda: None)

    def test_callback_runs_before_each_copy_and_mutation_is_observed(self):
        bulk_value = artifact()
        bulk_calls = []

        def mutate_bulk():
            bulk_calls.append("check")
            object.__setattr__(bulk_value, "status", "changed-during-check")

        row = bulk._artifact_cohort_key((bulk_value,), mutate_bulk)[0]
        self.assertEqual(row[15], "changed-during-check")
        self.assertEqual(bulk_calls, ["check"])

        freeze_value = artifact()
        freeze_calls = []

        def mutate_freeze():
            freeze_calls.append("check")
            object.__setattr__(freeze_value, "status", "changed-during-check")

        frozen = search._freeze_artifacts({"7": freeze_value}, mutate_freeze)
        self.assertEqual(frozen[0][1][15], "changed-during-check")
        self.assertEqual(freeze_calls, ["check"])


if __name__ == "__main__":
    unittest.main()
