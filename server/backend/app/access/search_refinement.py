"""Explicit slot removal and grounded people references in search contexts.

Removal phrases are syntax only outside quotes. They never mean excluding a
person or deleting data, and never reset another constraint implicitly.
"""
import re

from . import discovery as d
from .assistant_query_plan import QueryPlan, plan_query as _plan_query, query_mode as _query_mode
from .assistant_query_plan import _QUOTE, _consumed_label


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
    'singular': (r'same\s+person|him|her|his', r'这个人|那个人|他|她'),
}
_PEOPLE_REFERENCES = re.compile('|'.join(
    rf'(?P<{kind}>(?<![a-z0-9_])(?:{english})(?![a-z0-9_])|{chinese})'
    for kind, (english, chinese) in _REFERENCE_FORMS.items()), re.I)
_JOIN = r'(?:and(?![a-z0-9_])|和)'


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


def query_mode(words):
    if type(words) is not str:
        return _query_mode(words)
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
