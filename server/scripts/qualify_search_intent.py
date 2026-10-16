"""Plan or measure a bounded local descriptive-intent trial on synthetic data.

No arguments only emits the original static twelve-case plan. A separate
reviewed-v1 regression suite is available with --suite. Execution requires an
explicit loopback URL, model name, and new private output file. Each case goes
through the real deterministic compiler; it may make zero or one provider call.
The executable path has no warm-up or retry.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime
import json
import os
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "server" / "backend"))

from app.access.private_storage import require_private_directory, require_private_file, sync_directory
from app.access.search_description import match_description
from app.access.search_intent import IntentUnavailable, plan_query, validate_proposal
from app.access.search_intent_local import LocalIntentPlanner
from app.access.search_text import normalize_sources
from search_intent_cases import CASES, NOW, cases_by_cohort, cases_digest

QUALIFICATION_POLICY_VERSION = 2
DIAGNOSTICS_SCHEMA_VERSION = 1
_DIAGNOSTIC_CODE = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")


class _CountingPlanner:
    """Capture the real compiler's single adapter attempt without retrying."""
    def __init__(self, planner, *, clock):
        self.planner = planner
        self.clock = clock
        self.calls = 0
        self.query_views = []
        self.response = None
        self.outcome = "not_needed"
        self.error = None
        self.elapsed_ms = 0

    def propose(self, query, today, has_previous_search):
        if self.calls >= 1:
            raise RuntimeError("qualification_retry_refused")
        self.calls += 1
        self.query_views.append(query)
        start = self.clock()
        try:
            self.response = self.planner.propose(query, today, has_previous_search)
            self.outcome = "response"
            return self.response
        except IntentUnavailable:
            self.outcome = "intent_unavailable"
            self.error = "intent_unavailable"
            raise
        except Exception:
            # Normalize opaque adapter failures into the planner's bounded
            # unavailable path, while retaining only a fixed report code.
            self.outcome = "adapter_error"
            self.error = "adapter_error"
            raise IntentUnavailable() from None
        finally:
            self.elapsed_ms = max(0, int((self.clock() - start) * 1000))


def audit_reviewed_cases(cases) -> dict:
    """Check annotation completeness, never infer semantic truth from labels.

    Exact support quotations make independent review possible. This structural
    check cannot prove that a quotation entails a requested condition. None of
    these annotations enters the planner or changes evidence matching.
    """
    if (len(cases) != 12 or any(
            sum(c["cohort"] == cohort and c["expected_status"] == status for c in cases) != count
            for cohort in ("en", "zh", "mixed")
            for status, count in (("ready", 3), ("clarification", 1)))):
        raise ValueError("reviewed_fixture_invalid")
    counts = {"positive_assets": 0, "negative_assets": 0, "conditions": 0}
    case_ids, asset_ids = set(), set()
    for case in cases:
        if case["id"] in case_ids:
            raise ValueError("reviewed_fixture_invalid")
        case_ids.add(case["id"])
        conditions = case.get("conditions")
        if type(conditions) is not dict:
            raise ValueError("reviewed_fixture_invalid")
        if case["expected_status"] == "clarification":
            if (conditions or case["evidence"] or case["expected_question"] != "date" or
                    case["expected_hard_filters"]):
                raise ValueError("reviewed_fixture_invalid")
            continue
        if (case["expected_question"] is not None or not 3 <= len(conditions) <= 4 or
                len(case["evidence"]) != 2 + len(conditions) or
                any(not key or type(value) is not str or not value.strip()
                    for key, value in conditions.items())):
            raise ValueError("reviewed_fixture_invalid")
        counts["conditions"] += len(conditions)
        positives, isolated_missing = 0, set()
        for asset in case["evidence"]:
            if asset["asset_id"] in asset_ids:
                raise ValueError("reviewed_fixture_invalid")
            asset_ids.add(asset["asset_id"])
            sources = {s["source_id"]: s["content"] for s in asset["sources"]}
            support, missing = asset.get("support_quotes"), asset.get("missing_conditions")
            if (len(sources) != len(asset["sources"]) or type(support) is not dict or
                    type(missing) is not list or len(set(missing)) != len(missing) or
                    set(support) & set(missing) or
                    set(support) | set(missing) != set(conditions) or
                    type(asset["expected_match"]) is not bool or
                    asset["expected_match"] != (not missing)):
                raise ValueError("reviewed_fixture_invalid")
            for quote in support.values():
                if (type(quote) is not dict or set(quote) != {"source_id", "quote"} or
                        type(quote["quote"]) is not str or not quote["quote"].strip() or
                        quote["source_id"] not in sources or
                        quote["quote"] not in sources[quote["source_id"]]):
                    raise ValueError("reviewed_fixture_invalid")
            if asset["expected_match"]:
                positives += 1
                counts["positive_assets"] += 1
            else:
                if len(missing) != 1:
                    raise ValueError("reviewed_fixture_invalid")
                counts["negative_assets"] += 1
                isolated_missing.add(missing[0])
        if positives != 2 or isolated_missing != set(conditions):
            raise ValueError("reviewed_fixture_invalid")
    return {"annotation_structure_verified": True, "semantic_truth_verified": False,
            "annotations_sent_to_provider": False, **counts}


