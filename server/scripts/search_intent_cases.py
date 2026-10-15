"""Public, synthetic-only fixtures for descriptive intent qualification.

Names, entities, dates, notes and captions below are invented. They are never
loaded from PhotoHouse, and this module performs no provider or filesystem I/O.
"""
from __future__ import annotations

import hashlib
import json


NOW = "2032-09-14"
_ENABLED = ["people", "date", "tags", "locations", "media", "text"]


def _entities(*, person=None, labels=()):
    people = {"Sample Child": "301", "示例儿童": "301",
              "Sample Adult": "302", "示例成人": "302"}
    selected = [people[person]] if person else []
    return {
        "binding": "f" * 64,
        "enabled": list(_ENABLED),
        "groups": {"people": selected, "tags": [], "locations": []},
        "labels": list(labels),
        "ambiguous": False,
    }


def _asset(name, expected, *sources):
    return {
        "asset_id": name,
        "expected_match": expected,
        "sources": [
            {"source": kind, "source_id": f"{name}-{index}",
             "revision": 1, "content": content}
            for index, (kind, content) in enumerate(sources, 1)
        ],
    }


def _snow_red_assets(case_id):
    return [
        _asset(case_id + "-positive", True,
               ("generated_caption", "Fresh snow covers the path."),
               ("photo_memory", "Sample Child wore a red coat.")),
        _asset(case_id + "-blue-coat", False,
               ("generated_caption", "Fresh snow covers the path."),
               ("photo_memory", "Sample Child wore a blue coat.")),
        _asset(case_id + "-snow-only", False,
               ("generated_caption", "Fresh snow covers the path."),
               ("photo_memory", "A warm winter afternoon.")),
        _asset(case_id + "-coat-only", False,
               ("generated_caption", "Sample Child wore a red coat."),
               ("photo_memory", "The path was clear.")),
    ]


def _cake_assets(case_id):
    return [
        _asset(case_id + "-positive", True,
               ("generated_caption", "A birthday cake sat on the table."),
               ("photo_memory", "Sample Adult was cutting the cake.")),
        _asset(case_id + "-holding", False,
               ("generated_caption", "A birthday cake sat on the table."),
               ("photo_memory", "Sample Adult held a candle.")),
        _asset(case_id + "-other-dessert", False,
               ("generated_caption", "Sample Adult cut a loaf of bread."),
               ("photo_memory", "A birthday party was underway.")),
        _asset(case_id + "-cake-only", False,
               ("generated_caption", "A birthday cake sat on the table."),
               ("photo_memory", "Guests gathered near the table.")),
    ]


def _rain_umbrella_assets(case_id):
    return [
        _asset(case_id + "-positive", True,
               ("generated_caption", "A rainy street celebration filled the city square."),
               ("photo_memory", "Several umbrellas were open.")),
        _asset(case_id + "-rain-no-umbrella", False,
               ("generated_caption", "A rainy street celebration filled the city square."),
               ("photo_memory", "People watched from nearby shops.")),
        _asset(case_id + "-umbrella-no-rain", False,
               ("generated_caption", "A street celebration filled the city square."),
               ("photo_memory", "Several umbrellas were open.")),
        _asset(case_id + "-street-only", False,
               ("generated_caption", "Rain fell on a quiet city street."),
               ("photo_memory", "A few people walked past.")),
    ]


def _dog_park_assets(case_id):
    return [
        _asset(case_id + "-positive", True,
               ("generated_caption", "Dog running beside an old park bench."),
               ("photo_memory", "The park path was busy.")),
        _asset(case_id + "-walking", False,
               ("generated_caption", "Dog walking beside the old park bench."),
               ("photo_memory", "The bench stood near the path.")),
        _asset(case_id + "-running-no-bench", False,
               ("generated_caption", "Dog running across the lawn."),
               ("photo_memory", "The lawn was empty of benches.")),
        _asset(case_id + "-bench-only", False,
               ("generated_caption", "A wooden park bench stood by the path."),
               ("photo_memory", "No dog was nearby.")),
    ]


