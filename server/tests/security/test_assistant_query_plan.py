"""Pure bilingual search-v2 query planning; no providers or live data."""
from datetime import datetime
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))

from app.access.assistant_query_plan import QueryPlan, plan_query, query_mode


NOW = datetime(2032, 9, 14, 16, 20)
ENTITIES = {
    'binding': 'a' * 64,
    'enabled': ['people', 'date', 'tags', 'locations', 'media', 'text'],
    'groups': {'people': ['301', '302'], 'tags': ['501'], 'locations': ['601']},
    'labels': ['Sample Child', '示例儿童', 'Sample Adult', '示例成人', '海边', 'Park', '公园'],
    'ambiguous': False,
}


def resolved_entities(words):
    outside = re.sub(r'[“"][^“”"]+[”"]', ' ', words)
    groups = {'people': [], 'tags': [], 'locations': []}
    labels = []
    for name, ident in (('Sample Child', '301'), ('示例儿童', '301'),
                        ('Sample Adult', '302'), ('示例成人', '302')):
        if name.casefold() in outside.casefold():
            groups['people'].append(ident)
            labels.append(name)
    for name, ident, facet in (('Park', '501', 'tags'), ('公园', '501', 'tags'),
                               ('Home', '601', 'locations')):
        if name.casefold() in outside.casefold():
            groups[facet].append(ident)
            labels.append(name)
    return {**ENTITIES, 'groups': groups, 'labels': labels}


def plan(words, *, entities=None, previous=None, refine=False):
    if entities is None:
        entities = resolved_entities(words)
    return plan_query(words, now=NOW, entities=entities,
                      previous_filters=previous, refine=refine)