def _select_cases(suite):
    if suite == "fixed-v1":
        return CASES, cases_by_cohort(), cases_digest(), None
    if suite == "reviewed-v1":
        import search_intent_review_cases as reviewed
        if reviewed.NOW != NOW:
            raise ValueError("reviewed_fixture_invalid")
        audit = audit_reviewed_cases(reviewed.CASES)
        return reviewed.CASES, reviewed.cases_by_cohort(), reviewed.cases_digest(), audit
    raise ValueError("qualification_suite_invalid")


def plan_summary(*, suite="fixed-v1") -> dict:
    cases, cohorts, digest, audit = _select_cases(suite)
    return {
        "status": "plan_only",
        "case_ids": [case["id"] for case in cases],
        "cohorts": {name: [case["id"] for case in group]
                    for name, group in cohorts.items()},
        "case_count": len(cases),
        "cohort_counts": {name: len(group) for name, group in cohorts.items()},
        "cases_sha256": digest,
        **({"suite": suite, "fixture_audit": audit} if audit is not None else {}),
        "provider_calls": 0,
        "synthetic_expectations_evaluated": False,
        "quality_evaluated": False,
        "family_data_used": False,
        "activation_performed": False,
    }


def _hard_filters(filters):
    return {key: value for key, value in filters.items() if key != "descriptive"}


def _evaluate_evidence(case: dict, description: dict) -> tuple[list[dict], bool]:
    checks = []
    all_expected = True
    for asset in case["evidence"]:
        normalized = normalize_sources(asset["sources"], lambda: None)
        matched, _reasons, _quality = match_description(normalized, description)
        expected = asset["expected_match"]
        checks.append({
            "fixture_id": asset["asset_id"],
            "expected_match": expected,
            "actual_match": matched,
            "expectation_met": matched is expected,
        })
        all_expected = all_expected and matched is expected
    return checks, all_expected


def _evidence_diagnostics(case: dict, checks: list[dict], evaluated: bool) -> dict:
    if case["expected_status"] != "ready":
        state = "not_applicable"
    elif evaluated:
        state = "evaluated"
    else:
        state = "skipped_expected_ready"

    positives = [asset["asset_id"] for asset in case["evidence"]
                 if asset["expected_match"] is True]
    negatives = [asset["asset_id"] for asset in case["evidence"]
                 if asset["expected_match"] is False]
    by_id = {check["fixture_id"]: check for check in checks}
    return {
        "state": state,
        "positive_hits": sum(
            by_id.get(ident, {}).get("actual_match") is True for ident in positives),
        "positive_total": len(positives),
        "negative_false_positives": sum(
            by_id.get(ident, {}).get("actual_match") is True for ident in negatives),
        "negative_total": len(negatives),
        "positive_recall_met": (state == "evaluated" and bool(positives) and all(
            by_id.get(ident, {}).get("actual_match") is True for ident in positives)
            if state != "not_applicable" else None),
        "negative_false_positive_expectation_met": (state == "evaluated" and bool(negatives) and all(
            by_id.get(ident, {}).get("actual_match") is False for ident in negatives)
            if state != "not_applicable" else None),
    }


