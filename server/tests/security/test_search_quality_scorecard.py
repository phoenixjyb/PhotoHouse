"""Private, cohort-aware v2 search quality scorecard tests."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'tests' / 'security'))

from app.access import discovery as d
from app.access.search_evaluation import evaluate_cases
from app.access.service import AccessDenied
from phone_discovery_fixture import TOKEN, NOW


class FakeEngine:
    def __init__(self, fail_presentation=None):
        self.presentation_count = 0
        self.fail_presentation = fail_presentation

    def call(self, operation, token, library, cancelled, values):
        if operation == 'readiness':
            return {'version': 1, 'search_version': 2, 'binding': 'a' * 64}
        if operation == 'presentation':
            self.presentation_count += 1
            if self.presentation_count == self.fail_presentation:
                raise d.DiscoveryChanged()
            return {'version': 2}
        raise AssertionError(operation)


def case(ident, language=None, category=None, *, after=None, relevant=None):
    value = {'id': ident, 'text': 'private query ' + ident,
             'expect': {'kind': 'results'}}
    if language is not None:
        value['language'] = language
    if category is not None:
        value['category'] = category
    if after is not None:
        value['after'] = after
    if relevant is not None:
        value['expect']['relevant_ids'] = relevant
    if category == 'no_match':
        value['expect']['total'] = 0
    return value


class SearchQualityScorecardTests(unittest.TestCase):
    def test_v2_cohort_denominators_misses_latency_and_privacy(self):
        engine = FakeEngine()
        document = {'version': 2, 'cases': [
            case('en_hit', 'en', 'person', relevant=['101', '106']),
            case('zh_miss', 'zh', 'person', relevant=['106']),
            case('mixed_none', 'mixed', 'no_match'),
            case('zh_follow', 'zh', 'followup', after='zh_miss', relevant=['101']),
            case('unassigned', category='text'),
        ]}
        document['cases'][0]['expect']['total'] = 99
        document['cases'][0]['expect'].update(filters={'media': ['wrong']}, absent_ids=['999'])
        ids = [str(100 + index) for index in range(1, 7)]

        def turn(_engine, _token, _library, words, previous, _clock):
            if words.endswith('zh_miss'):
                return {'kind': 'clarification', 'context': None, 'items': [], 'total': 0,
                        'filters': None, 'has_more': False, 'reply': 'private reply'}
            if words.endswith('mixed_none'):
                return {'kind': 'results', 'context': None, 'items': [], 'total': 0,
                        'filters': {}, 'has_more': False, 'reply': 'private reply'}
            return {'kind': 'results', 'context': {}, 'items': [{'id': ident} for ident in ids],
                    'total': 6, 'filters': {}, 'has_more': True, 'reply': 'private reply'}

        ticks = iter([0, .010, 1, 1.020, 2, 2.030, 3, 3.040, 4, 4.050])
        with patch('app.access.assistant._turn', side_effect=turn):
            report = evaluate_cases(engine, TOKEN, 'family-private', document,
                                    clock=lambda: NOW, monotonic=lambda: next(ticks))

        score = report['scorecard']['cohorts']
        self.assertEqual(report['version'], 2)
        self.assertEqual((score['en']['denominator'], score['en']['passed_count'],
                          score['en']['failed_count']), (1, 0, 1))
        self.assertEqual((score['en']['relevance_denominator'], score['en']['hit_at_5_count']), (1, 1))
        self.assertEqual(score['en']['labeled_recall_at_5'], .5)
        self.assertEqual(score['zh']['failed_dependency_count'], 1)
        self.assertEqual(score['zh']['no_match_count'], 0)
        self.assertEqual(score['zh']['relevance_denominator'], 2)
        self.assertEqual(score['zh']['hit_at_5'], 0)
        self.assertEqual(score['mixed']['no_match_count'], 1)
        self.assertEqual(score['unassigned']['denominator'], 1)
        self.assertEqual(score['unassigned']['passed_count'], 1)
        self.assertAlmostEqual(score['zh']['elapsed_ms_median'], 20.0)
        self.assertAlmostEqual(score['zh']['elapsed_ms_p95'], 20.0)
        self.assertEqual(score['zh']['executed_count'], 1)
        self.assertEqual(score['zh']['latency_sample_count'], 1)
        self.assertEqual(score['zh']['mrr_at_20'], 0)
        self.assertEqual(score['zh']['relevance_denominator'], 2)
        self.assertEqual(score['en']['mrr_at_20'], 1)
        self.assertEqual(score['en']['hard_filter_checked_count'], 1)
        self.assertEqual(score['en']['hard_filter_failed_count'], 1)
        self.assertEqual(score['en']['absence_checked_count'], 1)
        self.assertEqual(score['en']['absence_failed_count'], 1)
        self.assertEqual(report['scorecard']['categories']['person']['denominator'], 2)
        self.assertEqual(report['scorecard']['categories']['person']['failed_count'], 2)
        self.assertEqual(report['scorecard']['categories']['date'],
                         {'denominator': 0, 'passed_count': 0, 'failed_count': 0})
        self.assertEqual(report['scorecard']['recall_at_5_note'],
                         'Fraction of supplied relevant IDs retrieved; incomplete labels do not measure population recall.')
        packed = repr(report)
        for private in ('private query', 'private reply', 'family-private', '101', '106', 'zh_miss'):
            self.assertNotIn(private, packed)

    def test_v2_rejects_unknown_or_unbounded_cohort_values_before_source_access(self):
        for document in (
                {'version': 2, 'cases': [case('bad', 'fr', 'text')]},
                {'version': 2, 'cases': [case('bad', 'en', 'arbitrary_label')]},
                {'version': True, 'cases': [case('bad', 'en', 'text')]},):
            engine = FakeEngine()
            with self.assertRaises(d.DiscoveryInvalid):
                evaluate_cases(engine, TOKEN, 'family-private', document, clock=lambda: NOW)
            self.assertEqual(engine.presentation_count, 0)

    def test_empty_cohorts_are_visible_with_null_metrics_and_explicit_unassigned(self):
        document = {'version': 2, 'cases': [case('one', 'unassigned', 'text')]}
        with patch('app.access.assistant._turn', return_value={
                'kind': 'results', 'context': {}, 'items': [], 'total': 0,
                'filters': {}, 'has_more': False, 'reply': 'private reply'}):
            report = evaluate_cases(FakeEngine(), TOKEN, 'family-private', document,
                                    clock=lambda: NOW, monotonic=iter((0, .01)).__next__)
        score = report['scorecard']
        self.assertEqual(score['cohorts']['unassigned']['denominator'], 1)
        for name in ('en', 'zh', 'mixed'):
            self.assertEqual(score['cohorts'][name]['denominator'], 0)
            self.assertIsNone(score['cohorts'][name]['hit_at_5'])
            self.assertIsNone(score['cohorts'][name]['labeled_recall_at_5'])
            self.assertIsNone(score['cohorts'][name]['mrr_at_20'])
            self.assertIsNone(score['cohorts'][name]['elapsed_ms_median'])
            self.assertIsNone(score['cohorts'][name]['elapsed_ms_p95'])

    def test_denial_and_pre_or_mid_turn_source_drift_return_no_partial_report(self):
        document = {'version': 2, 'cases': [case('one', 'en', 'scene')]}

        class DeniedEngine(FakeEngine):
            def call(self, operation, *args):
                if operation == 'readiness':
                    raise AccessDenied()
                return super().call(operation, *args)

        with self.assertRaises(AccessDenied):
            evaluate_cases(DeniedEngine(), TOKEN, 'family-private', document, clock=lambda: NOW)

        with patch('app.access.assistant._turn', return_value={
                    'kind': 'results', 'context': {}, 'items': [], 'total': 0,
                    'filters': {}, 'has_more': False, 'reply': 'private reply'}):
            for fail_presentation in (1, 2):
                with self.subTest(fail_presentation=fail_presentation):
                    with self.assertRaises(d.DiscoveryChanged):
                        evaluate_cases(FakeEngine(fail_presentation=fail_presentation),
                                       TOKEN, 'family-private', document, clock=lambda: NOW)

    def test_no_match_annotation_requires_expected_and_actual_zero_results(self):
        invalid = case('bad_no_match', 'en', 'no_match')
        del invalid['expect']['total']
        with self.assertRaises(d.DiscoveryInvalid):
            evaluate_cases(FakeEngine(), TOKEN, 'family-private',
                           {'version': 2, 'cases': [invalid]}, clock=lambda: NOW)

        document = {'version': 2, 'cases': [case('wrong_no_match', 'en', 'no_match')]}
        with patch('app.access.assistant._turn', return_value={
                'kind': 'results', 'context': {}, 'items': [{'id': '101'}], 'total': 1,
                'filters': {}, 'has_more': False, 'reply': 'private reply'}):
            report = evaluate_cases(FakeEngine(), TOKEN, 'family-private', document, clock=lambda: NOW)
        self.assertFalse(report['cases'][0]['passed'])
        self.assertFalse(report['cases'][0]['checks']['total'])
        self.assertEqual(report['scorecard']['categories']['no_match']['failed_count'], 1)


if __name__ == '__main__':
    unittest.main()
