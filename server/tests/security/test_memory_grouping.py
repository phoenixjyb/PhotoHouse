"""Security checks for pure, anchor-only memory photo group proposals."""
from pathlib import Path
import math
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.access.memory_grouping import UNAVAILABLE, propose_memory_group
from app.access.visual_candidates import (
    AuthorizationSnapshot,
    VectorRecord,
    VectorSpaceIdentity,
    canonical_vector_checksum,
)


IDENTITY = VectorSpaceIdentity("a" * 64, "b" * 64, "synthetic-space-v1",
                               "synthetic-model-v1", 2, "unit_l2")


def record(asset_id, vector=(1.0, 0.0), identity=IDENTITY, checksum=None):
    vector = tuple(vector)
    return VectorRecord(asset_id, identity, vector,
                        checksum or canonical_vector_checksum(vector))


def propose(seed_records, candidate_records, *, times=None, exclusions=(), seed_ids=None,
            candidate_ids=None, authorized_ids=None, minimum_similarity=0.9,
            max_gap_seconds=21600):
    seed_ids = tuple(seed_ids if seed_ids is not None else (item.asset_id for item in seed_records))
    candidate_ids = tuple(candidate_ids if candidate_ids is not None
                          else (item.asset_id for item in candidate_records))
    cohort = set(seed_ids) | set(candidate_ids)
    return propose_memory_group(
        AuthorizationSnapshot("family-a", frozenset(cohort if authorized_ids is None
                                                       else authorized_ids)),
        seed_ids=seed_ids, seed_vectors=tuple(seed_records),
        candidate_ids=candidate_ids, candidate_vectors=tuple(candidate_records),
        expected_identity=IDENTITY,
        capture_times=times if times is not None else {asset_id: "2026-05-01T10:00:00"
                                                         for asset_id in cohort},
        excluded_ids=exclusions, minimum_similarity=minimum_similarity,
        max_gap_seconds=max_gap_seconds,
    )


