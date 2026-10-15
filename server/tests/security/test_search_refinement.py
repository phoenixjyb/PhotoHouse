"""Slot removal is explicit, preserves other constraints and stays read-only."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'tests/security')]

from app.access.search_refinement import plan_people_answer, plan_query, query_mode
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
    def people_answer(self, words, *, previous=PREVIOUS, entities=None):
        return plan_people_answer(words, now=NOW,
                                  entities=resolved_entities(words) if entities is None else entities,
                                  previous_filters=previous)

    def test_complete_reviewed_people_answers_replace_only_people_and_preserve_scope(self):
        cases = {
            'Sample Child': {**PREVIOUS, 'people': {'ids': ['301'], 'match': 'any'}},
            '示例儿童': {**PREVIOUS, 'people': {'ids': ['301'], 'match': 'any'}},
            'Sample Child and Sample Adult': {
                **PREVIOUS, 'people': {'ids': ['301', '302'], 'match': 'all'}},
            '示例儿童和示例成人': {
                **PREVIOUS, 'people': {'ids': ['301', '302'], 'match': 'all'}},
            '示例儿童 and Sample Adult': {
                **PREVIOUS, 'people': {'ids': ['301', '302'], 'match': 'all'}},
            'Sample Child or Sample Adult': {
                **PREVIOUS, 'people': {'ids': ['301', '302'], 'match': 'any'}},
            'both Sample Child and Sample Adult': {
                **PREVIOUS, 'people': {'ids': ['301', '302'], 'match': 'all'}},
            'Sample Child together Sample Adult': {
                **PREVIOUS, 'people': {'ids': ['301', '302'], 'match': 'all'}},
        }
        for words, expected in cases.items():
            with self.subTest(words=words):
                result = self.people_answer(words)
                self.assertIsNotNone(result)
                self.assertEqual(result.status, 'ready', result)
                self.assertEqual(result.filters, expected)

    def test_people_answer_requires_context_and_a_valid_current_filter_shape(self):
        missing = self.people_answer('Sample Child', previous=None)
        self.assertEqual(missing.status, 'clarification')
        self.assertEqual(missing.reason, 'refine_without_context')

        invalid = self.people_answer('Sample Child', previous={'date': {'from': 'not-a-date', 'to': None}})
        self.assertEqual(invalid.status, 'clarification')
        self.assertEqual(invalid.reason, 'invalid_previous_filters')

    def test_people_answer_needs_explicit_relation_for_multiple_names(self):
        for words in ('Sample Child Sample Adult', '示例儿童 示例成人'):
            with self.subTest(words=words):
                result = self.people_answer(words)
                self.assertEqual(result.status, 'clarification', result)
                self.assertEqual(result.reason, 'ambiguous_people_answer')
                self.assertEqual(result.filters, PREVIOUS)

    def test_people_answer_does_not_consume_quotes_actions_or_other_conditions(self):
        for words in ('"Sample Child"', 'find Sample Child', 'open Sample Child',
                      'delete Sample Child', 'Sample Child at Mars',
                      'Sample Child September 2032'):
            with self.subTest(words=words):
                self.assertIsNone(self.people_answer(words))

        # A non-people facet in the same phrase is an ordinary search request,
        # not an answer that should replace only the people slot.
        self.assertIsNone(self.people_answer('Sample Child and Park'))

    def test_people_answer_rejects_ambiguous_resolvers_and_operator_label_collisions(self):
        entities = resolved_entities('Sample Child')
        entities['ambiguous'] = True
        ambiguous = self.people_answer('Sample Child', entities=entities)
        self.assertEqual(ambiguous.status, 'clarification')
        self.assertEqual(ambiguous.reason, 'ambiguous_entities')

        entities = resolved_entities('Sample Child and Sample Adult')
        entities['labels'].append('and')
        collision = self.people_answer('Sample Child and Sample Adult', entities=entities)
        self.assertEqual(collision.status, 'clarification')
        self.assertEqual(collision.reason, 'ambiguous_entities')

    def test_correction_surface_whitespace_mixed_scripts_and_quoted_literals(self):
        cases = {
            '  no, I meant videos  ': {**PREVIOUS, 'media': ['video']},
            '不是photos，是videos': {**PREVIOUS, 'media': ['video']},
            'I meant视频': {**PREVIOUS, 'media': ['video']},
        }
        for words, expected in cases.items():
            with self.subTest(words=words):
                self.assertEqual(query_mode(words), 'refine')
                result = plan(words)
                self.assertEqual(result.status, 'ready', (words, result))
                self.assertEqual(result.filters, expected)

        words = 'find photos containing "no, I meant videos"'
        self.assertEqual(query_mode(words), 'search')
        result = plan_query(words, now=NOW, entities=resolved_entities(words),
                            previous_filters=PREVIOUS, refine=False)
        self.assertEqual(result.status, 'ready', result)
        self.assertEqual(result.filters, {'media': ['image'], 'text': 'no, I meant videos'})

    def test_correction_keeps_original_validation_and_requires_refinement_context(self):
        for words in ('actually, February 31, 2032',
                      'not February 31, 2032 but August 2032',
                      'not September 2032 but February 31, 2032'):
            with self.subTest(words=words):
                result = plan(words)
                self.assertEqual(result.status, 'clarification')
                self.assertEqual(result.reason, 'invalid_date')
                self.assertEqual(result.filters, PREVIOUS)

        # A correction cannot turn a new search into a refinement or reset.
        result = plan_query('no, I meant videos', now=NOW,
                            entities=resolved_entities('no, I meant videos'),
                            previous_filters=PREVIOUS, refine=False)
        self.assertEqual(result.status, 'clarification')
        self.assertEqual(result.reason, 'refine_without_context')

        invalid_previous = {'media': ['photos']}
        result = plan('no, I meant videos', previous=invalid_previous)
        self.assertEqual(result.status, 'clarification')
        self.assertEqual(result.reason, 'invalid_previous_filters')

    def test_correction_rejects_colliding_resolved_labels_and_extra_body_operations(self):
        for words, label, reason in (('I meant videos', 'videos', 'ambiguous_media_entity'),
                                     ('actually, September 2032', 'September', 'ambiguous_date_entity')):
            entities = resolved_entities('')
            entities['groups']['people'] = ['301']
            entities['labels'] = [label]
            with self.subTest(words=words, label=label):
                result = plan_query(words, now=NOW, entities=entities,
                                    previous_filters=PREVIOUS, refine=True)
                self.assertEqual(result.status, 'clarification')
                self.assertEqual(result.reason, reason)
                self.assertEqual(result.filters, PREVIOUS)

        for words in ('actually, videos and any date',
                      'actually, videos and same person',
                      'not photos but videos and remove the date filter'):
            with self.subTest(words=words):
                result = plan(words)
                self.assertEqual(result.status, 'clarification')
                self.assertEqual(result.reason, 'unsupported_correction')
                self.assertEqual(result.filters, PREVIOUS)

    def test_bilingual_media_and_date_corrections_replace_exactly_one_slot(self):
        cases = {
            # Intro forms state one positive replacement and inherit every
            # other reviewed constraint from the prior result.
            'no, I meant videos': {**PREVIOUS, 'media': ['video']},
            'I meant photos': PREVIOUS,
            'actually, August 2032': {
                **PREVIOUS, 'date': {'from': '2032-08-01', 'to': '2032-08-31'}},
            '不对，我说的是视频': {**PREVIOUS, 'media': ['video']},
            '我说的是2032年8月': {
                **PREVIOUS, 'date': {'from': '2032-08-01', 'to': '2032-08-31'}},
            'actually，我说的是2032年8月': {
                **PREVIOUS, 'date': {'from': '2032-08-01', 'to': '2032-08-31'}},
            # Paired forms must agree with the old value in PREVIOUS and
            # resolve both sides to the same single slot.
            'not photos but videos': {**PREVIOUS, 'media': ['video']},
            'not photos, but videos': {**PREVIOUS, 'media': ['video']},
            '不是照片，是视频': {**PREVIOUS, 'media': ['video']},
            '不是2032年9月，而是2032年8月': {
                **PREVIOUS, 'date': {'from': '2032-08-01', 'to': '2032-08-31'}},
            'not September 2032 but August 2032': {
                **PREVIOUS, 'date': {'from': '2032-08-01', 'to': '2032-08-31'}},
        }
        for words, expected in cases.items():
            with self.subTest(words=words):
                self.assertEqual(query_mode(words), 'refine')
                result = plan(words)
                self.assertEqual(result.status, 'ready', (words, result))
                self.assertEqual(result.filters, expected)

    def test_correction_requires_a_prior_result_and_an_existing_target_slot(self):
        for words in ('no, I meant videos', '不对，我说的是视频',
                      'not photos but videos', '不是照片，是视频'):
            with self.subTest(words=words):
                self.assertEqual(query_mode(words), 'refine')
                result = plan(words, previous=None)
                self.assertEqual(result.status, 'clarification')
                self.assertEqual(result.reason, 'refine_without_context')

        for words, slot in (('actually, videos', 'media'),
                            ('我说的是2032年8月', 'date')):
            previous = {key: value for key, value in PREVIOUS.items() if key != slot}
            with self.subTest(words=words):
                result = plan(words, previous=previous)
                self.assertEqual(result.status, 'clarification')
                self.assertEqual(result.reason, 'correction_target_unavailable')
                self.assertEqual(result.filters, previous)

    def test_paired_corrections_fail_closed_on_mismatch_cross_slot_and_extra_operations(self):
        cases = {
            'not videos but photos': 'correction_mismatch',
            '不是视频，是照片': 'correction_mismatch',
            'not August 2032 but July 2032': 'correction_mismatch',
            'not photos but August 2032': 'unsupported_correction',
            'not photos but videos in August 2032': 'unsupported_correction',
            'not Sample Child but Sample Adult': 'unsupported_correction',
            'no, I meant videos and any date': 'unsupported_correction',
            'actually, videos, same person': 'unsupported_correction',
            'no, I meant videos on Mars': 'unsupported_condition',
            'no, I meant videos, not Sample Child': 'unsupported_negation',
        }
        for words, reason in cases.items():
            with self.subTest(words=words):
                result = plan(words)
                self.assertEqual(result.status, 'clarification')
                self.assertEqual(result.reason, reason)
                self.assertEqual(result.filters, PREVIOUS)

    def test_correction_validates_original_syntax_limits_and_entity_collisions(self):
        for words, expected_reason in (
                ('actually, videos containing "unfinished', 'ambiguous_quote'),
                ('no, I meant videos ' + ('x' * 1024), 'invalid_query'),
                ('我说的是视频' + ('中' * 600), 'invalid_query'),
                ('I meant videos \ud800', 'invalid_query')):
            with self.subTest(length=len(words)):
                result = plan(words)
                self.assertEqual(result.status, 'clarification')
                self.assertEqual(result.reason, expected_reason)

        words = 'no, I meant Sample Child videos'
        result = plan(words)
        self.assertEqual(result.status, 'clarification')
        self.assertEqual(result.reason, 'unsupported_correction')
        self.assertEqual(result.filters, PREVIOUS)

        # Even an entity label inside the correction introducer is ambiguous;
        # it cannot be consumed as harmless framing.
        entities = resolved_entities('')
        entities['groups']['people'] = ['301']
        entities['labels'] = ['I meant']
        result = plan_query('I meant videos', now=NOW, entities=entities,
                            previous_filters=PREVIOUS, refine=True)
        self.assertEqual(result.status, 'clarification')
        self.assertEqual(result.reason, 'ambiguous_entities')
        self.assertEqual(result.filters, PREVIOUS)

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

    def test_bounded_people_references_preserve_prior_slots_and_cardinality(self):
        plural = deepcopy(PREVIOUS)
        plural['people'] = {'ids': ['301', '302'], 'match': 'all'}
        singular = deepcopy(PREVIOUS)
        singular['people'] = {'ids': ['301'], 'match': 'any'}
        plural_markers = ('same people', 'these people', 'those people', 'them', 'they', 'their',
                          '同一批人', '他们', '她们', '这些人', '那些人')
        singular_markers = ('same person', 'him', 'her', 'his', '他', '她', '这个人', '那个人')

        for marker in plural_markers:
            with self.subTest(marker=marker):
                self.assertEqual(query_mode(marker), 'refine')
                result = plan(marker, previous=plural)
                self.assertEqual(result.status, 'ready', result)
                self.assertEqual(result.filters, plural)
        for marker in singular_markers:
            with self.subTest(marker=marker):
                self.assertEqual(query_mode(marker), 'refine')
                result = plan(marker, previous=singular)
                self.assertEqual(result.status, 'ready', result)
                self.assertEqual(result.filters, singular)

        # The prior people operator is an opaque resolved constraint. Reuse it
        # exactly for both supported match modes; never reconstruct IDs.
        for match in ('any', 'all'):
            previous = deepcopy(plural)
            previous['people']['match'] = match
            result = plan('same people', previous=previous)
            self.assertEqual(result.status, 'ready', result)
            self.assertEqual(result.filters['people'], previous['people'])
            self.assertEqual({key: value for key, value in result.filters.items() if key != 'people'},
                             {key: value for key, value in previous.items() if key != 'people'})

    def test_people_references_combine_with_date_and_media_without_dropping_other_slots(self):
        result = plan('same people, last month')
        self.assertEqual(result.status, 'ready', result)
        self.assertEqual(result.filters, {
            **PREVIOUS, 'date': {'from': '2032-08-01', 'to': '2032-08-31'}})

        plural = deepcopy(PREVIOUS)
        plural['people'] = {'ids': ['301', '302'], 'match': 'all'}
        cases = {
            'show videos of them': {**plural, 'media': ['video']},
            'their videos': {**plural, 'media': ['video']},
            '他们上个月的视频': {**plural, 'media': ['video'],
                               'date': {'from': '2032-08-01', 'to': '2032-08-31'}},
        }
        for words, expected in cases.items():
            with self.subTest(words=words):
                self.assertEqual(query_mode(words), 'refine')
                result = plan(words, previous=plural)
                self.assertEqual(result.status, 'ready', result)
                self.assertEqual(result.filters, expected)

        self.assertEqual(query_mode('his photos'), 'refine')
        singular = deepcopy(PREVIOUS)
        singular['people'] = {'ids': ['301'], 'match': 'any'}
        his_photos = plan('his photos', previous=singular)
        self.assertEqual(his_photos.status, 'ready', his_photos)
        self.assertEqual(his_photos.filters, singular)

        for words, expected in (
                ('same people and last month', {
                    **PREVIOUS, 'date': {'from': '2032-08-01', 'to': '2032-08-31'}}),
                ('同一批人和上个月的视频', {
                    **PREVIOUS, 'media': ['video'],
                    'date': {'from': '2032-08-01', 'to': '2032-08-31'}})):
            with self.subTest(words=words):
                self.assertEqual(query_mode(words), 'refine')
                result = plan(words)
                self.assertEqual(result.status, 'ready', result)
                self.assertEqual(result.filters, expected)

        removed = plan('same people, any date')
        self.assertEqual(removed.status, 'ready', removed)
        self.assertEqual(removed.filters, {key: value for key, value in PREVIOUS.items() if key != 'date'})

    def test_people_reference_context_and_cardinality_fail_closed(self):
        for words in ('same people', 'them', '他们'):
            with self.subTest(words=words):
                missing_context = plan(words, previous=None)
                self.assertEqual(missing_context.status, 'clarification')
                self.assertEqual(missing_context.reason, 'refine_without_context')
                without_people = {key: value for key, value in PREVIOUS.items() if key != 'people'}
                missing_people = plan(words, previous=without_people)
                self.assertEqual(missing_people.status, 'clarification')
                self.assertEqual(missing_people.reason, 'people_reference_unavailable')

        for words, previous in (
                ('these people', {'people': {'ids': ['301'], 'match': 'any'}}),
                ('same person', {'people': {'ids': ['301', '302'], 'match': 'all'}}),
                ('same people', {'people': {'ids': ['301'], 'match': 'invalid'}})):
            with self.subTest(words=words, previous=previous):
                result = plan(words, previous=previous)
                self.assertEqual(result.status, 'clarification')
                expected = 'invalid_previous_filters' if previous['people']['match'] == 'invalid' else 'ambiguous_people_reference'
                self.assertEqual(result.reason, expected)

        for words in ('him and her', '他和她'):
            with self.subTest(words=words):
                self.assertEqual(query_mode(words), 'refine')
                result = plan(words)
                self.assertEqual(result.status, 'clarification')
                self.assertEqual(result.reason, 'ambiguous_people_reference')
                self.assertEqual(result.filters, PREVIOUS)

    def test_people_reference_collisions_and_explicit_people_edits_clarify(self):
        entities = resolved_entities('same people Sample Child')
        result = plan_query('same people Sample Child', now=NOW, entities=entities,
                            previous_filters=PREVIOUS, refine=True)
        self.assertEqual(result.status, 'clarification')
        self.assertEqual(result.reason, 'conflicting_people_reference')

        entities = resolved_entities('same people')
        entities['labels'] = ['them']
        result = plan_query('them', now=NOW, entities=entities,
                            previous_filters=PREVIOUS, refine=True)
        self.assertEqual(result.status, 'clarification')
        self.assertEqual(result.reason, 'ambiguous_entities')

        entities = resolved_entities('')
        entities['groups']['people'] = ['301']
        entities['labels'] = ['他山']
        result = plan_query('他山', now=NOW, entities=entities,
                            previous_filters=PREVIOUS, refine=True)
        self.assertEqual(result.status, 'clarification')
        self.assertEqual(result.reason, 'ambiguous_entities')

        for words in ('same people, anyone', 'same people, last month except Sample Child',
                      'same people 13月', 'same people, only photos and videos'):
            with self.subTest(words=words):
                result = plan(words)
                self.assertEqual(result.status, 'clarification', result)
                self.assertEqual(result.filters, PREVIOUS)
        self.assertEqual(plan('same people, anyone').reason, 'conflicting_people_reference')

    def test_people_reference_markers_inside_quotes_remain_literal_text(self):
        self.assertIsNone(query_mode('"them"'))
        self.assertIsNone(query_mode('gather'))
        self.assertIsNone(query_mode('Herbert'))
        self.assertIsNone(query_mode('other people'))
        self.assertIsNone(query_mode('containing "they"'))
        for marker in ('them', 'same people', '他们'):
            words = f'only photos containing "{marker}"'
            with self.subTest(marker=marker):
                result = plan(words)
                self.assertEqual(result.status, 'ready', result)
                self.assertEqual(result.filters['text'], marker)
                self.assertEqual(result.filters['people'], PREVIOUS['people'])

    def test_reference_wrapper_preserves_original_validation(self):
        cases = (
            ('him containing "unfinished', 'ambiguous_quote'),
            ('him containing ""', 'ambiguous_quote'),
            ('him ' + ('x' * 1024), 'invalid_query'),
            ('他' + ('中' * 600), 'invalid_query'),
            ('him \ud800', 'invalid_query'),
        )
        for words, expected_reason in cases:
            with self.subTest(expected_reason=expected_reason, length=len(words)):
                result = plan(words)
                self.assertEqual(result.status, 'clarification')
                self.assertEqual(result.reason, expected_reason)

        invalid_previous = {'people': {'ids': ['301'], 'match': 'unknown'}}
        result = plan('him', previous=invalid_previous)
        self.assertEqual(result.status, 'clarification')
        self.assertEqual(result.reason, 'invalid_previous_filters')


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

    def test_corrections_replay_exact_filters_and_return_exact_synthetic_results(self):
        initial = self.fixture.turn(
            'find Sample Child and Sample Adult photos in September 2032 containing "海边"').json()
        self.assertEqual(initial['kind'], 'results', initial)
        self.assertEqual([item['id'] for item in initial['items']], ['103'])

        # One-slot date correction keeps the media, people and literal text
        # filters. The synthetic fixture has no matching August asset.
        corrected_date = self.fixture.turn(
            'not September 2032 but August 2032', context=initial['context']).json()
        self.assertEqual(corrected_date['kind'], 'results', corrected_date)
        self.assertEqual(corrected_date['filters'], {
            **initial['filters'], 'date': {'from': '2032-08-01', 'to': '2032-08-31'}})
        self.assertEqual(corrected_date['items'], [])
        self.assertEqual(corrected_date['total'], 0)

        # A media correction also changes only its slot. There are no videos
        # with the inherited September date and people assignment.
        corrected_media = self.fixture.turn(
            'not photos but videos', context=initial['context']).json()
        self.assertEqual(corrected_media['kind'], 'results', corrected_media)
        self.assertEqual(corrected_media['filters'], {
            **initial['filters'], 'media': ['video']})
        self.assertEqual(corrected_media['items'], [])
        self.assertEqual(corrected_media['total'], 0)

    def test_correction_mismatch_and_missing_context_preserve_response_state(self):
        initial = self.fixture.turn('find photos containing "海边"').json()
        self.assertEqual(initial['kind'], 'results', initial)
        mismatch = self.fixture.turn(
            'not videos but photos', context=initial['context']).json()
        self.assertEqual(mismatch['kind'], 'clarification', mismatch)
        self.assertEqual(mismatch['filters'], initial['filters'])
        self.assertEqual(mismatch['context'], initial['context'])
        self.assertEqual(mismatch['items'], initial['items'])

        no_context = self.fixture.turn('no, I meant videos').json()
        self.assertEqual(no_context['kind'], 'clarification', no_context)
        self.assertIsNone(no_context['context'])
        self.assertEqual(no_context['items'], [])

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

    def test_people_reference_replays_context_and_replaces_only_explicit_slots(self):
        initial = self.fixture.turn(
            'find Sample Child and Sample Adult photos in August 2032 containing "海边"').json()
        self.assertEqual(initial['kind'], 'results', initial)
        self.assertEqual(initial['total'], 0)
        self.assertEqual(initial['filters']['people'], {'ids': ['301', '302'], 'match': 'all'})

        date_result = self.fixture.turn('these people September 2032', context=initial['context']).json()
        self.assertEqual(date_result['kind'], 'results', date_result)
        self.assertEqual(date_result['filters'], {
            **initial['filters'], 'date': {'from': '2032-09-01', 'to': '2032-09-30'}})
        self.assertEqual([item['id'] for item in date_result['items']], ['103'])

        media_result = self.fixture.turn('show videos of them', context=date_result['context']).json()
        self.assertEqual(media_result['kind'], 'results', media_result)
        self.assertEqual(media_result['filters'], {**date_result['filters'], 'media': ['video']})
        # The video has no reviewed assignment to this person, so retaining
        # the exact people constraint correctly yields no cards.
        self.assertEqual(media_result['items'], [])
        self.assertEqual(media_result['total'], 0)

    def test_people_reference_rejects_missing_or_nonpeople_context_and_keeps_it_on_clarification(self):
        without_people = self.fixture.turn('find photos').json()
        self.assertEqual(without_people['kind'], 'results', without_people)
        self.assertTrue(without_people['items'])  # Visible faces/cards do not supply a people filter.
        no_people = self.fixture.turn('them', context=without_people['context']).json()
        self.assertEqual(no_people['kind'], 'clarification', no_people)
        self.assertEqual(no_people['context'], without_people['context'])
        self.assertEqual(no_people['items'], without_people['items'])

        no_context = self.fixture.turn('them').json()
        self.assertEqual(no_context['kind'], 'clarification', no_context)
        self.assertIsNone(no_context['context'])
        self.assertEqual(no_context['items'], [])

    def test_people_reference_rejects_denied_tampered_and_stale_context(self):
        response = self.fixture.turn('find Sample Child and Sample Adult photos in September 2032')
        self.assertEqual(response.status_code, 200, response.text)
        initial = response.json()
        self.assertEqual(initial['kind'], 'results', initial)
        context = initial['context']

        denied = self.fixture.turn('same person', context=context, token=OTHER)
        self.assertNotEqual(denied.status_code, 200)

        tampered_context = deepcopy(context)
        tampered_context['filters']['people'] = {'ids': ['302'], 'match': 'any'}
        tampered = self.fixture.turn('same person', context=tampered_context)
        self.assertNotEqual(tampered.status_code, 200)

        self.fixture.mutate("UPDATE assets SET status='hidden' WHERE id=103")
        stale = self.fixture.turn('same person', context=context)
        self.assertEqual(stale.status_code, 409, stale.text)

    def test_corrections_reject_denied_tampered_and_stale_context(self):
        response = self.fixture.turn(
            'find Sample Child and Sample Adult photos in September 2032')
        self.assertEqual(response.status_code, 200, response.text)
        initial = response.json()
        self.assertEqual(initial['kind'], 'results', initial)
        self.assertTrue(initial['items'])
        context = initial['context']

        denied = self.fixture.turn('not photos but videos', context=context, token=OTHER)
        self.assertNotEqual(denied.status_code, 200)

        tampered_context = deepcopy(context)
        tampered_context['filters']['media'] = ['video']
        tampered = self.fixture.turn('not photos but videos', context=tampered_context)
        self.assertNotEqual(tampered.status_code, 200)

        self.fixture.mutate("UPDATE assets SET status='hidden' WHERE id=103")
        stale = self.fixture.turn('not photos but videos', context=context)
        self.assertEqual(stale.status_code, 409, stale.text)


if __name__ == '__main__':
    unittest.main()
