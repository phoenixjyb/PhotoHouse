"""Separately reviewed synthetic fixtures for descriptive intent regressions.

All people, captions and literal note text are invented. Caption annotations
record only which requested descriptive conditions each caption supports; a
missing condition means insufficient evidence, not proof that the scene lacked
it. Hard filters are expected separately and are not asserted by captions.
This module performs no provider, network or filesystem I/O.
"""
from __future__ import annotations

import hashlib
import json


NOW = "2032-09-14"
_ENABLED = ["people", "date", "tags", "locations", "media", "text"]


def _entities(person: str, label: str) -> dict:
    people = {"Mira": "401", "米拉": "401"}
    return {
        "binding": "e" * 64,
        "enabled": list(_ENABLED),
        "groups": {"people": [people[person]], "tags": [], "locations": []},
        "labels": [label],
        "ambiguous": False,
    }


def _asset(name: str, expected: bool, content: str, supported: dict[str, str],
           condition_keys: tuple[str, ...]) -> dict:
    source_id = f"{name}-caption"
    missing = [key for key in condition_keys if key not in supported]
    if set(supported) & set(missing) or set(supported) | set(missing) != set(condition_keys):
        raise ValueError("condition_annotation_partition_invalid")
    if expected != (not missing):
        raise ValueError("fixture_expectation_annotation_mismatch")
    quotes = {}
    for key, quote in supported.items():
        if not isinstance(quote, str) or not quote or quote not in content:
            raise ValueError("support_quote_not_in_caption")
        quotes[key] = {"source_id": source_id, "quote": quote}
    return {
        "asset_id": name,
        "expected_match": expected,
        "sources": [{"source": "generated_caption", "source_id": source_id,
                     "revision": 1, "content": content}],
        "support_quotes": quotes,
        "missing_conditions": missing,
    }


def _ready_case(case_id: str, cohort: str, query: str, conditions: dict[str, str],
                hard_filters: dict, positives: tuple[tuple[str, str, dict], ...],
                negatives: tuple[tuple[str, str, dict], ...], person: str,
                label: str) -> dict:
    keys = tuple(conditions)
    evidence = [
        _asset(f"{case_id}-{suffix}", True, caption, quotes, keys)
        for suffix, caption, quotes in positives
    ] + [
        _asset(f"{case_id}-{suffix}", False, caption, quotes, keys)
        for suffix, caption, quotes in negatives
    ]
    return {
        "id": case_id,
        "cohort": cohort,
        "query": query,
        "entities": _entities(person, label),
        "expected_status": "ready",
        "expected_question": None,
        "expected_hard_filters": hard_filters,
        "conditions": dict(conditions),
        "evidence": evidence,
    }


def _clarification(case_id: str, cohort: str, query: str, person: str,
                   label: str) -> dict:
    return {
        "id": case_id,
        "cohort": cohort,
        "query": query,
        "entities": _entities(person, label),
        "expected_status": "clarification",
        "expected_question": "date",
        "expected_hard_filters": {},
        "conditions": {},
        "evidence": [],
    }


_YELLOW_MAILBOX = {
    "yellow_coat": "Mira wears a yellow coat.",
    "waving": "Mira is waving.",
    "beside_mailbox": "Mira is beside a red mailbox.",
}
_RED_CABIN = {
    "red_backpack": "The backpack is red.",
    "carrying_backpack": "Mira carries the backpack.",
    "entering_cabin": "Mira walks into a wooden cabin.",
}
_ORANGE_BASKET = {
    "orange_gloves": "The gloves are orange.",
    "putting_gloves": "Mira puts the gloves somewhere.",
    "inside_canvas_basket": "The gloves end up inside a canvas basket.",
}


def _date_photo_filters() -> dict:
    return {"people": {"ids": ["401"], "match": "any"},
            "media": ["image"],
            "date": {"from": "2032-09-01", "to": "2032-09-30"}}


def _date_video_filters() -> dict:
    return {"people": {"ids": ["401"], "match": "any"},
            "media": ["video"],
            "date": {"from": "2032-09-01", "to": "2032-09-30"}}


