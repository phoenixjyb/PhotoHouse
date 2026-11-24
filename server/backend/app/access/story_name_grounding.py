"""Deterministic, bounded name grounding for review-required story drafts.

The only packaged-data reads are the two fixed JSON files beside this module.
Callers can inject catalog and reading maps for tests. No network, database,
model, or fuzzy string matching is used here.
"""
from __future__ import annotations

from functools import lru_cache
import itertools
import json
from pathlib import Path
import re
import unicodedata
from typing import Any


MAX_TEXT_BYTES = 64 * 1024
MAX_PEOPLE = 32
MAX_ALIASES_PER_PERSON = 16
MAX_CATALOG_ENTRIES = 100_000
MAX_REPAIRS = 32
MAX_CONTEXT_SPANS = 256
MAX_SYLLABLE_VARIANTS = 64
_HAN = r'\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff'
_HAN_ONLY = re.compile(rf'\A[{_HAN}]+\Z')
_SYLLABLE = re.compile(r'\A[a-züv]{1,8}\Z', re.IGNORECASE | re.ASCII)
_DATA_DIR = Path(__file__).resolve().parent / 'data'


def _read_fixed_json(filename: str, max_bytes: int) -> Any:
    path = _DATA_DIR / filename
    try:
        if path.stat().st_size > max_bytes:
            return None
        raw = path.read_bytes()
        if len(raw) > max_bytes:
            return None
        return json.loads(raw.decode('utf-8', errors='strict'))
    except (OSError, UnicodeError, ValueError):
        return None


@lru_cache(maxsize=1)
def _packaged_data() -> tuple[Any, Any]:
    """Load only fixed package data, once; missing/invalid data fails closed."""
    return (_read_fixed_json('story-public-names.json', 32 * 1024 * 1024),
            _read_fixed_json('pinyin-readings.json', 8 * 1024 * 1024))


def _validate_catalog(value: Any) -> list[dict[str, str]]:
    if type(value) is not dict or set(value) != {'version', 'source', 'entries'}:
        raise ValueError('public name catalog is invalid')
    if type(value['version']) is not int or value['version'] != 1:
        raise ValueError('public name catalog is unsupported')
    if type(value['source']) is not str or not value['source'] or len(value['source']) > 512:
        raise ValueError('public name catalog is invalid')
    entries = value['entries']
    if type(entries) is not list or len(entries) > MAX_CATALOG_ENTRIES:
        raise ValueError('public name catalog size is invalid')
    clean = []
    seen_ids = set()
    for entry in entries:
        if type(entry) is not dict or set(entry) != {'id', 'name', 'kind'}:
            raise ValueError('public name catalog entry is invalid')
        identifier, name, kind = entry['id'], entry['name'], entry['kind']
        if (type(identifier) is not str or not re.fullmatch(r'Q[A-Za-z0-9_-]{1,64}', identifier)
                or identifier in seen_ids):
            raise ValueError('public name catalog identifier is invalid')
        if (type(name) is not str or len(name) > 32 or not _HAN_ONLY.fullmatch(name)):
            raise ValueError('public name catalog name is invalid')
        if type(kind) is not str or kind not in {'singer'}:
            raise ValueError('public name catalog kind is invalid')
        seen_ids.add(identifier)
        clean.append({'id': identifier, 'name': name, 'kind': kind})
    return clean


def _validate_readings(value: Any) -> dict[str, tuple[str, ...]]:
    if type(value) is not dict or len(value) > 40_000:
        raise ValueError('pinyin reading table is invalid')
    clean = {}
    for character, readings in value.items():
        if (type(character) is not str or len(character) != 1
                or not _HAN_ONLY.fullmatch(character) or type(readings) is not list
                or not 1 <= len(readings) <= 8):
            raise ValueError('pinyin reading entry is invalid')
        syllables = []
        for syllable in readings:
            if type(syllable) is not str or not _SYLLABLE.fullmatch(syllable):
                raise ValueError('pinyin syllable is invalid')
            normalized = syllable.casefold().replace('ü', 'v')
            if normalized not in syllables:
                syllables.append(normalized)
        clean[character] = tuple(syllables)
    return clean