CASES = (
    {
        "id": "en_snow_redcoat_hard_filters", "cohort": "en",
        "query": "Find photos of Sample Child wearing a red coat in snow on 2032-09-14",
        "entities": _entities(person="Sample Child", labels=("Sample Child",)),
        "expected_status": "ready", "expected_question": None,
        "expected_hard_filters": {
            "people": {"ids": ["301"], "match": "any"}, "media": ["image"],
            "date": {"from": "2032-09-14", "to": "2032-09-14"},
        },
        "evidence": _snow_red_assets("en1"),
    },
    {
        "id": "en_birthday_cutting_adult_year_video", "cohort": "en",
        "query": "Find 2024 videos of Sample Adult cutting a birthday cake",
        "entities": _entities(person="Sample Adult", labels=("Sample Adult",)),
        "expected_status": "ready", "expected_question": None,
        "expected_hard_filters": {
            "people": {"ids": ["302"], "match": "any"}, "media": ["video"],
            "date": {"from": "2024-01-01", "to": "2024-12-31"},
        },
        "evidence": _cake_assets("en2"),
    },
    {
        "id": "en_rain_umbrella_and", "cohort": "en",
        "query": "Find photos of umbrellas at a rainy street celebration",
        "entities": _entities(),
        "expected_status": "ready", "expected_question": None,
        "expected_hard_filters": {"media": ["image"]},
        "evidence": _rain_umbrella_assets("en3"),
    },
    {
        "id": "en_childhood_needs_date", "cohort": "en",
        "query": "Find photos of Sample Child from childhood",
        "entities": _entities(person="Sample Child", labels=("Sample Child",)),
        "expected_status": "clarification", "expected_question": "date",
        "expected_hard_filters": {}, "evidence": [],
    },
    {
        "id": "zh_snow_redcoat_hard_filters", "cohort": "zh",
        "query": "找示例儿童2032年9月14日在雪地穿红色外套的照片",
        "entities": _entities(person="示例儿童", labels=("示例儿童",)),
        "expected_status": "ready", "expected_question": None,
        "expected_hard_filters": {
            "people": {"ids": ["301"], "match": "any"}, "media": ["image"],
            "date": {"from": "2032-09-14", "to": "2032-09-14"},
        },
        "evidence": [
            _asset("zh1-positive", True,
                   ("generated_caption", "雪地里有新雪。"),
                   ("photo_memory", "示例儿童穿着红色外套。")),
            _asset("zh1-blue-coat", False,
                   ("generated_caption", "雪地里有新雪。"),
                   ("photo_memory", "示例儿童穿着蓝色外套。")),
            _asset("zh1-snow-only", False,
                   ("generated_caption", "雪地里有新雪。"),
                   ("photo_memory", "冬日午后。")),
            _asset("zh1-coat-only", False,
                   ("generated_caption", "示例儿童穿着红色外套。"),
                   ("photo_memory", "路面没有积雪。")),
        ],
    },
    {
        "id": "zh_birthday_cutting_adult_year_video", "cohort": "zh",
        "query": "找2024年示例成人切生日蛋糕的视频",
        "entities": _entities(person="示例成人", labels=("示例成人",)),
        "expected_status": "ready", "expected_question": None,
        "expected_hard_filters": {
            "people": {"ids": ["302"], "match": "any"}, "media": ["video"],
            "date": {"from": "2024-01-01", "to": "2024-12-31"},
        },
        "evidence": [
            _asset("zh2-positive", True,
                   ("generated_caption", "桌上放着生日蛋糕。"),
                   ("photo_memory", "示例成人切开了蛋糕。")),
            _asset("zh2-holding", False,
                   ("generated_caption", "桌上放着生日蛋糕。"),
                   ("photo_memory", "示例成人拿着蜡烛。")),
            _asset("zh2-other-dessert", False,
                   ("generated_caption", "示例成人切开了一条面包。"),
                   ("photo_memory", "生日聚会正在进行。")),
            _asset("zh2-cake-only", False,
                   ("generated_caption", "桌上放着生日蛋糕。"),
                   ("photo_memory", "客人聚在桌边。")),
        ],
    },
    {
        "id": "zh_rain_umbrella_and", "cohort": "zh",
        "query": "找雨天街道上的雨伞照片",
        "entities": _entities(),
        "expected_status": "ready", "expected_question": None,
        "expected_hard_filters": {"media": ["image"]},
        "evidence": [
            _asset("zh3-positive", True,
                   ("generated_caption", "雨天街道很安静。"),
                   ("photo_memory", "几把雨伞撑开了。")),
            _asset("zh3-rain-no-umbrella", False,
                   ("generated_caption", "雨天街道很安静。"),
                   ("photo_memory", "行人没有带伞。")),
            _asset("zh3-umbrella-no-rain", False,
                   ("generated_caption", "几把雨伞撑开了。"),
                   ("photo_memory", "午后天气晴朗。")),
            _asset("zh3-street-only", False,
                   ("generated_caption", "雨水沿着街道路面流淌。"),
                   ("photo_memory", "雨后街道很安静。")),
        ],
    },
    {
        "id": "zh_childhood_needs_date", "cohort": "zh",
        "query": "找示例儿童小时候的照片",
        "entities": _entities(person="示例儿童", labels=("示例儿童",)),
        "expected_status": "clarification", "expected_question": "date",
        "expected_hard_filters": {}, "evidence": [],
    },
    {
        "id": "mixed_snow_redcoat_ascii_name_hard_filters", "cohort": "mixed",
        "query": "Find Sample Child昨天在雪地穿红色外套的photos",
        "entities": _entities(person="Sample Child", labels=("Sample Child",)),
        "expected_status": "ready", "expected_question": None,
        "expected_hard_filters": {
            "people": {"ids": ["301"], "match": "any"}, "media": ["image"],
            "date": {"from": "2032-09-13", "to": "2032-09-13"},
        },
        "evidence": [
            _asset("mix1-positive", True,
                   ("generated_caption", "雪地里有薄雪。"),
                   ("photo_memory", "Sample Child穿红色外套。")),
            _asset("mix1-blue-coat", False,
                   ("generated_caption", "雪地里有薄雪。"),
                   ("photo_memory", "Sample Child穿蓝色外套。")),
            _asset("mix1-snow-only", False,
                   ("generated_caption", "雪地里有薄雪。"),
                   ("photo_memory", "冬日午后。")),
            _asset("mix1-coat-only", False,
                   ("generated_caption", "Sample Child穿红色外套。"),
                   ("photo_memory", "小路上没有雪。")),
        ],
    },
    {
        "id": "mixed_birthday_cutting_adult_year_video", "cohort": "mixed",
        "query": "Find Sample Adult在2024年切生日蛋糕的videos",
        "entities": _entities(person="Sample Adult", labels=("Sample Adult",)),
        "expected_status": "ready", "expected_question": None,
        "expected_hard_filters": {
            "people": {"ids": ["302"], "match": "any"}, "media": ["video"],
            "date": {"from": "2024-01-01", "to": "2024-12-31"},
        },
        "evidence": [
            _asset("mix2-positive", True,
                   ("generated_caption", "生日蛋糕放在桌上。"),
                   ("photo_memory", "Sample Adult切生日蛋糕。")),
            _asset("mix2-holding", False,
                   ("generated_caption", "生日蛋糕放在桌上。"),
                   ("photo_memory", "Sample Adult拿着蜡烛。")),
            _asset("mix2-other-dessert", False,
                   ("generated_caption", "Sample Adult切开了一条面包。"),
                   ("photo_memory", "生日聚会正在进行。")),
            _asset("mix2-cake-only", False,
                   ("generated_caption", "生日蛋糕放在桌上。"),
                   ("photo_memory", "客人聚在桌边。")),
        ],
    },
    {
        "id": "mixed_dog_running_park_literal", "cohort": "mixed",
        "query": "Find a dog running beside the old park bench in videos about \"school concert\"",
        "entities": _entities(),
        "expected_status": "ready", "expected_question": None,
        "expected_hard_filters": {"media": ["video"], "text": "school concert"},
        "evidence": _dog_park_assets("mix3"),
    },
    {
        "id": "mixed_long_ago_needs_date", "cohort": "mixed",
        "query": "Find photos of Sample Adult from long ago",
        "entities": _entities(person="Sample Adult", labels=("Sample Adult",)),
        "expected_status": "clarification", "expected_question": "date",
        "expected_hard_filters": {}, "evidence": [],
    },
)


def cases_digest() -> str:
    canonical = json.dumps(CASES, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def cases_by_cohort() -> dict[str, tuple[dict, ...]]:
    return {cohort: tuple(case for case in CASES if case["cohort"] == cohort)
            for cohort in ("en", "zh", "mixed")}
