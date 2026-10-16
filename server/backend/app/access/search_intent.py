"""Compile bounded language-model suggestions into authorized search filters.

The model supplies descriptive spans and alternatives, never IDs, SQL, tools or
hard filters. The ordinary planner interprets the remaining original words.
Known dates, media types, reviewed labels and quoted literals cannot be hidden
inside a descriptive span. Alternatives are interpretations requiring separate
language/relevance qualification, rather than independent family evidence.
"""
from datetime import datetime
import re

from . import discovery as d
from .assistant_query_plan import (QueryPlan, _QUOTE, _MEDIA, _NEGATION, _entity_filters,
                                   _extract_dates, _consumed_label, _valid_previous,
                                   _strip_prefix, _remove_occurrences)
from .kinship import SELECTORS
from .search_refinement import _operations, plan_query as literal_plan, query_mode
from .search_description import MAX_CONCEPTS, normalize_description
from .search_pending import _AGE_PHRASE
from .search_intent_view import scene_view

POLICY_VERSION = 1
QUESTIONS = frozenset(('date', 'person', 'description', 'scope', 'unsupported_action'))


class IntentUnavailable(RuntimeError):
    def __init__(self):
        super().__init__('Local intent planning unavailable')


_REMOVAL = re.compile(r'^(?:any description|clear (?:the )?description filter|不限描述|不限场景)[。.!！?？]*$', re.I)
_QUOTED_TARGET = r'(?:"(?P<target_ascii>[^"\r\n]+)"|“(?P<target_curly>[^“”\r\n]+)”)'
_DESCRIPTIVE_REMOVALS = (
    (re.compile(rf'^\s*(?:please[ \t]+)?(?:remove|drop)[ \t]+(?:the[ \t]+)?{_QUOTED_TARGET}[ \t]+clue[ \t]*[。.!！?？]*\s*$', re.I), True),
    (re.compile(rf'^\s*(?:请)?(?:移除|去掉)[ \t]*{_QUOTED_TARGET}[ \t]*(?:这条|这个)?线索[ \t]*[。.!！?？]*\s*$'), True),
    (re.compile(r'^\s*(?:please[ \t]+)?(?:remove|drop)[ \t]+(?:the[ \t]+)?(?P<target_unquoted>\S(?:[^\r\n]*?\S)?)[ \t]+clue[ \t]*[。.!！?？]*\s*$', re.I), False),
    (re.compile(r'^\s*(?:请)?(?:移除|去掉)[ \t]*(?P<target_unquoted>\S(?:[^\r\n]*?\S)?)[ \t]*(?:这条|这个)?线索[ \t]*[。.!！?？]*\s*$'), False),
)
_MALFORMED_DESCRIPTIVE_REMOVAL = re.compile(
    r'^(?:(?:please\s+)?(?:remove|drop)(?a:\b).*clues?.*|(?:请)?(?:移除|去掉).*线索.*)$', re.I | re.S)
_UNQUOTED_REMOVAL_CONNECTOR = re.compile(
    r'(?a:(?:^|\s)(?:and|or|both|together|then)(?:$|\s))|以及|并且|同时|然后|和|或')
_UNQUOTED_REMOVE_ALL = frozenset(('all', '所有', '全部'))
_REMOVAL_QUOTES = frozenset('"“”')
_ACTION = re.compile(r'^(?:delete|remove all|share|send|upload|rename|move|record|take a photo|'
                     r'删除|分享|发送|上传|重命名|移动|录音|拍照|照一下)(?a:\b)|^(?:删除|分享|发送|上传|重命名|移动|录音|拍照|照一下)', re.I)
_GRAMMAR = re.compile(r'(?a:\b)(?:the|a|an|of|in|on|at|by|from|during|taken|please|me|for|and|or|both|together|with)(?a:\b)|'
                      r'请|麻烦|帮忙|帮我|替我|我想|能不能|可以|一下|的|那些|一些|里面|有关|关于|在|于|呢|吗|和|与|及|或|一起|同时|[\s。！？.!?、，,：:]+', re.I)
