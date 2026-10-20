"""Strict private state for bounded date and description clarifications.

This module recognizes a closed set of literal age/vague-time phrases and
resolves only a date answer. It does not inspect people, captions, or media,
call a model, or rewrite the original query. A caller must independently bind
the pending object to its authenticated thread and fresh source snapshot.
Description continuations bind the exact prior v3 result context by digest.
"""
from datetime import date, datetime
import hashlib
import json
import re

from . import discovery as d
from .assistant_query_plan import _QUOTE, _consumed_label, _extract_dates
from .search_refinement import plan_query as literal_plan


PENDING_TTL_SECONDS = 15 * 60
_MAX_QUERY_BYTES = 1024
_BINDING = re.compile(r'[0-9a-f]{64}')
_LEGACY_AGE_PHRASE = re.compile(
    r'(?P<english>(?ai:(?<![a-z0-9_])(?:from[ \t]+childhood|childhood|'
    r'when[ \t]+younger|a[ \t]+long[ \t]+time[ \t]+ago)(?![a-z0-9_])))'
    r'|(?P<chinese>小时候|儿时|小的时候|很久以前|好久以前)', re.I)
_V2_AGE_PHRASE = re.compile(
    r'(?P<english>(?ai:(?<![a-z0-9_])(?:'
    r'(?:maybe|about|around)[ \t]+(?:one|two|three|a[ \t]+few|[1-3])'
    r'[ \t]+(?:summers|winters|years)[ \t]+ago|'
    r'from[ \t]+childhood|childhood|when[ \t]+younger|'
    r'a[ \t]+long[ \t]+time[ \t]+ago)(?![a-z0-9_])))'
    r'|(?P<chinese>(?:大概|可能)(?:是|在)?[ \t]*(?:[1-3]|一|二|两|三)[ \t]*年[ \t]*前|'
    r'前(?:[1-3]|一|二|两|三|几)年|前些年|小时候|儿时|小的时候|很久以前|好久以前)', re.I)
_AGE_PHRASE = re.compile(
    r'(?P<english>(?ai:(?<![a-z0-9_])(?:'
    r'(?:maybe|about|around)[ \t]+(?:one|two|three|a[ \t]+few|[1-3])'
    r'[ \t]+(?:summers|winters|years)[ \t]+ago|'
    r'from[ \t]+childhood|childhood|when[ \t]+younger|'
    r'a[ \t]+long[ \t]+time[ \t]+ago|long[ \t]+ago)(?![a-z0-9_])))'
    r'|(?P<chinese>(?:大概|可能)(?:是|在)?[ \t]*(?:[1-3]|一|二|两|三)[ \t]*年[ \t]*前|'
    r'前(?:[1-3]|一|二|两|三|几)年|前些年|小时候|儿时|小的时候|很久以前|好久以前)', re.I)
_QUOTE_MARKS = frozenset(('"', '“', '”'))
def _invalid():
    return ValueError('Invalid pending date')


def _query(value):
    if type(value) is not str or not value.strip():
        raise _invalid()
    try:
        raw = value.encode('utf-8', errors='strict')
    except UnicodeError:
        raise _invalid() from None
    if len(raw) > _MAX_QUERY_BYTES or any(
            ord(char) < 32 and char not in '\n\t' or ord(char) == 127
            for char in value):
        raise _invalid()
    # Offsets in the private object are Python code-point offsets. NFKC or
    # case-fold expansions would make normalized offsets unsafe to persist.
    folded = d.fold(value)
    if len(folded) != len(value):
        raise _invalid()
    return folded


def _quote_mask(query):
    masked = list(query)
    quotes = list(_QUOTE.finditer(query))
    for match in quotes:
        masked[match.start():match.end()] = ' ' * (match.end() - match.start())
    residue = ''.join(masked)
    if any(mark in residue for mark in _QUOTE_MARKS):
        return residue, quotes, False
    return residue, quotes, True


def _has_explicit_date(text, today):
    dates, _residue, error = _extract_dates(text, today)
    return bool(dates) or error is not None


def find_date_slot(query, entities, now):
    """Return the sole eligible vague-time phrase's exact ``(start, end)``.

    Invalid queries, competing phrases, any recognized date, quote overlap,
    or a phrase consumed as a reviewed label produce ``None``. ``entities`` is
    an already-authorized resolver result; only its bounded ``labels`` field
    is inspected. ``now`` supplies the civil date for relative-date checks.
    """
    if not isinstance(now, datetime) or type(entities) is not dict:
        return None
    today = now.date()
    labels = entities.get('labels', [])
    if type(labels) is not list or any(type(label) is not str for label in labels):
        return None
    try:
        folded = _query(query)
    except ValueError:
        return None
    outside, quotes, quotes_valid = _quote_mask(query)
    if not quotes_valid:
        return None
    spans = [(match.start(), match.end()) for match in _AGE_PHRASE.finditer(query)]
    # More than one candidate is ambiguous even if one candidate is quoted.
    if len(spans) != 1 or _has_explicit_date(d.fold(outside), today):
        return None
    start, end = spans[0]
    if any(start < quote.end() and end > quote.start() for quote in quotes):
        return None
    residue = list(folded)
    residue[start:end] = ' ' * (end - start)
    if _consumed_label(folded, ''.join(residue), labels):
        return None
    return start, end


