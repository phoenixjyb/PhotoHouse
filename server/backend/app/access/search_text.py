"""Request-local literal text matching and evidence ranking helpers.

Matching is intentionally lexical: NFKC/casefolded substring presence decides
eligibility. The quality tuple only orders already-matching evidence; it never
adds candidates or changes hard-filter behavior.
"""
from __future__ import annotations

from dataclasses import dataclass
import importlib
import os
import re
import unicodedata
from typing import Callable, Mapping, Sequence


# Bump this value when normalization or ranking semantics change. Callers can
# include it in their source binding so old result contexts are refreshed.
SEARCH_TEXT_POLICY_VERSION = 1
MAX_MATCH_REASONS = 43

_AUTHORED_SOURCES = frozenset(("photo_memory", "edited_caption"))
_WORD = re.compile(r"[\w]+", re.UNICODE)
_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


def normalize_text(value: str) -> str:
    """Apply the same Unicode compatibility/case-fold policy used by search."""
    return unicodedata.normalize("NFKC", value).casefold()


@dataclass(frozen=True, slots=True)
class NormalizedSource:
    """One request-local normalized source, retaining only approved evidence."""

    source: str
    source_id: str
    revision: object
    content: str
    normalized_text: str

    def reason(self) -> dict:
        return {"source": self.source, "source_id": self.source_id,
                "revision": self.revision}


def normalize_sources(text_sources: Sequence[Mapping], check: Callable[[], None]) -> tuple[NormalizedSource, ...]:
    """Normalize current source records once for one request/facts snapshot.

    No process-wide cache is kept: an edited source or a new revision must be
    folded again from its current snapshot. Extra fields are deliberately
    discarded so prose and unrelated metadata cannot leak into match reasons.
    """
    result = []
    if type(text_sources) not in (list, tuple):
        return ()
    for item in text_sources:
        check()
        if type(item) is not dict:
            continue
        source = item.get("source")
        source_id = item.get("source_id")
        revision = item.get("revision")
        content = item.get("content")
        if (type(source) is not str or type(source_id) is not str
                or type(content) is not str):
            continue
        result.append(NormalizedSource(source, source_id, revision, content,
                                       normalize_text(content)))
    check()
    return tuple(result)


def normalize_filters(filters: Mapping) -> dict:
    """Copy filters and fold only the literal text phrase once per request."""
    normalized = dict(filters)
    if "text" in normalized:
        phrase = normalized["text"]
        if type(phrase) is str:
            normalized["text"] = normalize_text(phrase)
    return normalized


def _tokens(value: str) -> tuple[str, ...]:
    """Tokenize for quality only; this never participates in eligibility."""
    tokens = []
    for match in _WORD.finditer(value):
        token = match.group(0)
        # Chinese text commonly arrives without spaces. Character units provide
        # a stable coverage signal while substring matching remains authoritative.
        characters = _CJK.findall(token)
        if characters:
            tokens.extend(characters)
            remainder = _CJK.sub("", token)
            if remainder:
                tokens.append(remainder)
        else:
            tokens.append(token)
    return tuple(tokens)


class TextQueryCache:
    """One reader's literal query tokens; never stores source text or results.

    Entries are immutable and replaced together. Returning the local entry keeps
    a simultaneous different query from mixing a phrase with another token set.
    Tokens are prepared lazily after the existing source cancellation check and
    literal eligibility test, so a query with no matching source does no work.
    """

    __slots__ = ("_entry", "_native", "_shadow")

    def __init__(self, *, engine=None):
        self._entry = None
        engine = os.environ.get('PHOTOHOUSE_LITERAL_TEXT_ENGINE', 'python') if engine is None else engine
        if engine not in ('python', 'rust', 'shadow'):
            raise ValueError('invalid_literal_text_engine')
        self._native = None
        self._shadow = engine == 'shadow'
        if engine != 'python':
            try:
                native = importlib.import_module('photohouse_literal_kernel')
                if native.POLICY_VERSION != SEARCH_TEXT_POLICY_VERSION or not callable(native.quality):
                    raise ValueError()
                self._native = native.quality
            except (ImportError, AttributeError, ValueError):
                raise RuntimeError('literal_text_kernel_unavailable') from None

    def tokens_for(self, phrase: str) -> tuple[str, ...]:
        entry = self._entry
        if entry is None or entry[0] != phrase:
            entry = (phrase, _tokens(phrase))
            self._entry = entry
        return entry[1]

    def quality_for(self, content: str, phrase: str):
        if self._native is None:
            return None
        value = self._native(content, phrase)
        if value is not None and (type(value) is not tuple or len(value) != 3
                or any(type(n) is not int for n in value)
                or not 0 <= value[0] <= 1000 or value[1] not in (0, 1)
                or value[2] != -len(content)):
            raise RuntimeError('invalid_literal_text_kernel_result')
        return value