_INTENT_OPEN = re.compile(
    r'^\s*(?:(?:please\s+)?(?:i(?:\s+am|[\x27’]m)\s+looking\s+for|i\s+would\s+like\s+to\s+see|'
    r'do\s+we\s+have|can\s+you\s+pull\s+up|where\s+are(?:\s+those)?)(?a:\b)|'
    r'(?:请)?(?:我想看看|我想看|我想找|想找|想看|有没有|还有没有))\s*', re.I)
_DESCRIPTIVE_CORRECTIONS = (
    re.compile(r'^\s*not(?a:\b)\s*(?P<old>.+?)\s*[,，]?\s*but(?a:\b)\s*(?P<new>.+?)\s*$', re.I),
    re.compile(r'^\s*不是\s*(?P<old>.+?)\s*[，,]?\s*(?:而)?是\s*(?P<new>.+?)\s*$'),
)
_CORRECTION_EDGE = ' \t\r\n,，;；、。.!！?？:'
_DESCRIPTIVE_ADDITIONS = (
    re.compile(r'^\s*(?:please[ \t]+)?(?:also[ \t]+)?add[ \t]+(?P<target>.+?)[ \t]+(?:as[ \t]+(?:a|another)[ \t]+)?(?:visual[ \t]+)?clue[ \t]*[。.!！?？]*\s*$', re.I),
    re.compile(r'^\s*(?:please[ \t]+)?also[ \t]+(?:add|with)[ \t]+(?P<target>.+?)[ \t]*[。.!！?？]*\s*$', re.I),
    re.compile(r'^\s*(?:请)?再加上[ \t]*(?P<target>.+?)(?:(?:这条)?(?:视觉)?线索)?[ \t]*[。.!！?？]*\s*$'),
    re.compile(r'^\s*(?:请)?(?:加上|添加)[ \t]*(?P<target>.+?)(?:这条)?(?:视觉)?线索[ \t]*[。.!！?？]*\s*$'),
)
_DESCRIPTIVE_ADDITION_OPEN = re.compile(
    r'^\s*(?:(?:please[ \t]+)?(?:(?:also[ \t]+)?add(?a:\b)|also[ \t]+with(?a:\b))|(?:请)?(?:再加上|加上|添加))', re.I)
_ADDITION_COMPOUND = re.compile(
    r'(?a:\b)(?:and|or|both|together|then|but|instead|also|add|remove|drop|clear|'
    r'replace|delete|share|send|upload|rename|move|record|take a photo)(?a:\b)|'
    r'和|与|及|或者|一起|同时|然后|接着|但是|而是|移除|去掉|取消|清除|换成|改成|'
    r'添加|加上|删除|分享|发送|上传|重命名|移动|录音|拍照|照一下', re.I)
_STRONG_CONTENT_INTRO = re.compile(
    r'包含|含有|關於|关于|(?a:\b)(?:containing|contains|about|with the words)(?a:\b)', re.I)


def _strong_content_cue_before(words, boundary):
    outside_quotes = _QUOTE.sub(lambda match: ' ' * len(match.group(0)), words)
    return any(match.end() <= boundary for match in _STRONG_CONTENT_INTRO.finditer(outside_quotes))


def intent_mode(words):
    if type(words) is str and _DESCRIPTIVE_ADDITION_OPEN.match(words):
        return 'refine'
    if type(words) is str and _INTENT_OPEN.match(words):
        return 'search'
    return query_mode(words)


def _invalid():
    return ValueError('Invalid intent proposal')


def validate_proposal(value, query):
    """Validate a suggestion and derive surfaces from exact source offsets."""
    if type(value) is not dict or set(value) != {'version', 'status', 'concepts', 'question'}:
        raise _invalid()
    if type(value['version']) is not int or value['version'] != 1:
        raise _invalid()
    if type(value['status']) is not str or value['status'] not in ('ready', 'clarification', 'unsupported'):
        raise _invalid()
    if type(value['concepts']) is not list or len(value['concepts']) > 6:
        raise _invalid()
    if value['status'] != 'ready':
        if value['concepts'] or type(value['question']) is not str or value['question'] not in QUESTIONS:
            raise _invalid()
        return dict(value)
    if value['question'] is not None or not value['concepts']:
        raise _invalid()
    concepts = []
    end = 0
    for item in value['concepts']:
        if type(item) is not dict or set(item) != {'start', 'end', 'alternatives'}:
            raise _invalid()
        start, stop = item['start'], item['end']
        if type(start) is not int or type(stop) is not int or not end <= start < stop <= len(query):
            raise _invalid()
        surface = query[start:stop]
        if not _GRAMMAR.sub('', _strip_prefix(d.fold(surface))).strip():
            raise _invalid()
        concepts.append({'surface': surface, 'alternatives': item['alternatives']})
        end = stop
    description = normalize_description({'version': 1, 'concepts': concepts})
    return {**value, 'concepts': [dict(raw, surface=clean['surface'], alternatives=clean['alternatives'])
                                for raw, clean in zip(value['concepts'], description['concepts'])]}


