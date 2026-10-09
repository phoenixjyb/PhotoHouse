"""Pure synthetic checks for bounded photo-vector candidate ranking."""
from dataclasses import replace
import math
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.access.visual_candidates import (
    MAX_CANDIDATES,
    MAX_DIMENSION,
    MAX_RESULTS,
    MAX_SEEDS,
    UNAVAILABLE,
    AuthorizationSnapshot,
    VectorRecord,
    VectorSpaceIdentity,
    canonical_vector_checksum,
    rank_visual_candidates,
)


IDENTITY = VectorSpaceIdentity(
    artifact_sha256="a" * 64,
    preprocessing_sha256="b" * 64,
    vector_space_id="synthetic-clip-space-v1",
    model_version="synthetic-v1",
    dimension=2,
    normalization="unit_l2",
)


def record(asset_id, vector, identity=IDENTITY, checksum=None):
    vector = tuple(vector)
    return VectorRecord(asset_id, identity, vector,
                        checksum or canonical_vector_checksum(vector))


def rank(seed_vectors, candidate_vectors, *, seed_ids=None, candidate_ids=None,
         authorized_ids=None, expected_identity=IDENTITY):
    seed_ids = tuple(seed_ids if seed_ids is not None else (item.asset_id for item in seed_vectors))
    candidate_ids = tuple(candidate_ids if candidate_ids is not None
                          else (item.asset_id for item in candidate_vectors))
    authorized_ids = (set(seed_ids) | set(candidate_ids) if authorized_ids is None
                      else set(authorized_ids))
    return rank_visual_candidates(
        AuthorizationSnapshot("family-a", frozenset(authorized_ids)),
        seed_ids=seed_ids,
        seed_vectors=tuple(seed_vectors),
        candidate_ids=candidate_ids,
        candidate_vectors=tuple(candidate_vectors),
        expected_identity=expected_identity,
    )