class MemoryGroupingTests(unittest.TestCase):
    def test_validates_entire_authorized_cohort_and_all_vector_records(self):
        seed, candidate = record("1"), record("2")
        self.assertIs(propose([seed], [candidate], authorized_ids={"1"}), UNAVAILABLE)
        self.assertIs(propose([seed], [candidate], candidate_ids=["3"]), UNAVAILABLE)
        self.assertIs(propose([seed], [] , candidate_ids=["2"]), UNAVAILABLE)
        self.assertEqual((), propose([seed], [record("2", (0.0, 1.0))]).candidates)
        self.assertIs(propose([seed], [record("2", identity=None)]), UNAVAILABLE)
        self.assertIs(propose([seed], [record("2", checksum="0" * 64)]), UNAVAILABLE)

    def test_temporal_filter_happens_before_ranking_and_result_cap(self):
        seeds = [record("1")]
        # Candidate 2 is a better raw match but falls outside the recorded
        # window. Eligible items still fill all twenty result slots.
        candidates = [record("2")] + [record(str(i), (0.95, math.sqrt(1 - 0.95**2)))
                                      for i in range(3, 24)]
        times = {"1": "2026-05-01T10:00:00", "2": "2026-05-02T10:00:00"}
        times.update({item.asset_id: "2026-05-01T10:01:00" for item in candidates[1:]})
        result = propose(seeds, candidates, times=times)
        self.assertEqual("ready", result.status)
        self.assertEqual(20, len(result.candidates))
        self.assertNotIn("2", [item.asset_id for item in result.candidates])
        self.assertEqual("3", result.candidates[0].asset_id)

    def test_similarity_threshold_and_anchor_only_membership(self):
        seed = record("1")
        candidate = record("2", (0.8, 0.6))
        self.assertEqual((), propose([seed], [candidate]).candidates)
        self.assertEqual("2", propose([seed], [candidate], minimum_similarity=0.79)
                         .candidates[0].asset_id)
        # A-B and B-C similarity cannot bridge C from anchor A.
        diagonal = record("2", (0.8, 0.6))
        chain_end = record("3", (0.0, 1.0))
        result = propose([seed], [diagonal, chain_end], minimum_similarity=0.59)
        self.assertEqual(["2"], [item.asset_id for item in result.candidates])

    def test_uses_recorded_instants_and_never_guesses_mixed_timezone(self):
        seed, candidate = record("1"), record("2")
        result = propose([seed], [candidate], times={
            "1": "2026-05-01T23:30:00-02:00", "2": "2026-05-02T01:00:00Z",
        }, max_gap_seconds=5400)
        self.assertEqual("within_recorded_window", result.candidates[0].time_reason)
        mixed = propose([seed], [candidate], times={
            "1": "2026-05-01T01:30:00", "2": "2026-05-01T01:30:00Z",
        })
        self.assertEqual((), mixed.candidates)
        naive = propose([seed], [candidate], times={
            "1": "2026-11-01T01:30:00", "2": "2026-11-01T02:00:00",
        }, max_gap_seconds=1800)
        self.assertEqual("within_recorded_window", naive.candidates[0].time_reason)

    def test_date_precision_means_written_day_not_exact_window(self):
        seed, candidate = record("1"), record("2")
        result = propose([seed], [candidate], times={
            "1": "2026-02-28", "2": "2026-02-28T23:59:59Z",
        })
        self.assertEqual("same_recorded_day", result.candidates[0].time_reason)
        invalid = propose([seed], [candidate], times={
            "1": "2026-02-30", "2": "2026-02-28",
        })
        self.assertEqual((), invalid.candidates)
        across_day = propose([seed], [candidate], times={
            "1": "2026-02-28", "2": "2026-03-01",
        })
        self.assertEqual((), across_day.candidates)

    def test_exclusions_are_sticky_bounded_and_disjoint_from_seeds(self):
        seed, candidate = record("1"), record("2")
        self.assertEqual((), propose([seed], [candidate], exclusions=("2",)).candidates)
        self.assertIs(propose([seed], [candidate], exclusions=("1",)), UNAVAILABLE)
        self.assertIs(propose([seed], [candidate], exclusions=tuple(str(i) for i in range(1, 514))),
                      UNAVAILABLE)
        self.assertEqual("2", propose([seed], [candidate], exclusions=("500",))
                         .candidates[0].asset_id)

    def test_strict_shapes_capture_times_and_ids_refuse_without_partial_results(self):
        seed, candidate = record("1"), record("2")
        valid = {"1": "2026-05-01", "2": "2026-05-01"}
        cases = [
            {"1": "2026-05-01"},
            {"1": "2026-05-01", "2": "2026-05-01", "99": None},
            {"1": 123, "2": "2026-05-01"},
            {"1": "x" * 129, "2": "2026-05-01"},
        ]
        self.assertIs(propose([seed], [candidate], times=iter(valid.items())), UNAVAILABLE)
        self.assertTrue(all(propose([seed], [candidate], times=case) is UNAVAILABLE
                            for case in cases))
        self.assertIs(propose([seed], [candidate], seed_ids=["01"]), UNAVAILABLE)
        self.assertIs(propose([seed], [candidate], minimum_similarity=float("nan")), UNAVAILABLE)

    def test_recorded_date_metadata_is_the_only_time_input(self):
        seed, candidate = record("1"), record("2")
        # No filename, upload time, date hint, or timezone guess enters this API.
        result = propose([seed], [candidate], times={"1": None, "2": "2026-05-01"})
        self.assertEqual((), result.candidates)

    def test_scoring_only_receives_temporally_eligible_pairs_and_outputs_are_immutable(self):
        seed = record("1")
        candidates = [record("2"), record("3")]
        times = {"1": "2026-05-01T10:00:00", "2": "2026-05-01T10:01:00",
                 "3": "2026-05-02T10:00:00"}
        from app.access import memory_grouping
        with patch.object(memory_grouping, "_score", wraps=memory_grouping._score) as score:
            result = propose([seed], candidates, times=times)
        self.assertEqual(1, score.call_count)
        self.assertEqual(["2"], [item.asset_id for item in result.candidates])
        self.assertIsInstance(result.candidates, tuple)
        with self.assertRaises(Exception):
            result.candidates[0].asset_id = "3"


if __name__ == "__main__":
    unittest.main()