def _people(value: Any) -> list[dict[str, Any]]:
    if type(value) is not list or len(value) > MAX_PEOPLE:
        raise ValueError('reviewed people are invalid')
    clean = []
    for person in value:
        if type(person) is not dict or set(person) != {'name', 'aliases'}:
            raise ValueError('reviewed person is invalid')
        name, aliases = person['name'], person['aliases']
        if type(name) is not str or not name.strip():
            raise ValueError('reviewed person name is invalid')
        try:
            if len(name.encode('utf-8', errors='strict')) > 256:
                raise ValueError('reviewed person name is invalid')
        except UnicodeError:
            raise ValueError('reviewed person name is invalid') from None
        if type(aliases) is not list or len(aliases) > MAX_ALIASES_PER_PERSON:
            raise ValueError('reviewed aliases are invalid')
        if any(type(alias) is not str or not alias.strip() for alias in aliases):
            raise ValueError('reviewed alias is invalid')
        try:
            if (any(len(alias.encode('utf-8', errors='strict')) > 256 for alias in aliases)
                    or len({alias.casefold() for alias in aliases}) != len(aliases)):
                raise ValueError('reviewed alias is invalid')
        except UnicodeError:
            raise ValueError('reviewed alias is invalid') from None
        clean.append({'name': name, 'aliases': list(aliases)})
    return clean


def _name_syllables(name: str, readings: dict[str, tuple[str, ...]]) -> tuple[tuple[str, ...], ...]:
    choices = [readings.get(character, ()) for character in name]
    if not choices or any(not values for values in choices):
        return ()
    # Matching is position-wise, so there is no need to enumerate polyphonic products.
    return tuple(choices)  # each position is its bounded set of toneless readings


def _same_pronunciation(left: str, right: str,
                        readings: dict[str, tuple[str, ...]]) -> bool:
    left_choices = _name_syllables(left, readings)
    right_choices = _name_syllables(right, readings)
    return (len(left_choices) == len(right_choices) and bool(left_choices)
            and all(set(a).intersection(b) for a, b in zip(left_choices, right_choices)))


def _phonetic_variants(name: str, readings: dict[str, tuple[str, ...]]):
    choices = _name_syllables(name, readings)
    if not choices:
        return ()
    count = 1
    for syllables in choices:
        count *= len(syllables)
        if count > MAX_SYLLABLE_VARIANTS:
            return ()
    return itertools.product(*choices)


def _alias_matches(text: str, alias: str) -> list[tuple[int, int]]:
    flags = re.IGNORECASE | re.ASCII if alias.isascii() else 0
    if alias.isascii():
        pattern = re.compile(rf'(?<![A-Za-z0-9_]){re.escape(alias)}(?![A-Za-z0-9_])', flags)
    else:
        pattern = re.compile(re.escape(alias))
    result = []
    for match in pattern.finditer(text):
        result.append((match.start(), match.end()))
        if len(result) > MAX_REPAIRS:
            break
    return result


def _public_cue_spans(text: str) -> list[tuple[int, int, str]]:
    suffix = re.compile(r'(?:的演唱会|演唱会|的演出|演出|的歌曲|歌曲|的歌|歌)')
    cues = ('歌手', '去看', '看', '去听', '听')
    found = set()
    for context in suffix.finditer(text):
        name_end = context.start()
        name_start = name_end
        while name_start > 0 and re.fullmatch(rf'[{_HAN}]', text[name_start - 1]):
            name_start -= 1
        run = text[name_start:name_end]
        cue_positions = [(run.rfind(cue), cue) for cue in cues if cue in run]
        if cue_positions:
            cue_at, cue = max(cue_positions)
            candidate_start = name_start + cue_at + len(cue)
            candidate = text[candidate_start:name_end]
        else:
            candidate_start, candidate = name_start, run
        if 2 <= len(candidate) <= 5:
            found.add((candidate_start, name_end, candidate))

    # An explicit role cue also stands on its own, as in "歌手X".
    standalone = re.compile(rf'(?P<cue>歌手)(?P<name>[{_HAN}]{{2,5}})(?![{_HAN}])')
    for match in standalone.finditer(text):
        found.add((*match.span('name'), match.group('name')))
    return sorted(found)


