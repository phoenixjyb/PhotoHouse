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
from .assistant_query_plan import (QueryPlan, _QUOTE, _MEDIA, _NEGATION, _extract_dates,
                                   _consumed_label, _valid_previous, _strip_prefix)
from .kinship import SELECTORS
from .search_refinement import plan_query as literal_plan, query_mode
from .search_description import normalize_description
from .search_pending import _AGE_PHRASE

POLICY_VERSION = 1
QUESTIONS = frozenset(('date', 'person', 'description', 'scope', 'unsupported_action'))


class IntentUnavailable(RuntimeError):
    def __init__(self):
        super().__init__('Local intent planning unavailable')


_REMOVAL = re.compile(r'^(?:any description|clear (?:the )?description filter|不限描述|不限场景)[。.!！?？]*$', re.I)
_ACTION = re.compile(r'^(?:delete|remove all|share|send|upload|rename|move|record|take a photo|'
                     r'删除|分享|发送|上传|重命名|移动|录音|拍照|照一下)(?a:\b)|^(?:删除|分享|发送|上传|重命名|移动|录音|拍照|照一下)', re.I)
_GRAMMAR = re.compile(r'(?a:\b)(?:the|a|an|of|in|on|at|by|from|during|taken|please|me|for|and|or|both|together|with)(?a:\b)|'
                      r'请|麻烦|帮忙|帮我|替我|我想|能不能|可以|一下|的|那些|一些|里面|有关|关于|在|于|呢|吗|和|与|及|或|一起|同时|[\s。！？.!?、，,：:]+', re.I)
_INTENT_OPEN = re.compile(
    r'^\s*(?:(?:please\s+)?(?:i(?:\s+am|[\x27’]m)\s+looking\s+for|i\s+would\s+like\s+to\s+see|'
    r'do\s+we\s+have|can\s+you\s+pull\s+up|where\s+are(?:\s+those)?)(?a:\b)|'
    r'(?:请)?(?:我想看看|我想看|我想找|想找|想看|有没有|还有没有))\s*', re.I)


def intent_mode(words):
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
    mode = intent_mode(words)
    if mode == 'refine' and previous is None:
        return QueryPlan(3, 'clarification', {}, 'refine_without_context')
    refine = previous is not None and mode != 'search'
    kept = dict(previous or {}) if refine else {}
    if _REMOVAL.fullmatch(words.strip()):
        if previous is None:
            return QueryPlan(3, 'clarification', {}, 'refine_without_context')
        return QueryPlan(3, 'ready', {key: value for key, value in previous.items() if key != 'descriptive'})
    # Preserve the explicit capture/search uncertainty boundary.
    if _ACTION.match(words.strip()):
        return QueryPlan(3, 'unsupported', kept, 'unsupported_action')
    # Read-only conversational openings are grammar in v3 only. Keep their
    # offsets fixed for proposals, and refuse collisions with reviewed labels.
    grammar_words = _INTENT_OPEN.sub(lambda match: ' ' * len(match.group(0)), words)
    if _consumed_label(d.fold(words), d.fold(grammar_words), entities.get('labels', [])):
        return QueryPlan(3, 'clarification', kept, 'ambiguous_entities')
    original = literal_plan(grammar_words, now=now, entities=entities,
                            previous_filters=hard_previous, refine=refine)
    quoted = list(_QUOTE.finditer(words))
    updates = literal_plan(grammar_words, now=now, entities=entities,
                           previous_filters={} if refine else None, refine=refine)
    if original.status == 'ready' and ('text' not in updates.filters or quoted):
        filters = dict(original.filters)
        if refine and 'descriptive' in kept:
            filters['descriptive'] = kept['descriptive']
        return QueryPlan(3, 'ready', filters)
    if original.status != 'ready' and original.reason not in ('unsupported_condition', 'missing_conditions',
                                                            'incomplete_people_relation'):
        return QueryPlan(3, 'clarification', kept, original.reason)
    if planner is None:
        return QueryPlan(3, 'clarification', kept, 'intent_unavailable')
    try:
        suggestion = validate_proposal(planner.propose(words, now.date().isoformat(), previous is not None), words)
    except IntentUnavailable:
        return QueryPlan(3, 'clarification', kept, 'intent_unavailable')
    except ValueError:
        return QueryPlan(3, 'clarification', kept, 'invalid_intent')
    if suggestion['status'] != 'ready':
        return QueryPlan(3, suggestion['status'], kept, 'intent_' + suggestion['question'])
    masked = list(grammar_words)
    for concept in suggestion['concepts']:
        start, stop = concept['start'], concept['end']
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