def _hard_surface(query):
    return _QUOTE.sub(lambda match: ' ' * len(match.group(0)), query)


_GENERIC_CHILD_SELECTORS = frozenset(('children', '孩子们'))


def _kinship_hits(surface):
    """Find public selector words, without reading any private kinship graph."""
    unquoted = _hard_surface(surface)
    hits = []
    for alias in SELECTORS:
        pattern_text = re.escape(alias).replace(r'\ ', r'[ \t]+')
        if alias.isascii():
            pattern_text = r'(?<![a-z0-9_])' + pattern_text + r'(?![a-z0-9_])'
        pattern = re.compile(pattern_text, re.I | (re.A if alias.isascii() else 0))
        for match in pattern.finditer(unquoted):
            if alias in _GENERIC_CHILD_SELECTORS:
                before = unquoted[:match.start()]
                after = unquoted[match.end():]
                english_possessive = re.search(r'(?<![a-z0-9_])(?:my|our)[ \t]+$', before,
                                               re.I | re.A)
                chinese_possessive = re.search(r'(?:我的|我们的)[ \t]*$', before)
                possessive_suffix = re.match(r"[ \t]+of[ \t]+(?:mine|ours)(?![a-z0-9_])",
                                             after, re.I | re.A)
                if not (english_possessive or chinese_possessive or possessive_suffix):
                    continue
            hits.append((match.start(), match.end(), alias))
    return tuple(sorted(hits))


def _vague_date_hits(surface):
    unquoted = _hard_surface(surface)
    return tuple((match.start(), match.end(), match.group(0))
                 for match in _AGE_PHRASE.finditer(unquoted))


def _media(surface):
    return tuple(kind for kind, pattern in _MEDIA if pattern.search(d.fold(surface)))


def _descriptive_correction_parts(words):
    """Return exact paired correction surfaces without normalizing NEW."""
    for pattern in _DESCRIPTIVE_CORRECTIONS:
        match = pattern.fullmatch(words)
        if match is None:
            continue
        old = match.group('old').strip(_CORRECTION_EDGE)
        new = match.group('new').strip(_CORRECTION_EDGE)
        if old and new:
            return old, new
    return None


def _descriptive_removal_parts(words):
    """Return an exact stored-surface target from a closed removal command."""
    for pattern, quoted in _DESCRIPTIVE_REMOVALS:
        match = pattern.fullmatch(words)
        if match is not None:
            if quoted:
                target = match.group('target_ascii') or match.group('target_curly')
                span = (match.span('target_ascii') if match.group('target_ascii') is not None
                        else match.span('target_curly'))
                return target, span, True
            target = match.group('target_unquoted')
            if any(char in target for char in _REMOVAL_QUOTES):
                return None
            normalized = d.fold(target)
            if (normalized in _UNQUOTED_REMOVE_ALL or
                    _UNQUOTED_REMOVAL_CONNECTOR.search(normalized)):
                return None
            return target, match.span('target_unquoted'), False
    return None


def _removal_consumes_label(words, target_span, target, entities):
    """Do not let either command syntax or its quoted target shadow a label."""
    start, end = target_span
    target_only = (' ' * start) + words[start:end] + (' ' * (len(words) - end))
    labels = entities.get('labels', [])
    return (_consumed_label(d.fold(words), d.fold(target_only), labels) or
            _consumed_label(d.fold(target), ' ' * len(d.fold(target)), labels))


