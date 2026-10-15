"""Explicit slot removal and grounded people references in search contexts.

Removal phrases are syntax only outside quotes. They never mean excluding a
person or deleting data, and never reset another constraint implicitly.
"""
import re

from . import discovery as d
from .assistant_query_plan import QueryPlan, plan_query as _plan_query, query_mode as _query_mode
from .assistant_query_plan import _QUOTE, _consumed_label, _remove_occurrences


_SLOTS = {
    'date': ('date', '日期', '时间', ('any date', 'all dates', 'any time', 'all time')),
    'people': ('people', '人物', None, ('anyone', 'any person', 'all people')),
    'locations': ('location', '地点', None, ('anywhere', 'any location')),
    'tags': ('tag', '标签', None, ('any tag',)),
    'text': ('text', '内容', '文字', ('any text',)),
    'media': ('media type', '类型', None, ('any media type',)),
}


def _pattern(english, chinese, alternate, short):
    nouns = '|'.join(re.escape(value) for value in (chinese, alternate) if value)
    phrases = '|'.join(re.escape(value) for value in short)
    return re.compile(
        rf'(?<![a-z0-9_])(?:(?:remove|clear)\s+(?:the\s+)?{re.escape(english)}\s+filter|{phrases})(?![a-z0-9_])'
        rf'|(?:不限(?:{nouns})|取消(?:{nouns})筛选|清除(?:{nouns})筛选)', re.I)


_REMOVALS = {slot: _pattern(*values) for slot, values in _SLOTS.items()}
_SEPARATORS = re.compile(r'^[\s,，;；、。.!！?？]+|[\s,，;；、。.!！?？]+$')

# These words refer only to the explicit people filter of a revalidated search.
# They never select people from visible faces, gender, a roster or kinship data.
_REFERENCE_FORMS = {
    'group': (r'same\s+people', r'同一批人'),
    'plural': (r'these\s+people|those\s+people|them|they|their', r'他们|她们|这些人|那些人'),
    # Chinese exclusions are lexical compounds, not a semantic guess about
    # the surrounding sentence. Keep a standalone 他 available as a reference.
    'singular': (r'he|she|same\s+person|him|her|his',
                 r'这个人|那个人|(?<![吉其利排])他(?!人)|她'),
}
_PEOPLE_REFERENCES = re.compile('|'.join(
    rf'(?P<{kind}>(?<![a-z0-9_])(?:{english})(?![a-z0-9_])|{chinese})'
    for kind, (english, chinese) in _REFERENCE_FORMS.items()), re.I)
_JOIN = r'(?:and(?![a-z0-9_])|和)'
_PEOPLE_ANSWER_RELATIONS = re.compile(
    r'(?<![a-z0-9_])(?:and|or|both|together)(?![a-z0-9_])|和|与|及|或者|或|一起|同时', re.I)

_CORRECTION_INTRO = re.compile(
    r'^(?:(?:no(?:\s*[,，:：]\s*|\s+))?i\s+meant(?a:\b)|'
    r'actually(?a:\b)\s*[,，:：]?(?:\s*我说的是)?|(?:不对\s*[,，:：]?\s*)?我说的是)\s*', re.I)
_CORRECTION_PAIRS = (
    re.compile(r'^not(?a:\b)\s*(?P<old>.*?)\s*[,，]?\s*(?a:\b)but(?a:\b)\s*(?P<new>.*)$', re.I),
    re.compile(r'^不是\s*(?P<old>.*?)\s*(?:[,，]\s*(?:而)?是|而是|是)\s*(?P<new>.*)$'),
)


def _correction_parts(words):
    """Recognize only anchored correction forms; conditions remain untrusted."""
    surface = d.fold(words.strip())
    intro = _CORRECTION_INTRO.match(surface)
    if intro:
        spans = [None, (intro.end(), len(surface))]
    else:
        pair = next((match for pattern in _CORRECTION_PAIRS
                     if (match := pattern.fullmatch(surface)) is not None), None)
        if pair is None:
            return None
        spans = [pair.span('old'), pair.span('new')]
    masked = list(' ' * len(surface))
    for span in spans:
        if span is not None:
            start, end = span
            masked[start:end] = surface[start:end]
    parts = [None if span is None else _SEPARATORS.sub('', surface[span[0]:span[1]])
             for span in spans]
    return surface, ''.join(masked), *parts