class VisualCandidateRankingTests(unittest.TestCase):
    def test_cosine_ranking_uses_best_individual_seed_and_excludes_seeds(self):
        seeds = [record("1", (1.0, 0.0)), record("2", (0.0, 1.0))]
        candidates = [
            record("3", (0.8, 0.6)),
            record("4", (0.6, 0.8)),
            record("5", (0.6, -0.8)),
            record("1", (1.0, 0.0)),  # seed repeated in candidate cohort
        ]
        result = rank(seeds, candidates)
        self.assertEqual("ready", result.status)
        self.assertEqual([("3", "1"), ("4", "2"), ("5", "1")],
                         [(item.asset_id, item.matched_seed_asset_id)
                          for item in result.candidates])

    def test_ties_are_stable_by_numeric_candidate_then_seed_id(self):
        diagonal = 0.70710677
        seeds = [record("10", (0.0, 1.0)), record("2", (1.0, 0.0))]
        candidates = [record("11", (diagonal, diagonal)),
                      record("10", (0.0, 1.0)),
                      record("3", (diagonal, diagonal))]
        result = rank(seeds, candidates)
        self.assertEqual(["3", "11"], [item.asset_id for item in result.candidates])
        self.assertEqual(["2", "2"], [item.matched_seed_asset_id for item in result.candidates])

    def test_norm_tolerance_cannot_boost_collinear_candidate_rank(self):
        seeds = [record("1", (1.0, 0.0))]
        # Both vectors fall within the accepted float32 unit-norm tolerance.
        # Their cosine similarities are equal even though their raw dot
        # products differ; numeric ID must therefore decide the tie.
        candidates = [record("2", (0.9991, 0.0)), record("3", (0.9999, 0.0))]
        result = rank(seeds, candidates)
        self.assertEqual(["2", "3"], [item.asset_id for item in result.candidates])

    def test_repeated_seed_asset_with_conflicting_vector_record_is_refused(self):
        seed = record("1", (1.0, 0.0))
        conflicting = record("1", (0.0, 1.0))
        candidate = record("2", (0.8, 0.6))
        self.assertIs(rank([seed], [conflicting, candidate]), UNAVAILABLE)

    def test_foreign_id_refuses_before_any_scoring_and_cannot_influence_top_k(self):
        seeds = [record("1", (1.0, 0.0))]
        candidates = [record("2", (0.8, 0.6)), record("99", (0.0, 1.0))]
        with patch("app.access.visual_candidates._score", side_effect=AssertionError("scored before authorization")) as score:
            result = rank(seeds, candidates, authorized_ids={"1", "2"})
        self.assertIs(result, UNAVAILABLE)
        score.assert_not_called()
        baseline = rank(seeds, candidates[:1])
        self.assertEqual(["2"], [item.asset_id for item in baseline.candidates])

    def test_missing_vectors_duplicate_ids_and_noncanonical_ids_fail_as_a_whole(self):
        seed = record("1", (1.0, 0.0))
        candidate = record("2", (0.8, 0.6))
        cases = [
            rank([seed], [], candidate_ids=["2"]),
            rank([seed], [candidate], candidate_ids=["2", "2"]),
            rank([seed], [candidate], seed_ids=["1", "1"]),
            rank([seed], [candidate], candidate_ids=["02"]),
            rank([seed], [candidate], candidate_ids=["3"]),
            rank([], [candidate], seed_ids=["1"]),
        ]
        self.assertTrue(all(result is UNAVAILABLE for result in cases))

    def test_vector_checksum_is_canonical_and_mismatches_are_refused(self):
        self.assertEqual(canonical_vector_checksum((1.0, 0.0)),
                         canonical_vector_checksum([1, 0]))
        seed = record("1", (1.0, 0.0))
        wrong = record("2", (0.8, 0.6), checksum="0" * 64)
        self.assertIs(rank([seed], [wrong]), UNAVAILABLE)

    def test_missing_or_mixed_exact_identity_is_refused(self):
        seed = record("1", (1.0, 0.0))
        candidate = record("2", (0.8, 0.6))
        identity_changes = [
            replace(IDENTITY, artifact_sha256="c" * 64),
            replace(IDENTITY, preprocessing_sha256="d" * 64),
            replace(IDENTITY, vector_space_id="other-space-v1"),
            replace(IDENTITY, model_version="other-v2"),
            replace(IDENTITY, dimension=3),
            replace(IDENTITY, normalization="none"),
        ]
        for changed in identity_changes:
            with self.subTest(identity=changed):
                mixed = record("2", (0.8, 0.6), identity=changed)
                self.assertIs(rank([seed], [mixed]), UNAVAILABLE)
        missing = VectorRecord("2", None, (0.8, 0.6), canonical_vector_checksum((0.8, 0.6)))
        self.assertIs(rank([seed], [missing]), UNAVAILABLE)
        self.assertIs(rank([seed], [candidate], expected_identity=None), UNAVAILABLE)

    def test_wrong_shape_nonfinite_zero_and_nonunit_vectors_are_refused(self):
        seed = record("1", (1.0, 0.0))
        invalid_vectors = [
            (0.8,),
            (math.nan, 1.0),
            (math.inf, 0.0),
            (0.0, 0.0),
            (0.5, 0.5),
        ]
        for vector in invalid_vectors:
            with self.subTest(vector=vector):
                try:
                    checksum = canonical_vector_checksum(vector)
                except ValueError:
                    checksum = "0" * 64
                bad = VectorRecord("2", IDENTITY, tuple(vector), checksum)
                self.assertIs(rank([seed], [bad]), UNAVAILABLE)
        with self.assertRaisesRegex(ValueError, "invalid_vector"):
            canonical_vector_checksum((True, 0.0))
        with self.assertRaisesRegex(ValueError, "invalid_vector"):
            canonical_vector_checksum((10 ** 10000, 0.0))

    def test_record_coverage_duplicates_and_cohort_bounds_fail_closed(self):
        seed = record("1", (1.0, 0.0))
        candidate = record("2", (0.8, 0.6))
        self.assertIs(rank([seed], [candidate, candidate]), UNAVAILABLE)
        self.assertIs(rank([seed], [candidate], candidate_ids=["2", "3"]), UNAVAILABLE)
        seed_ids = tuple(str(value) for value in range(1, MAX_SEEDS + 2))
        too_many_seed_vectors = [record(value, (1.0, 0.0)) for value in seed_ids]
        self.assertIs(rank(too_many_seed_vectors, [], candidate_ids=[]), UNAVAILABLE)
        too_many_candidates = [record(str(value), (0.8, 0.6))
                               for value in range(100, 100 + MAX_CANDIDATES + 1)]
        self.assertIs(rank([seed], too_many_candidates), UNAVAILABLE)

    def test_dimension_and_result_limits_are_hard(self):
        maximum_identity = replace(IDENTITY, dimension=MAX_DIMENSION)
        maximum_vector = (1.0,) + (0.0,) * (MAX_DIMENSION - 1)
        seed = record("1", maximum_vector, maximum_identity)
        candidate = record("2", maximum_vector, maximum_identity)
        self.assertEqual(["2"], [item.asset_id for item in rank(
            [seed], [candidate], expected_identity=maximum_identity).candidates])
        too_wide_identity = replace(IDENTITY, dimension=MAX_DIMENSION + 1)
        self.assertIs(rank([seed], [candidate], expected_identity=too_wide_identity), UNAVAILABLE)

        many = [record(str(value), (0.8, 0.6)) for value in range(100, 100 + MAX_CANDIDATES)]
        result = rank([record("1", (1.0, 0.0))], many)
        self.assertEqual(MAX_RESULTS, len(result.candidates))
        self.assertEqual([str(value) for value in range(100, 100 + MAX_RESULTS)],
                         [item.asset_id for item in result.candidates])

    def test_inputs_are_not_mutated_or_retained_as_mutable_vectors(self):
        source_vector = [1.0, 0.0]
        seed = VectorRecord("1", IDENTITY, source_vector, canonical_vector_checksum(source_vector))
        candidate = record("2", (0.8, 0.6))
        snapshot = AuthorizationSnapshot("family-a", {"1", "2"})
        before = (source_vector[:], seed.vector, candidate.vector, snapshot.photo_ids)
        result = rank_visual_candidates(snapshot, seed_ids=["1"], seed_vectors=[seed],
            candidate_ids=["2"], candidate_vectors=[candidate], expected_identity=IDENTITY)
        self.assertEqual(before, (source_vector, seed.vector, candidate.vector, snapshot.photo_ids))
        self.assertIsInstance(seed.vector, tuple)
        self.assertEqual("ready", result.status)
        with self.assertRaises((AttributeError, TypeError)):
            result.candidates[0].asset_id = "3"

    def test_authorization_snapshot_rejects_lazy_and_overbound_iterables_without_iteration(self):
        consumed = []
        def lazy_ids():
            consumed.append("iterated")
            yield "1"
        lazy = lazy_ids()
        lazy_snapshot = AuthorizationSnapshot("family-a", lazy)
        self.assertEqual([], consumed)
        self.assertEqual(frozenset(), lazy_snapshot.photo_ids)

        oversized = [str(value) for value in range(1, MAX_SEEDS + MAX_CANDIDATES + 2)]
        oversized_snapshot = AuthorizationSnapshot("family-a", oversized)
        self.assertEqual(frozenset(), oversized_snapshot.photo_ids)

        malformed = AuthorizationSnapshot("family-a", ["1", object()])
        self.assertEqual(frozenset(), malformed.photo_ids)

        class IterationTrap(list):
            def __iter__(self):
                raise AssertionError("snapshot copied an unsupported iterable")
        trap_snapshot = AuthorizationSnapshot("family-a", IterationTrap(["1", "2"]))
        self.assertEqual(frozenset(), trap_snapshot.photo_ids)

        seed = record("1", (1.0, 0.0))
        self.assertIs(rank_visual_candidates(lazy_snapshot, seed_ids=("1",), seed_vectors=(seed,),
            candidate_ids=(), candidate_vectors=(), expected_identity=IDENTITY), UNAVAILABLE)
        self.assertEqual([], consumed)

    def test_ranker_makes_no_storage_process_or_network_calls(self):
        seed = record("1", (1.0, 0.0))
        candidate = record("2", (0.8, 0.6))
        def forbidden(*_args, **_kwargs):
            raise AssertionError("pure ranker attempted I/O or process work")
        with patch("builtins.open", side_effect=forbidden), \
             patch.object(sqlite3, "connect", side_effect=forbidden), \
             patch.object(socket, "create_connection", side_effect=forbidden), \
             patch.object(socket, "socket", side_effect=forbidden), \
             patch.object(subprocess, "Popen", side_effect=forbidden), \
             patch.object(subprocess, "run", side_effect=forbidden):
            result = rank([seed], [candidate])
        self.assertEqual("ready", result.status)


if __name__ == "__main__":
    unittest.main()