def _plan_descriptive_removal(target, *, previous, hard_previous):
    """Remove one uniquely named stored surface while retaining every other slot."""
    if previous is None or 'descriptive' not in previous:
        return QueryPlan(3, 'clarification', dict(previous or {}),
                         'description_removal_target_unavailable')
    from .search_text import normalize_text

    description = normalize_description(previous['descriptive'])
    key = normalize_text(target)
    matches = [index for index, concept in enumerate(description['concepts'])
               if normalize_text(concept['surface']) == key]
    if not matches:
        return QueryPlan(3, 'clarification', dict(previous), 'description_removal_mismatch')
    if len(matches) != 1:
        return QueryPlan(3, 'clarification', dict(previous), 'description_removal_ambiguous')
    concepts = [dict(concept) for index, concept in enumerate(description['concepts'])
                if index != matches[0]]
    filters = dict(hard_previous or {})
    if concepts:
        filters['descriptive'] = normalize_description({'version': 1, 'concepts': concepts})
    return QueryPlan(3, 'ready', filters)


def _correction_consumes_label(words, entities):
    """Keep paired syntax and stripped edge punctuation from shadowing labels."""
    for pattern in _DESCRIPTIVE_CORRECTIONS:
        match = pattern.fullmatch(words)
        if match is None:
            continue
        masked = [' '] * len(words)
        for name in ('old', 'new'):
            start, end = match.span(name)
            while start < end and words[start] in _CORRECTION_EDGE:
                start += 1
            while end > start and words[end - 1] in _CORRECTION_EDGE:
                end -= 1
            masked[start:end] = words[start:end]
        return _consumed_label(d.fold(words), d.fold(''.join(masked)),
                               entities.get('labels', []))
    return False


def _compile_plan(words, *, now, entities, previous_search, hard_previous,
                  refine, kept, planner):
    """Compile one source query through the closed descriptive-span checks."""
    grammar_words = _INTENT_OPEN.sub(lambda match: ' ' * len(match.group(0)), words)
    original = literal_plan(grammar_words, now=now, entities=entities,
                            previous_filters=hard_previous, refine=refine)
    quoted = list(_QUOTE.finditer(words))
    updates = literal_plan(grammar_words, now=now, entities=entities,
                           previous_filters={} if refine else None, refine=refine)
    outside_quotes = _QUOTE.sub(lambda match: ' ' * len(match.group(0)), grammar_words)
    date_spans = _vague_date_hits(grammar_words)
    explicit_content_literal = any(
        not any(match.start() < end and match.end() > start for start, end, _ in date_spans)
        for match in _STRONG_CONTENT_INTRO.finditer(outside_quotes))
    if original.status == 'ready' and ('text' not in updates.filters or quoted or
                                       explicit_content_literal):
        filters = dict(original.filters)
        if refine and 'descriptive' in kept:
            filters['descriptive'] = kept['descriptive']
        return QueryPlan(3, 'ready', filters)
    if original.status != 'ready' and original.reason not in ('unsupported_condition', 'missing_conditions',
                                                            'incomplete_people_relation'):
        return QueryPlan(3, 'clarification', kept, original.reason)
    # Age-relative time belongs to deterministic clarification, never to scene
    # extraction. Reviewed names and exact quoted words remain opaque here.
    age_surface = _remove_occurrences(d.fold(_hard_surface(grammar_words)),
                                      entities.get('labels', []))
    if _vague_date_hits(age_surface):
        return QueryPlan(3, 'clarification', kept, 'intent_date')
    if planner is None:
        return QueryPlan(3, 'clarification', kept, 'intent_unavailable')
    try:
        provider_words = scene_view(grammar_words, now.date(), entities.get('labels', []))
        suggestion = validate_proposal(
            planner.propose(provider_words, now.date().isoformat(), previous_search), provider_words)
    except IntentUnavailable:
        return QueryPlan(3, 'clarification', kept, 'intent_unavailable')
    except ValueError:
        return QueryPlan(3, 'clarification', kept, 'invalid_intent')
    if suggestion['status'] != 'ready':
        return QueryPlan(3, suggestion['status'], kept, 'intent_' + suggestion['question'])
    masked = list(grammar_words)
    for concept in suggestion['concepts']:
        start, stop = concept['start'], concept['end']
        if provider_words[start:stop] != words[start:stop]:
            return QueryPlan(3, 'clarification', kept, 'invalid_intent')
        if any(start < quote.end() and stop > quote.start() for quote in quoted):
            return QueryPlan(3, 'clarification', kept, 'invalid_intent')
        masked[start:stop] = ' ' * (stop - start)
    residue = ''.join(masked)
    if (_kinship_hits(grammar_words) != _kinship_hits(residue) or
            _vague_date_hits(grammar_words) != _vague_date_hits(residue)):
        return QueryPlan(3, 'clarification', kept, 'invalid_intent')
    original_surface, hard_surface = _hard_surface(words), _hard_surface(residue)
    labels = entities.get('labels', [])
    if _consumed_label(d.fold(original_surface), d.fold(hard_surface), labels):
        return QueryPlan(3, 'clarification', kept, 'invalid_intent')
    dates, _, date_error = _extract_dates(d.fold(original_surface), now.date())
    remaining_dates, _, remaining_error = _extract_dates(d.fold(hard_surface), now.date())
    if ((dates, date_error) != (remaining_dates, remaining_error)
            or _media(original_surface) != _media(hard_surface)
            or bool(_NEGATION.search(original_surface)) != bool(_NEGATION.search(hard_surface))):
        return QueryPlan(3, 'clarification', kept, 'invalid_intent')
    hard = (literal_plan(residue, now=now, entities=entities,
                         previous_filters=hard_previous, refine=refine) if residue.strip() else
            QueryPlan(1, 'ready', dict(hard_previous or {}) if refine else {}))
    if hard.status != 'ready' and hard.reason != 'missing_conditions':
        return QueryPlan(3, 'clarification', kept, hard.reason)
    filters = dict(hard.filters) if hard.status == 'ready' else dict(hard_previous or {}) if refine else {}
    filters['descriptive'] = {'version': 1, 'concepts': [
        {'surface': item['surface'], 'alternatives': item['alternatives']}
        for item in suggestion['concepts']]}
    return QueryPlan(3, 'ready', filters)