def ground_text(text: str, people: Any, *, catalog: Any = None,
                readings: Any = None) -> dict[str, Any]:
    """Ground exact reviewed aliases and context-cued public singer homophones.

    Public repair requires a unique singer catalog match with identical syllable
    alternatives. Private normalization requires an exact reviewed alias. The
    returned repair list is a trace; callers must keep the original text intact.
    """
    if type(text) is not str:
        raise ValueError('story text is invalid')
    try:
        text_bytes = text.encode('utf-8', errors='strict')
    except UnicodeError:
        raise ValueError('story text is invalid') from None
    if len(text_bytes) > MAX_TEXT_BYTES or any(
            (ord(character) < 32 or 0x7f <= ord(character) <= 0x9f)
            and character not in '\n\t' for character in text):
        raise ValueError('story text is invalid')

    if catalog is None or readings is None:
        package_catalog, package_readings = _packaged_data()
        catalog = package_catalog if catalog is None else catalog
        readings = package_readings if readings is None else readings
    if catalog is None:
        catalog = {'version': 1, 'source': 'unavailable', 'entries': []}
    if readings is None:
        readings = {}
    clean_catalog = _validate_catalog(catalog)
    clean_readings = _validate_readings(readings)
    clean_people = _people(people)

    # Validate all person records before matching; ambiguity never guesses an owner.
    alias_owners: dict[str, set[int]] = {}
    for index, person in enumerate(clean_people):
        for identity in [person['name'], *person['aliases']]:
            alias_owners.setdefault(identity.casefold(), set()).add(index)

    ambiguous: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    private_spans: list[tuple[int, int]] = []

    # A reviewed alias anchors the private canonical name. Latin aliases use word bounds.
    for index, person in enumerate(clean_people):
        for start, end in _alias_matches(text, person['name']):
            private_spans.append((start, end))
        for alias in person['aliases']:
            matches = _alias_matches(text, alias)
            if len(matches) > MAX_REPAIRS:
                raise ValueError('story name grounding repair limit exceeded')
            alias_owner_set = alias_owners[alias.casefold()]
            canonical_owner_set = alias_owners[person['name'].casefold()]
            owners = sorted(alias_owner_set | canonical_owner_set)
            if (len(alias_owner_set) != 1 or alias_owner_set != {index}
                    or len(canonical_owner_set) != 1):
                for start, end in matches:
                    private_spans.append((start, end))
                    ambiguous.append({'before': text[start:end], 'kind': 'reviewed_alias',
                                      'references': [f'reviewed_person:{owner}' for owner in owners]})
                    if len(ambiguous) > MAX_REPAIRS:
                        raise ValueError('story name grounding ambiguity limit exceeded')
                continue
            for start, end in matches:
                if text[start:end].casefold() == person['name'].casefold():
                    private_spans.append((start, end))
                    continue
                # A reviewed Latin alias followed by an equivalent Chinese canonical
                # spelling is one anchored same-person phrase; collapse it once.
                conjunction = (re.match(
                    rf'(?:或者|[，,]\s*也叫)\s*(?P<name>[{_HAN}]{{{len(person["name"])}}})'
                    rf'(?=$|[^\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]|了|呢|呀|啊|吧|'
                    rf'演唱会|演出|的歌|歌曲)',
                    text[end:]) if _HAN_ONLY.fullmatch(person['name']) else None)
                if conjunction:
                    second = conjunction.group('name')
                    peer_matches = [candidate for candidate in clean_people
                                    if _same_pronunciation(second, candidate['name'], clean_readings)]
                    canonical_matches = [candidate for candidate in clean_people
                                         if _same_pronunciation(person['name'], candidate['name'], clean_readings)]
                    unique_peer = len(peer_matches) == 1 and peer_matches[0]['name'] == person['name']
                    unique_canonical = len(canonical_matches) == 1
                    if unique_peer and unique_canonical:
                        span_end = end + conjunction.end()
                        candidates.append({'start': start, 'end': span_end,
                                           'before': text[start:span_end],
                                           'after': person['name'], 'kind': 'reviewed_alias',
                                           'reference': f'reviewed_person:{index}'})
                        private_spans.append((start, span_end))
                        if len(candidates) > MAX_REPAIRS:
                            raise ValueError('story name grounding repair limit exceeded')
                        continue
                    if peer_matches or canonical_matches:
                        span_end = end + conjunction.end()
                        private_spans.append((start, span_end))
                        ambiguous.append({'before': text[start:span_end],
                                          'kind': 'reviewed_alias',
                                          'references': [f'reviewed_person:{i}'
                                                         for i, p in enumerate(clean_people)
                                                         if p in peer_matches or p is person]})
                        if len(ambiguous) > MAX_REPAIRS:
                            raise ValueError('story name grounding ambiguity limit exceeded')
                        continue
                candidates.append({'start': start, 'end': end, 'before': text[start:end],
                                   'after': person['name'], 'kind': 'reviewed_alias',
                                   'reference': f'reviewed_person:{index}'})
                private_spans.append((start, end))
                if len(candidates) > MAX_REPAIRS:
                    raise ValueError('story name grounding repair limit exceeded')

    singer_entries = [entry for entry in clean_catalog if entry['kind'] == 'singer']
    phonetic_index: dict[tuple[str, ...], list[dict[str, str]]] = {}
    for entry in singer_entries:
        for signature in _phonetic_variants(entry['name'], clean_readings):
            phonetic_index.setdefault(tuple(signature), []).append(entry)

    public_names = {entry['name'] for entry in clean_catalog}

    def overlaps_catalog_name(start: int, end: int) -> bool:
        # Check bounded windows containing the proposed span, so an inexact
        # shorter spelling inside a correct longer catalog name is protected.
        for left in range(max(0, start - 31), start + 1):
            for right in range(end, min(len(text), left + 32) + 1):
                if text[left:right] in public_names:
                    return True
        return False

    context_spans = _public_cue_spans(text)
    if len(context_spans) > MAX_CONTEXT_SPANS:
        raise ValueError('story name grounding context limit exceeded')
    for start, end, source_name in context_spans:
        if any(start < stop and begin < end for begin, stop in private_spans):
            continue
        if overlaps_catalog_name(start, end):
            continue
        matches_by_id = {}
        for signature in _phonetic_variants(source_name, clean_readings):
            for entry in phonetic_index.get(tuple(signature), ()):
                matches_by_id[entry['id']] = entry
        matches = list(matches_by_id.values())
        distinct = {(entry['id'], entry['name']) for entry in matches}
        if len(distinct) == 1:
            identifier, public_name = next(iter(distinct))
            if source_name != public_name:
                candidates.append({'start': start, 'end': end, 'before': source_name,
                                   'after': public_name, 'kind': 'public_singer',
                                   'reference': identifier})
        elif len(distinct) > 1:
            ambiguous.append({'before': source_name, 'kind': 'public_singer',
                              'references': sorted(identifier for identifier, _name in distinct)})
        if len(ambiguous) > MAX_REPAIRS:
            raise ValueError('story name grounding ambiguity limit exceeded')
        if len(candidates) > MAX_REPAIRS:
            raise ValueError('story name grounding repair limit exceeded')

    # Once an explicit cue uniquely grounds one source spelling, propagate
    # only that exact spelling and correction across this same input text.
    grounded = {(item['before'], item['after'], item['reference'])
                for item in candidates if item['kind'] == 'public_singer'}
    for before, after, reference in sorted(grounded):
        for match in re.finditer(re.escape(before), text):
            start, end = match.span()
            if any(start < stop and begin < end for begin, stop in private_spans):
                continue
            if overlaps_catalog_name(start, end):
                continue
            if any(item['start'] == start and item['end'] == end for item in candidates):
                continue
            if any(start < item['end'] and item['start'] < end for item in candidates):
                continue
            candidates.append({'start': start, 'end': end, 'before': before,
                               'after': after, 'kind': 'public_singer',
                               'reference': reference})
            if len(candidates) > MAX_REPAIRS:
                raise ValueError('story name grounding repair limit exceeded')

    candidates.sort(key=lambda item: (item['start'], item['end'], item['kind']))
    accepted = []
    for candidate in candidates:
        if accepted and candidate['start'] < accepted[-1]['end']:
            # Do not let one grounding source silently shadow another.
            ambiguous.append({'before': candidate['before'], 'kind': candidate['kind'],
                              'references': [candidate['reference']]})
            continue
        accepted.append(candidate)
    if len(accepted) > MAX_REPAIRS:
        raise ValueError('story name grounding repair limit exceeded')

    output = []
    cursor = 0
    repairs = []
    for candidate in accepted:
        output.append(text[cursor:candidate['start']])
        output.append(candidate['after'])
        cursor = candidate['end']
        repairs.append({key: candidate[key]
                        for key in ('before', 'after', 'kind', 'reference')})
    output.append(text[cursor:])
    return {'text': ''.join(output), 'repairs': repairs, 'ambiguous': ambiguous}
