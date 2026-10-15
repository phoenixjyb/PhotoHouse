"""Offline checks for the bounded v3 intent span compiler."""
from datetime import datetime
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))

from app.access.search_intent import plan_query, validate_proposal


NOW = datetime(2032, 9, 14, 16, 20)


def entities(*, labels=(), people=(), tags=(), locations=()):
    return {
        'binding': 'a' * 64,
        'enabled': ['people', 'date', 'tags', 'locations', 'media', 'text'],
        'groups': {'people': list(people), 'tags': list(tags), 'locations': list(locations)},
        'labels': list(labels),
        'ambiguous': False,
    }


class Proposal:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def propose(self, query, today, has_previous_search):
        self.calls.append((query, today, has_previous_search))
        return self.result


def ready(query, spans):
    """Build a provider proposal from exact original query substrings."""
    concepts = []
    for surface, alternatives in spans:
        start = query.find(surface)
        assert start >= 0 and query.find(surface, start + 1) < 0
        concepts.append({'start': start, 'end': start + len(surface),
                         'alternatives': alternatives})
    return {'version': 1, 'status': 'ready', 'concepts': concepts, 'question': None}


class SearchIntentTests(unittest.TestCase):
    def test_and_concepts_keep_hard_filters_and_resolve_each_authored_alternative(self):
        query = 'find Sample Child at Home yesterday videos wearing red holding a cake "family day"'
        planner = Proposal(ready(query, [
            ('wearing red', ['wearing red', '穿红色衣服']),
            ('holding a cake', ['holding a cake', '拿着蛋糕']),
        ]))
        result = plan_query(query, now=NOW,
            entities=entities(labels=('Sample Child', 'Home'), people=('301',),
                              locations=('601',)),
            previous_filters=None, planner=planner)
        self.assertEqual('ready', result.status)
        self.assertEqual({
            'people': {'ids': ['301'], 'match': 'any'},
            'locations': ['601'],
            'date': {'from': '2032-09-13', 'to': '2032-09-13'},
            'media': ['video'],
            'text': 'family day',
            'descriptive': {'version': 1, 'concepts': [
                {'surface': 'wearing red', 'alternatives': ['wearing red', '穿红色衣服']},
                {'surface': 'holding a cake', 'alternatives': ['holding a cake', '拿着蛋糕']},
            ]},
        }, result.filters)
        self.assertEqual([(query, '2032-09-14', False)], planner.calls)

    def test_model_cannot_consume_reviewed_people_tags_locations_dates_media_or_quotes(self):
        cases = [
            ('find Sample Child wearing red photos', 'Sample Child',
             entities(labels=('Sample Child',), people=('301',))),
            ('find Park wearing red photos', 'Park',
             entities(labels=('Park',), tags=('501',))),
            ('find Home wearing red photos', 'Home',
             entities(labels=('Home',), locations=('601',))),
            ('find yesterday wearing red photos', 'yesterday', entities()),
            ('find videos wearing red', 'videos', entities()),
            ('find "red cake" photos with candles', 'red cake', entities()),
            ('find photos without red cake', 'red cake', entities()),
        ]
        for query, protected, resolved in cases:
            with self.subTest(query=query):
                planner = Proposal(ready(query, [(protected, [protected])]))
                result = plan_query(query, now=NOW, entities=resolved,
                                    previous_filters=None, planner=planner)
                self.assertEqual('clarification', result.status)
                self.assertEqual({}, result.filters)

    def test_protected_words_must_remain_parseable_and_residue_is_never_dropped(self):
        query = 'find a child maybe by the lake photos yesterday'
        planner = Proposal(ready(query, [('child', ['child', '孩子'])]))
        result = plan_query(query, now=NOW, entities=entities(), previous_filters=None, planner=planner)
        self.assertEqual('clarification', result.status)
        self.assertIn(result.reason, ('unsupported_condition', 'invalid_intent'))

    def test_unresolved_public_kinship_selectors_cannot_become_descriptive_concepts(self):
        cases = (
            ('find grandma playing in snow photos', 'grandma playing in snow'),
            ('find mom playing in snow photos', 'mom playing in snow'),
            ('find 姥姥在雪地里玩耍的照片', '姥姥在雪地里玩耍'),
            ('find my children playing in snow photos', 'my children playing in snow'),
            ('找我的孩子们在雪地里玩耍的照片', '我的孩子们在雪地里玩耍'),
        )
        for query, surface in cases:
            with self.subTest(query=query):
                planner = Proposal(ready(query, [(surface, [surface])]))
                result = plan_query(query, now=NOW, entities=entities(),
                                    previous_filters=None, planner=planner)
                self.assertEqual(('clarification', 'invalid_intent', {}),
                                 (result.status, result.reason, result.filters))

    def test_generic_children_and_quoted_kinship_literals_remain_searchable(self):
        for query, surface in (
                ('find children playing in snow photos', 'children playing in snow'),
                ('找孩子们在雪地里玩耍的照片', '孩子们在雪地里玩耍')):
            with self.subTest(query=query):
                planner = Proposal(ready(query, [(surface, [surface])]))
                result = plan_query(query, now=NOW, entities=entities(),
                                    previous_filters=None, planner=planner)
                self.assertEqual('ready', result.status)
                self.assertIn('descriptive', result.filters)

        query = 'find photos containing "grandma"'
        planner = Proposal(None)
        result = plan_query(query, now=NOW, entities=entities(),
                            previous_filters=None, planner=planner)
        self.assertEqual('grandma', result.filters['text'])
        self.assertEqual([], planner.calls)

        # A reviewed label and its already-resolved person filter retain the
        # ordinary deterministic path before the language planner is consulted.
        planner = Proposal(None)
        result = plan_query('find Grandma photos', now=NOW,
                            entities=entities(labels=('Grandma',), people=('301',)),
                            previous_filters=None, planner=planner)
        self.assertEqual({'ids': ['301'], 'match': 'any'}, result.filters['people'])
        self.assertEqual([], planner.calls)

    def test_selector_boundaries_and_vague_date_slots_cannot_be_masked(self):
        query = 'find a motherboard and a grandmaster figurine photos'
        planner = Proposal(ready(query, [
            ('a motherboard and a grandmaster figurine',
             ['a motherboard and a grandmaster figurine']),
        ]))
        result = plan_query(query, now=NOW, entities=entities(),
                            previous_filters=None, planner=planner)
        self.assertEqual('ready', result.status)

        for query, surface in (
                ('find photos from childhood', 'childhood'),
                ('find photos from a long time ago', 'a long time ago'),
                ('找小时候的照片', '小时候')):
            with self.subTest(query=query):
                planner = Proposal(ready(query, [(surface, [surface])]))
                result = plan_query(query, now=NOW, entities=entities(),
                                    previous_filters=None, planner=planner)
                self.assertEqual(('clarification', 'invalid_intent', {}),
                                 (result.status, result.reason, result.filters))

        clarification = Proposal({'version': 1, 'status': 'clarification',
                                  'concepts': [], 'question': 'date'})
        result = plan_query('find photos from childhood', now=NOW, entities=entities(),
                            previous_filters=None, planner=clarification)
        self.assertEqual(('clarification', 'intent_date', {}),
                         (result.status, result.reason, result.filters))

    def test_proposal_closed_shape_and_span_bounds_are_enforced(self):
        query = 'find red cake photos'
        good = ready(query, [('red cake', ['red cake'])])
        bad_values = [
            {**good, 'extra': 'must not pass'},
            {**good, 'version': True},
            {**good, 'concepts': [{**good['concepts'][0], 'ids': ['301']}]},
            {**good, 'concepts': [dict(good['concepts'][0], start=True)]},
            {**good, 'concepts': [dict(good['concepts'][0], start=-1)]},
            {**good, 'concepts': [dict(good['concepts'][0], end=len(query) + 1)]},
            {**good, 'concepts': [good['concepts'][0], good['concepts'][0]]},
            {**good, 'concepts': [dict(good['concepts'][0], alternatives=[])]},
            {**good, 'status': 'clarification', 'question': 'date'},
        ]
        for value in bad_values:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_proposal(value, query)

    def test_duplicate_or_overlapping_source_spans_are_rejected(self):
        query = 'find red cake with cake photos'
        duplicated = {'version': 1, 'status': 'ready', 'question': None, 'concepts': [
            {'start': 9, 'end': 13, 'alternatives': ['cake']},
            {'start': 19, 'end': 23, 'alternatives': ['cake']},
        ]}
        with self.assertRaises(ValueError):
            validate_proposal(duplicated, query)
        overlap = {'version': 1, 'status': 'ready', 'question': None, 'concepts': [
            {'start': 5, 'end': 13, 'alternatives': ['red cake']},
            {'start': 9, 'end': 13, 'alternatives': ['cake']},
        ]}
        with self.assertRaises(ValueError):
            validate_proposal(overlap, query)
        repeated_surface = {'version': 1, 'status': 'ready', 'question': None, 'concepts': [
            {'start': 5, 'end': 9, 'alternatives': ['cake']},
            {'start': 18, 'end': 22, 'alternatives': ['cake']},
        ]}
        with self.assertRaises(ValueError):
            validate_proposal(repeated_surface, query)

    def test_unsupported_negation_stale_context_and_model_outage_fail_closed(self):
        query = 'only videos'
        unavailable = Proposal(None)
        missing_context = plan_query(query, now=NOW, entities=entities(),
                                     previous_filters=None, planner=unavailable)
        self.assertEqual(('clarification', 'refine_without_context'),
                         (missing_context.status, missing_context.reason))
        self.assertEqual([], unavailable.calls)
        result = plan_query(query, now=NOW, entities=entities(),
                            previous_filters={'descriptive': {'version': 1, 'concepts': []}},
                            planner=unavailable)
        self.assertEqual('clarification', result.status)
        self.assertEqual('invalid_previous_filters', result.reason)
        self.assertEqual([], unavailable.calls)

        unsupported = Proposal({'version': 1, 'status': 'unsupported',
                                'concepts': [], 'question': 'unsupported_action'})
        result = plan_query('delete all photos', now=NOW, entities=entities(),
                            previous_filters=None, planner=unsupported)
        self.assertEqual('unsupported', result.status)
        self.assertEqual('unsupported_action', result.reason)
        self.assertEqual([], unsupported.calls)

        class Down:
            def propose(self, *_):
                from app.access.search_intent import IntentUnavailable
                raise IntentUnavailable()
        query = 'find photos of a child dancing'
        result = plan_query(query, now=NOW, entities=entities(),
                            previous_filters=None, planner=Down())
        self.assertEqual(('clarification', 'intent_unavailable'), (result.status, result.reason))

    def test_date_media_only_refinement_bypasses_model_and_keeps_description_and_quote(self):
        previous = {
            'media': ['image'], 'text': 'Exact Family Phrase',
            'date': {'from': '2032-09-01', 'to': '2032-09-30'},
            'descriptive': {'version': 1, 'concepts': [
                {'surface': 'red cake', 'alternatives': ['red cake', '红色蛋糕']}]},
        }
        planner = Proposal(None)
        result = plan_query('only videos', now=NOW, entities=entities(),
                            previous_filters=previous, planner=planner)
        self.assertEqual('ready', result.status)
        self.assertEqual({**previous, 'media': ['video']}, result.filters)
        self.assertEqual([], planner.calls)


if __name__ == '__main__':
    unittest.main()
