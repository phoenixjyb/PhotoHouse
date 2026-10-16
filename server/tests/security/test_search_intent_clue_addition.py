"""Closed additive refinement for saved descriptive search concepts."""
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))

from app.access.search_intent import plan_query


NOW = datetime(2032, 9, 14, 16, 20)
DESCRIPTION = {'version': 1, 'concepts': [
    {'surface': 'Red coat', 'alternatives': ['Red coat', '红外套']},
    {'surface': 'playing in snow', 'alternatives': ['playing in snow', '在雪地里玩']},
]}
HARD_FILTERS = {
    'people': {'ids': ['301'], 'match': 'any'},
    'date': {'from': '2032-09-01', 'to': '2032-09-30'},
    'media': ['image'],
    'text': 'secret memory phrase',
    'tags': {'ids': ['501'], 'match': 'all'},
    'locations': ['601'],
}


def entities(*, labels=()):
    return {
        'binding': 'a' * 64,
        'enabled': ['people', 'date', 'tags', 'locations', 'media', 'text'],
        'groups': {'people': ['301'], 'tags': ['501'], 'locations': ['601']},
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


class UnavailablePlanner:
    def __init__(self):
        self.calls = []

    def propose(self, *args):
        self.calls.append(args)
        from app.access.search_intent import IntentUnavailable
        raise IntentUnavailable()


def ready(query, spans):
    """Build a provider proposal from exact original query substrings."""
    concepts = []
    for surface, alternatives in spans:
        start = query.find(surface)
        assert start >= 0 and query.find(surface, start + 1) < 0
        concepts.append({'start': start, 'end': start + len(surface),
                         'alternatives': alternatives})
    return {'version': 1, 'status': 'ready', 'concepts': concepts, 'question': None}


class DescriptiveClueAdditionTests(unittest.TestCase):
    def test_english_chinese_and_mixed_commands_append_one_new_concept(self):
        cases = (
            ('also with blue hat', 'blue hat', ['blue hat', '蓝帽子']),
            ('please also with blue hat', 'blue hat', ['blue hat', '蓝帽子']),
            ('add blue hat clue', 'blue hat', ['blue hat', '蓝帽子']),
            ('please also add blue hat clue', 'blue hat', ['blue hat', '蓝帽子']),
            ('please add 蓝帽子 as a clue', '蓝帽子', ['蓝帽子', 'blue hat']),
            ('请再加上blue hat线索', 'blue hat', ['blue hat', '蓝帽子']),
            ('请加上蓝帽子这条视觉线索', '蓝帽子', ['蓝帽子', 'blue hat']),
            ('添加blue hat这条线索', 'blue hat', ['blue hat', '蓝帽子']),
        )
        for query, surface, alternatives in cases:
            with self.subTest(query=query):
                previous = {**HARD_FILTERS, 'descriptive': deepcopy(DESCRIPTION)}
                original = deepcopy(previous)
                planner = Proposal(ready(surface, [(surface, alternatives)]))
                result = plan_query(query, now=NOW, entities=entities(),
                                    previous_filters=previous, planner=planner)

                self.assertEqual('ready', result.status, result)
                self.assertEqual({**HARD_FILTERS, 'descriptive': {
                    'version': 1, 'concepts': [
                        *DESCRIPTION['concepts'],
                        {'surface': surface, 'alternatives': alternatives},
                    ],
                }}, result.filters)
                self.assertEqual(original, previous)
                self.assertEqual(1, len(planner.calls))
                provider_query, today, has_previous_search = planner.calls[0]
                self.assertEqual(surface, provider_query)
                self.assertEqual(('2032-09-14', False), (today, has_previous_search))
                for private_value in ('secret memory phrase', 'Red coat', 'playing in snow'):
                    self.assertNotIn(private_value, provider_query)

    def test_missing_or_invalid_saved_context_is_not_guessed(self):
        planner = UnavailablePlanner()
        result = plan_query('also with blue hat', now=NOW, entities=entities(),
                            previous_filters=None, planner=planner)
        self.assertEqual(('clarification', 'description_addition_target_unavailable', {}),
                         (result.status, result.reason, result.filters))
        self.assertEqual([], planner.calls)

        first = Proposal(ready('蓝帽子', [('蓝帽子', ['蓝帽子', 'blue hat'])]))
        result = plan_query('请再加上蓝帽子', now=NOW, entities=entities(),
                            previous_filters=HARD_FILTERS, planner=first)
        self.assertEqual('ready', result.status, result)
        self.assertEqual({**HARD_FILTERS, 'descriptive': {'version': 1, 'concepts': [
            {'surface': '蓝帽子', 'alternatives': ['蓝帽子', 'blue hat']},
        ]}}, result.filters)

        invalid = {'version': 1, 'concepts': [
            {'surface': 'Red coat', 'alternatives': ['red coat']},
            {'surface': 'RED COAT', 'alternatives': ['red coat']},
        ]}
        previous = {**HARD_FILTERS, 'descriptive': invalid}
        result = plan_query('also with blue hat', now=NOW, entities=entities(),
                            previous_filters=previous, planner=planner)
        self.assertEqual(('clarification', 'invalid_previous_filters', {}),
                         (result.status, result.reason, result.filters))
        self.assertEqual([], planner.calls)

    def test_duplicate_and_six_concept_limit_fail_before_planner(self):
        previous = {**HARD_FILTERS, 'descriptive': {
            'version': 1, 'concepts': [
                {'surface': 'Red Coat', 'alternatives': ['Red Coat', '红外套']},
            ]}}
        original = deepcopy(previous)
        planner = UnavailablePlanner()
        result = plan_query('also with red coat', now=NOW, entities=entities(),
                            previous_filters=previous, planner=planner)
        self.assertEqual(('clarification', 'description_addition_duplicate', previous),
                         (result.status, result.reason, result.filters))
        self.assertEqual(original, previous)

        six = {**HARD_FILTERS, 'descriptive': {'version': 1, 'concepts': [
            {'surface': f'cue {index}', 'alternatives': [f'cue {index}']}
            for index in range(6)
        ]}}
        original_six = deepcopy(six)
        result = plan_query('请再加上蓝帽子', now=NOW, entities=entities(),
                            previous_filters=six, planner=planner)
        self.assertEqual(('clarification', 'description_addition_limit', six),
                         (result.status, result.reason, result.filters))
        self.assertEqual(original_six, six)
        self.assertEqual([], planner.calls)

    def test_reviewed_labels_in_wrapper_or_target_are_ambiguous_before_model(self):
        previous = {**HARD_FILTERS, 'descriptive': deepcopy(DESCRIPTION)}
        for query, label in (
                ('also with blue hat', 'also'),
                ('add blue hat clue', 'clue'),
                ('also with blue hat', 'blue hat'),
                ('请再加上蓝帽子线索', '请'),
                ('请再加上蓝帽子线索', '蓝帽子')):
            with self.subTest(query=query, label=label):
                planner = Proposal(ready('blue hat', [('blue hat', ['blue hat'])]))
                original = deepcopy(previous)
                result = plan_query(query, now=NOW, entities=entities(labels=(label,)),
                                    previous_filters=previous, planner=planner)
                self.assertEqual(('clarification', 'ambiguous_entities', previous),
                                 (result.status, result.reason, result.filters))
                self.assertEqual(original, previous)
                self.assertEqual([], planner.calls)

    def test_malformed_multi_slot_or_nested_additions_preserve_prior_filters(self):
        previous = {**HARD_FILTERS, 'descriptive': deepcopy(DESCRIPTION)}
        cases = (
            ('also with', 'description_addition_unsupported'),
            ('also with “blue hat”', 'description_addition_unsupported'),
            ('also with blue hat and red shoes', 'description_addition_unsupported'),
            ('also add blue hat, not red coat clue', 'description_addition_unsupported'),
            ('also with blue hat then remove red coat clue', 'description_addition_unsupported'),
            ('also add blue hat and red hat clue', 'description_addition_unsupported'),
            ('请再加上蓝帽子然后移除红外套线索', 'description_addition_unsupported'),
            ('请添加蓝帽子和红鞋线索', 'description_addition_unsupported'),
            ('also with my children playing in snow', 'description_addition_unsupported'),
            ('also with September 2032', 'description_addition_unsupported'),
            ('also with videos', 'description_addition_unsupported'),
        )
        for query, reason in cases:
            with self.subTest(query=query):
                if query == 'also with blue hat and red shoes':
                    planner = Proposal(ready('blue hat and red shoes', [
                        ('blue hat', ['blue hat']), ('red shoes', ['red shoes'])]))
                elif query == 'also add blue hat and red hat clue':
                    planner = Proposal(ready('blue hat and red hat', [
                        ('blue hat', ['blue hat']), ('red hat', ['red hat'])]))
                elif query == '请添加蓝帽子和红鞋线索':
                    planner = Proposal(ready('蓝帽子和红鞋', [
                        ('蓝帽子', ['蓝帽子']), ('红鞋', ['红鞋'])]))
                elif query == 'also with videos':
                    planner = Proposal(ready('videos', [('videos', ['videos'])]))
                elif query == '请再加上蓝帽子然后移除红外套线索':
                    target = '蓝帽子然后移除红外套线索'
                    planner = Proposal(ready(target, [(target, [target])]))
                else:
                    planner = Proposal(None)
                original = deepcopy(previous)
                result = plan_query(query, now=NOW, entities=entities(),
                                    previous_filters=previous, planner=planner)
                self.assertEqual(('clarification', reason, previous),
                                 (result.status, result.reason, result.filters))
                self.assertEqual(original, previous)
                self.assertLessEqual(len(planner.calls), 1)

    def test_hard_slot_offsets_cannot_be_hidden_by_proposed_new_concept(self):
        previous = {**HARD_FILTERS, 'descriptive': deepcopy(DESCRIPTION)}
        cases = (
            ('also with Blue Mira coat', 'Blue Mira coat',
             entities(labels=('Mira',))),
            ('also with blue coat September 2032', 'blue coat September 2032',
             entities()),
            ('also with blue coat videos', 'blue coat videos', entities()),
            ('also with not blue coat', 'not blue coat', entities()),
        )
        for query, proposed, resolved in cases:
            with self.subTest(query=query):
                planner = Proposal(ready(proposed, [(proposed, [proposed])]))
                original = deepcopy(previous)
                result = plan_query(query, now=NOW, entities=resolved,
                                    previous_filters=previous, planner=planner)
                self.assertEqual('clarification', result.status)
                self.assertIn(result.reason, ('ambiguous_entities', 'intent_date',
                                              'description_addition_unsupported', 'invalid_intent'))
                self.assertEqual(previous, result.filters)
                self.assertEqual(original, previous)

    def test_planner_outage_preserves_all_prior_slots(self):
        previous = {**HARD_FILTERS, 'descriptive': deepcopy(DESCRIPTION)}
        original = deepcopy(previous)
        planner = UnavailablePlanner()
        result = plan_query('also with blue hat', now=NOW, entities=entities(),
                            previous_filters=previous, planner=planner)
        self.assertEqual(('clarification', 'intent_unavailable', previous),
                         (result.status, result.reason, result.filters))
        self.assertEqual(original, previous)
        self.assertEqual(1, len(planner.calls))

    def test_single_combined_model_span_cannot_hide_compound_changes_or_actions(self):
        previous = {**HARD_FILTERS, 'descriptive': deepcopy(DESCRIPTION)}
        for target in ('blue hat and red shoes', 'blue hat or red shoes',
                       '蓝帽子和红鞋', 'blue hat and delete all photos',
                       'blue hat; share photos', '蓝帽子然后分享照片'):
            with self.subTest(target=target):
                planner = Proposal(ready(target, [(target, ['blue hat'])]))
                result = plan_query('also with ' + target, now=NOW, entities=entities(),
                                    previous_filters=previous, planner=planner)
                self.assertEqual(('clarification', 'description_addition_unsupported', previous),
                                 (result.status, result.reason, result.filters))
                self.assertEqual([], planner.calls)

    def test_addition_does_not_turn_a_planner_question_into_person_selection(self):
        previous = {**HARD_FILTERS, 'descriptive': deepcopy(DESCRIPTION)}
        planner = Proposal({'version': 1, 'status': 'clarification',
                            'concepts': [], 'question': 'person'})
        result = plan_query('also with blue hat', now=NOW, entities=entities(),
                            previous_filters=previous, planner=planner)
        self.assertEqual(('clarification', 'description_addition_unsupported', previous),
                         (result.status, result.reason, result.filters))


if __name__ == '__main__':
    unittest.main()
