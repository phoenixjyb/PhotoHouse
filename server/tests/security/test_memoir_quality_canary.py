"""Offline contract checks for the explicitly bounded memoir canary."""

from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "server" / "backend"))
sys.path.insert(0, str(ROOT / "server" / "scripts"))

import run_memoir_quality_canary as canary  # noqa: E402
from app.access import memory_narrative, model_deployment, private_storage  # noqa: E402


class MemoirQualityCanaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.root.chmod(0o700)
        self.network_guard = patch.object(
            memory_narrative.httpx, "Client",
            side_effect=AssertionError("unexpected Ollama client construction"))
        self.network_guard.start()

    def tearDown(self):
        self.network_guard.stop()
        self.temp.cleanup()

    def configuration(self, **updates):
        config = {
            "format_version": 1,
            "ollama_url": "http://127.0.0.1:11434",
            "ollama_model": "synthetic-fixture-model",
            "timeout_seconds": 12,
        }
        config.update(updates)
        path = self.root / "configuration.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        path.chmod(0o600)
        return path

    def case(self, case_id):
        return canary._case_plan(case_id)

    @staticmethod
    def narrative_output(bundle):
        return {
            "version": 1,
            "title": bundle["title"],
            "chapters": [{
                "id": chapter["id"],
                "narration": chapter["narration"],
                "source_ids": chapter["evidence_ids"],
            } for chapter in bundle["chapters"]],
            "questions": [],
            "needs_review": True,
        }

    class FakeNarrator:
        def __init__(self, url, model, *, timeout, calls, fail=None):
            calls.append({"url": url, "model": model, "timeout": timeout, "methods": []})
            self.entry = calls[-1]
            self.fail = fail

        def narrative(self, bundle):
            self.entry["methods"].append("narrative")
            if self.fail is not None:
                raise self.fail
            return MemoirQualityCanaryTests.narrative_output(bundle)

        def companion(self, bundle):
            self.entry["methods"].append("companion")
            if self.fail == "answer":
                return {"version": 1, "kind": "answer", "reply": "A valid answer.",
                        "source_ids": [], "questions": [], "proposal": None}
            if self.fail == "clarification":
                return {"version": 1, "kind": "clarification", "reply": "A useful clarification.",
                        "source_ids": [], "questions": ["Which approved source should I use?"],
                        "proposal": None}
            if self.fail is not None:
                raise self.fail
            return {
                "version": 1,
                "kind": "proposal",
                "reply": "A synthetic proposal is ready for review.",
                "source_ids": [source["id"] for source in bundle["sources"]],
                "questions": [],
                "proposal": MemoirQualityCanaryTests.narrative_output(bundle),
            }

    def run_fake(self, case_id, output, *, calls, fail=None):
        case, criteria = self.case(case_id)
        config = {"ollama_url": "http://127.0.0.1:11434",
                  "ollama_model": "synthetic-fixture-model", "timeout_seconds": 12.0}

        def factory(url, model, *, timeout):
            return self.FakeNarrator(url, model, timeout=timeout, calls=calls, fail=fail)

        report = canary._run_case(case, criteria, config, output, narrator_factory=factory)
        return report, case, criteria

    def test_default_plan_never_reads_private_configuration_or_constructs_adapter(self):
        output = []
        with patch.object(model_deployment, "_load_private_document",
                          side_effect=AssertionError("private config read")), \
             patch.object(memory_narrative, "LocalMemoryNarrator",
                          side_effect=AssertionError("adapter constructed")):
            code = canary.main([], stdout=type("Writer", (), {"write": output.append})())
        self.assertEqual(0, code)
        report = json.loads(output[0])
        self.assertEqual("plan_only", report["status"])
        self.assertFalse(report["quality_evaluated"])
        self.assertFalse(report["activation_performed"])
        self.assertFalse(report["resource_limits_verified"])
        self.assertEqual({"synthetic-coherence", "synthetic-conflict", "synthetic-provenance"},
                         {case["case_id"] for case in report["cases"]})

    def test_private_configuration_is_closed_bounded_loopback_only_and_redacted(self):
        path = self.configuration()
        loaded = canary._load_configuration(path)
        self.assertEqual("synthetic-fixture-model", loaded["ollama_model"])
        for changes in (
            {"extra": "secret-extra"},
            {"format_version": True},
            {"ollama_url": "https://provider.invalid"},
            {"timeout_seconds": 31},
            {"timeout_seconds": 10 ** 1000},
            {"timeout_seconds": True},
            {"ollama_model": " "},
        ):
            with self.subTest(changes=changes):
                path = self.configuration(**changes)
                with self.assertRaises(canary.CanaryError) as caught:
                    canary._load_configuration(path)
                self.assertIn(caught.exception.code, {"configuration_invalid", "configuration_unavailable"})

        secret = "private-model-marker "
        config_path = self.configuration(ollama_model=secret)
        stdout = []
        code = canary.main(["--run", "--case", "synthetic-coherence",
                            "--configuration", str(config_path),
                            "--output-directory", str(self.root / "attempt")],
                           stdout=type("Writer", (), {"write": stdout.append})())
        self.assertEqual(2, code)
        self.assertNotIn(secret, stdout[0])
        self.assertEqual("configuration_invalid", json.loads(stdout[0])["error_code"])

    def test_all_three_exact_cases_route_once_with_matching_hash_and_unreviewed_criteria(self):
        expected = {
            "synthetic-coherence": ("narrative", "4146b546ba71f011b9062017c5eb57e1addaefa6ed2a08e613df1b926532a5f3"),
            "synthetic-conflict": ("narrative", "ca79efa76960d1c7f4cbf1fdf997679032b656da45a266a3ca516b1ae6772767"),
            "synthetic-provenance": ("companion", "733dbf227527f1bac08f89b9a83fa02bd60885fc04f63599e6039ce47603ca88"),
        }
        for case_id, (task, input_hash) in expected.items():
            with self.subTest(case_id=case_id):
                calls = []
                output = self.root / (case_id + "-run")
                report, case, criteria = self.run_fake(case_id, output, calls=calls)
                self.assertEqual("captured_for_human_review", report["status"])
                self.assertEqual(task, case["task"])
                self.assertEqual(input_hash, report["input_sha256"])
                self.assertEqual([task], calls[0]["methods"])
                self.assertEqual(12.0, calls[0]["timeout"])
                self.assertEqual({"input-bundle.json", "output.json", "record.json"},
                                 {path.name for path in output.iterdir()})
                record = json.loads((output / "record.json").read_text(encoding="utf-8"))
                self.assertEqual(input_hash, record["input_sha256"])
                self.assertEqual(report["output_sha256"], record["output_sha256"])
                self.assertEqual("synthetic-fixture-model", record["provider_configuration"]["ollama_model"])
                self.assertEqual(canary._sha256(canary._canonical(record["provider_configuration"])),
                                 record["configuration_identity_sha256"])
                self.assertNotIn("ollama_model", report)
                self.assertEqual(input_hash, hashlib.sha256(
                    (output / "input-bundle.json").read_bytes()).hexdigest())
                self.assertEqual(report["output_sha256"], hashlib.sha256(
                    (output / "output.json").read_bytes()).hexdigest())
                self.assertEqual({name: "unreviewed" for name in criteria}, record["quality"])
                self.assertFalse(record["quality_evaluated"])
                self.assertFalse(record["activation_performed"])
                self.assertFalse(record["resource_limits_verified"])

    def test_case_task_or_pinned_hash_mismatch_refuses_before_execution(self):
        plan = canary.planner.build_plan()
        provenance = next(case for case in plan["cases"]
                          if case["case_id"] == "synthetic-provenance")
        provenance["task"] = "narrative"
        with patch.object(canary.planner, "build_plan", return_value=plan):
            with self.assertRaises(canary.CanaryError) as caught:
                canary._case_plan("synthetic-provenance")
        self.assertEqual("case_unavailable", caught.exception.code)

        plan = canary.planner.build_plan()
        coherence = next(case for case in plan["cases"]
                         if case["case_id"] == "synthetic-coherence")
        coherence["bundle_sha256"] = "0" * 64
        with patch.object(canary.planner, "build_plan", return_value=plan):
            with self.assertRaises(canary.CanaryError) as caught:
                canary._case_plan("synthetic-coherence")
        self.assertEqual("case_unavailable", caught.exception.code)

    def test_existing_output_is_refused_before_adapter_construction(self):
        output = self.root / "existing"
        output.mkdir(mode=0o700)
        output.chmod(0o700)
        calls = []
        case, criteria = self.case("synthetic-coherence")
        with self.assertRaises(canary.CanaryError) as caught:
            canary._run_case(case, criteria,
                {"ollama_url": "http://127.0.0.1:11434", "ollama_model": "fixture", "timeout_seconds": 5.0},
                output, narrator_factory=lambda *_args, **_kwargs: calls.append("constructed"))
        self.assertEqual("output_exists", caught.exception.code)
        self.assertEqual([], calls)

    def test_malformed_response_keeps_input_and_failure_record_without_output_capture(self):
        calls = []
        output = self.root / "malformed-run"
        report, case, _criteria = self.run_fake(
            "synthetic-conflict", output, calls=calls,
            fail=memory_narrative.LocalMemoryNarrativeError("invalid_response"))
        self.assertEqual("request_failed", report["status"])
        self.assertFalse((output / "output.json").exists())
        self.assertTrue((output / "input-bundle.json").is_file())
        record = json.loads((output / "record.json").read_text(encoding="utf-8"))
        self.assertEqual("request_failed", record["status"])
        self.assertIsNone(record["output_sha256"])
        self.assertEqual("invalid_response", record["failure_category"])
        self.assertEqual([case["task"]], calls[0]["methods"])

    def test_valid_companion_answer_and_clarification_are_captured(self):
        for kind in ("answer", "clarification"):
            with self.subTest(kind=kind):
                calls = []
                output = self.root / (kind + "-run")
                report, _case, criteria = self.run_fake(
                    "synthetic-provenance", output, calls=calls, fail=kind)
                self.assertEqual("captured_for_human_review", report["status"])
                self.assertEqual(["companion"], calls[0]["methods"])
                private_output = json.loads((output / "output.json").read_text(encoding="utf-8"))
                self.assertEqual(kind, private_output["kind"])
                record = json.loads((output / "record.json").read_text(encoding="utf-8"))
                self.assertEqual({criterion: "unreviewed" for criterion in criteria}, record["quality"])

    def test_provider_failure_text_is_discarded_and_public_output_has_no_proposal(self):
        calls = []
        secret = "provider-body-secret-marker"
        output = self.root / "failed-run"
        report, _case, _criteria = self.run_fake(
            "synthetic-provenance", output, calls=calls,
            fail=RuntimeError(secret))
        public = json.dumps(report)
        self.assertNotIn(secret, public)
        self.assertNotIn("proposal", public)
        self.assertEqual("provider_failure", report["error_code"])
        private_record = (output / "record.json").read_text(encoding="utf-8")
        self.assertNotIn(secret, private_record)
        self.assertFalse((output / "output.json").exists())

    def test_provider_error_category_is_whitelisted_before_private_recording(self):
        error = memory_narrative.LocalMemoryNarrativeError("provider")
        error.category = "private-category-marker"
        calls = []
        output = self.root / "category-run"
        report, _case, _criteria = self.run_fake(
            "synthetic-conflict", output, calls=calls, fail=error)
        self.assertEqual("provider_failure", report["error_code"])
        record = (output / "record.json").read_text(encoding="utf-8")
        self.assertNotIn("private-category-marker", record)

    def test_cli_makes_one_bounded_call_and_keeps_proposal_out_of_stdout(self):
        config_path = self.configuration(timeout_seconds=29)
        output_path = self.root / "cli-run"
        calls = []
        case, _criteria = self.case("synthetic-provenance")

        def factory(url, model, *, timeout):
            return self.FakeNarrator(url, model, timeout=timeout, calls=calls)

        stdout = []
        with patch.object(memory_narrative, "LocalMemoryNarrator", side_effect=factory):
            code = canary.main([
                "--run", "--case", "synthetic-provenance",
                "--configuration", str(config_path),
                "--output-directory", str(output_path),
            ], stdout=type("Writer", (), {"write": stdout.append})())
        self.assertEqual(0, code)
        report_text = stdout[0]
        report = json.loads(report_text)
        self.assertEqual("captured_for_human_review", report["status"])
        self.assertEqual(["companion"], calls[0]["methods"])
        self.assertEqual(29.0, calls[0]["timeout"])
        self.assertNotIn("proposal", report_text)
        self.assertNotIn("reply", report_text)
        self.assertNotIn("A synthetic proposal is ready for review.", report_text)
        private_output = json.loads((output_path / "output.json").read_text(encoding="utf-8"))
        self.assertEqual("proposal", private_output["kind"])
        if os.name == "nt":
            private_storage.require_private_directory(output_path)
            for name in ("input-bundle.json", "output.json", "record.json"):
                private_storage.require_private_file(output_path / name)
        else:
            self.assertEqual(0o700, output_path.stat().st_mode & 0o777)
            for name in ("input-bundle.json", "output.json", "record.json"):
                self.assertEqual(0o600, (output_path / name).stat().st_mode & 0o777)

    def test_cli_argument_errors_are_fixed_and_do_not_echo_values_to_stderr(self):
        import contextlib
        import io

        marker = "private-argument-marker"
        stdout, stderr = [], io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = canary.main(["--case", marker],
                               stdout=type("Writer", (), {"write": stdout.append})())
        self.assertEqual(2, code)
        self.assertEqual("arguments_invalid", json.loads(stdout[0])["error_code"])
        self.assertNotIn(marker, stdout[0])
        self.assertEqual("", stderr.getvalue())

    def test_default_plan_validates_all_pinned_cases_before_reporting(self):
        plan = canary.planner.build_plan()
        provenance = next(case for case in plan["cases"]
                          if case["case_id"] == "synthetic-provenance")
        provenance["task"] = "narrative"
        output = []
        with patch.object(canary.planner, "build_plan", return_value=plan):
            code = canary.main([], stdout=type("Writer", (), {"write": output.append})())
        self.assertEqual(2, code)
        report = json.loads(output[0])
        self.assertEqual("refused", report["status"])
        self.assertEqual("case_unavailable", report["error_code"])

    def test_output_persistence_failure_is_not_retried_or_reclassified(self):
        calls = []
        output = self.root / "record-write-failure"
        case, criteria = self.case("synthetic-conflict")
        config = {"ollama_url": "http://127.0.0.1:11434",
                  "ollama_model": "synthetic-fixture-model", "timeout_seconds": 12.0}
        original = canary._write_exclusive
        attempted = []

        def fail_record(directory, name, payload):
            attempted.append(name)
            if name == "record.json":
                raise canary.CanaryError("output_unavailable")
            original(directory, name, payload)

        def factory(url, model, *, timeout):
            return self.FakeNarrator(url, model, timeout=timeout, calls=calls)

        with patch.object(canary, "_write_exclusive", side_effect=fail_record):
            with self.assertRaises(canary.CanaryError) as caught:
                canary._run_case(case, criteria, config, output, narrator_factory=factory)
        self.assertEqual("output_unavailable", caught.exception.code)
        self.assertEqual(["input-bundle.json", "output.json", "record.json"], attempted)
        self.assertTrue((output / "output.json").is_file())
        self.assertFalse((output / "record.json").exists())
        self.assertEqual(["narrative"], calls[0]["methods"])

    def test_each_output_file_is_private_checked_while_empty_before_payload_write(self):
        calls = []
        output = self.root / "checked-files-run"
        case, criteria = self.case("synthetic-coherence")
        config = {"ollama_url": "http://127.0.0.1:11434",
                  "ollama_model": "synthetic-fixture-model", "timeout_seconds": 12.0}
        checked = []
        real_check = private_storage.require_private_file

        def check_empty_private_file(path):
            self.assertEqual(0, path.stat().st_size)
            checked.append(path.name)
            return real_check(path)

        def factory(url, model, *, timeout):
            return self.FakeNarrator(url, model, timeout=timeout, calls=calls)

        with patch.object(private_storage, "require_private_file", side_effect=check_empty_private_file):
            report = canary._run_case(case, criteria, config, output, narrator_factory=factory)
        self.assertEqual("captured_for_human_review", report["status"])
        self.assertEqual(["input-bundle.json", "output.json", "record.json"], checked)

    def test_configuration_requires_owner_private_file_outside_checkout(self):
        path = self.configuration()
        if os.name == "nt":
            with patch.object(private_storage, "_windows_acl", side_effect=ValueError("synthetic DACL refusal")):
                with self.assertRaises(canary.CanaryError) as caught:
                    canary._load_configuration(path)
        else:
            path.chmod(0o644)
            with self.assertRaises(canary.CanaryError) as caught:
                canary._load_configuration(path)
        self.assertEqual("configuration_unavailable", caught.exception.code)
        with self.assertRaises(canary.CanaryError) as caught:
            canary._load_configuration(ROOT / "models" / "quality-cases.json")
        self.assertEqual("configuration_unavailable", caught.exception.code)


if __name__ == "__main__":
    unittest.main()