def _plan_descriptive_correction(old, new, *, now, entities, previous,
                                 hard_previous, planner):
    """Replace one exact saved descriptive surface, preserving all hard slots."""
    from .search_text import normalize_text

    prior_description = normalize_description(previous['descriptive'])
    old_key = normalize_text(old)
    matching = [index for index, concept in enumerate(prior_description['concepts'])
                if normalize_text(concept['surface']) == old_key]
    if not matching:
        return QueryPlan(3, 'clarification', dict(previous), 'description_correction_mismatch')
    if len(matching) != 1:
        return QueryPlan(3, 'clarification', dict(previous), 'description_correction_ambiguous')
    for part in (old, new):
        folded = d.fold(part)
        if _consumed_label(folded, ' ' * len(folded), entities.get('labels', [])):
            return QueryPlan(3, 'clarification', dict(previous), 'ambiguous_entities')
    if _QUOTE.search(new) or any(mark in new for mark in '“”"'):
        return QueryPlan(3, 'clarification', dict(previous), 'description_correction_unsupported')
    _, _, removed, references = _operations(new)
    if (_ACTION.match(new.strip()) or _REMOVAL.fullmatch(new.strip()) or removed or references):
        return QueryPlan(3, 'clarification', dict(previous), 'description_correction_unsupported')

    # Interpret NEW without inherited slots. Otherwise a phrase such as
    # "blue coat photos" could silently reassert a prior media filter and
    # appear descriptor-only merely because its value did not change.
    compiled = _compile_plan(new, now=now, entities=entities,
                             previous_search=False, hard_previous=None,
                             refine=False, kept={}, planner=planner)
    if compiled.status != 'ready':
        reason = compiled.reason
        if reason == 'intent_unavailable':
            return QueryPlan(3, 'clarification', dict(previous), reason)
        return QueryPlan(3, 'clarification', dict(previous),
                         'description_correction_unsupported')
    if set(compiled.filters) != {'descriptive'}:
        return QueryPlan(3, 'clarification', dict(previous), 'description_correction_unsupported')
    replacement = compiled.filters.get('descriptive')
    if type(replacement) is not dict or len(replacement.get('concepts', ())) != 1:
        return QueryPlan(3, 'clarification', dict(previous), 'description_correction_unsupported')
    concepts = [dict(concept) for concept in prior_description['concepts']]
    concepts[matching[0]] = replacement['concepts'][0]
    filters = dict(hard_previous or {})
    filters['descriptive'] = {'version': 1, 'concepts': concepts}
    try:
        filters['descriptive'] = normalize_description(filters['descriptive'])
    except ValueError:
        return QueryPlan(3, 'clarification', dict(previous), 'description_correction_unsupported')
    return QueryPlan(3, 'ready', filters)


