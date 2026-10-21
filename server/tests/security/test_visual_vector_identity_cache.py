"""Bounded pure identity-validity cache contracts."""
from dataclasses import replace
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "tests/security")]

from app.access import visual_vector_artifacts as artifacts_module
from app.access.visual_candidates import VectorSpaceIdentity
from app.access.visual_vector_artifacts import _identity_fields_valid_cached, _valid_identity
import test_semantic_bulk_search as bulk_fixture


IDENTITY = VectorSpaceIdentity(
    artifact_sha256="a" * 64,
    preprocessing_sha256="b" * 64,
    vector_space_id="synthetic-clip-space-v1",
    model_version="synthetic-v1",
    dimension=2,
    normalization="unit_l2",
)


def identity(**changes):
    return replace(IDENTITY, **changes)


class VisualVectorIdentityCacheTests(unittest.TestCase):
    def setUp(self):
        _identity_fields_valid_cached.cache_clear()
        self.addCleanup(_identity_fields_valid_cached.cache_clear)

    def test_validity_cache_is_bounded_and_keys_only_copied_identity_values(self):
        self.assertTrue(_valid_identity(IDENTITY))
        self.assertTrue(_valid_identity(replace(IDENTITY)))
        info = _identity_fields_valid_cached.cache_info()
        self.assertEqual((info.misses, info.hits, info.currsize), (1, 1, 1))

        for number in range(130):
            self.assertTrue(_valid_identity(identity(model_version=f"synthetic-{number}")))
        info = _identity_fields_valid_cached.cache_info()
        self.assertEqual(info.maxsize, 128)
        self.assertEqual(info.currsize, 128)
        self.assertEqual(info.misses, 131)

    def test_each_call_observes_mutated_frozen_identity_fields(self):
        changed = replace(IDENTITY)
        self.assertTrue(_valid_identity(changed))
        object.__setattr__(changed, "artifact_sha256", "g" * 64)
        self.assertFalse(_valid_identity(changed))
        object.__setattr__(changed, "artifact_sha256", IDENTITY.artifact_sha256)
        self.assertTrue(_valid_identity(changed))
        info = _identity_fields_valid_cached.cache_info()
        self.assertEqual((info.misses, info.hits, info.currsize), (2, 1, 2))

    def test_invalid_types_and_unbounded_strings_bypass_cache(self):
        class AliasedString(str):
            pass

        class AliasedInteger(int):
            pass

        class DerivedIdentity(VectorSpaceIdentity):
            pass

        invalid = (
            object(),
            DerivedIdentity(IDENTITY.artifact_sha256, IDENTITY.preprocessing_sha256,
                            IDENTITY.vector_space_id, IDENTITY.model_version,
                            IDENTITY.dimension, IDENTITY.normalization),
            identity(artifact_sha256=AliasedString("a" * 64)),
            identity(model_version=AliasedString("synthetic-v1")),
            identity(dimension=True),
            identity(dimension=AliasedInteger(2)),
            identity(artifact_sha256="a" * 1_000_000),
            identity(preprocessing_sha256="b" * 1_000_000),
            identity(vector_space_id="s" * 1_000_000),
            identity(model_version="v" * 1_000_000),
        )
        before = _identity_fields_valid_cached.cache_info()
        for value in invalid:
            with self.subTest(value_type=type(value).__name__):
                self.assertFalse(_valid_identity(value))
                self.assertEqual(before, _identity_fields_valid_cached.cache_info())

    def test_same_length_invalid_regex_values_are_cached_as_false(self):
        invalid = identity(artifact_sha256="g" * 64)
        self.assertFalse(_valid_identity(invalid))
        self.assertFalse(_valid_identity(replace(invalid)))
        info = _identity_fields_valid_cached.cache_info()
        self.assertEqual((info.misses, info.hits, info.currsize), (1, 1, 1))
        self.assertFalse(_valid_identity(identity(model_version="INVALID")))
        self.assertEqual(_identity_fields_valid_cached.cache_info().currsize, 2)

    def test_uncached_and_cached_endpoint_responses_are_identical(self):
        fixture = bulk_fixture.SemanticBulkEndpointTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)

        def uncached(*fields):
            return artifacts_module._valid_identity_uncached(VectorSpaceIdentity(*fields))

        with patch.object(artifacts_module, "_identity_fields_valid_cached", side_effect=uncached):
            baseline = fixture.query(query="family garden")
        _identity_fields_valid_cached.cache_clear()
        cached = fixture.query(query="family garden")

        self.assertEqual(baseline.status_code, 200, baseline.text)
        self.assertEqual(cached.status_code, 200, cached.text)
        # The full body includes exact cards/scores, binding and fingerprint.
        self.assertEqual(baseline.json(), cached.json())
        self.assertGreaterEqual(cached.json()["semantic"]["candidate_count"], 1)
        info = _identity_fields_valid_cached.cache_info()
        self.assertEqual(info.misses, 1)
        self.assertGreater(info.hits, 0)
        self.assertEqual(len(fixture.calls), 2)


if __name__ == "__main__":
    unittest.main()
