"""Private harness profiling stays bounded, phase-only and result-neutral."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts"),
                str(ROOT / "tests/security")]

import semantic_request_profile as profile
import test_semantic_search as semantic_fixtures
from app.access import discovery as discovery_module


def _patched_class_namespaces():
    from app.access.discovery import DiscoveryReads, ReadBudget
    from app.access.semantic_encoder import LocalSemanticEncoder
    from app.access.semantic_eligibility import SemanticEligibilityStore
    from app.access.semantic_search import SemanticSearchReads, SemanticSearchRuntime

    classes = (DiscoveryReads, ReadBudget, LocalSemanticEncoder,
               SemanticEligibilityStore, SemanticSearchReads, SemanticSearchRuntime)
    return {owner: dict(vars(owner)) for owner in classes}


def _assert_class_namespaces_unchanged(test, before):
    for owner, prior in before.items():
        current = vars(owner)
        test.assertEqual(set(current), set(prior), owner.__name__)
        for name, descriptor in prior.items():
            test.assertIs(current[name], descriptor, (owner.__name__, name))


class SemanticRequestProfileTests(unittest.TestCase):
    def test_real_semantic_endpoint_is_profiled_without_retaining_request_data(self):
        fixture = semantic_fixtures.SemanticSearchTests(
            "test_semantic_scores_replace_literal_eligibility_only_on_the_explicit_api")
        fixture.setUp()
        try:
            namespaces = _patched_class_namespaces()
            original_digest = discovery_module.digest
            ticks = iter(range(0, 100_000_000, 1_000_000))
            with profile.request_profile(enabled=True, clock=lambda: next(ticks)) as observer:
                response = fixture.query(query="private phrase marker-92831")
                result = observer.snapshot()
            self.assertEqual(response.status_code, 200, response.text)
            _assert_class_namespaces_unchanged(self, namespaces)
            self.assertIs(discovery_module.digest, original_digest)
            self.assertEqual(result["schema"], "photohouse.semantic_request_profile.v1")
            self.assertIs(result["diagnostic_only"], True)
            self.assertEqual(observer.request_count, 1)
            self.assertEqual(len(result["requests"]), 1)
            request = result["requests"][0]
            self.assertGreater(request["total_ms"], 0)
            for phase in ("runtime_total", "authorization", "source_binding",
                          "source_sql", "source_extra", "prepared_facts",
                          "artifacts", "canonical_hash", "encoder_roundtrip", "rank"):
                self.assertGreater(result["phases"][phase]["calls"], 0, phase)
                self.assertLessEqual(result["phases"][phase]["exclusive_ms"],
                                     result["phases"][phase]["inclusive_ms"] + 0.000001)
            exclusive_sum = sum(values["exclusive_ms"] for values in request["phases"].values())
            self.assertAlmostEqual(exclusive_sum, request["total_ms"], places=5)
            encoded = json.dumps(result, sort_keys=True)
            for secret in ("private phrase marker-92831", "Bearer ", str(fixture.root),
                           "qualification_sha256", "semantic_score", "query_sha256"):
                self.assertNotIn(secret, encoded)
        finally:
            fixture.doCleanups()

    def test_failed_request_is_counted_and_all_patches_restore(self):
        fixture = semantic_fixtures.SemanticSearchTests(
            "test_semantic_scores_replace_literal_eligibility_only_on_the_explicit_api")
        fixture.setUp()
        try:
            namespaces = _patched_class_namespaces()
            fixture.files["101"][0].write_bytes(b"corrupt")
            with profile.instrument_requests() as observer:
                response = fixture.query()
                result = observer.snapshot()
            self.assertEqual(response.status_code, 503)
            _assert_class_namespaces_unchanged(self, namespaces)
            self.assertGreater(result["phases"]["rank"]["errors"], 0)
            self.assertGreater(result["phases"]["runtime_total"]["errors"], 0)
        finally:
            fixture.doCleanups()

    def test_nested_span_exclusive_time_and_request_cap_are_deterministic(self):
        observer = profile.RequestObserver()
        record = observer._start_request()
        ticks = iter(range(0, 20_000_000, 1_000_000))
        state = profile._RequestState(observer, record, lambda: next(ticks))
        token = profile._ACTIVE.set(state)
        try:
            with profile._span("source_binding"):
                with profile._span("source_sql"):
                    pass
        finally:
            profile._ACTIVE.reset(token)
        nested = observer.snapshot()["requests"][0]["phases"]
        self.assertEqual(nested["source_sql"]["inclusive_ms"], 1.0)
        self.assertEqual(nested["source_binding"]["inclusive_ms"], 3.0)
        self.assertEqual(nested["source_binding"]["exclusive_ms"], 2.0)

        bounded = profile.RequestObserver()
        for _ in range(profile._MAX_REQUESTS + 5):
            bounded._start_request()
        snapshot = bounded.snapshot()
        self.assertEqual(len(snapshot["requests"]), profile._MAX_REQUESTS)
        self.assertEqual(snapshot["dropped_requests"], 5)
        self.assertEqual(bounded.request_count, profile._MAX_REQUESTS + 5)

    def test_broken_clock_cannot_change_endpoint_result_or_leak_error_text(self):
        fixture = semantic_fixtures.SemanticSearchTests(
            "test_semantic_scores_replace_literal_eligibility_only_on_the_explicit_api")
        fixture.setUp()
        try:
            def broken_clock():
                raise RuntimeError("clock failure secret marker")

            with profile.instrument_requests(clock=broken_clock) as observer:
                response = fixture.query()
                result = observer.snapshot()
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(observer.request_count, 1)
            self.assertNotIn("clock failure secret marker", json.dumps(result))
        finally:
            fixture.doCleanups()

    def test_overlapping_instrumentation_is_refused_without_nested_patch(self):
        with profile.instrument_requests():
            with self.assertRaisesRegex(ValueError, "already active"):
                with profile.instrument_requests():
                    self.fail("nested patch unexpectedly entered")

    def test_concurrent_requests_keep_separate_phase_stacks(self):
        fixture = semantic_fixtures.SemanticSearchTests(
            "test_semantic_scores_replace_literal_eligibility_only_on_the_explicit_api")
        fixture.setUp()
        try:
            def search(number):
                return fixture.runtime.call('search', semantic_fixtures.TOKEN, 'family-a', lambda: False,
                    {'query': f'private concurrent scene {number}', 'filters': {}})
            with profile.instrument_requests() as observer, ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(search, (1, 2)))
            self.assertEqual([result['total'] for result in results], [2, 2])
            snapshot = observer.snapshot()
            self.assertEqual(observer.request_count, 2)
            self.assertEqual([row['ordinal'] for row in snapshot['requests']], [1, 2])
            for row in snapshot['requests']:
                self.assertEqual(row['phases']['runtime_total']['calls'], 1)
                self.assertEqual(row['phases']['encoder_roundtrip']['calls'], 1)
                self.assertAlmostEqual(sum(phase['exclusive_ms'] for phase in row['phases'].values()),
                                       row['total_ms'], places=5)
        finally:
            fixture.doCleanups()


if __name__ == "__main__":
    unittest.main()
