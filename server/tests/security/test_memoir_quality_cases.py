"""Offline fixtures for planning later synthetic memoir quality review."""

from __future__ import annotations

import json
import io
import socket
import sqlite3
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT_ROOT = Path(__file__).resolve().parents[2] / "scripts"
BACKEND_ROOT = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.access.memory_narrative import (  # noqa: E402
    MAX_BUNDLE_BYTES,
    MAX_CHAPTERS,
    MAX_RECENT_TURNS,
    MAX_SOURCES,
    _validate_bundle,
    validate_companion,
)
from app.access.story_titles import validate_bundle as validate_title_bundle  # noqa: E402

import httpx  # noqa: E402

if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import plan_memoir_quality_cases as planner  # noqa: E402


class MemoirQualityCasePlanTests(unittest.TestCase):
    def test_original_case_ids_tasks_and_bundle_hashes_remain_pinned(self):
        cases = {case["case_id"]: case for case in planner.build_plan()["cases"]}
        self.assertEqual({
            "synthetic-coherence": ("narrative", "4146b546ba71f011b9062017c5eb57e1addaefa6ed2a08e613df1b926532a5f3"),
            "synthetic-conflict": ("narrative", "ca79efa76960d1c7f4cbf1fdf997679032b656da45a266a3ca516b1ae6772767"),
            "synthetic-provenance": ("companion", "733dbf227527f1bac08f89b9a83fa02bd60885fc04f63599e6039ce47603ca88"),
        }, {case_id: (cases[case_id]["task"], cases[case_id]["bundle_sha256"])
            for case_id in ("synthetic-coherence", "synthetic-conflict", "synthetic-provenance")})

    def test_cases_pass_real_bundle_validator_and_stay_within_all_bounds(self):
        plan = planner.build_plan()
        self.assertEqual("offline_plan_only", plan["status"])
        self.assertTrue(plan["synthetic_data_only"])
        self.assertFalse(plan["model_executed"])
        self.assertEqual(0, plan["external_requests_made"])
        self.assertEqual(0, plan["database_writes"])
        self.assertEqual(6, len(plan["cases"]))
        self.assertEqual(6, len({case["case_id"] for case in plan["cases"]}))

        all_ids = set()
        for case in plan["cases"]:
            bundle = case["bundle"]
            if case["task"] == "suggest":
                self.assertEqual(bundle, validate_title_bundle(bundle))
                self.assertNotIn("chapters", bundle)
                self.assertEqual("everyday", bundle["theme"])
            else:
                self.assertEqual("book", bundle["target"]["type"])
                self.assertEqual(bundle, _validate_bundle(bundle))
                self.assertLessEqual(len(bundle["chapters"]), MAX_CHAPTERS)
                self.assertLessEqual(len(bundle["sources"]), MAX_SOURCES)
                self.assertLessEqual(len(bundle["recent_turns"]), MAX_RECENT_TURNS)
            encoded = planner._canonical_json(bundle)
            self.assertLessEqual(len(encoded), MAX_BUNDLE_BYTES)
            self.assertEqual(planner.hashlib.sha256(encoded).hexdigest(), case["bundle_sha256"])

            if case["task"] == "suggest":
                id_list = [source["id"] for source in bundle["sources"]]
            else:
                source_ids = {source["id"] for source in bundle["sources"]}
                source_assets = {source["asset_id"] for source in bundle["sources"]
                                 if source["asset_id"] is not None}
                referenced_assets = set()
                for chapter in bundle["chapters"]:
                    self.assertTrue(set(chapter["evidence_ids"]) <= source_ids)
                    referenced_assets.update(chapter["asset_ids"])
                self.assertEqual(source_assets, referenced_assets)
                id_list = planner._bundle_id_list(bundle)
            ids = set(id_list)
            self.assertEqual(len(id_list), len(ids))
            self.assertFalse(all_ids & ids)
            all_ids.update(ids)
            self.assertTrue(set(case["withheld_source_ids"]).isdisjoint(ids))

        focus = {case["focus"] for case in plan["cases"]}
        self.assertIn("ordered_multichapter_coherence_and_exact_citations", focus)
        self.assertIn("conflicting_multi_author_memories_and_uncertain_date", focus)
        self.assertIn("recent_multiturn_clarification_and_source_provenance", focus)

    def test_title_cases_use_distinct_validated_inputs_and_title_specific_review_criteria(self):
        cases = {case["case_id"]: case for case in planner.build_plan()["cases"]
                 if case["task"] == "suggest"}
        self.assertEqual({"synthetic-title-family", "synthetic-title-uncertainty",
                          "synthetic-title-abstention"}, set(cases))
        family = cases["synthetic-title-family"]
        self.assertEqual("zh", family["bundle"]["language"])
        self.assertEqual({"family", "draft"}, {source["source"] for source in family["bundle"]["sources"]})
        uncertainty = cases["synthetic-title-uncertainty"]
        self.assertEqual("en", uncertainty["bundle"]["language"])
        self.assertEqual({"family", "ai", "draft"}, {source["source"] for source in uncertainty["bundle"]["sources"]})
        self.assertIn("not state", uncertainty["human_review_expectations"]["uncertainty"])
        abstention = cases["synthetic-title-abstention"]
        self.assertEqual([], abstention["bundle"]["sources"])
        self.assertIn("zero title suggestions", abstention["human_review_expectations"]["abstention"])
        for case in cases.values():
            self.assertEqual(case["bundle"], validate_title_bundle(case["bundle"]))
            self.assertEqual("suggest", case["task"])

    def test_chinese_coherence_fixture_has_language_consistent_input_and_review_text(self):
        case = next(item for item in planner.build_plan()["cases"]
                    if item["focus"] == "ordered_multichapter_coherence_and_exact_citations")
        bundle = case["bundle"]
        self.assertEqual("zh", bundle["language"])
        chinese_text = [bundle["title"], bundle["theme"], bundle["instructions"]]
        chinese_text.extend(chapter[field] for chapter in bundle["chapters"]
                            for field in ("title", "narration"))
        chinese_text.extend(source["text"] for source in bundle["sources"])
        chinese_text.extend(source["author"] for source in bundle["sources"])
        self.assertTrue(all(any("一" <= char <= "鿿" for char in text)
                            for text in chinese_text))
        self.assertTrue(all(any("一" <= char <= "鿿" for char in text)
                            for text in case["human_review_expectations"].values()))

    def test_conflicting_authors_and_uncertain_event_date_are_explicit(self):
        case = next(item for item in planner.build_plan()["cases"]
                    if item["focus"] == "conflicting_multi_author_memories_and_uncertain_date")
        sources = {source["id"]: source for source in case["bundle"]["sources"]}
        accounts = [source for source in sources.values() if source["kind"] == "family"]
        self.assertEqual({"Synthetic family member A", "Synthetic family member B"},
                         {source["author"] for source in accounts})
        self.assertTrue(any("2018" in source["text"] for source in accounts))
        self.assertTrue(any("2019" in source["text"] for source in accounts))
        self.assertIn("uncertain", case["human_review_expectations"]["chronology"])
        self.assertIn("not an event date", sources["synthetic-conflict-date-metadata"]["text"])
        self.assertEqual({"synthetic-conflict-shared-picnic-photo"},
                         {source["asset_id"] for source in accounts})
        self.assertTrue(all(source["id"] in case["bundle"]["chapters"][0]["evidence_ids"]
                            for source in accounts))
        self.assertEqual(["synthetic-conflict-shared-picnic-photo"],
                         case["bundle"]["chapters"][0]["asset_ids"])

    def test_withheld_source_is_absent_and_unknown_citations_fail_real_companion_validator(self):
        case = next(item for item in planner.build_plan()["cases"]
                    if item["focus"] == "recent_multiturn_clarification_and_source_provenance")
        bundle = case["bundle"]
        withheld = case["withheld_source_ids"]
        self.assertEqual(1, len(withheld))
        bundle_bytes = planner._canonical_json(bundle)
        for source_id in withheld:
            self.assertNotIn(source_id.encode("ascii"), bundle_bytes)
        self.assertEqual(3, len(bundle["recent_turns"]))
        allowed = {source["id"] for source in bundle["sources"]}
        self.assertNotIn(withheld[0], allowed)

        authorized_result = {
            "version": 1,
            "kind": "answer",
            "reply": "The approved note confirms a greenhouse visit, but it does not give a year.",
            "source_ids": ["synthetic-provenance-approved-note"],
            "questions": ["Can you share an approved source that dates the visit?"],
            "proposal": None,
        }
        self.assertTrue(set(authorized_result["source_ids"]) <= allowed)
        self.assertEqual(authorized_result, validate_companion(authorized_result, bundle))

        synthetic_untrusted_result = {
            "version": 1,
            "kind": "answer",
            "reply": "The withheld source says more.",
            "source_ids": [withheld[0]],
            "questions": [],
            "proposal": None,
        }
        with self.assertRaisesRegex(ValueError, "unknown source"):
            validate_companion(synthetic_untrusted_result, bundle)

    def test_plan_json_is_deterministic_bounded_and_contains_no_quality_result(self):
        first = planner.build_plan()
        second = planner.build_plan()
        first_json = planner._canonical_json(first)
        second_json = planner._canonical_json(second)
        self.assertEqual(first_json, second_json)
        self.assertLessEqual(len(first_json), planner.MAX_PLAN_BYTES)
        self.assertNotIn(b'"score"', first_json)
        self.assertNotIn(b'"model_pass"', first_json)
        self.assertNotIn(b'"result"', first_json)

    def test_calls_return_fresh_deep_copies(self):
        first = planner.build_plan()
        pristine_json = planner._canonical_json(first)
        second = planner.build_plan()
        self.assertIsNot(first["cases"][0], second["cases"][0])
        self.assertIsNot(first["cases"][0]["bundle"], second["cases"][0]["bundle"])
        self.assertIsNot(first["cases"][0]["bundle"]["chapters"],
                         second["cases"][0]["bundle"]["chapters"])
        first["cases"][0]["bundle"]["chapters"][0]["title"] = "mutated fixture"
        first["cases"][0]["human_review_expectations"]["grounding"] = "mutated review text"
        self.assertEqual(pristine_json, planner._canonical_json(second))
        self.assertEqual(pristine_json, planner._canonical_json(planner.build_plan()))

    def test_default_cli_emits_only_offline_plan_without_external_calls(self):
        output = io.StringIO()

        def forbidden(*_args, **_kwargs):
            raise AssertionError("offline fixture planning attempted an external operation")

        with (
            patch.object(socket, "create_connection", forbidden),
            patch.object(socket, "socket", forbidden),
            patch.object(httpx, "Client", forbidden),
            patch.object(httpx, "AsyncClient", forbidden),
            patch.object(subprocess, "run", forbidden),
            patch.object(subprocess, "Popen", forbidden),
            patch.object(sqlite3, "connect", forbidden),
        ):
            self.assertEqual(0, planner.main([], stdout=output))

        emitted = output.getvalue()
        parsed = json.loads(emitted)
        self.assertEqual(planner._canonical_json(parsed).decode("utf-8") + "\n", emitted)
        self.assertEqual("offline_plan_only", parsed["status"])
        self.assertFalse(parsed["model_executed"])


if __name__ == "__main__":
    unittest.main()