CASES = (
    _ready_case(
        "review_en_yellow_mailbox", "en",
        "Find September 2032 photos of Mira in her yellow coat waving beside the red mailbox.",
        _YELLOW_MAILBOX, _date_photo_filters(),
        (("positive-en", "Mira waves beside a red mailbox in her yellow coat.", {
            "yellow_coat": "yellow coat", "waving": "Mira waves",
            "beside_mailbox": "beside a red mailbox"}),
         ("positive-zh", "米拉穿着黄色外套，在红色邮箱旁挥手。", {
            "yellow_coat": "黄色外套", "waving": "挥手",
            "beside_mailbox": "在红色邮箱旁"})),
        (("green-coat", "Mira waves beside a red mailbox in a green coat.", {
            "waving": "Mira waves", "beside_mailbox": "beside a red mailbox"}),
         ("no-wave", "Mira in a yellow coat stands beside the red mailbox and smiles at the camera.", {
            "yellow_coat": "yellow coat", "beside_mailbox": "stands beside the red mailbox"}),
         ("across-street", "Mira waves in her yellow coat while the red mailbox stands across the street.", {
            "yellow_coat": "yellow coat", "waving": "Mira waves"})),
        "Mira", "Mira"),
    _ready_case(
        "review_en_cabin", "en",
        "Find September 2032 photos of Mira carrying a red backpack as she walks into a wooden cabin.",
        _RED_CABIN, _date_photo_filters(),
        (("positive-en", "Mira carries a red backpack while walking into a wooden cabin.", {
            "red_backpack": "red backpack", "carrying_backpack": "carries a red backpack",
            "entering_cabin": "walking into a wooden cabin"}),
         ("positive-zh", "米拉背着红色背包，正走进木屋。", {
            "red_backpack": "红色背包", "carrying_backpack": "背着红色背包",
            "entering_cabin": "走进木屋"})),
        (("blue-backpack", "Mira carries a blue backpack while walking into a wooden cabin.", {
            "carrying_backpack": "carries a blue backpack",
            "entering_cabin": "walking into a wooden cabin"}),
         ("backpack-resting", "Mira's red backpack rests on the porch as she walks into the wooden cabin.", {
            "red_backpack": "red backpack", "entering_cabin": "walks into the wooden cabin"}),
         ("outside-cabin", "Mira carries her red backpack along a path beside the wooden cabin.", {
            "red_backpack": "red backpack", "carrying_backpack": "carries her red backpack"})),
        "Mira", "Mira"),
    _ready_case(
        "review_en_basket", "en",
        "Find September 2032 photos of Mira putting orange gloves inside the canvas basket.",
        _ORANGE_BASKET, _date_photo_filters(),
        (("positive-en", "Mira puts the orange gloves into a canvas basket.", {
            "orange_gloves": "orange gloves", "putting_gloves": "Mira puts the orange gloves",
            "inside_canvas_basket": "into a canvas basket"}),
         ("positive-zh", "米拉把橙色手套放进帆布篮里。", {
            "orange_gloves": "橙色手套", "putting_gloves": "把橙色手套放进",
            "inside_canvas_basket": "放进帆布篮里"})),
        (("blue-gloves", "Mira puts the blue gloves into a canvas basket.", {
            "putting_gloves": "Mira puts the blue gloves",
            "inside_canvas_basket": "into a canvas basket"}),
         ("already-inside", "Orange gloves sit inside the canvas basket while Mira points at a shelf.", {
            "orange_gloves": "Orange gloves", "inside_canvas_basket": "inside the canvas basket"}),
         ("on-shelf", "Mira puts the orange gloves on a wooden shelf beside the canvas basket.", {
            "orange_gloves": "orange gloves", "putting_gloves": "Mira puts the orange gloves"})),
        "Mira", "Mira"),
    _clarification("review_en_childhood_date", "en",
                   "Find photos of Mira from childhood.", "Mira", "Mira"),

    _ready_case(
        "review_zh_yellow_mailbox", "zh",
        "找2032年9月米拉穿黄色外套、在红色邮箱旁挥手的照片。",
        _YELLOW_MAILBOX, _date_photo_filters(),
        (("positive-en", "Mira waves beside a red mailbox in her yellow coat.", {
            "yellow_coat": "yellow coat", "waving": "Mira waves",
            "beside_mailbox": "beside a red mailbox"}),
         ("positive-zh", "米拉穿着黄色外套，在红色邮箱旁挥手。", {
            "yellow_coat": "黄色外套", "waving": "挥手",
            "beside_mailbox": "在红色邮箱旁"})),
        (("green-coat", "米拉穿着绿色外套，在红色邮箱旁挥手。", {
            "waving": "挥手", "beside_mailbox": "在红色邮箱旁"}),
         ("no-wave", "米拉穿黄色外套站在红色邮箱旁，对着镜头微笑。", {
            "yellow_coat": "黄色外套", "beside_mailbox": "站在红色邮箱旁"}),
         ("across-street", "米拉穿黄色外套挥手，红色邮箱在街道对面。", {
            "yellow_coat": "黄色外套", "waving": "挥手"})),
        "米拉", "米拉"),
    _ready_case(
        "review_zh_cabin", "zh",
        "找2032年9月米拉背着红色背包走进木屋的照片。",
        _RED_CABIN, _date_photo_filters(),
        (("positive-en", "Mira carries a red backpack while walking into a wooden cabin.", {
            "red_backpack": "red backpack", "carrying_backpack": "carries a red backpack",
            "entering_cabin": "walking into a wooden cabin"}),
         ("positive-zh", "米拉背着红色背包，正走进木屋。", {
            "red_backpack": "红色背包", "carrying_backpack": "背着红色背包",
            "entering_cabin": "走进木屋"})),
        (("blue-backpack", "米拉背着蓝色背包走进木屋。", {
            "carrying_backpack": "背着蓝色背包", "entering_cabin": "走进木屋"}),
         ("backpack-resting", "米拉的红色背包放在门廊上，她走进木屋。", {
            "red_backpack": "红色背包", "entering_cabin": "走进木屋"}),
         ("outside-cabin", "米拉背着红色背包沿着木屋旁的小路行走。", {
            "red_backpack": "红色背包", "carrying_backpack": "背着红色背包"})),
        "米拉", "米拉"),
    _ready_case(
        "review_zh_basket", "zh",
        "找2032年9月米拉把橙色手套放进帆布篮里的照片。",
        _ORANGE_BASKET, _date_photo_filters(),
        (("positive-en", "Mira puts the orange gloves into a canvas basket.", {
            "orange_gloves": "orange gloves", "putting_gloves": "Mira puts the orange gloves",
            "inside_canvas_basket": "into a canvas basket"}),
         ("positive-zh", "米拉把橙色手套放进帆布篮里。", {
            "orange_gloves": "橙色手套", "putting_gloves": "把橙色手套放进",
            "inside_canvas_basket": "放进帆布篮里"})),
        (("blue-gloves", "米拉把蓝色手套放进帆布篮里。", {
            "putting_gloves": "把蓝色手套放进", "inside_canvas_basket": "放进帆布篮里"}),
         ("already-inside", "橙色手套放在帆布篮里，米拉指着旁边的架子。", {
            "orange_gloves": "橙色手套", "inside_canvas_basket": "放在帆布篮里"}),
         ("on-shelf", "米拉把橙色手套放在帆布篮旁边的木架上。", {
            "orange_gloves": "橙色手套", "putting_gloves": "米拉把橙色手套放在"})),
        "米拉", "米拉"),
    _clarification("review_zh_childhood_date", "zh",
                   "找米拉小时候的照片。", "米拉", "米拉"),

    _ready_case(
        "review_mixed_yellow_mailbox", "mixed",
        "Find September 2032 photos of Mira穿黄色外套、在红色邮箱旁 waving.",
        _YELLOW_MAILBOX, _date_photo_filters(),
        (("positive-en", "Mira waves beside a red mailbox in her yellow coat.", {
            "yellow_coat": "yellow coat", "waving": "Mira waves",
            "beside_mailbox": "beside a red mailbox"}),
         ("positive-zh", "米拉穿着黄色外套，在红色邮箱旁挥手。", {
            "yellow_coat": "黄色外套", "waving": "挥手",
            "beside_mailbox": "在红色邮箱旁"})),
        (("green-coat", "米拉穿绿色外套，在红色邮箱旁挥手。", {
            "waving": "挥手", "beside_mailbox": "在红色邮箱旁"}),
         ("no-wave", "米拉穿黄色外套站在红色邮箱旁，对着镜头微笑。", {
            "yellow_coat": "黄色外套", "beside_mailbox": "站在红色邮箱旁"}),
         ("across-street", "米拉穿黄色外套挥手，红色邮箱在街道对面。", {
            "yellow_coat": "黄色外套", "waving": "挥手"})),
        "Mira", "Mira"),
    _ready_case(
        "review_mixed_cabin", "mixed",
        "Find September 2032 photos of Mira背着红色背包 walking into the wooden cabin.",
        _RED_CABIN, _date_photo_filters(),
        (("positive-en", "Mira carries a red backpack while walking into a wooden cabin.", {
            "red_backpack": "red backpack", "carrying_backpack": "carries a red backpack",
            "entering_cabin": "walking into a wooden cabin"}),
         ("positive-zh", "米拉背着红色背包，正走进木屋。", {
            "red_backpack": "红色背包", "carrying_backpack": "背着红色背包",
            "entering_cabin": "走进木屋"})),
        (("blue-backpack", "Mira carries a blue backpack while walking into a wooden cabin.", {
            "carrying_backpack": "carries a blue backpack",
            "entering_cabin": "walking into a wooden cabin"}),
         ("backpack-resting", "米拉的红色背包放在门廊上，她走进木屋。", {
            "red_backpack": "红色背包", "entering_cabin": "走进木屋"}),
         ("outside-cabin", "Mira carries her red backpack along a path beside the wooden cabin.", {
            "red_backpack": "red backpack", "carrying_backpack": "carries her red backpack"})),
        "Mira", "Mira"),
    _ready_case(
        "review_mixed_basket_literal", "mixed",
        'Find September 2032 videos of Mira把橙色手套放进帆布篮里 containing "paper workshop".',
        _ORANGE_BASKET,
        {**_date_video_filters(), "text": "paper workshop"},
        (("positive-en", "Mira puts the orange gloves into a canvas basket.", {
            "orange_gloves": "orange gloves", "putting_gloves": "Mira puts the orange gloves",
            "inside_canvas_basket": "into a canvas basket"}),
         ("positive-zh", "米拉把橙色手套放进帆布篮里。", {
            "orange_gloves": "橙色手套", "putting_gloves": "把橙色手套放进",
            "inside_canvas_basket": "放进帆布篮里"})),
        (("blue-gloves", "Mira puts the blue gloves into a canvas basket.", {
            "putting_gloves": "Mira puts the blue gloves",
            "inside_canvas_basket": "into a canvas basket"}),
         ("already-inside", "橙色手套放在帆布篮里，米拉指着旁边的架子。", {
            "orange_gloves": "橙色手套", "inside_canvas_basket": "放在帆布篮里"}),
         ("on-shelf", "米拉把橙色手套放在帆布篮旁边的木架上。", {
            "orange_gloves": "橙色手套", "putting_gloves": "米拉把橙色手套放在"})),
        "Mira", "Mira"),
    _clarification("review_mixed_childhood_date", "mixed",
                   "Find photos of Mira很久以前.", "Mira", "Mira"),
)


def cases_digest() -> str:
    canonical = json.dumps(CASES, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def cases_by_cohort() -> dict[str, tuple[dict, ...]]:
    return {cohort: tuple(case for case in CASES if case["cohort"] == cohort)
            for cohort in ("en", "zh", "mixed")}