def _plan_descriptive_addition(words, *, now, entities, previous,
                               hard_previous, planner):
    """Append one explicit visual clue without replacing saved conditions."""
    kept = dict(previous or {})

    def clarify(reason='description_addition_unsupported'):
        return QueryPlan(3, 'clarification', kept, reason)

    if previous is None:
        return clarify('description_addition_target_unavailable')
    _, entity_error = _entity_filters(entities)
    if entity_error:
        return clarify(entity_error)
    folded = d.fold(words)
    # Neither command grammar nor a new clue may consume a reviewed label.
    if _consumed_label(folded, ' ' * len(folded), entities.get('labels', [])):
        return clarify('ambiguous_entities')
    match = next((match for pattern in _DESCRIPTIVE_ADDITIONS
                  if (match := pattern.fullmatch(words)) is not None), None)
    if match is None:
        return clarify()
    target = match['target'].strip(_CORRECTION_EDGE)
    if not target or any(mark in target for mark in '“”"\r\n\t'):
        return clarify()
    _, _, removed, references = _operations(target)
    if (_ACTION.match(target) or _NEGATION.search(target) or _ADDITION_COMPOUND.search(target)
            or _REMOVAL.fullmatch(target)
            or removed or references or _kinship_hits(target)
            or _descriptive_correction_parts(target) is not None
            or intent_mode(target) in ('search', 'refine')
            or _DESCRIPTIVE_ADDITION_OPEN.match(target)):
        return clarify()
    prior = normalize_description(previous['descriptive'])['concepts'] if 'descriptive' in previous else []
    from .search_text import normalize_text
    if normalize_text(target) in {normalize_text(item['surface']) for item in prior}:
        return clarify('description_addition_duplicate')
    if len(prior) >= MAX_CONCEPTS:
        return clarify('description_addition_limit')
    # Compile in isolation: comparing only final inherited values would miss
    # a repeated hard condition such as "photos" when media is already image.
    compiled = _compile_plan(target, now=now, entities=entities,
                             previous_search=False, hard_previous=None,
                             refine=False, kept={}, planner=planner)
    if compiled.status != 'ready':
        return clarify(compiled.reason if compiled.reason in (
            'intent_unavailable', 'invalid_intent', 'intent_date',
            'ambiguous_entities', 'ambiguous_date_entity', 'ambiguous_media_entity',
            'invalid_date', 'conflicting_dates') else 'description_addition_unsupported')
    if set(compiled.filters) != {'descriptive'}:
        return clarify()
    added = compiled.filters['descriptive']['concepts']
    if len(added) != 1:
        return clarify()
    if normalize_text(added[0]['surface']) in {normalize_text(item['surface']) for item in prior}:
        return clarify('description_addition_duplicate')
    try:
        description = normalize_description({'version': 1, 'concepts': [*prior, added[0]]})
    except ValueError:
        return clarify()
    return QueryPlan(3, 'ready', {**(hard_previous or {}), 'descriptive': description})


