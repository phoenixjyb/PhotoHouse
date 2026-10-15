"""Closed, exact single-concept removal from a saved descriptive search."""
from datetime import datetime
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))

from app.access.search_intent import plan_query


NOW = datetime(2032, 9, 14, 16, 20)
DESCRIPTION = {'version': 1, 'concepts': [
    {'surface': 'red coat', 'alternatives': ['red coat', '红外套']},
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


class UnavailablePlanner:
    def __init__(self):
        self.calls = []

    def propose(self, *args):
        self.calls.append(args)
        raise AssertionError('exact clue removal must not call the planner')


class DescriptiveClueRemovalTests(unittest.TestCase):
    def test_english_chinese_and_mixed_commands_remove_exact_surface_only(self):
        cases = (
            ('remove the “red coat” clue', 'red coat'),
            ('drop "red coat" clue.', 'red coat'),
            ('移除“red coat”这条线索。', 'red coat'),
            ('去掉"red coat"线索！', 'red coat'),
        )
        for query, target in cases:
            with self.subTest(query=query):
                planner = UnavailablePlanner()
                previous = {**HARD_FILTERS, 'descriptive': DESCRIPTION}
                result = plan_query(query, now=NOW, entities=entities(),
                                    previous_filters=previous, planner=planner)
                self.assertEqual('ready', result.status)
                self.assertEqual(HARD_FILTERS, {key: value for key, value in result.filters.items()
                                                if key != 'descriptive'})
                self.assertEqual([DESCRIPTION['concepts'][1]], result.filters['descriptive']['concepts'])
                self.assertEqual([], planner.calls)

    def test_ambiguous_wrapper_or_target_label_is_not_interpreted_as_removal(self):
        previous = {**HARD_FILTERS, 'descriptive': DESCRIPTION}
        for label in ('Remove', 'red coat'):
            with self.subTest(label=label):
                planner = UnavailablePlanner()
                result = plan_query('remove “red coat” clue', now=NOW,
                                    entities=entities(labels=(label,)),
                                    previous_filters=previous, planner=planner)
                self.assertEqual(('clarification', 'ambiguous_entities', previous),
                                 (result.status, result.reason, result.filters))
                self.assertEqual([], planner.calls)

    def test_only_exact_stored_surfaces_match_not_alternatives(self):
        previous = {**HARD_FILTERS, 'descriptive': DESCRIPTION}
        for query in ('remove "红外套" clue', '移除“scarlet coat”线索',
                      'remove “scarlet coat” clue'):
            with self.subTest(query=query):
                planner = UnavailablePlanner()
                result = plan_query(query, now=NOW, entities=entities(),
                                    previous_filters=previous, planner=planner)
                self.assertEqual(('clarification', 'description_removal_mismatch', previous),
                                 (result.status, result.reason, result.filters))
                self.assertEqual([], planner.calls)

    def test_missing_or_invalid_saved_descriptive_context_is_not_guessed(self):
        planner = UnavailablePlanner()
        result = plan_query('remove “red coat” clue', now=NOW, entities=entities(),
                            previous_filters=None, planner=planner)
        self.assertEqual(('clarification', 'description_removal_target_unavailable', {}),
                         (result.status, result.reason, result.filters))
        self.assertEqual([], planner.calls)

        result = plan_query('移除“红外套”线索', now=NOW, entities=entities(),
                            previous_filters=HARD_FILTERS, planner=planner)
        self.assertEqual(('clarification', 'description_removal_target_unavailable', HARD_FILTERS),
                         (result.status, result.reason, result.filters))

        duplicate = {'version': 1, 'concepts': [
            {'surface': 'red coat', 'alternatives': ['red coat']},
            {'surface': 'RED COAT', 'alternatives': ['red coat']},
        ]}
        result = plan_query('remove “red coat” clue', now=NOW, entities=entities(),
                            previous_filters={**HARD_FILTERS, 'descriptive': duplicate},
                            planner=planner)
        self.assertEqual(('clarification', 'invalid_previous_filters', {}),
                         (result.status, result.reason, result.filters))

    def test_malformed_or_extra_words_and_unmatched_quotes_never_fall_through(self):
        previous = {**HARD_FILTERS, 'descriptive': DESCRIPTION}
        for query in (
                'remove “red coat” clue and September 2032',
                'remove red coat clue',
                'remove “red coat” clue please',
                '移除“红外套"线索',
                '去掉“红外套”线索然后找照片'):
            with self.subTest(query=query):
                planner = UnavailablePlanner()
                result = plan_query(query, now=NOW, entities=entities(),
                                    previous_filters=previous, planner=planner)
                self.assertEqual(('clarification', 'description_removal_unsupported', previous),
                                 (result.status, result.reason, result.filters))
                self.assertEqual([], planner.calls)

    def test_removing_last_concept_clears_only_descriptive_filter(self):
        previous = {**HARD_FILTERS, 'descriptive': {
            'version': 1,
            'concepts': [{'surface': 'red coat', 'alternatives': ['red coat', '红外套']}],
        }}
        planner = UnavailablePlanner()
        result = plan_query('remove "red coat" clue', now=NOW, entities=entities(),
                            previous_filters=previous, planner=planner)
        self.assertEqual('ready', result.status)
        self.assertEqual(HARD_FILTERS, result.filters)
        self.assertNotIn('descriptive', result.filters)
        self.assertEqual([], planner.calls)


if __name__ == '__main__':
    unittest.main()
