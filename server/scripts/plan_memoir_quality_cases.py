#!/usr/bin/env python3
"""Emit bounded, synthetic memoir bundles for future human quality review.

This module only creates an offline review plan. It does not contact providers,
load models, invoke subprocesses, or write to a database.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Sequence, TextIO


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.access.memory_narrative import (  # noqa: E402
    MAX_BUNDLE_BYTES,
    MAX_CHAPTERS,
    MAX_RECENT_TURNS,
    MAX_SOURCES,
    _validate_bundle,
)
from app.access.story_titles import validate_bundle as _validate_title_bundle  # noqa: E402


MAX_PLAN_BYTES = 256 * 1024


def _source(source_id: str, kind: str, text: str, asset_id: str | None,
            author: str | None) -> dict:
    return {
        "id": source_id,
        "kind": kind,
        "text": text,
        "asset_id": asset_id,
        "author": author,
    }


def _chapter(chapter_id: str, title: str, narration: str, *,
             assets: list[str], evidence: list[str]) -> dict:
    return {
        "id": chapter_id,
        "title": title,
        "narration": narration,
        "asset_ids": assets,
        "evidence_ids": evidence,
    }


def _bundle(prefix: str, title: str, theme: str, chapters: list[dict],
            sources: list[dict], recent_turns: list[dict], instructions: str,
            *, language: str = "en") -> dict:
    return {
        "version": 1,
        "library_id": f"{prefix}-library",
        "target": {"type": "book", "id": f"{prefix}-book", "revision": 1},
        "language": language,
        "title": title,
        "theme": theme,
        "chapters": chapters,
        "sources": sources,
        "recent_turns": recent_turns,
        "instructions": instructions,
    }


def _case_one() -> dict:
    prefix = "synthetic-coherence"
    sources = [
        _source(f"{prefix}-planting", "family",
                "一位家庭成员记得，家人在五月初把豆种种在后院围栏旁。",
                f"{prefix}-garden-photo", "合成家庭成员甲"),
        _source(f"{prefix}-watering", "transcript",
                "一段合成语音记录提到，孩子们每天早晨给标好的菜畦浇水。",
                None, "合成家庭成员乙"),
        _source(f"{prefix}-sensory-note", "family",
                "家庭成员乙记得，浇水后能闻到泥土气息；孩子们为自己照料的菜畦感到自豪。",
                None, "合成家庭成员乙"),
        _source(f"{prefix}-bloom", "family",
                "后来的一则记录说，播种几周后开出了第一批花。",
                f"{prefix}-bloom-photo", "合成家庭成员甲"),
    ]
    bundle = _bundle(
        prefix,
        "围栏旁的小菜园",
        "按时间顺序回忆一家人照料小菜园的经历",
        [
            _chapter(f"{prefix}-chapter-01", "围栏旁的豆种",
                     "五月初，家人在后院围栏旁种下了豆种。",
                     assets=[f"{prefix}-garden-photo"], evidence=[f"{prefix}-planting"]),
            _chapter(f"{prefix}-chapter-02", "每天早晨的照料",
                     "孩子们每天早晨给标好的菜畦浇水。家庭成员乙还记得，浇水后能闻到泥土气息，孩子们也为自己照料的菜畦感到自豪。",
                     assets=[], evidence=[f"{prefix}-watering", f"{prefix}-sensory-note"]),
            _chapter(f"{prefix}-chapter-03", "几周后的第一批花",
                     "几周后，菜畦里开出了第一批花。",
                     assets=[f"{prefix}-bloom-photo"], evidence=[f"{prefix}-bloom"]),
        ],
        sources,
        [],
        "保留现有章节顺序。每个细节都应由对应来源支持；不要补写收获情节或具体日期。",
        language="zh",
    )
    return {
        "case_id": prefix,
        "focus": "ordered_multichapter_coherence_and_exact_citations",
        "task": "narrative",
        "bundle": bundle,
        "withheld_source_ids": [],
        "human_review_expectations": {
            "grounding": "每个具体情节都应得到该章节所引来源的支持。",
            "conflicts": "不要编造收获、具体播种日期或第一批花以外的结果。可使用来源明确记载的泥土气息和孩子们的自豪感，不要另加情绪。",
            "attribution": "涉及不同说法时，保留家庭成员的回忆与语音记录之间的归属差异。",
            "chronology": "按播种、早晨浇水、几周后开花的顺序组织；不要把相对时间改成日历日期。",
            "transitions": "用清楚的开篇和衔接把照料菜园写成一个连贯故事，而不是逐张照片的说明；围绕耐心照料展开，不要增添未经支持的因果关系。",
            "literary_style": "保持连贯的家庭叙述视角，让已有的感官细节自然融入文字。避免泄露不透明来源编号或原始技术元数据；可用自然语言解释相关的文件日期。对有依据的陈述无需刻意加上猜测语气。",
        },
    }


def _case_two() -> dict:
    prefix = "synthetic-conflict"
    sources = [
        _source(f"{prefix}-account-a", "family",
                "Synthetic family member A remembers the lakeside picnic as happening in 2018.",
                f"{prefix}-shared-picnic-photo", "Synthetic family member A"),
        _source(f"{prefix}-account-b", "family",
                "Synthetic family member B remembers the same picnic as happening in 2019.",
                f"{prefix}-shared-picnic-photo", "Synthetic family member B"),
        _source(f"{prefix}-date-metadata", "metadata",
                "The supplied image export date is 2025-06-12; this is a file date, not an event date.",
                None, None),
    ]
    bundle = _bundle(
        prefix,
        "Two Memories of the Lakeside Picnic",
        "Keep differing recollections visible while the year remains uncertain",
        [
            _chapter(f"{prefix}-chapter-01", "A picnic by the lake",
                     "Two family members remember the same lakeside picnic, but place it in different years.",
                     assets=[f"{prefix}-shared-picnic-photo"],
                     evidence=[f"{prefix}-account-a", f"{prefix}-account-b"]),
            _chapter(f"{prefix}-chapter-02", "An open date",
                     "One recollection places it in 2018 and the other in 2019; the available file date does not settle the event year.",
                     assets=[], evidence=[f"{prefix}-account-a", f"{prefix}-account-b", f"{prefix}-date-metadata"]),
        ],
        sources,
        [
            {"user": "Which year should the book use?", "assistant": "The available memories disagree, so the event year is still uncertain."},
            {"user": "Could the image date settle it?", "assistant": "The supplied date describes the export, not when the picnic happened."},
        ],
        "Preserve both attributed recollections and the uncertain event date. Ask a useful question if a single year is needed; never treat file date as event date.",
    )
    return {
        "case_id": prefix,
        "focus": "conflicting_multi_author_memories_and_uncertain_date",
        "task": "narrative",
        "bundle": bundle,
        "withheld_source_ids": [],
        "human_review_expectations": {
            "grounding": "Use only the two supplied recollections and the narrowly described file-date metadata.",
            "conflicts": "Retain the 2018 and 2019 disagreement; do not silently choose, average, or reconcile the years.",
            "attribution": "Name the two accounts as separate synthetic family-member recollections, without merging their voices.",
            "chronology": "Keep the event year explicitly uncertain; the 2025 export date is not event chronology.",
            "transitions": "Move from the shared picnic memory to the unresolved date without implying that metadata confirms either account.",
            "clarification": "If a single year matters, ask which recollection the family wants to preserve or whether they can clarify.",
            "literary_style": "Give the shared event a clear opening and connect the two accounts as one readable episode, rather than concatenating source summaries. Keep the voices balanced; do not expose opaque source IDs or raw technical metadata. Explain relevant file-date uncertainty in plain language when useful.",
        },
    }


def _case_three() -> dict:
    prefix = "synthetic-provenance"
    sources = [
        _source(f"{prefix}-approved-note", "family",
                "An approved synthetic note says the family visited the greenhouse together; it does not give a year.",
                f"{prefix}-greenhouse-photo", "Synthetic family member C"),
        _source(f"{prefix}-upload-date", "metadata",
                "The photo was imported on 2024-09-03; this is not an event date.",
                None, None),
    ]
    bundle = _bundle(
        prefix,
        "A Greenhouse Visit with an Open Question",
        "Separate new conversation details from approved source material",
        [
            _chapter(f"{prefix}-chapter-01", "The greenhouse visit",
                     "The approved note remembers a family visit to the greenhouse, without dating it.",
                     assets=[f"{prefix}-greenhouse-photo"], evidence=[f"{prefix}-approved-note"]),
            _chapter(f"{prefix}-chapter-02", "What remains unknown",
                     "The visit year is unknown in the approved note; the import date only dates the file handling.",
                     assets=[], evidence=[f"{prefix}-approved-note", f"{prefix}-upload-date"]),
        ],
        sources,
        [
            {"user": "I think there was a blue blanket in one of our greenhouse photos, but I am not sure it was this visit.",
             "assistant": "I will keep that as an uncertain detail from this conversation, not as a confirmed source fact."},
            {"user": "Can you tell which year this visit happened?", "assistant": "The sources currently available do not give the visit year."},
            {"user": "Please use only the sources currently approved for this draft.",
             "assistant": "I will stay within those sources and ask if more evidence is needed."},
        ],
        "Use only sources present in this bundle as evidence. Treat recent turns as conversation context, not source citations. Keep the date unresolved and ask for an approved source if needed.",
    )
    return {
        "case_id": prefix,
        "focus": "recent_multiturn_clarification_and_source_provenance",
        "task": "companion",
        "bundle": bundle,
        "withheld_source_ids": [f"{prefix}-withheld-audio"],
        "human_review_expectations": {
            "grounding": "The approved note supports a greenhouse visit only; recent turns do not add a citable source.",
            "conflicts": "Keep the blue-blanket recollection tentative because the user is unsure it belongs to this visit.",
            "attribution": "If mentioning the blanket, attribute it to the recent conversation and preserve the user's uncertainty.",
            "chronology": "Do not infer the event year from the 2024 import date or from the recent turns.",
            "transitions": "Respond to the latest year question while retaining the earlier uncertainty and approved-source boundary.",
            "withheld_sources": "Do not refer to or cite the deliberately omitted source; use only the approved note and upload-date metadata if a source citation is needed.",
            "clarification": "Ask for an approved source or family clarification if the year or photo detail must be established.",
            "literary_style": "Answer the current question directly in a coherent conversational voice; do not turn the sources into a caption list or expose opaque source IDs or raw technical metadata. Explain relevant file-date uncertainty in plain language when useful.",
        },
    }


def _title_case(prefix: str, language: str, sources: list[dict], focus: str,
                expectations: dict[str, str]) -> dict:
    """Build an independent title API bundle; it contains no narrative fields."""
    revision = hashlib.sha256((prefix + ":selection-v1").encode("ascii")).hexdigest()
    bundle = {
        "version": 1,
        "language": language,
        "theme": "everyday",
        "selection_revision": revision,
        "sources": sources,
    }
    return {
        "case_id": prefix,
        "focus": focus,
        "task": "suggest",
        "bundle": bundle,
        "withheld_source_ids": [],
        "human_review_expectations": expectations,
    }


def _title_family_case() -> dict:
    prefix = "synthetic-title-family"
    return _title_case(prefix, "zh", [
        {"id": f"{prefix}-family", "source": "family",
         "text": "周末我们和外婆在院子里种下了向日葵。"},
        {"id": f"{prefix}-draft", "source": "draft",
         "text": "孩子每天给花浇水。几周后花开了，我们一起拍照留念。"},
    ], "grounded_chinese_family_and_draft_title", {
        "grounding": "The title should reflect planting sunflowers with grandma in the yard or the later watering and bloom, without inventing a date, place detail, or event.",
        "citations": "Each title must cite a supplied family or draft source that directly supports its wording; opaque source IDs must not appear in title text.",
        "language": "Write a concise, natural Chinese family-memory title, not a source list or translation of metadata.",
        "review_boundary": "Keep proposals as unapproved choices for family review; do not imply the title or draft was saved.",
    })


def _title_uncertainty_case() -> dict:
    prefix = "synthetic-title-uncertainty"
    return _title_case(prefix, "en", [
        {"id": f"{prefix}-family", "source": "family",
         "text": "I remember our lakeside picnic happened in 2018."},
        {"id": f"{prefix}-ai", "source": "ai",
         "text": "An AI observation estimates that the visible clothing may be from 2019; this estimate is uncertain."},
        {"id": f"{prefix}-draft", "source": "draft",
         "text": "We do not know whether the picnic was in 2018 or 2019."},
    ], "preserve_conflicting_family_and_uncertain_ai_date", {
        "grounding": "Use only the lakeside picnic and the supplied year recollections; do not add people, activities, or locations.",
        "citations": "Each candidate must cite a supplied source that supports the wording; avoid citing the uncertain AI estimate as confirmed fact.",
        "uncertainty": "Do not state that the picnic definitely happened in 2018 or 2019, and do not let the AI estimate override the family recollection or draft uncertainty.",
        "language": "Use concise, natural English that frames the shared memory or open question rather than presenting source IDs.",
        "review_boundary": "These are unapproved title proposals for family review, not a chosen or saved title.",
    })


def _title_abstention_case() -> dict:
    prefix = "synthetic-title-abstention"
    return _title_case(prefix, "en", [], "abstain_when_title_bundle_has_no_sources", {
        "abstention": "Return zero title suggestions when the bundle has no sources; do not invent a memory title from the theme alone.",
        "review_boundary": "The empty proposal list remains a review result and does not write or approve a title.",
    })


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":"), sort_keys=True).encode("utf-8", errors="strict")


def _bundle_id_list(bundle: dict) -> list[str]:
    ids = [bundle["library_id"], bundle["target"]["id"]]
    ids.extend(chapter["id"] for chapter in bundle["chapters"])
    ids.extend(source["id"] for source in bundle["sources"])
    # Asset IDs identify media, so multiple source records may legitimately
    # refer to the same asset. Count each media identity once.
    assets = sorted({source["asset_id"] for source in bundle["sources"]
                     if source["asset_id"] is not None})
    return ids + assets


def _check_asset_crosslinks(bundle: dict) -> None:
    source_assets = {source["asset_id"] for source in bundle["sources"] if source["asset_id"] is not None}
    chapter_assets = {asset_id for chapter in bundle["chapters"] for asset_id in chapter["asset_ids"]}
    if source_assets != chapter_assets:
        raise ValueError("synthetic bundle asset links are incomplete")


def build_plan() -> dict:
    """Return a deterministic plan containing fresh, validated synthetic bundles."""
    cases = [_case_one(), _case_two(), _case_three(), _title_family_case(),
             _title_uncertainty_case(), _title_abstention_case()]
    case_ids: set[str] = set()
    all_bundle_ids: set[str] = set()
    planned_cases = []
    for case in cases:
        if case["case_id"] in case_ids:
            raise ValueError("synthetic case identifiers must be unique")
        case_ids.add(case["case_id"])
        if case["task"] == "suggest":
            bundle = _validate_title_bundle(case["bundle"])
            identifier_list = [source["id"] for source in bundle["sources"]]
        else:
            bundle = _validate_bundle(case["bundle"])
            if len(bundle["chapters"]) > MAX_CHAPTERS or len(bundle["sources"]) > MAX_SOURCES:
                raise ValueError("synthetic bundle exceeds narrative limits")
            if len(bundle["recent_turns"]) > MAX_RECENT_TURNS:
                raise ValueError("synthetic turns exceed narrative limits")
            _check_asset_crosslinks(bundle)
            identifier_list = _bundle_id_list(bundle)
        bundle_bytes = _canonical_json(bundle)
        if len(bundle_bytes) > MAX_BUNDLE_BYTES:
            raise ValueError("synthetic bundle exceeds narrative byte limit")
        identifiers = set(identifier_list)
        if len(identifier_list) != len(identifiers):
            raise ValueError("synthetic identifiers must be distinct within each bundle")
        if identifiers & all_bundle_ids:
            raise ValueError("synthetic identifiers must be distinct across cases")
        all_bundle_ids.update(identifiers)
        withheld = set(case["withheld_source_ids"])
        if withheld & identifiers:
            raise ValueError("withheld source identifiers must not appear in a bundle")
        planned_cases.append({
            "case_id": case["case_id"],
            "focus": case["focus"],
            "task": case["task"],
            "bundle_sha256": hashlib.sha256(bundle_bytes).hexdigest(),
            "bundle": bundle,
            "withheld_source_ids": list(case["withheld_source_ids"]),
            "human_review_expectations": dict(case["human_review_expectations"]),
        })
    plan = {
        "schema_version": 1,
        "status": "offline_plan_only",
        "synthetic_data_only": True,
        "model_executed": False,
        "external_requests_made": 0,
        "database_writes": 0,
        "cases": planned_cases,
    }
    if len(_canonical_json(plan)) > MAX_PLAN_BYTES:
        raise ValueError("quality plan exceeds its output limit")
    return plan


def main(argv: Sequence[str] | None = None, *, stdout: TextIO | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    output = stdout if stdout is not None else sys.stdout
    output.write(_canonical_json(build_plan()).decode("utf-8") + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