def _diagnostic_summary(rows: list[dict]) -> dict:
    def counts(values):
        result = {}
        for value in values:
            key = value if type(value) is str else "none"
            result[key] = result.get(key, 0) + 1
        return result

    evidence = [row["diagnostics"]["evidence"] for row in rows]
    positive_hits = sum(item["positive_hits"] for item in evidence)
    positive_total = sum(item["positive_total"] for item in evidence)
    false_positives = sum(item["negative_false_positives"] for item in evidence)
    negative_total = sum(item["negative_total"] for item in evidence)
    skipped_evidence = sum(item["state"] == "skipped_expected_ready" for item in evidence)
    return {
        "case_count": len(rows),
        "provider_stages": counts(row["diagnostics"]["provider_stage"] for row in rows),
        "proposal_stages": counts(row["diagnostics"]["proposal_stage"] for row in rows),
        "compiler_statuses": counts(row["diagnostics"]["compiler_status"] for row in rows),
        "compiler_reasons": counts(row["diagnostics"]["compiler_reason"] for row in rows),
        "status_expectations_met": sum(row["status_expectation_met"] for row in rows),
        "question_expectations_met": sum(row["question_expectation_met"] for row in rows),
        "hard_filter_expectations_met": sum(row["hard_filters_preserved"] for row in rows),
        "evidence": {
            "applicable_case_count": sum(item["state"] != "not_applicable" for item in evidence),
            "not_applicable_case_count": sum(item["state"] == "not_applicable" for item in evidence),
            "skipped_expected_ready_case_count": sum(
                item["state"] == "skipped_expected_ready" for item in evidence),
            "positive_hits": positive_hits,
            "positive_total": positive_total,
            "positive_recall_met": (positive_total > 0 and skipped_evidence == 0
                                     and positive_hits == positive_total),
            "negative_false_positives": false_positives,
            "negative_total": negative_total,
            "negative_false_positive_expectation_met": (
                negative_total > 0 and skipped_evidence == 0 and false_positives == 0),
        },
    }


