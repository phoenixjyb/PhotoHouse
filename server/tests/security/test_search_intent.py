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
    def test_person_led_disposal_construction_preserves_every_covered_condition(self):
        cases = (
            ('找示例儿童把绿色卡片放进纸盒的2031年6月视频包含“spring fair”',
             '示例儿童', ('绿色卡片', '放进', '纸盒')),
            ('find Mira 把 green card 放进 paper box 的 videos in June 2031 containing "spring fair"',
             'Mira', ('green card', '放进', 'paper box')),
            ('找Mira把红色纸条折成小船的2031年6月视频包含“spring fair”',
             'Mira', ('红色纸条', '折成', '小船')),
            ('找Mira把透明杯子摆在木桌的2031年6月视频包含“spring fair”',
             'Mira', ('透明杯子', '摆', '木桌')),
        )
        for query, label, clues in cases:
            with self.subTest(query=query):
                planner = Proposal(ready(query, [(clue, [clue]) for clue in clues]))
                result = plan_query(query, now=NOW, entities=entities(labels=[label], people=['301']),
                                    previous_filters=None, planner=planner)
                self.assertEqual('ready', result.status, result)
                self.assertEqual({'media': ['video'], 'people': {'ids': ['301'], 'match': 'any'},
                                  'date': {'from': '2031-06-01', 'to': '2031-06-30'},
                                  'text': 'spring fair'},
                                 {k: v for k, v in result.filters.items() if k != 'descriptive'})
                self.assertEqual(list(clues), [c['surface'] for c in
                                              result.filters['descriptive']['concepts']])
                self.assertEqual(1, len(planner.calls))

    def test_disposal_grammar_never_consumes_missing_actions_objects_or_quantities(self):
        cases = (
            ('找Mira把绿色卡片放进纸盒的视频', ('绿色卡片', '纸盒')),
            ('找Mira把绿色卡片放进纸盒的视频', ('绿色卡片', '放进')),
            ('找Mira把两张绿色卡片放进纸盒的视频', ('绿色卡片', '放进', '纸盒')),
            ('找Mira把绿色卡片悄悄放进纸盒的视频', ('绿色卡片', '放进', '纸盒')),
            ('找Mira把绿色卡片放进纸盒旁边的视频', ('绿色卡片', '放进', '纸盒')),
            ('找Mira把绿色卡片的视频', ('绿色卡片',)),
        )
        for query, clues in cases:
            with self.subTest(query=query, clues=clues):
                planner = Proposal(ready(query, [(clue, [clue]) for clue in clues]))
                result = plan_query(query, now=NOW, entities=entities(labels=['Mira'], people=['301']),
                                    previous_filters=None, planner=planner)
                self.assertEqual(('clarification', 'unsupported_condition'),
                                 (result.status, result.reason))
                self.assertEqual({}, result.filters)
                self.assertEqual(1, len(planner.calls))

    def test_disposal_grammar_requires_one_unambiguous_person_label(self):
        query = '找Mira把绿色卡片放进纸盒的视频'
        for resolved in (entities(), entities(labels=['Mira'], tags=['301']),
                         entities(labels=['Mira'], people=['301', '302']),
                         entities(labels=['Mira', 'Alias'], people=['301']),
                         entities(labels=['Mira'], people=['301'], locations=['401']),
                         entities(labels=[''], people=['301'])):
            with self.subTest(resolved=resolved):
                planner = Proposal(ready(query, [(x, [x]) for x in ('绿色卡片', '放进', '纸盒')]))
                result = plan_query(query, now=NOW, entities=resolved,
                                    previous_filters=None, planner=planner)
                self.assertEqual('clarification', result.status, result)
                self.assertEqual({}, result.filters)

    def test_disposal_grammar_preserves_compound_words_and_refinement_scope(self):
        for full, partial in (('把手', '手'), ('把玩红色丝带', '玩红色丝带')):
            query = '找Mira' + full + '放进纸盒的视频'
            for surface, expected in ((full, 'ready'), (partial, 'clarification')):
                with self.subTest(surface=surface):
                    planner = Proposal(ready(query, [(x, [x]) for x in (surface, '放进', '纸盒')]))
                    result = plan_query(query, now=NOW, entities=entities(labels=['Mira'], people=['301']),
                                        previous_filters=None, planner=planner)
                    self.assertEqual(expected, result.status, result)
                    if result.status == 'ready':
                        self.assertEqual(full, result.filters['descriptive']['concepts'][0]['surface'])

        previous = {'date': {'from': '2030-01-01', 'to': '2030-12-31'},
                    'media': ['image'], 'text': 'retained note'}
        query = '再找Mira把绿色卡片放进纸盒的视频'
        planner = Proposal(ready(query, [(x, [x]) for x in ('绿色卡片', '放进', '纸盒')]))
        result = plan_query(query, now=NOW, entities=entities(labels=['Mira'], people=['301']),
                            previous_filters=previous, planner=planner)
        self.assertEqual('ready', result.status, result)
        self.assertEqual(previous['date'], result.filters['date'])
        self.assertEqual(previous['text'], result.filters['text'])
        self.assertEqual(['video'], result.filters['media'])
        self.assertEqual({'ids': ['301'], 'match': 'any'}, result.filters['people'])

    def test_additional_provider_boundary_only_accepts_an_already_blank_slot(self):
        query = 'find photos carrying    red bag'
        gap = (query.index('    '), query.index('    ') + 4)
        for invalid in ((0, 4), (gap[0], gap[1] + 1), (-1, 2), (2, 1),
                        (True, 2), [*gap], 'gap', (gap[0],), (0, len(query) + 1)):
            with self.subTest(span=invalid):
                planner = Proposal(None)
                result = plan_query(query, now=NOW, entities=entities(), previous_filters=None,
                                    planner=planner, redacted_span=invalid)
                self.assertEqual(('clarification', 'invalid_query'), (result.status, result.reason))
                self.assertEqual([], planner.calls)

        planner = Proposal(ready(query, [('carrying', ['carrying']), ('red bag', ['red bag'])]))
        result = plan_query(query, now=NOW, entities=entities(), previous_filters=None,
                            planner=planner, redacted_span=gap)
        self.assertEqual('ready', result.status)
        self.assertEqual('█' * 4, planner.calls[0][0][gap[0]:gap[1]])
        self.assertEqual(len(query), len(planner.calls[0][0]))

    def test_about_approximate_time_is_not_an_unquoted_content_cue(self):
        for query in ('find photos about two years ago',
                      'find photos about a few winters ago'):
            with self.subTest(query=query):
                planner = Proposal(None)
                result = plan_query(query, now=NOW, entities=entities(),
                                    previous_filters=None, planner=planner)
                self.assertEqual(('clarification', 'intent_date'),
                                 (result.status, result.reason))
                self.assertEqual([], planner.calls)

    def test_strong_unquoted_content_cues_stay_literal_without_provider_calls(self):
        cases = (
            ('find photos containing childhood snow', 'childhood snow'),
            ('find photos about childhood red coat', 'childhood red coat'),
            ('find photos with the words childhood snow', 'childhood snow'),
            ('找包含小时候玩雪的照片', '小时候玩雪'),
            ('找关于小时候玩雪的照片', '小时候玩雪'),
        )
        for query, expected in cases:
            with self.subTest(query=query):
                planner = Proposal(None)
                result = plan_query(query, now=NOW, entities=entities(),
                                    previous_filters=None, planner=planner)
                self.assertEqual('ready', result.status, result)
                self.assertEqual(expected, result.filters['text'])
                self.assertNotIn('descriptive', result.filters)
                self.assertEqual([], planner.calls)

        # A bare content noun does not activate the literal-cue fast path.
        planner = Proposal(ready('find photos content birthday cake',
                                 [('birthday cake', ['birthday cake'])]))
        result = plan_query('find photos content birthday cake', now=NOW,
                            entities=entities(), previous_filters=None, planner=planner)
        self.assertEqual(('clarification', 'unsupported_condition'),
                         (result.status, result.reason))
        self.assertEqual(1, len(planner.calls))

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
        self.assertEqual(1, len(planner.calls))
        visible, today, previous = planner.calls[0]
        self.assertEqual(('2032-09-14', False), (today, previous))
        self.assertEqual(len(query), len(visible))
        for hidden in ('Sample Child', 'Home', 'yesterday', 'videos', 'family day'):
            self.assertNotIn(hidden, visible)
        for clue in ('wearing red', 'holding a cake'):
            start = query.index(clue)
            self.assertEqual(clue, visible[start:start + len(clue)])

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

    def test_provider_spans_cannot_bridge_redacted_words_or_a_conversational_opening(self):
        for query, surface, resolved in (
                ('find red Mira coat photos', 'red Mira coat',
                 entities(labels=('Mira',), people=('301',))),
                ('I am looking for red coat photos', 'I am looking for red coat', entities())):
            with self.subTest(query=query):
                planner = Proposal(ready(query, [(surface, ['red coat'])]))
                result = plan_query(query, now=NOW, entities=resolved,
                                    previous_filters=None, planner=planner)
                self.assertEqual(('clarification', 'invalid_intent', {}),
                                 (result.status, result.reason, result.filters))

    def test_reviewed_age_like_name_is_hidden_from_scenes_without_a_date_question(self):
        query = 'find photos of Childhood wearing red'
        planner = Proposal(ready(query, [('wearing red', ['wearing red'])]))
        result = plan_query(query, now=NOW,
                            entities=entities(labels=('Childhood',), people=('301',)),
                            previous_filters=None, planner=planner)
        self.assertEqual('ready', result.status, result)
        self.assertEqual({'ids': ['301'], 'match': 'any'}, result.filters['people'])
        self.assertNotIn('Childhood', planner.calls[0][0])

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
                ('找小时候的照片', '小时候'),
                ('find photos about two years ago', 'about two years ago'),
                ('找大概两年前的照片', '大概两年前')):
            with self.subTest(query=query):
                planner = Proposal(ready(query, [(surface, [surface])]))
                result = plan_query(query, now=NOW, entities=entities(),
                                    previous_filters=None, planner=planner)
                self.assertEqual(('clarification', 'intent_date', {}),
                                 (result.status, result.reason, result.filters))
                self.assertEqual([], planner.calls)

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

    def test_paired_descriptive_corrections_replace_one_surface_and_preserve_context(self):
        previous = {
            'people': {'ids': ['301'], 'match': 'any'},
            'media': ['image'],
            'date': {'from': '2032-09-01', 'to': '2032-09-30'},
            'text': 'Exact Family Phrase',
            'descriptive': {'version': 1, 'concepts': [
                {'surface': 'red coat', 'alternatives': ['red coat', '红外套']},
                {'surface': 'playing in snow', 'alternatives': ['playing in snow', '在雪地里玩']},
            ]},
        }
        cases = (
            ('not red coat, but blue coat', 'red coat', 'blue coat', ['blue coat', '蓝外套']),
            ('不是红外套，是蓝外套', '红外套', '蓝外套', ['blue coat', '蓝外套']),
            ('不是red coat，而是蓝外套', 'red coat', '蓝外套', ['blue coat', '蓝外套']),
        )
        for query, old_surface, replacement_surface, alternatives in cases:
            with self.subTest(query=query):
                case_previous = {**previous, 'descriptive': {'version': 1, 'concepts': [
                    {'surface': old_surface, 'alternatives': [old_surface]},
                    previous['descriptive']['concepts'][1],
                ]}}
                planner = Proposal(ready(replacement_surface,
                                         [(replacement_surface, alternatives)]))
                result = plan_query(query, now=NOW, entities=entities(people=('301',)),
                                    previous_filters=case_previous, planner=planner)
                expected = {**case_previous, 'descriptive': {'version': 1, 'concepts': [
                    {'surface': replacement_surface, 'alternatives': alternatives},
                    previous['descriptive']['concepts'][1],
                ]}}
                self.assertEqual(('ready', None, expected),
                                 (result.status, result.reason, result.filters))
                self.assertEqual([(replacement_surface, '2032-09-14', False)], planner.calls)

    def test_descriptive_correction_requires_unique_exact_stored_surface_and_one_concept(self):
        previous = {'descriptive': {'version': 1, 'concepts': [
            {'surface': 'red coat', 'alternatives': ['red coat', '红外套']},
            {'surface': 'snow', 'alternatives': ['snow', '雪']},
        ]}}
        planner = Proposal(ready('blue coat', [('blue coat', ['blue coat'])]))
        result = plan_query('not RED COAT but blue coat', now=NOW, entities=entities(),
                            previous_filters=previous, planner=planner)
        self.assertEqual('ready', result.status)
        self.assertEqual('blue coat', result.filters['descriptive']['concepts'][0]['surface'])
        self.assertEqual([('blue coat', '2032-09-14', False)], planner.calls)

        planner = Proposal(ready('blue coat', [('blue coat', ['blue coat'])]))
        mismatch = plan_query('not scarlet coat but blue coat', now=NOW,
                              entities=entities(), previous_filters=previous, planner=planner)
        self.assertEqual(('clarification', 'description_correction_mismatch', previous),
                         (mismatch.status, mismatch.reason, mismatch.filters))
        self.assertEqual([], planner.calls)

        alternative_only = plan_query('不是红外套，是蓝外套', now=NOW,
                                      entities=entities(), previous_filters=previous,
                                      planner=Proposal(None))
        self.assertEqual(('clarification', 'description_correction_mismatch', previous),
                         (alternative_only.status, alternative_only.reason,
                          alternative_only.filters))

        no_description = {'media': ['image']}
        planner = Proposal(None)
        unavailable = plan_query('not red coat but blue coat', now=NOW,
                                 entities=entities(), previous_filters=no_description,
                                 planner=planner)
        self.assertEqual(('clarification', 'description_correction_target_unavailable',
                          no_description),
                         (unavailable.status, unavailable.reason, unavailable.filters))
        self.assertEqual([], planner.calls)

        planner = Proposal(None)
        no_previous = plan_query('not red coat but blue coat', now=NOW,
                                 entities=entities(), previous_filters=None, planner=planner)
        self.assertEqual(('clarification', 'refine_without_context'),
                         (no_previous.status, no_previous.reason))
        self.assertEqual([], planner.calls)

        # A malformed stale context is refused before provider work.
        stale = {'descriptive': {'version': 1, 'concepts': [
            {'surface': 'red coat', 'alternatives': ['red coat']},
            {'surface': 'RED COAT', 'alternatives': ['red coat two']},
        ]}}
        planner = Proposal(None)
        invalid = plan_query('not red coat but blue coat', now=NOW,
                             entities=entities(), previous_filters=stale, planner=planner)
        self.assertEqual(('clarification', 'invalid_previous_filters'),
                         (invalid.status, invalid.reason))
        self.assertEqual([], planner.calls)

    def test_descriptive_correction_never_consumes_protected_or_hardfilter_new_phrases(self):
        previous = {
            'people': {'ids': ['301'], 'match': 'any'},
            'date': {'from': '2032-09-01', 'to': '2032-09-30'},
            'descriptive': {'version': 1, 'concepts': [
                {'surface': 'red coat', 'alternatives': ['red coat']}]},
        }
        cases = (
            ('not red coat but "blue coat"', entities(), 'description_correction_unsupported'),
            ('not red coat but Blue Coat', entities(labels=('Blue Coat',)), 'ambiguous_entities'),
            ('not red coat but blue coat', entities(labels=('But',)), 'ambiguous_entities'),
            ('not red coat but Blue Coat!', entities(labels=('Blue Coat!',)), 'ambiguous_entities'),
            ('not red coat but September 2032', entities(), 'description_correction_unsupported'),
            ('not red coat but videos', entities(), 'description_correction_unsupported'),
            ('not red coat but delete photos', entities(), 'description_correction_unsupported'),
            ('not red coat but clear date filter', entities(), 'description_correction_unsupported'),
        )
        for query, resolved, reason in cases:
            with self.subTest(query=query):
                planner = Proposal(None)
                result = plan_query(query, now=NOW, entities=resolved,
                                    previous_filters=previous, planner=planner)
                self.assertEqual(('clarification', reason, previous),
                                 (result.status, result.reason, result.filters))
                self.assertEqual([], planner.calls)

        invalid_date = plan_query('not red coat but February 31 2032', now=NOW,
                                  entities=entities(), previous_filters=previous,
                                  planner=Proposal(None))
        self.assertEqual(('clarification', 'invalid_date', previous),
                         (invalid_date.status, invalid_date.reason, invalid_date.filters))

        same_media = {**previous, 'media': ['image']}
        media_attempt = plan_query('not red coat but blue coat photos', now=NOW,
                                   entities=entities(), previous_filters=same_media,
                                   planner=Proposal(None))
        self.assertEqual(('clarification', 'description_correction_unsupported', same_media),
                         (media_attempt.status, media_attempt.reason, media_attempt.filters))

        # The date is already present with this exact value, but NEW still
        # contributes a hard filter and cannot be accepted as a description.
        date_attempt = plan_query('not red coat but September 2032', now=NOW,
                                  entities=entities(), previous_filters=previous,
                                  planner=Proposal(None))
        self.assertEqual(('clarification', 'description_correction_unsupported', previous),
                         (date_attempt.status, date_attempt.reason, date_attempt.filters))

        query = 'not red coat but my children playing in snow'
        planner = Proposal(ready(query.split('but ', 1)[1], [
            (query.split('but ', 1)[1], ['my children playing in snow'])]))
        result = plan_query(query, now=NOW, entities=entities(),
                            previous_filters=previous, planner=planner)
        self.assertEqual(('clarification', 'description_correction_unsupported', previous),
                         (result.status, result.reason, result.filters))
        self.assertEqual([(query.split('but ', 1)[1], '2032-09-14', False)], planner.calls)

        planner = Proposal(ready('blue coat and red hat', [
            ('blue coat', ['blue coat']), ('red hat', ['red hat'])]))
        multiple = plan_query('not red coat but blue coat and red hat', now=NOW,
                              entities=entities(), previous_filters=previous, planner=planner)
        self.assertEqual(('clarification', 'description_correction_unsupported', previous),
                         (multiple.status, multiple.reason, multiple.filters))
        self.assertEqual([('blue coat and red hat', '2032-09-14', False)], planner.calls)

    def test_descriptive_correction_provider_failures_preserve_prior_plan_and_do_not_retry(self):
        previous = {'media': ['image'], 'descriptive': {'version': 1, 'concepts': [
            {'surface': 'red coat', 'alternatives': ['red coat']}]}}

        class Down:
            def __init__(self):
                self.calls = []

            def propose(self, query, today, has_previous_search):
                self.calls.append((query, today, has_previous_search))
                from app.access.search_intent import IntentUnavailable
                raise IntentUnavailable()

        planner = Down()
        result = plan_query('not red coat but blue coat', now=NOW, entities=entities(),
                            previous_filters=previous, planner=planner)
        self.assertEqual(('clarification', 'intent_unavailable', previous),
                         (result.status, result.reason, result.filters))
        self.assertEqual([('blue coat', '2032-09-14', False)], planner.calls)

        unsupported = Proposal({'version': 1, 'status': 'clarification',
                                'concepts': [], 'question': 'description'})
        result = plan_query('not red coat but blue coat', now=NOW, entities=entities(),
                            previous_filters=previous, planner=unsupported)
        self.assertEqual(('clarification', 'description_correction_unsupported', previous),
                         (result.status, result.reason, result.filters))
        self.assertEqual([('blue coat', '2032-09-14', False)], unsupported.calls)

    def test_existing_date_and_media_paired_corrections_remain_authoritative(self):
        previous = {'media': ['image'], 'descriptive': {'version': 1, 'concepts': [
            {'surface': 'red coat', 'alternatives': ['red coat']}]}}
        planner = Proposal(None)
        result = plan_query('not images but videos', now=NOW, entities=entities(),
                            previous_filters=previous, planner=planner)
        self.assertEqual(('ready', {**previous, 'media': ['video']}),
                         (result.status, result.filters))
        self.assertEqual([], planner.calls)


if __name__ == '__main__':
    unittest.main()