def _has_whole_phrase_boundary(content: str, phrase: str) -> bool:
    """Return whether any literal occurrence has non-word edges on both sides."""
    offset = 0
    while True:
        start = content.find(phrase, offset)
        if start < 0:
            return False
        end = start + len(phrase)
        left_ok = start == 0 or not (content[start - 1].isalnum() or content[start - 1] == "_")
        right_ok = end == len(content) or not (content[end].isalnum() or content[end] == "_")
        if left_ok and right_ok:
            return True
        offset = start + 1


def _coverage(content: str, phrase: str, query_tokens=None) -> int:
    if query_tokens is None:
        query_tokens = _tokens(phrase)
    if not query_tokens:
        return 0
    available = set(_tokens(content))
    # Integer thousandths keep the tuple deterministic and avoid float sorting.
    return sum(token in available for token in query_tokens) * 1000 // len(query_tokens)


def match_text(row: Mapping, normalized_filters: Mapping,
               check: Callable[[], None] = lambda: None, *,
               query_cache: TextQueryCache | None = None) -> tuple[bool, list, tuple[int, ...]]:
    """Match literal text and return bounded provenance plus quality metadata.

    `normalized_filters` should come from `normalize_filters`, and
    `row['text_sources']` from `normalize_sources`. The returned quality is
    `(authored, token_coverage, whole_phrase_boundary, -shortest_source_length)`.
    """
    check()
    if "text" not in normalized_filters:
        return True, [], (0, 0, 0, 0)
    phrase = normalized_filters.get("text")
    if type(phrase) is not str or not phrase:
        return False, [], (0, 0, 0, 0)
    sources = row.get("text_sources", ()) if isinstance(row, Mapping) else ()
    reasons = []
    best = None
    authored = 0
    query_tokens = None
    if type(sources) not in (tuple, list):
        sources = ()
    for source in sources:
        check()
        if type(source) is not NormalizedSource or phrase not in source.normalized_text:
            continue
        if query_tokens is None:
            query_tokens = (query_cache.tokens_for(phrase)
                            if type(query_cache) is TextQueryCache else _tokens(phrase))
        if len(reasons) < MAX_MATCH_REASONS:
            reasons.append(source.reason())
        authored = max(authored, int(source.source in _AUTHORED_SOURCES))
        candidate = (query_cache.quality_for(source.normalized_text, phrase)
                     if type(query_cache) is TextQueryCache else None)
        if candidate is None or query_cache._shadow:
            original = (
                _coverage(source.normalized_text, phrase, query_tokens),
                int(_has_whole_phrase_boundary(source.normalized_text, phrase)),
                -len(source.normalized_text),
            )
            if candidate is not None and candidate != original:
                raise RuntimeError('literal_text_shadow_mismatch')
            candidate = original
        if best is None or candidate > best:
            best = candidate
    check()
    if best is None:
        return False, [], (0, 0, 0, 0)
    return True, reasons, (authored, *best)


def rank_results(found: Sequence[Mapping], quality_by_id: Mapping[str, tuple[int, ...]],
                 check: Callable[[], None] = lambda: None) -> list:
    """Rank cards deterministically without adding fields to their wire shape.

    Checks surround the built-in sort and run through its input/output loops.
    If a check raises, no partially ranked list is returned.
    """
    check()
    decorated = []
    for original_index, item in enumerate(found):
        check()
        asset_id = str(item.get("_asset_id", item.get("id", "")))
        quality = quality_by_id.get(asset_id, (0, 0, 0, 0))
        try:
            stable_id = (1, int(asset_id))
        except (TypeError, ValueError, OverflowError):
            stable_id = (0, asset_id)
        decorated.append(((quality, stable_id, -original_index), item))

    check()
    ordered = sorted(decorated, key=lambda entry: entry[0], reverse=True)
    check()
    ranked = []
    for _key, item in ordered:
        check()
        # `_asset_id` is an internal join key used by the caller while ranking;
        # never let it cross the response boundary.
        if "_asset_id" in item:
            card = dict(item)
            card.pop("_asset_id", None)
            ranked.append(card)
        else:
            ranked.append(item)
    check()
    return ranked
