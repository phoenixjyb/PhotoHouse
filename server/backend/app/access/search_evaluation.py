"""Bounded, private relevance evaluation for the local assistant search CLI.

This module accepts expected behavior and private queries from its caller, runs
the ordinary read-only assistant turn against a bound SearchRuntime, and returns
only aggregate metrics and per-case check outcomes. It has no persistence or
media/speech path.
"""
import json
import math
import re
import time

from . import discovery as d

_CASE_ID = re.compile(r'[A-Za-z0-9_-]{1,64}', re.ASCII)
_EXPECT_FIELDS = frozenset(('kind', 'filters', 'top_ids', 'relevant_ids',
                            'absent_ids', 'total', 'effect'))
_KINDS = frozenset(('results', 'open', 'clarification', 'unsupported'))
_REPORT_FIELDS = ('kind', 'filters', 'top_ids', 'relevant_ids', 'absent_ids', 'total', 'effect')


def _invalid():
    raise d.DiscoveryInvalid()


def _json_value(value, *, depth=0, budget=None):
    """Bound expected filter/effect JSON without interpreting its authority."""
    if budget is None:
        budget = [512]
    budget[0] -= 1
    if budget[0] < 0 or depth > 8:
        _invalid()
    if value is None or type(value) in (bool, int):
        return
    if type(value) is float:
        if not math.isfinite(value):
            _invalid()
        return
    if type(value) is str:
        try:
            if len(value.encode('utf-8')) > 4096:
                _invalid()
        except UnicodeError:
            _invalid()
        return
    if type(value) is list:
        if len(value) > 128:
            _invalid()
        for item in value:
            _json_value(item, depth=depth + 1, budget=budget)
        return
    if type(value) is dict:
        if len(value) > 64:
            _invalid()
        for key, item in value.items():
            if type(key) is not str:
                _invalid()
            _json_value(key, depth=depth + 1, budget=budget)
            _json_value(item, depth=depth + 1, budget=budget)
        return
    _invalid()