def _plan_correction(words, parts, *, now, entities, previous_filters, refine):
    if not refine or previous_filters is None:
        return QueryPlan(1, 'clarification', {}, 'refine_without_context')
    original = _plan_query(words, now=now, entities=entities,
                           previous_filters=previous_filters, refine=True)
    # Paired corrections intentionally mention two values and a negation.
    # Input/quote/entity/context/calendar failures must remain authoritative.
    syntax_errors = {'unsupported_condition', 'unsupported_negation',
                     'incomplete_people_relation', 'conflicting_media', 'conflicting_dates'}
    if original.status != 'ready' and original.reason not in syntax_errors:
        return original

    def clarify(reason):
        return QueryPlan(1, 'clarification', dict(previous_filters), reason)

    surface, masked, old, new = parts
    if _consumed_label(surface, masked, entities.get('labels', [])):
        return clarify('ambiguous_entities')
    replacements = []
    for condition in (new,) if old is None else (old, new):
        operations = _operations(condition)
        if operations[2] or operations[3]:
            return clarify('unsupported_correction')
        planned = _plan_query(condition, now=now, entities=entities,
                              previous_filters={}, refine=True)
        if planned.status != 'ready':
            return clarify(planned.reason)
        # This is a single media/date replacement, not an exclusion, person
        # change, removal, scene rewrite or a multi-slot conversation reset.
        if len(planned.filters) != 1 or not set(planned.filters) <= {'media', 'date'}:
            return clarify('unsupported_correction')
        replacements.append(planned.filters)
    update = replacements[-1]
    slot = next(iter(update))
    if old is not None and set(replacements[0]) != {slot}:
        return clarify('unsupported_correction')
    if slot not in previous_filters:
        return clarify('correction_target_unavailable')
    if old is not None and replacements[0][slot] != previous_filters[slot]:
        return clarify('correction_mismatch')
    return QueryPlan(1, 'ready', {**previous_filters, **update})


def _operations(words):
    # Replace quotes with equal-length blanks so all masks share offsets.
    surface = d.fold(words)
    surface = _QUOTE.sub(lambda match: ' ' * len(match.group(0)), surface)
    spans = sorted((match.start(), match.end(), slot)
                   for slot, pattern in _REMOVALS.items() for match in pattern.finditer(surface))
    references = [(match.start(), match.end(), match.lastgroup)
                  for match in _PEOPLE_REFERENCES.finditer(surface)]
    residue = list(surface)
    for start, end, _ in spans + references:
        residue[start:end] = ' ' * (end - start)
    # An AND joins two removal commands only when it lies wholly between
    # them. Other conjunctions remain conditions for the ordinary planner.
    for (_, end, _), (start, _, _) in zip(spans, spans[1:]):
        if re.fullmatch(r'\s*(?:and|和|并且|并|且)\s*', surface[end:start], re.I):
            residue[end:start] = ' ' * (start - end)
    # AND next to a reference joins a refinement condition, not a new person.
    # Explicit new people are rejected separately; unknown residue stays intact.
    for start, end, _ in references:
        after = re.match(rf'\s*{_JOIN}\s*', surface[end:], re.I)
        if after:
            residue[end:end + after.end()] = ' ' * after.end()
        before = re.search(rf'(?<![a-z0-9_]){_JOIN}\s*$', surface[:start], re.I)
        if before:
            residue[before.start():start] = ' ' * (start - before.start())
    return surface, ''.join(residue), {slot for _, _, slot in spans}, references


def plan_people_answer(words, *, now, entities, previous_filters):
    """Accept a complete reviewed-people answer against a validated search.

    This handles only a bare people-slot replacement. A prior search is
    required, and multi-person answers must state how the people are related.
    Other query shapes remain for the ordinary planner to interpret.
    """
    if type(words) is not str or not words.strip() or type(entities) is not dict:
        return None
    groups = entities.get('groups')
    if type(groups) is not dict or not groups.get('people'):
        return None

    # Preserve the ordinary planner's input, entity, quote, date/media and
    # context checks before considering this narrow conversational shortcut.
    original = _plan_query(words, now=now, entities=entities,
                           previous_filters=previous_filters, refine=True)
    if original.status != 'ready':
        if original.reason in {'unsupported_condition', 'unsupported_negation',
                               'incomplete_people_relation', 'conflicting_people_mode'}:
            return None
        return original

    # Openings and quoted literals belong to normal search/content handling,
    # even when the resolver also found a reviewed name in the text.
    if _QUOTE.search(words) or any(mark in words for mark in '“”"') or _query_mode(words):
        return None
    if groups.get('tags') or groups.get('locations'):
        return None

    surface = d.fold(words.strip())
    relation_only_mask = _PEOPLE_ANSWER_RELATIONS.sub(
        lambda match: ' ' * len(match.group(0)), surface)
    if _consumed_label(surface, relation_only_mask, entities.get('labels', [])):
        return QueryPlan(1, 'clarification', dict(previous_filters or {}), 'ambiguous_entities')
    residue = _remove_occurrences(surface, entities.get('labels', []))
    relations = list(_PEOPLE_ANSWER_RELATIONS.finditer(residue))
    relation_mask = _PEOPLE_ANSWER_RELATIONS.sub(lambda match: ' ' * len(match.group(0)), residue)
    residue = _SEPARATORS.sub('', relation_mask)
    if residue.strip():
        return None

    people = original.filters.get('people')
    if type(people) is not dict or not people.get('ids'):
        return None
    if len(people['ids']) > 1 and not relations:
        return QueryPlan(1, 'clarification', dict(previous_filters or {}),
                         'ambiguous_people_answer')

    # The exact phrase must resolve only the people slot. In particular,
    # dates, media, scenes, tags and locations cannot hitch a ride here.
    expected = dict(previous_filters or {})
    expected['people'] = people
    if original.filters != expected:
        return None
    return QueryPlan(1, 'ready', expected)