class AssistantQueryPlanTests(unittest.TestCase):
    def assert_ready(self, words, expected, **kwargs):
        result = plan(words, **kwargs)
        self.assertIsInstance(result, QueryPlan)
        self.assertEqual(result.status, 'ready', (words, result))
        self.assertEqual(result.version, 1)
        self.assertIsNone(result.reason)
        self.assertEqual(result.filters, expected)

    def assert_clarifies(self, words, reason=None, **kwargs):
        result = plan(words, **kwargs)
        self.assertEqual(result.status, 'clarification', (words, result))
        self.assertTrue(result.reason)
        if reason:
            self.assertEqual(result.reason, reason)
        return result

    def test_chinese_and_english_search_openings_and_media_paraphrases(self):
        expected = {'media': ['image'], 'people': {'ids': ['301'], 'match': 'any'}}
        for words in ('帮忙找示例儿童的照片', '能不能找示例儿童的相片',
                      '可以帮我找示例儿童的图片', 'please find photographs of Sample Child',
                      'could you show me pictures of Sample Child'):
            with self.subTest(words=words):
                self.assert_ready(words, expected)
        self.assert_ready('帮我查一下示例儿童的视频',
                          {'media': ['video'], 'people': {'ids': ['301'], 'match': 'any'}})
        self.assert_ready('find videos of Sample Child',
                          {'media': ['video'], 'people': {'ids': ['301'], 'match': 'any'}})

    def test_explicit_dates_chinese_english_and_iso_day(self):
        cases = {
            'find photos taken in 2032-09-03': {'media': ['image'], 'date': {'from': '2032-09-03', 'to': '2032-09-03'}},
            '找2032年9月3日的照片': {'media': ['image'], 'date': {'from': '2032-09-03', 'to': '2032-09-03'}},
            'find photos from March 5, 2032': {'media': ['image'], 'date': {'from': '2032-03-05', 'to': '2032-03-05'}},
            'find photos during September 2032': {'media': ['image'], 'date': {'from': '2032-09-01', 'to': '2032-09-30'}},
            'find photos from 5 March 2032': {'media': ['image'], 'date': {'from': '2032-03-05', 'to': '2032-03-05'}},
            'find photos on March 5': {'media': ['image'], 'date': {'from': '2032-03-05', 'to': '2032-03-05'}},
            'find photos on 5 March': {'media': ['image'], 'date': {'from': '2032-03-05', 'to': '2032-03-05'}},
            '找2032年的照片': {'media': ['image'], 'date': {'from': '2032-01-01', 'to': '2032-12-31'}},
            '找2032年九月的照片': {'media': ['image'], 'date': {'from': '2032-09-01', 'to': '2032-09-30'}},
        }
        for words, expected in cases.items():
            with self.subTest(words=words):
                self.assert_ready(words, expected)

    def test_relative_calendar_ranges_use_supplied_civil_date(self):
        cases = {
            'find photos today': {'media': ['image'], 'date': {'from': '2032-09-14', 'to': '2032-09-14'}},
            'find photos yesterday': {'media': ['image'], 'date': {'from': '2032-09-13', 'to': '2032-09-13'}},
            'find photos this week': {'media': ['image'], 'date': {'from': '2032-09-13', 'to': '2032-09-19'}},
            'find photos last week': {'media': ['image'], 'date': {'from': '2032-09-06', 'to': '2032-09-12'}},
            'find photos this month': {'media': ['image'], 'date': {'from': '2032-09-01', 'to': '2032-09-30'}},
            'find photos last month': {'media': ['image'], 'date': {'from': '2032-08-01', 'to': '2032-08-31'}},
            '找今天的照片': {'media': ['image'], 'date': {'from': '2032-09-14', 'to': '2032-09-14'}},
            '找昨天照片': {'media': ['image'], 'date': {'from': '2032-09-13', 'to': '2032-09-13'}},
            '找去年九月照片': {'media': ['image'], 'date': {'from': '2031-09-01', 'to': '2031-09-30'}},
            '找今年十一月照片': {'media': ['image'], 'date': {'from': '2032-11-01', 'to': '2032-11-30'}},
            '找去年照片': {'media': ['image'], 'date': {'from': '2031-01-01', 'to': '2031-12-31'}},
            '找今年照片': {'media': ['image'], 'date': {'from': '2032-01-01', 'to': '2032-12-31'}},
        }
        for words, expected in cases.items():
            with self.subTest(words=words):
                self.assert_ready(words, expected)

    def test_bilingual_reviewed_people_tags_locations_and_explicit_quantifiers(self):
        self.assert_ready('find photos of Sample Child and Sample Adult together at the beach', {
            'media': ['image'], 'people': {'ids': ['301', '302'], 'match': 'all'}, 'text': 'beach'})
        self.assert_ready('找示例儿童或示例成人在公园的照片', {
            'media': ['image'], 'people': {'ids': ['301', '302'], 'match': 'any'},
            'tags': {'ids': ['501'], 'match': 'any'}})
        self.assert_ready('找示例儿童在海边的照片', {
            'media': ['image'], 'people': {'ids': ['301'], 'match': 'any'}, 'text': '海边'})
        self.assert_ready('找示例儿童在动物园玩的照片', {
            'media': ['image'], 'people': {'ids': ['301'], 'match': 'any'}, 'text': '动物园'})
        self.assert_ready('找示例儿童在海边游玩的照片', {
            'media': ['image'], 'people': {'ids': ['301'], 'match': 'any'}, 'text': '海边'})
        self.assert_ready('find photos at the beach', {'media': ['image'], 'text': 'beach'})

    def test_quoted_literals_are_exact_and_opaque_to_date_media_identity_and_negation(self):
        cases = (
            ('找包含“示例儿童”的照片', {'media': ['image'], 'text': '示例儿童'}),
            ('find photos containing "2032-09-03 videos Sample Child"',
             {'media': ['image'], 'text': '2032-09-03 videos Sample Child'}),
            ('找包含“不要海边”的照片', {'media': ['image'], 'text': '不要海边'}),
            ('find photos containing "妈妈"', {'media': ['image'], 'text': '妈妈'}),
        )
        for words, expected in cases:
            with self.subTest(words=words):
                self.assert_ready(words, expected)

    def test_invalid_conflicting_or_unsupported_constraints_clarify(self):
        cases = (
            ('find photos from 2032-02-30', 'invalid_date'),
            ('找2032年99月照片', 'invalid_date'),
            ('find photos from 2032-09 and October 2032', 'conflicting_dates'),
            ('find photos on March 5 and September', 'conflicting_dates'),
            ('找今年九月和10月照片', 'conflicting_dates'),
            ('找13月照片', 'invalid_date'),
            ('find photos ﬁ at the beach', 'unsupported_condition'),
            ('find photos of Sample Child and Sample Adult or together', 'conflicting_people_mode'),
            ('find photos of Sample Child and together', 'incomplete_people_relation'),
            ('find photos without "beach"', 'unsupported_negation'),
            ('find photos of Unknown Person', 'unsupported_condition'),
            ('find photos from a mystery place', 'unsupported_condition'),
            ('找示例儿童在海边拍摄的照片', 'unsupported_condition'),
            ('找示例儿童在海边拍的照片', 'unsupported_condition'),
            ('找示例儿童在动物园玩的陌生人物', 'unsupported_condition'),
            ('找示例儿童在海边玩然后在公园的照片', 'unsupported_condition'),
            ('find photos “unfinished', 'ambiguous_quote'),
            ('find photos "one" and "two"', 'ambiguous_quote'),
            ('find photos on the beach except Sample Child', 'unsupported_negation'),
        )
        for words, reason in cases:
            with self.subTest(words=words):
                self.assert_clarifies(words, reason)

    def test_entity_ambiguity_and_id_boundary_never_produce_searchable_guess(self):
        ambiguous = dict(ENTITIES, ambiguous=True)
        self.assert_clarifies('find photos of Sample Child', 'ambiguous_entities', entities=ambiguous)
        supplied_id = dict(ENTITIES, groups={**ENTITIES['groups'], 'people': ['999999']})
        result = plan('find photos of Sample Child', entities=supplied_id)
        # The planner can only pass through an identity selected by the
        # authorized resolver; it has no user-text-to-ID conversion.
        self.assertEqual(result.status, 'ready')
        self.assertEqual(result.filters['people']['ids'], ['999999'])
        no_match = dict(ENTITIES, groups={'people': [], 'tags': [], 'locations': []}, labels=[])
        refused = plan('find photos of Sample Child id 301', entities=no_match)
        self.assertEqual(refused.status, 'clarification')
        self.assertNotIn('people', refused.filters)
        malformed = dict(ENTITIES, groups={**ENTITIES['groups'], 'people': ['0']})
        self.assert_clarifies('find photos of Sample Child', 'invalid_entities', entities=malformed)

    def test_unavailable_search_slots_clarify(self):
        no_date = dict(ENTITIES, enabled=['people', 'tags', 'locations', 'media', 'text'])
        self.assert_clarifies('find photos from 2032-09', 'date_unavailable', entities=no_date)
        no_text = dict(ENTITIES, enabled=['people', 'date', 'tags', 'locations', 'media'])
        self.assert_clarifies('find photos containing "beach"', 'text_unavailable', entities=no_text)

    def test_refinement_preserves_omitted_filters_and_requires_prior_context(self):
        previous = {
            'media': ['image'], 'people': {'ids': ['301'], 'match': 'any'},
            'date': {'from': '2032-09-01', 'to': '2032-09-30'}, 'text': 'beach',
        }
        self.assert_ready('只看视频', {
            'media': ['video'], 'people': {'ids': ['301'], 'match': 'any'},
            'date': {'from': '2032-09-01', 'to': '2032-09-30'}, 'text': 'beach',
        }, previous=previous, refine=True)
        self.assert_clarifies('only videos', 'refine_without_context', refine=True)
        self.assert_clarifies('only videos', 'invalid_previous_filters',
                              previous={'people': {'ids': ['301'], 'match': 'unknown'}}, refine=True)

    def test_previous_filters_accept_all_current_discovery_date_shapes(self):
        previous = {
            'media': ['other'],
            'date': {'from': None, 'to': '2032-09-30'},
            'people': {'ids': ['301', '302'], 'match': 'all'},
            'tags': {'ids': ['501'], 'match': 'all'},
            'locations': ['601'],
        }
        self.assert_ready('只看照片', {
            'media': ['image'], 'date': {'from': None, 'to': '2032-09-30'},
            'people': {'ids': ['301', '302'], 'match': 'all'},
            'tags': {'ids': ['501'], 'match': 'all'}, 'locations': ['601'],
        }, previous=previous, refine=True)
        for invalid in (
            {'date': {'from': None, 'to': None}},
            {'date': {'from': '2032-09', 'to': '2032-09-30'}},
            {'people': {'ids': [['301']], 'match': 'any'}},
            {'locations': [['601']]},
        ):
            with self.subTest(invalid=invalid):
                self.assert_clarifies('only photos', 'invalid_previous_filters',
                                      previous=invalid, refine=True)

    def test_query_plan_is_frozen_and_contains_only_existing_filter_contract(self):
        result = plan('find photos containing "exact phrase"')
        self.assertEqual(set(result.__dataclass_fields__), {'version', 'status', 'filters', 'reason'})
        with self.assertRaises(Exception):
            result.status = 'results'
        self.assertEqual(set(result.filters), {'media', 'text'})

    def test_query_mode_accepts_explicit_openings_and_only_closed_bare_followups(self):
        cases = {
            '帮忙找昨天的照片': 'search',
            '麻烦你帮我找照片': 'search',
            '请你帮我找照片': 'search',
            '麻烦找照片': 'search',
            'could you find photographs from last week': 'search',
            'ＦＩＮＤ photos': 'search',
            'Ｆｉｎｄ 未知地点': 'search',
            'only this month': 'refine',
            '昨天': 'refine',
            '找昨天的照片': 'search',
            '今年九月': 'refine',
            '2032年': 'refine',
            '2032年九月的照片': 'refine',
            '9月': 'refine',
            '13月': 'refine',
            '2028-02-29': 'refine',
            'find': 'search',
            'some unrelated words': None,
            'yesterday maybe': None,
            '妈妈': None,
            '海边': None,
        }
        for words, expected in cases.items():
            with self.subTest(words=words):
                self.assertEqual(query_mode(words), expected)
        self.assert_clarifies('麻烦你帮我找未知地点的照片', 'unsupported_condition')


if __name__ == '__main__':
    unittest.main()
