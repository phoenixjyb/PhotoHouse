"""Offline, conservative fidelity checks for derived scene translations.

These checks cover a small set of explicit semantic markers. They are rejection
guards, not a translation judge; qualification still requires a hash-bound
review record for every translated query, with its declared reviewer type.
"""
from __future__ import annotations

import hashlib
import json
import re


REVIEW_SCHEMA = "photohouse.semantic_scene_translation_fidelity_review.v1"
_DIGEST = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)

# Only explicit cues are checked. Unknown wording is left for the required
# reviewer instead of being guessed by a broad parser.
_ZH_NEGATION = re.compile(
    r"没有|沒有|不是|并非|並非|未见|未見|不在|不含|不带|不帶|无雪|無雪|无积雪|無積雪")
_EN_NEGATION = re.compile(r"\b(?:no|not|never|without|neither|none)\b|\b\w+-free\b", re.I)
_ZH_COUNT = re.compile(r"(?P<number>零|一|二|两|兩|三|四|五|六|七|八|九|十|\d+)(?:个|個|位|只|隻|辆|輛|台|件|块|塊|张|張|名|群)")
_EN_COUNT = re.compile(r"\b(?P<number>single|one|two|three|four|five|six|seven|eight|nine|ten|\d+)\b", re.I)
_ZH_NUMBER_VALUES = {"零": 0, "一": 1, "二": 2, "两": 2, "兩": 2,
                    "三": 3, "四": 4, "五": 5, "六": 6, "七": 7,
                    "八": 8, "九": 9, "十": 10}
_EN_NUMBER_VALUES = {name: value for value, name in enumerate(
    ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"))}
_EN_NUMBER_VALUES["single"] = 1
_ZH_STATES = {
    # 停着等 is an explicit waiting state; 停着 alone remains stopped/parked.
    "waiting": re.compile(r"等待|等候|候车|候車|排队|排隊|停着等|停著等"),
    "parked": re.compile(r"停着(?!等)|停著(?!等)|停放|泊着|泊著|停车|停車"),
    # Avoid 开着/開著: without an object it can mean open, running, or driving.
    "moving": re.compile(r"行驶|行駛|行进|行進|移动|移動|驶过|駛過"),
    "stopped": re.compile(r"停下|停止|静止|靜止|不动|不動"),
}
_EN_STATES = {
    "waiting": re.compile(r"\b(?:wait(?:ing|s|ed)?|queued|standing by)\b", re.I),
    "parked": re.compile(r"\b(?:parked|parking)\b", re.I),
    "moving": re.compile(r"\b(?:driving|moving|traveling|travelling|in motion)\b", re.I),
    "stopped": re.compile(r"\b(?:stopped|stationary|motionless|at a standstill)\b", re.I),
}
_EN_SOURCE_STATES = _EN_STATES
_ZH_RELATIONS = {
    "alone": re.compile(r"独自|獨自|单独|單獨|一个人|一個人"),
    "separate": re.compile(r"分别|分別|分开|分開|各自"),
    "together": re.compile(r"一起|共同|相伴|陪同"),
}
_EN_RELATIONS = {
    "alone": re.compile(r"\b(?:alone|by oneself|on one's own)\b", re.I),
    "separate": re.compile(r"\b(?:separately|apart|separated)\b", re.I),
    "together": re.compile(r"\b(?:together|with each other|alongside each other)\b", re.I),
}
_EN_SOURCE_RELATIONS = _EN_RELATIONS
_AMBIGUOUS_NO_COMPOUND = re.compile(r"\bno\s+snow\s+sports?\s+field\b", re.I)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="strict")).hexdigest()


def _marker_set(text: str, patterns: dict[str, re.Pattern[str]]) -> set[str]:
    return {name for name, pattern in patterns.items() if pattern.search(text)}