def query_mode(words):
    if type(words) is not str:
        return _query_mode(words)
    if _correction_parts(words) is not None:
        return 'refine'
    operations = _operations(words)
    if operations[3]:
        return 'refine'
    mode = _query_mode(words)
    if mode is not None:
        return mode
    # An explicit removal is a read-only refinement. Unknown residue is still
    # validated by plan_query; detecting a command does not authorize a guess.
    return 'refine' if operations[2] else None


def plan_query(words, *, now, entities, previous_filters, refine):
    if type(words) is not str or len(words) > 1024:
        return _plan_query(words, now=now, entities=entities,
                           previous_filters=previous_filters, refine=refine)
    correction = _correction_parts(words)
    if correction is not None:
        return _plan_correction(words, correction, now=now, entities=entities,
                                previous_filters=previous_filters, refine=refine)
    surface, residue, removed, references = _operations(words)
    if not removed and not references:
        return _plan_query(words, now=now, entities=entities,
                           previous_filters=previous_filters, refine=refine)
    if not refine or previous_filters is None:
        return QueryPlan(1, 'clarification', {}, 'refine_without_context')
    # Validate original input limits, quotes, resolver data and context before
    # considering any transformed string. Most expected errors remain errors;
    # unsupported syntax is precisely the case handled by this wrapper.
    original = _plan_query(words, now=now, entities=entities,
                           previous_filters=previous_filters, refine=refine)
    if original.status != 'ready' and original.reason not in {'unsupported_condition', 'unsupported_negation',
                               'incomplete_people_relation'}:
        return original
    if _consumed_label(surface, residue, entities.get('labels', [])):
        return QueryPlan(1, 'clarification', dict(previous_filters), 'ambiguous_entities')
    if references:
        if 'people' in removed or entities['groups'].get('people'):
            return QueryPlan(1, 'clarification', dict(previous_filters), 'conflicting_people_reference')
        people = previous_filters.get('people')
        if people is None:
            return QueryPlan(1, 'clarification', dict(previous_filters), 'people_reference_unavailable')
        count = len(people['ids'])
        if len(references) > 1 or any((kind == 'singular' and count != 1) or (kind == 'plural' and count < 2)
               for _, _, kind in references):
            return QueryPlan(1, 'clarification', dict(previous_filters), 'ambiguous_people_reference')
    # Apply masks to the original string to preserve literal case/bytes.
    # NFKC can change offsets, so use folded text for syntax then restore the
    # quoted literal from the validated original input after planning.
    literal = _QUOTE.search(words)
    if literal is not None:
        # Quotes were blanked by _operations. Reinsert the original literal at
        # the end with the planner's explicit content introducer.
        residue += ' containing "' + literal.group(1) + '"'
    residue = _SEPARATORS.sub('', residue)
    planned = _plan_query(residue or 'refine', now=now, entities=entities,
                          previous_filters=previous_filters, refine=True)
    if planned.status != 'ready':
        return planned
    # A command cannot both remove and replace a slot. Build a second plan
    # without inherited slots to distinguish explicit updates from unchanged
    # previous values (including an identical replacement).
    updates = _plan_query(residue or 'refine', now=now, entities=entities,
                          previous_filters={}, refine=True)
    if updates.status != 'ready':
        return updates
    if removed.intersection(updates.filters):
        return QueryPlan(1, 'clarification', dict(previous_filters), 'conflicting_refinement')
    return QueryPlan(1, 'ready', {key: value for key, value in planned.filters.items() if key not in removed})
