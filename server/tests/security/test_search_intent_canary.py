"""Offline contract tests for the synthetic intent qualification runner."""
from contextlib import redirect_stdout
from datetime import datetime
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

from app.access.search_intent import IntentUnavailable
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


class FakePlanner:
    def __init__(self, *, failed_case=None):
        self.calls = []
        self.failed_case = failed_case
        self.by_query = {case["query"]: case for case in CASES}

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

    def test_one_proposal_per_case_compiles_hard_filters_and_checks_and_matches(self):
        planner = FakePlanner()
        report = qualify.run_qualification(planner, now=NOW_VALUE, clock=lambda: 100.0)
        self.assertEqual(12, len(planner.calls))
        self.assertTrue(all(today == NOW and previous is False
                            for _query, today, previous in planner.calls))
        self.assertEqual(12, report["provider_call_count"])
        self.assertEqual(12, report["provider_response_count"])
        self.assertEqual(0, report["retry_count"])
        self.assertEqual(0, report["warmup_call_count"])
        self.assertFalse(report["quality_evaluated"])
        self.assertTrue(report["synthetic_expectations_evaluated"])
        self.assertFalse(report["family_quality_evaluated"])
        self.assertFalse(report["activation_performed"])
        self.assertTrue(all(row["provider_call_count"] == 1 for row in report["cases"]))
        self.assertTrue(all(row["expectations_met"] for row in report["cases"]))
        self.assertTrue(all(row["actual_plan_status"] == row["expected_status"]
                            for row in report["cases"]))
        self.assertTrue(all(row["hard_filters_preserved"] for row in report["cases"]))
        self.assertTrue(all(row["compiler_replay_calls"] == 1 for row in report["cases"]))
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

    def test_failed_provider_call_marks_its_cohort_without_hiding_it_in_aggregate(self):
        planner = FakePlanner(failed_case="zh_rain_umbrella_and")
        report = qualify.run_qualification(planner, now=NOW_VALUE, clock=lambda: 100.0)
        self.assertEqual(12, report["provider_call_count"])
        self.assertEqual(1, report["timeouts_or_refusals"])
        self.assertEqual("expectations_missed", report["cohorts"]["zh"]["status"])
        self.assertEqual("expectations_met", report["cohorts"]["en"]["status"])
        self.assertEqual("expectations_met", report["cohorts"]["mixed"]["status"])
        failed = next(row for row in report["cases"] if row["case_id"] == "zh_rain_umbrella_and")
        self.assertEqual("intent_unavailable", failed["provider_outcome"])
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
        self.assertEqual(12, report["adapter_errors"])
        self.assertTrue(all(not row["expectations_met"] for row in report["cases"]))
        self.assertTrue(all(cohort["status"] == "expectations_missed"
                            for cohort in report["cohorts"].values()))
        self.assertNotIn("do not expose this", json.dumps(report))


if __name__ == "__main__":
    unittest.main()