def make_pending(query, slot, binding, created_at):
    """Create a strict private date-pending object or refuse the query."""
    if (type(binding) is not str or _BINDING.fullmatch(binding) is None or
            type(created_at) is not int or created_at < 0):
        raise _invalid()
    if (type(slot) is not tuple or len(slot) != 2 or
            type(slot[0]) is not int or type(slot[1]) is not int):
        raise _invalid()
    return validate_pending({
        'version': 3,
        'question': 'date',
        'query': query,
        'start': slot[0],
        'end': slot[1],
        'binding': binding,
        'created_at': created_at,
    })


def description_context_digest(context):
    """Hash the exact private v3 result context used by a description question."""
    if (type(context) is not dict or
            set(context) not in ({'library_id', 'binding', 'fingerprint', 'filters',
                                 'visible_ids', 'total', 'search_version'},
                                {'library_id', 'binding', 'fingerprint', 'filters',
                                 'visible_ids', 'total'})):
        raise _invalid()
    if (type(context.get('library_id')) is not str or not context['library_id'] or
            type(context.get('binding')) is not str or
            _BINDING.fullmatch(context['binding']) is None or
            type(context.get('fingerprint')) is not str or
            _BINDING.fullmatch(context['fingerprint']) is None or
            type(context.get('filters')) is not dict or
            type(context.get('visible_ids')) is not list or
            any(type(ident) is not str for ident in context['visible_ids']) or
            type(context.get('total')) is not int or context['total'] < 0 or
            ('search_version' in context and context['search_version'] != 3)):
        raise _invalid()
    try:
        encoded = json.dumps(context, ensure_ascii=False, sort_keys=True,
                             separators=(',', ':'), allow_nan=False).encode('utf-8')
    except (TypeError, ValueError, UnicodeError):
        raise _invalid() from None
    return hashlib.sha256(encoded).hexdigest()


def make_description_pending(query, binding, context, created_at):
    """Create a private pending description question bound to one v3 result."""
    if (type(binding) is not str or _BINDING.fullmatch(binding) is None or
            type(created_at) is not int or created_at < 0):
        raise _invalid()
    if (type(context) is not dict or context.get('search_version') != 3 or
            context.get('binding') != binding):
        raise _invalid()
    return validate_pending({
        'version': 1,
        'question': 'description',
        'query': query,
        'binding': binding,
        'context_digest': description_context_digest(context),
        'created_at': created_at,
    })


def _exclusion_query(value):
    """Validate an original query without normalizing away its exact surface."""
    if type(value) is not str or not value.strip():
        raise _invalid()
    try:
        if len(value.encode('utf-8', errors='strict')) > _MAX_QUERY_BYTES:
            raise _invalid()
    except UnicodeError:
        raise _invalid() from None
    if any(ord(char) < 32 and char not in '\n\t' or ord(char) == 127
           for char in value):
        raise _invalid()
    return value


def exclusion_context_digest(context):
    """Hash the exact prior v2/v3 context, including the absence of one."""
    if context is not None:
        fields = {'library_id', 'binding', 'fingerprint', 'filters',
                  'visible_ids', 'total'}
        if (type(context) is not dict or
                set(context) - {'search_version'} != fields or
                ('search_version' in context and
                 (type(context['search_version']) is not int or
                  context['search_version'] not in (2, 3))) or
                type(context.get('library_id')) is not str or not context['library_id'] or
                type(context.get('binding')) is not str or
                _BINDING.fullmatch(context['binding']) is None or
                type(context.get('fingerprint')) is not str or
                _BINDING.fullmatch(context['fingerprint']) is None or
                type(context.get('filters')) is not dict or
                type(context.get('visible_ids')) is not list or
                any(type(ident) is not str for ident in context['visible_ids']) or
                type(context.get('total')) is not int or context['total'] < 0):
            raise _invalid()
    try:
        encoded = json.dumps(context, ensure_ascii=False, sort_keys=True,
                             separators=(',', ':'), allow_nan=False).encode('utf-8')
    except (TypeError, ValueError, UnicodeError):
        raise _invalid() from None
    return hashlib.sha256(encoded).hexdigest()


