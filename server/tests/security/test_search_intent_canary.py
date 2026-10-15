"""Offline contract tests for the synthetic intent qualification runner."""
from contextlib import redirect_stdout
from datetime import date, datetime
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

from app.access import discovery as d
from app.access.assistant_query_plan import _MEDIA
from app.access.search_intent import IntentUnavailable, _INTENT_OPEN, plan_query
from app.access.search_intent_view import scene_view
import qualify_search_intent as qualify
from search_intent_cases import CASES, NOW, cases_by_cohort, cases_digest


NOW_VALUE = datetime(2032, 9, 14, 16, 0)


_SURFACES = {
    "en_snow_redcoat_hard_filters": (
        ("wearing a red coat", ["red coat", "red winter coat", "红色外套"]),
        ("in snow", ["snow", "雪"])),
    "en_birthday_cutting_adult_year_video": (
        ("cutting", ["cutting", "slicing", "切"]),
        ("birthday cake", ["birthday cake", "生日蛋糕"])),
    "en_rain_umbrella_and": (
        ("umbrellas", ["umbrella", "umbrellas", "雨伞"]),
        ("rainy street celebration", ["rainy street celebration",
                                       "street celebration in the rain",
                                       "雨中的街头庆祝"])),
    "zh_snow_redcoat_hard_filters": (
        ("雪地", ["雪地", "snow"]),
        ("穿红色外套", ["红色外套", "red coat"])),
    "zh_birthday_cutting_adult_year_video": (
        ("切", ["切", "cutting"]), ("生日蛋糕", ["生日蛋糕", "birthday cake"])),
    "zh_rain_umbrella_and": (
        ("雨天街道", ["雨天街道", "rainy street"]),
        ("雨伞", ["雨伞", "umbrella"])),
    "mixed_snow_redcoat_ascii_name_hard_filters": (
        ("雪地", ["雪地", "snow"]), ("穿红色外套", ["红色外套", "red coat"])),
    "mixed_birthday_cutting_adult_year_video": (
        ("切", ["切", "cutting"]), ("生日蛋糕", ["生日蛋糕", "birthday cake"])),
    "mixed_dog_running_park_literal": (
        ("dog running", ["dog running", "running dog", "跑动的狗"]),
        ("beside the old park bench", ["park bench", "公园长椅"])),
}


def proposal_for(case):
    if case["expected_status"] == "clarification":
        return {"version": 1, "status": "clarification", "concepts": [],
                "question": case["expected_question"]}
    spans = []
    for surface, alternatives in _SURFACES[case["id"]]:
        start = case["query"].find(surface)
        if start < 0 or case["query"].find(surface, start + 1) >= 0:
            raise AssertionError(f"fixture surface missing or repeated for {case['id']}")
        spans.append({"start": start, "end": start + len(surface),
                      "alternatives": alternatives})
    return {"version": 1, "status": "ready", "concepts": spans, "question": None}


def provider_view(case):
    query = case["query"]
    grammar_query = _INTENT_OPEN.sub(lambda match: " " * len(match.group(0)), query)
    return scene_view(grammar_query, date.fromisoformat(NOW), case["entities"]["labels"])


class FakePlanner:
    def __init__(self, *, failed_case=None):
        self.calls = []
        self.failed_case = failed_case
        self.by_query = {
            provider_view(case): case
            for case in CASES
        }

    def propose(self, query, today, has_previous_search):
        self.calls.append((query, today, has_previous_search))
        case = self.by_query[query]
        if case["id"] == self.failed_case:
            raise IntentUnavailable()
        return proposal_for(case)