def _measure_case(case: dict, planner, *, now: datetime, clock) -> dict:
    measured = _CountingPlanner(planner, clock=clock)
    try:
        result = plan_query(case["query"], now=now, entities=case["entities"],
                            previous_filters=None, planner=measured)
    except Exception:
        # An unexpected compiler failure aborts the run; it must not become a
        # partial expectation pass or expose exception text in the receipt.
        raise RuntimeError("qualification_operation_failed") from None

    # Preserve only a bounded validated response, checked against the exact
    # offset-preserving view supplied to the live compiler invocation.
    proposal = measured.response
    provider_outcome = measured.outcome
    observed_proposal = None
    validated = None
    if provider_outcome == "response":
        try:
            if len(measured.query_views) != 1:
                raise ValueError("missing query view")
            validated = validate_proposal(proposal, measured.query_views[0])
            observed_proposal = {"version": validated["version"], "status": validated["status"],
                "question": validated["question"], "concepts": [
                    {"start": c["start"], "end": c["end"], "alternatives": list(c["alternatives"])}
                    for c in validated["concepts"]]}
        except (ValueError, TypeError, KeyError):
            pass

    actual_question = validated.get("question") if validated is not None else None
    actual_proposal_status = validated.get("status") if validated is not None else None
    actual_hard = _hard_filters(result.filters)
    provider_not_needed = measured.calls == 0
    provider_question = actual_question
    if provider_not_needed and result.reason == "intent_date":
        provider_question = "date"
    status_ok = (result.status == case["expected_status"] and
                 ((actual_proposal_status == case["expected_status"] and provider_outcome == "response") or
                  (provider_not_needed and case["expected_status"] == "clarification")))
    question_ok = provider_question == case["expected_question"]
    hard_ok = actual_hard == case["expected_hard_filters"]

    evidence_checks = []
    evidence_ok = True
    evidence_evaluated = False
    if case["expected_status"] == "ready":
        description = result.filters.get("descriptive")
        if type(description) is dict:
            evidence_checks, evidence_ok = _evaluate_evidence(case, description)
            evidence_evaluated = True
        else:
            evidence_ok = False
    invoked_at_most_once = measured.calls <= 1
    met = status_ok and question_ok and hard_ok and evidence_ok and invoked_at_most_once
    provider_stage = {
        "not_needed": "not_needed",
        "response": "response",
        "intent_unavailable": "refused",
        "adapter_error": "error",
    }.get(provider_outcome, "error")
    proposal_stage = ("not_available" if provider_outcome != "response" else
                      "validated" if validated is not None else "invalid")
    reason = result.reason
    diagnostic_reason = (reason if type(reason) is str and _DIAGNOSTIC_CODE.fullmatch(reason)
                         else "other" if reason is not None else "none")
    evidence_diagnostic = _evidence_diagnostics(case, evidence_checks, evidence_evaluated)
    return {
        "case_id": case["id"],
        "cohort": case["cohort"],
        "provider_call_count": measured.calls,
        "provider_attempt_count": measured.calls,
        "provider_response_count": int(provider_outcome == "response"),
        "provider_refusal_count": int(provider_outcome == "intent_unavailable"),
        "provider_error_count": int(provider_outcome == "adapter_error"),
        "provider_outcome": provider_outcome,
        "provider_error": measured.error,
        "elapsed_ms": measured.elapsed_ms,
        "expected_status": case["expected_status"],
        "actual_proposal_status": actual_proposal_status,
        "actual_proposal": observed_proposal,
        "expected_question": case["expected_question"],
        "actual_question": provider_question,
        "actual_plan_status": result.status,
        "plan_reason": result.reason,
        "expected_hard_filters": case["expected_hard_filters"],
        "actual_hard_filters": actual_hard,
        "actual_descriptive": result.filters.get("descriptive"),
        "status_expectation_met": status_ok,
        "question_expectation_met": question_ok,
        "hard_filters_preserved": hard_ok,
        "evidence_checks": evidence_checks,
        "evidence_expectations_met": evidence_ok,
        "provider_invoked_at_most_once": invoked_at_most_once,
        "provider_query_view": measured.query_views[0] if measured.query_views else None,
        "expectations_met": met,
        "plan_query_invocations": 1,
        "diagnostics": {
            "provider_stage": provider_stage,
            "proposal_stage": proposal_stage,
            "compiler_status": result.status,
            "compiler_reason": diagnostic_reason,
            "status_expectation_met": status_ok,
            "question_expectation_met": question_ok,
            "hard_filters_expectation_met": hard_ok,
            "evidence": evidence_diagnostic,
        },
    }


