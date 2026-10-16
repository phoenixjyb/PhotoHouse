"""Pure, private-safe comparison of two semantic scene evaluation reports."""
from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any


_SCHEMA = "photohouse.semantic_scene_evaluation.v1"
_COMPARISON_SCHEMA = "photohouse.semantic_scene_comparison.v1"
_LANGUAGES = ("en", "zh", "zh-en")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_CASE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z", re.ASCII)
_COHORT_LABEL = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z", re.ASCII)
_REPORT_KEYS = {
    "schema", "dataset_sha256", "candidate_count", "matched_case_count",
    "all_languages_top1_cases", "top_k", "effective_top_k", "overall",
    "languages", "cases", "review_declarations", "dialect_relevance_measured",
    "family_relevance_measured", "activation_approved",
}
_SUMMARY_KEYS = {"queries", "top1", "top5", "mean_reciprocal_rank", "recall_at_5"}
_CASE_KEYS = {"case_id", "ranks", "all_languages_top1", "worst_language_rank"}
_REVIEW_KEYS = {"natural_scenes", "labels_reviewed"}
_ERROR = "invalid_semantic_scene_comparison"


def _invalid() -> None:
    raise ValueError(_ERROR)


def _is_int(value: object) -> bool:
    return type(value) is int


def _probability(value: object) -> bool:
    return (type(value) is float and math.isfinite(value)
            and 0.0 <= value <= 1.0)


def _close(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=1e-12, abs_tol=1e-12)


def _validate_summary(value: object, ranks: list[int]) -> None:
    if type(value) is not dict or set(value) != _SUMMARY_KEYS:
        _invalid()
    count = len(ranks)
    if (not _is_int(value["queries"]) or value["queries"] != count
            or not _is_int(value["top1"]) or value["top1"] != sum(rank == 1 for rank in ranks)
            or not _is_int(value["top5"]) or value["top5"] != sum(rank <= 5 for rank in ranks)
            or not _probability(value["mean_reciprocal_rank"])
            or not _probability(value["recall_at_5"])):
        _invalid()
    expected_mrr = math.fsum(1.0 / rank for rank in ranks) / count
    if not _close(value["mean_reciprocal_rank"], expected_mrr):
        _invalid()


def _validate_report(value: object) -> dict[str, Any]:
    if type(value) is not dict or set(value) != _REPORT_KEYS:
        _invalid()
    if (value["schema"] != _SCHEMA or type(value["dataset_sha256"]) is not str
            or not _DIGEST.fullmatch(value["dataset_sha256"])):
        _invalid()
    candidate_count = value["candidate_count"]
    if not _is_int(candidate_count) or not 4 <= candidate_count <= 64:
        _invalid()
    if (not _is_int(value["top_k"]) or value["top_k"] != 5
            or not _is_int(value["effective_top_k"])
            or value["effective_top_k"] != min(5, candidate_count)):
        _invalid()
    if (value["dialect_relevance_measured"] is not False
            or value["family_relevance_measured"] is not False
            or value["activation_approved"] is not False):
        _invalid()
    review = value["review_declarations"]
    if (type(review) is not dict or set(review) != _REVIEW_KEYS
            or any(type(review[key]) is not bool for key in _REVIEW_KEYS)):
        _invalid()

    cases = value["cases"]
    if type(cases) is not list or not 2 <= len(cases) <= 32:
        _invalid()
    normalized_cases: dict[str, dict[str, int]] = {}
    for case in cases:
        if type(case) is not dict or set(case) != _CASE_KEYS:
            _invalid()
        case_id = case["case_id"]
        ranks = case["ranks"]
        if (type(case_id) is not str or not _CASE_ID.fullmatch(case_id)
                or case_id in normalized_cases or type(ranks) is not dict
                or set(ranks) != set(_LANGUAGES)
                or any(not _is_int(rank) or not 1 <= rank <= candidate_count
                       for rank in ranks.values())):
            _invalid()
        all_top1 = all(ranks[language] == 1 for language in _LANGUAGES)
        worst = max(ranks.values())
        if (type(case["all_languages_top1"]) is not bool
                or case["all_languages_top1"] is not all_top1
                or not _is_int(case["worst_language_rank"]) or case["worst_language_rank"] != worst):
            _invalid()
        normalized_cases[case_id] = dict(ranks)

    case_count = len(normalized_cases)
    if (not _is_int(value["matched_case_count"]) or value["matched_case_count"] != case_count
            or not _is_int(value["all_languages_top1_cases"])
            or value["all_languages_top1_cases"] != sum(
                all(ranks[language] == 1 for language in _LANGUAGES)
                for ranks in normalized_cases.values())):
        _invalid()

    language_reports = value["languages"]
    if type(language_reports) is not dict or set(language_reports) != set(_LANGUAGES):
        _invalid()
    for language in _LANGUAGES:
        _validate_summary(language_reports[language],
                          [ranks[language] for ranks in normalized_cases.values()])
    all_ranks = [ranks[language] for ranks in normalized_cases.values()
                 for language in _LANGUAGES]
    _validate_summary(value["overall"], all_ranks)
    return {
        "dataset_sha256": value["dataset_sha256"],
        "candidate_count": candidate_count,
        "case_ids": set(normalized_cases),
        "cases": normalized_cases,
        "review_declarations": dict(review),
    }


