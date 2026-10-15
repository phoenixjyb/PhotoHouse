"""Plan or measure a bounded local descriptive-intent trial on synthetic data.

No arguments only emits the static twelve-case plan. Execution requires an
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


def plan_summary() -> dict:
    cohorts = cases_by_cohort()
    return {
        "status": "plan_only",
        "case_ids": [case["id"] for case in CASES],
        "cohorts": {name: [case["id"] for case in group]
                    for name, group in cohorts.items()},
        "case_count": len(CASES),
        "cohort_counts": {name: len(group) for name, group in cohorts.items()},
        "cases_sha256": cases_digest(),
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
    if case["expected_status"] == "ready":
        description = result.filters.get("descriptive")
        if type(description) is dict:
            evidence_checks, evidence_ok = _evaluate_evidence(case, description)
        else:
            evidence_ok = False
    invoked_at_most_once = measured.calls <= 1
    met = status_ok and question_ok and hard_ok and evidence_ok and invoked_at_most_once
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
    }


def run_qualification(planner, *, now: datetime | None = None, clock=time.perf_counter) -> dict:
    """Measure all fixed cases through the real planner and at most one provider call."""
    fixed_now = now or datetime.combine(date.fromisoformat(NOW), datetime.min.time())
    if fixed_now.date().isoformat() != NOW:
        raise ValueError("qualification date must remain fixed")
    if not callable(clock):
        raise ValueError("qualification clock invalid")

    results = []
    for case in CASES:
        results.append(_measure_case(case, planner, now=fixed_now, clock=clock))

    by_cohort = {}
    for name, group in cases_by_cohort().items():
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

    complete = len(results) == len(CASES)
    return {
        "status": "complete_synthetic_measurement" if complete else "incomplete",
        "policy_version": QUALIFICATION_POLICY_VERSION,
        "cases_sha256": cases_digest(),
        "expected_case_count": len(CASES),
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
    parser.add_argument("--url")
    parser.add_argument("--model")
    parser.add_argument("--out")
    parser.add_argument("--timeout", type=float, default=20)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _arguments(argv)
    if not args.run and not any((args.url, args.model, args.out)):
        print(json.dumps(plan_summary(), sort_keys=True))
        return 0
    if (not args.run or not args.url or not args.model or not args.out
            or type(args.timeout) not in (int, float) or not 0 < args.timeout <= 45):
        print("qualification_operation_refused", file=sys.stderr)
        return 2
    try:
        target = _private_output_target(args.out)
        planner = LocalIntentPlanner(args.url, args.model, timeout=args.timeout)
        report = run_qualification(planner)
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
    return 0 if report["attempted_case_count"] == len(CASES) else 2


if __name__ == "__main__":
    raise SystemExit(main())