def plan_query(words, *, now: datetime, entities, previous_filters, planner):
    """Plan v3 through current authorized entities and a separately supplied LLM.

    A supplied planner implements ``propose(query, today, has_previous_search)``.
    It receives no roster, captions, database, credentials or previous IDs.
    Invalid/unavailable suggestions ask for clarification and never broaden a
    search. Infrastructure exceptions from the supplied adapter remain opaque.
    """
    previous = previous_filters
    if (type(words) is not str or not words.strip() or not isinstance(now, datetime)
            or type(entities) is not dict):
        return QueryPlan(3, 'clarification', {}, 'invalid_query')
    try:
        if len(words.encode('utf-8', errors='strict')) > 1024:
            raise _invalid()
    except (UnicodeError, ValueError):
        return QueryPlan(3, 'clarification', {}, 'invalid_query')
    if previous is not None:
        if type(previous) is not dict:
            return QueryPlan(3, 'clarification', {}, 'invalid_previous_filters')
        hard_previous = {key: value for key, value in previous.items() if key != 'descriptive'}
        if not _valid_previous(hard_previous):
            return QueryPlan(3, 'clarification', {}, 'invalid_previous_filters')
        try:
            if 'descriptive' in previous:
                normalize_description(previous['descriptive'])
        except ValueError:
            return QueryPlan(3, 'clarification', {}, 'invalid_previous_filters')
    else:
        hard_previous = None
    if _DESCRIPTIVE_ADDITION_OPEN.match(words):
        return _plan_descriptive_addition(
            words, now=now, entities=entities, previous=previous,
            hard_previous=hard_previous, planner=planner)
    mode = intent_mode(words)
    refine = previous is not None and mode != 'search'
    kept = dict(previous or {}) if refine else {}
    if _REMOVAL.fullmatch(words.strip()):
        if previous is None:
            return QueryPlan(3, 'clarification', {}, 'refine_without_context')
        return QueryPlan(3, 'ready', {key: value for key, value in previous.items() if key != 'descriptive'})
    descriptive_removal = _descriptive_removal_parts(words)
    if descriptive_removal is not None:
        target, target_span, quoted = descriptive_removal
        # Preserve destructive/action classification ahead of the broader
        # unquoted transcription grammar.
        if not quoted and _ACTION.match(words.strip()):
            return QueryPlan(3, 'unsupported', kept, 'unsupported_action')
        _, entity_error = _entity_filters(entities)
        if entity_error:
            return QueryPlan(3, 'clarification', dict(previous or {}), entity_error)
        if _removal_consumes_label(words, target_span, target, entities):
            return QueryPlan(3, 'clarification', dict(previous or {}), 'ambiguous_entities')
        return _plan_descriptive_removal(target, previous=previous, hard_previous=hard_previous)
    if mode == 'refine' and previous is None:
        return QueryPlan(3, 'clarification', {}, 'refine_without_context')
    # Preserve the explicit capture/search uncertainty boundary.
    if _ACTION.match(words.strip()):
        return QueryPlan(3, 'unsupported', kept, 'unsupported_action')
    if _MALFORMED_DESCRIPTIVE_REMOVAL.fullmatch(words.strip()):
        return QueryPlan(3, 'clarification', dict(previous or {}), 'description_removal_unsupported')
    # Read-only conversational openings are grammar in v3 only. Keep their
    # offsets fixed for proposals, and refuse collisions with reviewed labels.
    grammar_words = _INTENT_OPEN.sub(lambda match: ' ' * len(match.group(0)), words)
    if _consumed_label(d.fold(words), d.fold(grammar_words), entities.get('labels', [])):
        return QueryPlan(3, 'clarification', kept, 'ambiguous_entities')
    correction = _descriptive_correction_parts(words)
    if correction is not None:
        old, new = correction
        if _correction_consumes_label(words, entities):
            return QueryPlan(3, 'clarification', dict(previous or {}), 'ambiguous_entities')
        # The v2 correction wrapper remains authoritative for media/date slot
        # updates and for invalid input, resolver, quote, and calendar errors.
        # Only its closed unsupported-correction result is eligible here.
        checked = literal_plan(words, now=now, entities=entities,
                               previous_filters=hard_previous, refine=refine)
        if checked.status == 'ready':
            filters = dict(checked.filters)
            if refine and 'descriptive' in kept:
                filters['descriptive'] = kept['descriptive']
            return QueryPlan(3, 'ready', filters)
        if checked.reason not in {'unsupported_correction', 'unsupported_condition',
                                  'unsupported_negation'}:
            return QueryPlan(3, 'clarification', dict(previous or {}), checked.reason)
        if previous is None or 'descriptive' not in previous:
            return QueryPlan(3, 'clarification', dict(previous or {}),
                             'description_correction_target_unavailable')
        return _plan_descriptive_correction(
            old, new, now=now, entities=entities, previous=previous,
            hard_previous=hard_previous, planner=planner)

    return _compile_plan(words, now=now, entities=entities,
                         previous_search=previous is not None,
                         hard_previous=hard_previous, refine=refine,
                         kept=kept, planner=planner)