class SearchIntentQualificationTests(unittest.TestCase):
    def test_plan_only_reports_twelve_ids_three_cohorts_and_no_provider_use(self):
        summary = qualify.plan_summary()
        self.assertEqual("plan_only", summary["status"])
        self.assertEqual(12, summary["case_count"])
        self.assertEqual({"en": 4, "zh": 4, "mixed": 4}, summary["cohort_counts"])
        self.assertEqual(cases_digest(), summary["cases_sha256"])
        self.assertEqual(0, summary["provider_calls"])
        self.assertFalse(summary["synthetic_expectations_evaluated"])
        self.assertFalse(summary["quality_evaluated"])
        self.assertNotIn("query", json.dumps(summary))

        output = io.StringIO()
        with mock.patch.object(qualify, "LocalIntentPlanner",
                               side_effect=AssertionError("plan mode created a provider")):
            with redirect_stdout(output):
                self.assertEqual(0, qualify.main([]))
        self.assertEqual("plan_only", json.loads(output.getvalue())["status"])

    def test_literal_hard_date_path_does_not_invoke_provider(self):
        class CountingPlanner:
            def __init__(self):
                self.calls = []

            def propose(self, *args):
                self.calls.append(args)
                raise AssertionError("literal hard filters must bypass intent planning")

        planner = CountingPlanner()
        resolved = {**CASES[0]["entities"],
                    "groups": {"people": [], "tags": [], "locations": []},
                    "labels": []}
        result = plan_query("Find photos on September 14, 2032", now=NOW_VALUE,
                            entities=resolved, previous_filters=None, planner=planner)
        self.assertEqual("ready", result.status)
        self.assertEqual({"media": ["image"],
                          "date": {"from": "2032-09-14", "to": "2032-09-14"}},
                         result.filters)
        self.assertEqual([], planner.calls)

    def test_cases_are_fixed_date_fictional_reviewed_entities_and_expected_hard_filters(self):
        self.assertEqual(NOW, "2032-09-14")
        self.assertEqual({"en": 4, "zh": 4, "mixed": 4},
                         {name: len(group) for name, group in cases_by_cohort().items()})
        self.assertEqual(12, len(CASES))
        for case in CASES:
            with self.subTest(case=case["id"]):
                self.assertEqual(case["cohort"], case["id"].split("_", 1)[0]
                                 if case["cohort"] in {"en", "zh"} else "mixed")
                self.assertIn(case["expected_status"], {"ready", "clarification"})
                self.assertEqual(set(case["entities"]["groups"]), {"people", "tags", "locations"})
                self.assertTrue(all(ident in {"301", "302"}
                                    for ident in case["entities"]["groups"]["people"]))
                self.assertNotIn("database", case)
                self.assertNotIn("captions", case)

    def test_real_planner_skips_date_clarifications_and_validates_masked_views(self):
        planner = FakePlanner()
        report = qualify.run_qualification(planner, now=NOW_VALUE, clock=lambda: 100.0)
        self.assertEqual(9, len(planner.calls))
        self.assertTrue(all(today == NOW and previous is False
                            for _query, today, previous in planner.calls))
        self.assertEqual(9, report["provider_call_count"])
        self.assertEqual(9, report["provider_attempt_count"])
        self.assertEqual(9, report["provider_response_count"])
        self.assertEqual(3, report["provider_not_needed_count"])
        self.assertEqual(0, report["retry_count"])
        self.assertEqual(0, report["warmup_call_count"])
        self.assertEqual(2, report["policy_version"])
        self.assertFalse(report["quality_evaluated"])
        self.assertTrue(report["synthetic_expectations_evaluated"])
        self.assertFalse(report["family_quality_evaluated"])
        self.assertFalse(report["activation_performed"])
        self.assertEqual(3, sum(row["provider_outcome"] == "not_needed" for row in report["cases"]))
        self.assertTrue(all(row["provider_invoked_at_most_once"] for row in report["cases"]))
        self.assertTrue(all(row["expectations_met"] for row in report["cases"]))
        self.assertTrue(all(row["actual_plan_status"] == row["expected_status"]
                            for row in report["cases"]))
        self.assertTrue(all(row["hard_filters_preserved"] for row in report["cases"]))
        self.assertTrue(all(row["plan_query_invocations"] == 1 for row in report["cases"]))
        for case, row in zip(CASES, report["cases"]):
            if case["expected_question"] == "date":
                self.assertEqual("not_needed", row["provider_outcome"])
                self.assertIsNone(row["actual_proposal"])
                self.assertIsNone(row["provider_query_view"])
            else:
                expected_view = provider_view(case)
                self.assertEqual(row["provider_query_view"], expected_view)
                self.assertEqual(len(row["provider_query_view"]), len(case["query"]))
                self.assertTrue(all(label not in row["provider_query_view"]
                                    for label in case["entities"]["labels"]))
                self.assertFalse(any(pattern.search(row["provider_query_view"])
                                     for _kind, pattern in _MEDIA))
                folded_view = d.fold(row["provider_query_view"])
                self.assertNotIn("2032-09-14", folded_view)
                self.assertNotIn("2032年9月14日", folded_view)
                self.assertNotIn("school concert", folded_view)
                self.assertEqual(row['actual_proposal'], proposal_for(case))
        self.assertEqual({"en": "expectations_met", "zh": "expectations_met",
                          "mixed": "expectations_met"},
                         {name: cohort["status"] for name, cohort in report["cohorts"].items()})

        by_id = {row["case_id"]: row for row in report["cases"]}
        self.assertEqual({"from": "2032-09-14", "to": "2032-09-14"},
                         by_id["en_snow_redcoat_hard_filters"]["actual_hard_filters"]["date"])
        self.assertEqual(["image"], by_id["en_snow_redcoat_hard_filters"]["actual_hard_filters"]["media"])
        self.assertEqual("school concert", by_id["mixed_dog_running_park_literal"]
                         ["actual_hard_filters"]["text"])
        self.assertTrue(all(len(row["evidence_checks"]) == 4
                            for row in report["cases"] if row["expected_status"] == "ready"))

    def test_proposal_targeting_masked_reviewed_label_is_invalid_and_redacted(self):
        case = CASES[0]
        start = case['query'].index('Sample Child')
        refused = {'version': 1, 'status': 'ready', 'question': None,
                   'concepts': [{'start': start, 'end': start + len('Sample Child'),
                                 'alternatives': ['Sample Child']}]}
        class ProtectedSpanPlanner(FakePlanner):
            def propose(self, query, today, has_previous_search):
                value = super().propose(query, today, has_previous_search)
                masked = provider_view(case)
                return refused if query == masked else value
        planner = ProtectedSpanPlanner()
        report = qualify.run_qualification(planner, now=NOW_VALUE)
        first = report['cases'][0]
        self.assertIsNone(first['actual_proposal'])
        self.assertEqual((first['actual_plan_status'], first['plan_reason']),
                         ('clarification', 'invalid_intent'))
        self.assertFalse(first['expectations_met'])
        self.assertEqual(len(planner.calls), 9)
        self.assertEqual(first['plan_query_invocations'], 1)
        self.assertNotIn('Sample Child', json.dumps(report))

    def test_invalid_provider_extensions_do_not_enter_proposal_diagnostics(self):
        class InvalidExtensionPlanner(FakePlanner):
            def propose(self, query, today, has_previous_search):
                result = super().propose(query, today, has_previous_search)
                return {**result, 'debug': {'private-marker-not-for-report': object()}}
        report = qualify.run_qualification(InvalidExtensionPlanner(), now=NOW_VALUE)
        self.assertTrue(all(row['actual_proposal'] is None for row in report['cases']))
        self.assertNotIn('private-marker-not-for-report', json.dumps(report, allow_nan=False))

    def test_failed_provider_call_marks_its_cohort_without_hiding_it_in_aggregate(self):
        planner = FakePlanner(failed_case="zh_rain_umbrella_and")
        report = qualify.run_qualification(planner, now=NOW_VALUE, clock=lambda: 100.0)
        self.assertEqual(9, report["provider_call_count"])
        self.assertEqual(1, report["timeouts_or_refusals"])
        self.assertEqual(1, report["provider_refusal_count"])
        self.assertEqual("expectations_missed", report["cohorts"]["zh"]["status"])
        self.assertEqual("expectations_met", report["cohorts"]["en"]["status"])
        self.assertEqual("expectations_met", report["cohorts"]["mixed"]["status"])
        failed = next(row for row in report["cases"] if row["case_id"] == "zh_rain_umbrella_and")
        self.assertEqual("intent_unavailable", failed["provider_outcome"])
        self.assertIsNone(failed['actual_proposal'])
        self.assertFalse(failed["expectations_met"])
        self.assertFalse(report["quality_evaluated"])

    def test_private_output_requires_new_absolute_file_outside_repository(self):
        with self.assertRaisesRegex(ValueError, "qualification_operation_refused"):
            qualify._private_output_target("relative-report.json")
        with self.assertRaisesRegex(ValueError, "qualification_operation_refused"):
            qualify._private_output_target(str(ROOT / "report.private.json"))
        with tempfile.TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory).resolve()
            target = directory / "report.private.json"
            self.assertEqual(target, qualify._private_output_target(str(target)))
            target.write_text("existing", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "qualification_operation_refused"):
                qualify._private_output_target(str(target))

    def test_no_partial_results_are_written_when_compiler_unexpectedly_fails(self):
        class ExplodingPlanner:
            def propose(self, *_):
                raise RuntimeError("do not expose this")

        # A transport exception is normalized as an adapter error; the complete
        # cohort is still represented and can never be reported as met.
        report = qualify.run_qualification(ExplodingPlanner(), now=NOW_VALUE,
                                           clock=lambda: 100.0)
        self.assertEqual(12, report["attempted_case_count"])
        self.assertEqual(9, report["adapter_errors"])
        self.assertEqual(3, report["provider_not_needed_count"])
        self.assertTrue(all(not row["expectations_met"] for row in report["cases"]
                            if row["provider_outcome"] == "adapter_error"))
        self.assertTrue(all(row["expectations_met"] for row in report["cases"]
                            if row["provider_outcome"] == "not_needed"))
        self.assertTrue(all(cohort["status"] == "expectations_missed"
                            for cohort in report["cohorts"].values()))
        self.assertNotIn("do not expose this", json.dumps(report))


if __name__ == "__main__":
    unittest.main()