def _bounded_object(value, *, allow_none=False):
    if value is None and allow_none:
        return
    if type(value) is not dict:
        _invalid()
    _json_value(value)
    try:
        packed = json.dumps(value, ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode('ascii')
    except (ValueError, TypeError, UnicodeError, RecursionError):
        _invalid()
    if len(packed) > 16384:
        _invalid()


def _expected_ids(value, *, required=False, maximum=100):
    if type(value) is not list or (required and not value) or len(value) > maximum:
        _invalid()
    for ident in value:
        d.identifier(ident)
    if len(set(value)) != len(value):
        _invalid()


def _validate_envelope(document):
    if type(document) is not dict or set(document) != {'version', 'cases'}:
        _invalid()
    if type(document['version']) is not int or document['version'] != 1:
        _invalid()
    cases = document['cases']
    if type(cases) is not list or not 1 <= len(cases) <= 100:
        _invalid()

    validated = []
    seen = set()
    for raw in cases:
        if type(raw) is not dict or set(raw) - {'id', 'text', 'expect', 'after'} or not {'id', 'text', 'expect'} <= set(raw):
            _invalid()
        ident = raw['id']
        if type(ident) is not str or _CASE_ID.fullmatch(ident) is None or ident in seen:
            _invalid()
        seen.add(ident)
        try:
            words = d.text(raw['text'], 1024)
        except d.DiscoveryInvalid:
            raise
        expected = raw['expect']
        if type(expected) is not dict or 'kind' not in expected or set(expected) - _EXPECT_FIELDS:
            _invalid()
        if type(expected['kind']) is not str or expected['kind'] not in _KINDS:
            _invalid()
        if 'filters' in expected:
            _bounded_object(expected['filters'], allow_none=True)
        if 'effect' in expected:
            _bounded_object(expected['effect'], allow_none=True)
        if 'top_ids' in expected:
            _expected_ids(expected['top_ids'], maximum=20)
            if not expected['top_ids'] and 'total' in expected and expected['total'] != 0:
                _invalid()
        if 'relevant_ids' in expected:
            _expected_ids(expected['relevant_ids'], required=True, maximum=20)
        if 'absent_ids' in expected:
            _expected_ids(expected['absent_ids'], maximum=100)
        if 'total' in expected:
            if type(expected['total']) is not int or not 0 <= expected['total'] <= d.MAX_ID:
                _invalid()
        after = raw.get('after')
        if 'after' in raw:
            if type(after) is not str or after not in seen - {ident}:
                _invalid()
        validated.append({'id': ident, 'text': words, 'expect': expected,
                          **({'after': after} if 'after' in raw else {})})
    return validated


def _bound_snapshot(engine, token, library, binding):
    # Calling presentation with the initial readiness binding forces SearchRuntime
    # to recheck membership, source digest and session binding on each boundary.
    result = engine.call('presentation', token, library, lambda: False, {'binding': binding})
    if type(result) is not dict or result.get('version') != 2:
        raise d.DiscoveryUnavailable()


def _readiness_binding(engine, token, library):
    state = engine.call('readiness', token, library, lambda: False, {})
    if (type(state) is not dict or not {'version', 'search_version', 'binding'} <= set(state)
            or type(state['version']) is not int or state['version'] != 1
            or type(state['search_version']) is not int or state['search_version'] != 2
            or not d.hashed(state['binding'])):
        raise d.DiscoveryUnavailable()
    return state['binding']


def evaluate_cases(engine, token, library, document, *, clock, monotonic=time.monotonic):
    """Run validated cases through ``assistant._turn`` and emit private-safe metrics.

    A relevance request on a clarification or empty page is a measured miss.
    ``absent_ids`` is proven only when the result page has no continuation.
    Access denial and discovery change/unavailability/busy exceptions intentionally
    pass through unchanged. In those cases no report is returned.
    """
    cases = _validate_envelope(document)
    from .assistant import _turn

    binding = _readiness_binding(engine, token, library)
    contexts = {}
    reports = []
    relevant_case_count = 0
    relevant_hit_count = 0
    reciprocal_ranks = []

    for ordinal, case in enumerate(cases, 1):
        previous = None
        dependency_failed = False
        if 'after' in case:
            previous = contexts[case['after']]
            if previous is None:
                dependency_failed = True
            elif type(previous) is not dict:
                _invalid()

        if dependency_failed:
            started = monotonic()
            _bound_snapshot(engine, token, library, binding)
            _bound_snapshot(engine, token, library, binding)
            ended = monotonic()
            if (type(started) not in (int, float) or type(ended) not in (int, float)
                    or not math.isfinite(started) or not math.isfinite(ended) or ended < started):
                _invalid()
            elapsed_ms = (ended - started) * 1000.0
            if not math.isfinite(elapsed_ms):
                _invalid()
            expected = case['expect']
            checks = {'kind': False, 'context_missing': True}
            skipped_case = {'ordinal': ordinal, 'checks': checks, 'passed': False,
                            'elapsed_ms': elapsed_ms, 'result_count': 0}
            if 'relevant_ids' in expected:
                checks['relevant_ids'] = False
                relevant_case_count += 1
                reciprocal_ranks.append(0.0)
                skipped_case['hit_at_20'] = False
                skipped_case['reciprocal_rank_at_20'] = 0.0
            reports.append(skipped_case)
            contexts[case['id']] = None
            continue

        _bound_snapshot(engine, token, library, binding)
        started = monotonic()
        result = None
        try:
            result = _turn(engine, token, library, case['text'], previous, clock)
        finally:
            _bound_snapshot(engine, token, library, binding)
        ended = monotonic()
        if (type(started) not in (int, float) or type(ended) not in (int, float)
                or not math.isfinite(started) or not math.isfinite(ended) or ended < started):
            _invalid()

        if type(result) is not dict or result.get('kind') not in _KINDS:
            raise d.DiscoveryUnavailable()
        items = result.get('items')
        total = result.get('total')
        if type(items) is not list or type(total) is not int or total < 0:
            raise d.DiscoveryUnavailable()
        item_ids = []
        for item in items[:20]:
            if type(item) is not dict:
                raise d.DiscoveryUnavailable()
            item_ids.append(d.identifier(item.get('id')))
        context = result.get('context')
        contexts[case['id']] = context

        expected = case['expect']
        checks = {}
        checks['kind'] = result['kind'] == expected['kind']
        for field in _REPORT_FIELDS[1:]:
            if field not in expected:
                continue
            if field == 'filters':
                actual = result.get('filters')
                checks[field] = actual == expected[field]
            elif field == 'top_ids':
                wanted = expected[field]
                checks[field] = (not item_ids and total == 0) if not wanted else item_ids[:len(wanted)] == wanted
            elif field == 'relevant_ids':
                relevant_case_count += 1
                # A clarification or empty page is a measured miss, never a
                # vacuous hit and never a reason to discard the rest of the batch.
                first_rank = (next((rank for rank, ident in enumerate(item_ids, 1)
                                    if ident in expected[field]), None)
                              if result['kind'] in ('results', 'open') else None)
                hit = first_rank is not None
                relevant_hit_count += int(hit)
                reciprocal = (1.0 / first_rank) if first_rank is not None else 0.0
                reciprocal_ranks.append(reciprocal)
                checks[field] = hit
            elif field == 'absent_ids':
                # Absence is proven only when the returned page is complete.
                # With has_more, an ID beyond the page may still be present.
                checks[field] = (result.get('has_more') is False and
                                 all(ident not in item_ids for ident in expected[field]))
            elif field == 'total':
                checks[field] = total == expected[field]
            else:
                checks[field] = result.get('effect') == expected[field]

        elapsed_ms = (ended - started) * 1000.0
        if not math.isfinite(elapsed_ms):
            _invalid()
        report_case = {'ordinal': ordinal, 'checks': checks,
                       'passed': all(checks.values()), 'elapsed_ms': elapsed_ms,
                       'result_count': len(item_ids)}
        if 'relevant_ids' in expected:
            report_case['hit_at_20'] = hit
            report_case['reciprocal_rank_at_20'] = reciprocal
        reports.append(report_case)

    passed = sum(case['passed'] for case in reports)
    report = {'version': 1, 'case_count': len(reports), 'passed_count': passed,
              'failed_count': len(reports) - passed, 'cases': reports}
    if relevant_case_count:
        report['relevance'] = {
            'evaluated_case_count': relevant_case_count,
            'hit_count': relevant_hit_count,
            'mrr_at_20': sum(reciprocal_ranks) / relevant_case_count,
        }
    return report