def _number_values(text: str, pattern: re.Pattern[str], names: dict[str, int],
                   *, lowercase: bool = False) -> set[int]:
    values = set()
    for match in pattern.finditer(text):
        raw = match.group("number")
        normalized = raw.lower() if lowercase else raw
        values.add(names.get(normalized,
                             int(raw) if raw.isdigit() else -1))
    return values


def feature_mismatch(source: str, translation: str) -> str | None:
    """Return a fixed cue category for explicit conflicts or unsafe scope."""
    source_counts = (_number_values(source, _ZH_COUNT, _ZH_NUMBER_VALUES)
                     | _number_values(source, _EN_COUNT, _EN_NUMBER_VALUES, lowercase=True))
    target_counts = _number_values(translation, _EN_COUNT, _EN_NUMBER_VALUES, lowercase=True)
    if source_counts and not target_counts:
        return "quantity"
    if not source_counts and target_counts:
        return "quantity"
    if source_counts and target_counts and source_counts != target_counts:
        return "quantity"

    source_states = (_marker_set(source, _ZH_STATES)
                     | _marker_set(source, _EN_SOURCE_STATES))
    target_states = _marker_set(translation, _EN_STATES)
    if source_states != target_states:
        return "state"

    source_relations = (_marker_set(source, _ZH_RELATIONS)
                        | _marker_set(source, _EN_SOURCE_RELATIONS))
    target_relations = _marker_set(translation, _EN_RELATIONS)
    if source_relations != target_relations:
        return "contrast"

    source_negation = bool(_ZH_NEGATION.search(source) or _EN_NEGATION.search(source))
    target_negation = bool(_EN_NEGATION.search(translation))
    if source_negation != target_negation:
        return "negation"
    if _AMBIGUOUS_NO_COMPOUND.search(translation):
        return "negation_scope"
    return None


def validate_fidelity_review(source: dict, translations: dict, provider_recipe_sha256: str,
                             review: object) -> dict[str, object]:
    """Validate complete manual review bound to exact source and output hashes.

    No reviewer identity or query text is returned in the receipt. The declared
    reviewer type and decision are offline claims and are not authenticated.
    """
    from semantic_scene_cases import dataset_sha256

    if (type(review) is not dict or set(review) != {
            "schema", "reviewer_type", "source_dataset_sha256",
            "translation_recipe_sha256", "reviewed_pairs"}
            or review["schema"] != REVIEW_SCHEMA
            or type(review["reviewer_type"]) is not str
            or review["reviewer_type"] not in {"assistant", "human"}
            or type(review["source_dataset_sha256"]) is not str
            or not _DIGEST.fullmatch(review["source_dataset_sha256"])
            or type(review["translation_recipe_sha256"]) is not str
            or not _DIGEST.fullmatch(review["translation_recipe_sha256"])):
        raise ValueError("invalid_scene_translation_fidelity_review")
    if (review["source_dataset_sha256"] != dataset_sha256(source)
            or review["translation_recipe_sha256"] != provider_recipe_sha256):
        raise ValueError("invalid_scene_translation_fidelity_review")
    expected = {}
    for case in source["cases"]:
        for language in ("zh", "zh-en"):
            key = f'{case["id"]}:{language}'
            text = case["queries"][language]
            if feature_mismatch(text, translations[key]) is not None:
                raise ValueError("scene_translation_fidelity_feature_mismatch")
            expected[key] = {"source_text_sha256": _sha(text),
                             "translation_text_sha256": _sha(translations[key]),
                             "decision": "faithful"}
    pairs = review["reviewed_pairs"]
    if type(pairs) is not dict or pairs != expected:
        raise ValueError("invalid_scene_translation_fidelity_review")
    canonical = json.dumps(review, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=True, allow_nan=False).encode("ascii")
    return {"schema": REVIEW_SCHEMA, "reviewer_type": review["reviewer_type"],
            "review_sha256": hashlib.sha256(canonical).hexdigest(),
            "reviewed_pair_count": len(expected)}
