"""Pure lexical matching for bounded descriptive search concepts.

Every concept is required, while any explicitly supplied linguistic alternative
can satisfy that concept. This module does not create translations or synonyms;
LLM-generated alternatives need separate quality qualification. Exact quoted
text remains an independent filter handled by ``search_text``.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

from .search_text import NormalizedSource, normalize_text
from .search_exclusions import requires_exclusion_clarification


MAX_CONCEPTS = 6
MAX_ALTERNATIVES = 4
MAX_PHRASE_BYTES = 128
MAX_DESCRIPTION_BYTES = 4096
MAX_MATCH_REASONS = 43
SEARCH_DESCRIPTION_POLICY_VERSION = 3
_AUTHORED_SOURCES = frozenset(("photo_memory", "edited_caption"))
_APPROVED_SOURCES = _AUTHORED_SOURCES | {"generated_caption"}

# Scene evidence must make a positive assertion. A negated clause is ambiguous
# about which parts remain positive, so exclude it as a whole. This deliberately
# trades some recall for precision; it is not general semantic negation parsing.
_CLAUSE_BREAK = re.compile(
    r'[.!?。！？;；\n]+|(?a:\b(?:but|however)\b)|但是|然而|不过|但', re.I)


def _latin_word_character(char):
    return (char == '_' or char.isdigit() or
            unicodedata.name(char, '').startswith('LATIN ') or
            unicodedata.category(char).startswith('M'))


def _positive_phrase_match(clauses, phrase):
    """Return best ordinary boundary quality, or None for absent evidence.

    Latin words cannot match within another Latin word/number. Han phrases
    retain substring matching because ordinary Chinese has no word spaces.
    """
    best = None
    for clause in clauses:
        offset = 0
        while True:
            start = clause.find(phrase, offset)
            if start < 0:
                break
            end = start + len(phrase)
            left = (start == 0 or not _latin_word_character(phrase[0]) or
                    not _latin_word_character(clause[start - 1]))
            right = (end == len(clause) or not _latin_word_character(phrase[-1]) or
                     not _latin_word_character(clause[end]))
            if left and right:
                quality = int((start == 0 or not (clause[start - 1].isalnum() or clause[start - 1] == '_')) and
                              (end == len(clause) or not (clause[end].isalnum() or clause[end] == '_')))
                best = quality if best is None else max(best, quality)
                if best == 1:
                    return best
            offset = start + 1
    return best


def _invalid() -> ValueError:
    return ValueError("Invalid descriptive query")


def _phrase(value: object) -> tuple[str, str]:
    if type(value) is not str or not value or value != value.strip():
        raise _invalid()
    try:
        encoded = value.encode("utf-8", errors="strict")
    except UnicodeError:
        raise _invalid() from None
    if len(encoded) > MAX_PHRASE_BYTES:
        raise _invalid()
    if any(unicodedata.category(character) == "Cc" for character in value):
        raise _invalid()
    folded = normalize_text(value)
    if not folded.strip():
        raise _invalid()
    return value, folded


def normalize_description(value: object) -> dict:
    """Validate and copy the closed canonical descriptive-filter object."""
    if type(value) is not dict or set(value) != {"version", "concepts"}:
        raise _invalid()
    version = value["version"]
    concepts = value["concepts"]
    if type(version) is not int or version != 1:
        raise _invalid()
    if type(concepts) is not list or not 1 <= len(concepts) <= MAX_CONCEPTS:
        raise _invalid()

    canonical_concepts = []
    seen_surfaces = set()
    for concept in concepts:
        if type(concept) is not dict or set(concept) != {"surface", "alternatives"}:
            raise _invalid()
        surface, normalized_surface = _phrase(concept["surface"])
        if normalized_surface in seen_surfaces:
            raise _invalid()
        seen_surfaces.add(normalized_surface)

        alternatives = concept["alternatives"]
        if type(alternatives) is not list or not 1 <= len(alternatives) <= MAX_ALTERNATIVES:
            raise _invalid()
        canonical_alternatives = []
        seen_alternatives = set()
        for alternative in alternatives:
            original, normalized = _phrase(alternative)
            if normalized in seen_alternatives:
                raise _invalid()
            seen_alternatives.add(normalized)
            canonical_alternatives.append(original)
        canonical_concepts.append({"surface": surface, "alternatives": canonical_alternatives})

    result = {"version": 1, "concepts": canonical_concepts}
    try:
        size = len(json.dumps(result, ensure_ascii=False, separators=(",", ":"),
                              allow_nan=False).encode("utf-8", errors="strict"))
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise _invalid() from None
    if size > MAX_DESCRIPTION_BYTES:
        raise _invalid()
    return result


@dataclass(frozen=True, slots=True)
class PreparedDescription:
    """Request-local normalized alternatives ready to match many assets."""

    alternatives: tuple[tuple[str, ...], ...]


def prepare_description(value: object) -> PreparedDescription:
    """Validate once and fold alternatives once for a bounded search cohort."""
    canonical = normalize_description(value)
    return PreparedDescription(tuple(
        tuple(normalize_text(alternative) for alternative in concept["alternatives"])
        for concept in canonical["concepts"]
    ))


def match_prepared_description(sources: Sequence[NormalizedSource], description: PreparedDescription,
                               check: Callable[[], None] = lambda: None) -> tuple[bool, list, tuple[int, ...]]:
    """Match all concepts against current approved normalized sources.

    Alternatives require affirmative-clause evidence with Latin word edges.
    Han phrases use substring matching. Explicitly negated clauses cannot supply
    positive scene evidence. Literal quoted-text matching is independent.
    Reasons identify matching source records only; no source prose leaves here.
    """
    check()
    if type(description) is not PreparedDescription or not 1 <= len(description.alternatives) <= MAX_CONCEPTS:
        raise _invalid()
    if type(sources) not in (tuple, list) or any(type(source) is not NormalizedSource for source in sources):
        raise _invalid()

    reasons = []
    authored_concepts = 0
    boundary_concepts = 0
    best_source_lengths = 0
    affirmative = {}

    for alternatives in description.alternatives:
        check()
        best_quality = None
        concept_matched = False
        for source in sources:
            check()
            if (type(source.source) is not str or source.source not in _APPROVED_SOURCES or
                    type(source.source_id) is not str or type(source.normalized_text) is not str):
                raise _invalid()
            for alternative in alternatives:
                check()
                if source.normalized_text not in affirmative:
                    affirmative[source.normalized_text] = tuple(
                        clause for clause in _CLAUSE_BREAK.split(source.normalized_text)
                        if clause and not requires_exclusion_clarification(clause))
                boundary = _positive_phrase_match(affirmative[source.normalized_text], alternative)
                if boundary is None:
                    continue
                concept_matched = True
                authored = int(source.source in _AUTHORED_SOURCES)
                quality = (authored, boundary, -len(source.normalized_text))
                if best_quality is None or quality > best_quality:
                    best_quality = quality
                reason = source.reason()
                if len(reasons) < MAX_MATCH_REASONS and reason not in reasons:
                    reasons.append(reason)
        if not concept_matched:
            check()
            return False, [], (0, 0, 0)
        authored_concepts += best_quality[0]
        boundary_concepts += best_quality[1]
        best_source_lengths += -best_quality[2]

    check()
    return True, reasons, (authored_concepts, boundary_concepts, -best_source_lengths)


def match_description(sources: Sequence[NormalizedSource], description: Mapping,
                      check: Callable[[], None] = lambda: None) -> tuple[bool, list, tuple[int, ...]]:
    """Validate, prepare and match one descriptive plan."""
    return match_prepared_description(sources, prepare_description(description), check)
