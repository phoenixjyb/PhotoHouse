"""Slot removal is explicit, preserves other constraints and stays read-only."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'tests/security')]

from app.access.search_refinement import plan_query, query_mode
from test_assistant_query_plan import NOW, resolved_entities
import test_assistant_joint_search as fixtures
from phone_discovery_fixture import OTHER


PREVIOUS = {
    'media': ['image'], 'people': {'ids': ['301'], 'match': 'all'},
    'date': {'from': '2032-09-01', 'to': '2032-09-30'},
    'locations': ['601'], 'tags': {'ids': ['501'], 'match': 'all'}, 'text': '海边',
}


def plan(words, previous=PREVIOUS, **kwargs):
    return plan_query(words, now=NOW, entities=resolved_entities(words),
                      previous_filters=previous, refine=True, **kwargs)


class SearchRefinementTests(unittest.TestCase):
    def test_each_removal_changes_only_the_requested_slot(self):
        cases = {
            'date': ('any date', 'all time', 'remove the date filter', '不限日期', '取消时间筛选'),
            'people': ('anyone', 'clear people filter', '不限人物'),
            'locations': ('anywhere', 'remove location filter', '不限地点'),
            'tags': ('any tag', 'clear the tag filter', '取消标签筛选'),
            'text': ('any text', 'remove text filter', '不限内容', '取消文字筛选'),
            'media': ('any media type', 'clear media type filter', '不限类型'),
        }
        before = deepcopy(PREVIOUS)
        for slot, queries in cases.items():
            for words in queries:
                with self.subTest(words=words):
                    self.assertEqual(query_mode(words), 'refine')
                    result = plan(words)
                    self.assertEqual(result.status, 'ready', result)
                    self.assertEqual(result.filters, {k: v for k, v in PREVIOUS.items() if k != slot})
        self.assertEqual(PREVIOUS, before)

    def test_combined_removal_and_explicit_replacement_of_other_slot(self):
        for words in ('only videos, any date', '不限日期，只看视频', '只看视频，不限日期'):
            result = plan(words)
            self.assertEqual(result.status, 'ready', (words, result))
            self.assertEqual(result.filters, {**{k: v for k, v in PREVIOUS.items() if k != 'date'},
                                               'media': ['video']})
        for words in ('any date and anyone', '不限日期和不限人物'):
            result = plan(words)
            self.assertEqual(result.status, 'ready', (words, result))
            self.assertEqual(result.filters, {k: v for k, v in PREVIOUS.items() if k not in {'date', 'people'}})

    def test_conflicting_replacement_unknown_conditions_and_negation_clarify(self):
        for words in ('any date, only September 2032', 'only September 2032, any date',
                      'anyone, only Sample Child', 'any text containing "海边"',
                      'any date except Sample Child', 'any date or anyone',
                      'any date, mysterious place', 'do not remove date filter',
                      '不要取消日期筛选', '不限日期以后', 'remove all filters'):
            result = plan(words)
            self.assertEqual(result.status, 'clarification', (words, result))
        self.assertEqual(plan('only September 2032, any date').reason, 'conflicting_refinement')

    def test_no_context_invalid_context_or_new_search_does_not_reset_filters(self):
        self.assertEqual(plan('any date', previous=None).reason, 'refine_without_context')
        self.assertEqual(plan('any date', previous={'unknown': True}).reason, 'invalid_previous_filters')
        result = plan_query('find photos any date', now=NOW, entities=resolved_entities(''),
                            previous_filters=PREVIOUS, refine=False)
        self.assertEqual(result.status, 'clarification')

    def test_quotes_remain_literal_and_syntax_looking_reviewed_labels_clarify(self):
        result = plan('only photos containing "ANY DATE", anyone')
        self.assertEqual(result.status, 'ready', result)
        self.assertEqual(result.filters['text'], 'ANY DATE')
        self.assertIn('date', result.filters)
        self.assertNotIn('people', result.filters)
        words = 'only photos containing "any date"'
        result = plan(words)
        self.assertEqual(result.filters['text'], 'any date')
        self.assertIn('date', result.filters)
        self.assertIsNone(query_mode('"any date"'))
        entities = resolved_entities('')
        entities['groups']['people'] = ['301']
        entities['labels'] = ['Anyone']
        result = plan_query('anyone', now=NOW, entities=entities,
                            previous_filters=PREVIOUS, refine=True)
        self.assertEqual(result.reason, 'ambiguous_entities')


class SearchRefinementHttpTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.AssistantJointSearchTests('test_text_union_dedup_reasons_and_authored_first_order')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_removing_date_keeps_joint_people_and_literal_over_http(self):
        initial = self.fixture.turn('找2031年9月示例儿童和示例成人包含“海边”的照片').json()
        self.assertEqual(initial['kind'], 'results', initial)
        self.assertEqual(initial['total'], 0)
        result = self.fixture.turn('不限日期', context=initial['context']).json()
        self.assertEqual(result['kind'], 'results', result)
        self.assertNotIn('date', result['filters'])
        self.assertEqual(result['filters']['people'], initial['filters']['people'])
        self.assertEqual(result['filters']['text'], '海边')
        self.assertEqual([item['id'] for item in result['items']], ['103'])
        self.assertNotEqual(result['context']['fingerprint'], initial['context']['fingerprint'])

    def test_bad_removal_keeps_result_and_unprivileged_user_cannot_reuse_context(self):
        initial = self.fixture.turn('find photos containing "海边"').json()
        for words in ('any text containing "海边"', 'any date mystery'):
            result = self.fixture.turn(words, context=initial['context']).json()
            self.assertEqual(result['kind'], 'clarification', result)
            self.assertEqual(result['context'], initial['context'])
            self.assertEqual(result['items'], initial['items'])
        denied = self.fixture.turn('any date', context=initial['context'], token=OTHER)
        self.assertNotEqual(denied.status_code, 200)
        no_context = self.fixture.turn('any date').json()
        self.assertEqual(no_context['kind'], 'clarification')
        self.assertIsNone(no_context['context'])

    def test_date_range_combines_with_people_and_text_and_reversed_range_keeps_context(self):
        initial = self.fixture.turn('find photos of 示例儿童和示例成人 from 2032-08-01 to 2032-09-30 containing "海边"').json()
        self.assertEqual(initial['kind'], 'results', initial)
        self.assertEqual(initial['filters']['date'], {'from': '2032-08-01', 'to': '2032-09-30'})
        self.assertEqual([item['id'] for item in initial['items']], ['103'])
        narrowed = self.fixture.turn('from 2032-09-02 to 2032-09-02', context=initial['context']).json()
        self.assertEqual(narrowed['kind'], 'results', narrowed)
        self.assertEqual(narrowed['filters'], {**initial['filters'],
                         'date': {'from': '2032-09-02', 'to': '2032-09-02'}})
        self.assertEqual([item['id'] for item in narrowed['items']], ['103'])
        invalid = self.fixture.turn('only from 2032-10-01 to 2032-09-01', context=initial['context']).json()
        self.assertEqual(invalid['kind'], 'clarification', invalid)
        self.assertEqual(invalid['context'], initial['context'])

    def test_explicit_date_removal_can_include_video_with_missing_capture_date(self):
        initial = self.fixture.turn('find videos in September 2032').json()
        self.assertEqual(initial['kind'], 'results', initial)
        self.assertEqual(initial['total'], 0)
        result = self.fixture.turn('any date', context=initial['context']).json()
        self.assertEqual(result['kind'], 'results', result)
        self.assertEqual(result['filters'], {'media': ['video']})
        self.assertEqual([item['id'] for item in result['items']], ['102'])
        self.assertIsNone(result['items'][0]['taken_at'])


if __name__ == '__main__':
    unittest.main()