def make_exclusion_pending(query, binding, context, created_at):
    """Create private state for one unsupported exclusion clarification."""
    if (type(binding) is not str or _BINDING.fullmatch(binding) is None or
            type(created_at) is not int or created_at < 0):
        raise _invalid()
    if context is not None:
        exclusion_context_digest(context)
        if context.get('binding') != binding:
            raise _invalid()
    return validate_pending({
        'version': 1,
        'question': 'exclusion',
        'query': query,
        'binding': binding,
        'context_digest': exclusion_context_digest(context),
        'created_at': created_at,
    })


def validate_pending(value):
    """Validate private pending structure without applying its expiry."""
    if type(value) is dict and value.get('question') == 'exclusion':
        fields = {'version', 'question', 'query', 'binding', 'context_digest', 'created_at'}
        if (set(value) != fields or type(value['version']) is not int or
                value['version'] != 1 or type(value['question']) is not str or
                type(value['created_at']) is not int or value['created_at'] < 0 or
                type(value['binding']) is not str or
                _BINDING.fullmatch(value['binding']) is None or
                type(value['context_digest']) is not str or
                _BINDING.fullmatch(value['context_digest']) is None):
            raise _invalid()
        _exclusion_query(value['query'])
        return dict(value)
    if type(value) is dict and value.get('question') == 'description':
        fields = {'version', 'question', 'query', 'binding', 'context_digest', 'created_at'}
        if (set(value) != fields or type(value['version']) is not int or
                value['version'] != 1 or type(value['question']) is not str or
                type(value['query']) is not str or type(value['created_at']) is not int or
                value['created_at'] < 0 or type(value['binding']) is not str or
                _BINDING.fullmatch(value['binding']) is None or
                type(value['context_digest']) is not str or
                _BINDING.fullmatch(value['context_digest']) is None):
            raise _invalid()
        try:
            _query(value['query'])
        except ValueError:
            raise _invalid() from None
        return dict(value)
    fields = {'version', 'question', 'query', 'start', 'end', 'binding', 'created_at'}
    if type(value) is not dict or set(value) != fields:
        raise _invalid()
    if (type(value['version']) is not int or value['version'] not in (1, 2, 3) or
            value['question'] != 'date' or type(value['question']) is not str or
            type(value['start']) is not int or type(value['end']) is not int or
            type(value['created_at']) is not int or value['created_at'] < 0 or
            type(value['binding']) is not str or _BINDING.fullmatch(value['binding']) is None):
        raise _invalid()
    try:
        folded = _query(value['query'])
    except ValueError:
        raise _invalid() from None
    start, end = value['start'], value['end']
    if not 0 <= start < end <= len(value['query']):
        raise _invalid()
    outside, quotes, quotes_valid = _quote_mask(value['query'])
    age_phrase = {1: _LEGACY_AGE_PHRASE, 2: _V2_AGE_PHRASE, 3: _AGE_PHRASE}[value['version']]
    spans = [(match.start(), match.end()) for match in age_phrase.finditer(value['query'])]
    if (not quotes_valid or len(spans) != 1 or spans[0] != (start, end) or
            any(start < quote.end() and end > quote.start() for quote in quotes) or
            _has_explicit_date(d.fold(outside), date(2000, 1, 1))):
        raise _invalid()
    return dict(value)


def current_pending(value, now):
    """Return valid pending data within its age limit; clock rollback refuses."""
    try:
        state = validate_pending(value)
    except ValueError:
        return None
    if (type(now) is not int or now < state['created_at'] or
            now - state['created_at'] > PENDING_TTL_SECONDS):
        return None
    return state


def resolve_date_answer(pending, answer, now, entities):
    """Resolve only a date-only answer and blank its original vague-time slot.

    The return query has exactly the original length, with the question slot
    replaced by spaces. The answer is never concatenated into or written over
    the original query. The caller keeps ``date`` as a separate hard filter.
    """
    try:
        state = validate_pending(pending)
        _query(answer)
    except ValueError:
        return None
    if type(entities) is not dict:
        return None
    enabled = entities.get('enabled')
    if (not isinstance(now, datetime) or type(entities.get('ambiguous')) is not bool or
            entities['ambiguous'] or type(enabled) is not list or
            any(type(item) is not str for item in enabled) or 'date' not in enabled or
            not answer.strip()):
        return None
    plan = literal_plan(answer, now=now, entities=entities,
                       previous_filters=None, refine=False)
    if plan.status != 'ready' or set(plan.filters) != {'date'}:
        return None
    masked = list(state['query'])
    masked[state['start']:state['end']] = ' ' * (state['end'] - state['start'])
    return ''.join(masked), dict(plan.filters['date'])