def run_qualification(planner, *, now: datetime | None = None, clock=time.perf_counter,
                      suite="fixed-v1") -> dict:
    """Measure all fixed cases through the real planner and at most one provider call."""
    cases, cohorts, digest, audit = _select_cases(suite)
    fixed_now = now or datetime.combine(date.fromisoformat(NOW), datetime.min.time())
    if fixed_now.date().isoformat() != NOW:
        raise ValueError("qualification date must remain fixed")
    if not callable(clock):
        raise ValueError("qualification clock invalid")

    results = []
    for case in cases:
        results.append(_measure_case(case, planner, now=fixed_now, clock=clock))

    by_cohort = {}
    for name, group in cohorts.items():
        members = [row for row in results if row["cohort"] == name]
        by_cohort[name] = {
            "case_ids": [case["id"] for case in group],
            "attempted": len(members),
            "provider_calls": sum(row["provider_call_count"] for row in members),
            "provider_responses": sum(row["provider_response_count"] for row in members),
            "not_needed": sum(row["provider_outcome"] == "not_needed" for row in members),
            "timeouts_or_refusals": sum(row["provider_outcome"] == "intent_unavailable"
                                         for row in members),
            "adapter_errors": sum(row["provider_outcome"] == "adapter_error" for row in members),
            "status": ("expectations_met" if len(members) == len(group)
                       and all(row["expectations_met"] for row in members)
                       else "expectations_missed" if len(members) == len(group)
                       else "incomplete"),
        }

    complete = len(results) == len(cases)
    return {
        "status": "complete_synthetic_measurement" if complete else "incomplete",
        "policy_version": QUALIFICATION_POLICY_VERSION,
        "diagnostics_schema_version": DIAGNOSTICS_SCHEMA_VERSION,
        "cases_sha256": digest,
        **({"suite": suite, "fixture_audit": audit} if audit is not None else {}),
        "expected_case_count": len(cases),
        "attempted_case_count": len(results),
        "provider_call_count": sum(row["provider_call_count"] for row in results),
        "provider_attempt_count": sum(row["provider_attempt_count"] for row in results),
        "provider_response_count": sum(row["provider_outcome"] == "response" for row in results),
        "provider_refusal_count": sum(row["provider_outcome"] == "intent_unavailable" for row in results),
        "provider_error_count": sum(row["provider_outcome"] == "adapter_error" for row in results),
        "provider_not_needed_count": sum(row["provider_outcome"] == "not_needed" for row in results),
        "timeouts_or_refusals": sum(row["provider_outcome"] == "intent_unavailable"
                                     for row in results),
        "adapter_errors": sum(row["provider_outcome"] == "adapter_error" for row in results),
        "retry_count": 0,
        "warmup_call_count": 0,
        "cohorts": by_cohort,
        "diagnostics": {
            "overall": _diagnostic_summary(results),
            "cohorts": {
                name: _diagnostic_summary(
                    [row for row in results if row["cohort"] == name])
                for name in cohorts
            },
        },
        "cases": results,
        "synthetic_expectations_evaluated": True,
        "quality_evaluated": False,
        "family_quality_evaluated": False,
        "family_data_used": False,
        "native_runtime_verified": False,
        "activation_performed": False,
        "service_reconfigured": False,
    }


def _private_output_target(value: str) -> Path:
    target = Path(value)
    if not target.is_absolute() or not target.name:
        raise ValueError("qualification_operation_refused")
    parent = target.parent
    resolved_parent = parent.resolve(strict=True)
    if parent != resolved_parent or (ROOT == target or ROOT in target.parents):
        raise ValueError("qualification_operation_refused")
    require_private_directory(parent)
    try:
        target.lstat()
    except FileNotFoundError:
        pass
    else:
        raise ValueError("qualification_operation_refused")
    return target


def _write_private_report(target: Path, report: dict) -> None:
    data = (json.dumps(report, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(target, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            descriptor = -1
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    require_private_file(target)
    sync_directory(target.parent)


def _arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true",
                        help="run the twelve synthetic cases through local intent planning")
    parser.add_argument("--suite", choices=("fixed-v1", "reviewed-v1"), default="fixed-v1")
    parser.add_argument("--url")
    parser.add_argument("--model")
    parser.add_argument("--out")
    parser.add_argument("--timeout", type=float, default=20)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _arguments(argv)
    if not args.run and not any((args.url, args.model, args.out)):
        print(json.dumps(plan_summary(suite=args.suite), sort_keys=True))
        return 0
    if (not args.run or not args.url or not args.model or not args.out
            or type(args.timeout) not in (int, float) or not 0 < args.timeout <= 45):
        print("qualification_operation_refused", file=sys.stderr)
        return 2
    try:
        target = _private_output_target(args.out)
        planner = LocalIntentPlanner(args.url, args.model, timeout=args.timeout)
        report = run_qualification(planner, suite=args.suite)
        report["provider_model"] = planner.model
        report["provider_call_url"] = "loopback"
        _write_private_report(target, report)
    except Exception:
        print("qualification_operation_refused", file=sys.stderr)
        return 2
    print(json.dumps({
        "status": report["status"],
        "case_count": report["attempted_case_count"],
        "provider_call_count": report["provider_call_count"],
        "timeouts_or_refusals": report["timeouts_or_refusals"],
        "report_sha256": __import__("hashlib").sha256(target.read_bytes()).hexdigest(),
        "quality_evaluated": False,
        "native_runtime_verified": False,
    }, sort_keys=True))
    return 0 if report["attempted_case_count"] == report["expected_case_count"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