def _validate_cohorts(value: object, case_ids: set[str]) -> dict[str, list[str]]:
    if type(value) is not dict or not 1 <= len(value) <= 8:
        _invalid()
    result: dict[str, list[str]] = {}
    seen: set[str] = set()
    for label, members in value.items():
        if (type(label) is not str or not _COHORT_LABEL.fullmatch(label)
                or type(members) is not list or not members):
            _invalid()
        selected: list[str] = []
        for case_id in members:
            if (type(case_id) is not str or case_id not in case_ids or case_id in seen):
                _invalid()
            seen.add(case_id)
            selected.append(case_id)
        result[label] = selected
    if seen != case_ids:
        _invalid()
    return result


def _summarize(rows: list[tuple[str, str, int, int]]) -> dict[str, Any]:
    before_ranks = [row[2] for row in rows]
    after_ranks = [row[3] for row in rows]
    regressed_case_ids = sorted({case_id for case_id, _, before, after in rows if after > before})
    return {
        "cases": len({row[0] for row in rows}),
        "queries": len(rows),
        "top1_before": sum(rank == 1 for rank in before_ranks),
        "top1_after": sum(rank == 1 for rank in after_ranks),
        "top5_before": sum(rank <= 5 for rank in before_ranks),
        "top5_after": sum(rank <= 5 for rank in after_ranks),
        "mean_reciprocal_rank_before": math.fsum(1.0 / rank for rank in before_ranks) / len(rows),
        "mean_reciprocal_rank_after": math.fsum(1.0 / rank for rank in after_ranks) / len(rows),
        "rank_gains": sum(after < before for before, after in zip(before_ranks, after_ranks)),
        "rank_regressions": sum(after > before for before, after in zip(before_ranks, after_ranks)),
        "rank_ties": sum(after == before for before, after in zip(before_ranks, after_ranks)),
        "top1_improved": sum(before != 1 and after == 1
                             for before, after in zip(before_ranks, after_ranks)),
        "top1_lost": sum(before == 1 and after != 1
                         for before, after in zip(before_ranks, after_ranks)),
        "regression_case_ids": regressed_case_ids,
    }


def _rows(before: dict[str, dict[str, int]], after: dict[str, dict[str, int]],
          case_ids: list[str], languages: tuple[str, ...]) -> list[tuple[str, str, int, int]]:
    return [(case_id, language, before[case_id][language], after[case_id][language])
            for case_id in sorted(case_ids) for language in languages]


def compare_evaluations(before: object, after: object, cohorts: object) -> dict[str, Any]:
    """Compare rank changes by frozen case cohorts and language, without recall claims."""
    before_report = _validate_report(before)
    after_report = _validate_report(after)
    if (before_report["case_ids"] != after_report["case_ids"]
            or before_report["candidate_count"] != after_report["candidate_count"]
            or before_report["review_declarations"] != after_report["review_declarations"]):
        _invalid()
    selected_cohorts = _validate_cohorts(cohorts, before_report["case_ids"])
    cohort_bytes = json.dumps(
        {label: sorted(members) for label, members in selected_cohorts.items()},
        sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("ascii")
    before_cases, after_cases = before_report["cases"], after_report["cases"]
    sorted_ids = sorted(before_report["case_ids"])
    overall = _summarize(_rows(before_cases, after_cases, sorted_ids, _LANGUAGES))
    languages = {
        language: _summarize(_rows(before_cases, after_cases, sorted_ids, (language,)))
        for language in _LANGUAGES
    }
    cohort_summaries = {}
    for label in sorted(selected_cohorts):
        cohort_ids = selected_cohorts[label]
        cohort_summaries[label] = {
            "overall": _summarize(_rows(before_cases, after_cases, cohort_ids, _LANGUAGES)),
            "languages": {
                language: _summarize(_rows(before_cases, after_cases, cohort_ids, (language,)))
                for language in _LANGUAGES
            },
        }
    return {
        "schema": _COMPARISON_SCHEMA,
        "before_dataset_sha256": before_report["dataset_sha256"],
        "after_dataset_sha256": after_report["dataset_sha256"],
        "candidate_count": before_report["candidate_count"],
        "matched_case_count": len(sorted_ids),
        "cohort_labels": sorted(selected_cohorts),
        "cohorts_sha256": hashlib.sha256(cohort_bytes).hexdigest(),
        "overall": overall,
        "languages": languages,
        "cohorts": cohort_summaries,
        "activation_approved": False,
        "semantic_faithfulness_qualified": False,
    }
