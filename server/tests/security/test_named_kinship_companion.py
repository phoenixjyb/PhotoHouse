"""Named person plus possessive parent queries stay explicit and fail closed."""
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'scripts'), str(ROOT / 'tests/security')]

import test_reviewed_family_search_journeys as family_journey
from phone_discovery_fixture import SECOND
from app.access.kinship import KinshipGraph


class UnexpectedIntentPlanner:
    def __init__(self):
        self.calls = []

    def propose(self, query, today, has_previous_search):
        self.calls.append(query)
        raise AssertionError('hard named-kinship searches must not call the intent planner')


class NamedKinshipCompanionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = family_journey.ReviewedFamilySearchJourneys('runTest')
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.f = self.fixture.fixture
        self.graph = family_journey.three_person_graph()
        self.f.kinship.install(self.graph)

    def assert_clarifies(self, words, *, token=None):
        response = self.f.turn(words, token=token or self.f.auth['Authorization'].split()[-1])
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertIn(body['kind'], ('clarification', 'unsupported'), body)
        self.assertEqual(body['items'], [])
        self.assertIsNone(body['context'])

    def turn_version(self, words, version):
        return self.f.client.post('/assistant/v1/turns',
            json={'library_id': 'family-a', 'text': words, 'context': None},
            headers={'Authorization': self.f.auth['Authorization'],
                     'X-PhotoHouse-Search-Version': str(version)})

    def test_english_chinese_and_mixed_named_child_parent_queries_are_together(self):
        planner = UnexpectedIntentPlanner()
        self.f.client.app.state.assistant_intent_planner = planner
        cases = (
            'find photos of Sample Child with her dad',
            '找示例儿童和她爸爸一起的照片',
            'find示例儿童with her dad的photos',
        )
        for words in cases:
            for version in (2, 3):
                with self.subTest(words=words, version=version):
                    response = self.turn_version(words, version)
                    self.assertEqual(response.status_code, 200, response.text)
                    body = response.json()
                    self.assertEqual(body['kind'], 'results', body)
                    self.assertEqual(body['filters']['people'],
                                     {'ids': ['301', '303'], 'match': 'all'})
                    self.assertEqual([item['id'] for item in body['items']], ['104', '103'])
        self.assertEqual(planner.calls, [])

    def test_explicit_alias_can_anchor_but_selector_only_alias_cannot(self):
        self.graph['people'][0]['aliases'] = ['Kiddo']
        self.f.kinship.install(self.graph)
        response = self.f.turn('find photos of Kiddo with her dad')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['kind'], 'results', response.json())
        self.assertEqual(response.json()['filters']['people'],
                         {'ids': ['301', '303'], 'match': 'all'})

        self.assert_clarifies('find photos of Dad with his dad')

    def test_noncenter_anchor_missing_parent_does_not_fall_back_to_graph_center(self):
        # The center child has a father, but this named noncenter father has no
        # father edge in the three-person graph.
        self.assert_clarifies('find photos of Sample Father with his dad')
        self.assert_clarifies('find photos of Sample Father with his dad and mother')

    def test_two_named_anchors_stay_ambiguous_even_when_both_parent_paths_exist(self):
        graph = family_journey.three_person_graph()
        graph['people'].append({
            'id': 'grandfather', 'name_en': 'Sample Grandfather',
            'name_zh': '示例祖父', 'aliases': [], 'catalog_binding': None})
        graph['assertions'].append({
            'id': 'father-father', 'subject_id': 'father', 'relation': 'father',
            'object_id': 'grandfather', 'source': 'user'})
        targets, _, ambiguous = KinshipGraph(graph).mentions(
            'Sample Child with her dad and Sample Father with his dad')
        self.assertEqual(targets, {'child', 'father', 'grandfather'})
        self.assertTrue(ambiguous)

        self.f.kinship.install(graph)
        self.assert_clarifies(
            'find photos of Sample Child with her dad and Sample Father with his dad')

    def test_and_or_conflict_after_named_join_is_not_treated_as_all(self):
        self.assert_clarifies('find photos of Sample Child with her dad or her mom')

    def test_with_is_a_together_connector_and_unresolved_or_dangling_text_is_not_dropped(self):
        for words in ('我想找Sample Child with her dad after midnight',
                      '我想找示例儿童跟她爸爸在屋顶照片'):
            with self.subTest(words=words):
                self.assert_clarifies(words)
        self.assert_clarifies('find photos with')

    def test_plural_previous_result_reference_stays_a_refinement(self):
        initial = self.f.turn('找示例儿童、妈妈和爸爸一起的照片')
        self.assertEqual(initial.status_code, 200, initial.text)
        self.assertEqual(initial.json()['kind'], 'results', initial.json())
        refined = self.f.turn('find videos of them', context=initial.json()['context'])
        self.assertEqual(refined.status_code, 200, refined.text)
        self.assertEqual(refined.json()['kind'], 'results', refined.json())
        self.assertEqual(refined.json()['filters']['people'],
                         {'ids': ['301', '302', '303'], 'match': 'all'})
        self.assertEqual(refined.json()['filters']['media'], ['video'])

    def test_bare_pronoun_multiple_anchors_and_ambiguous_anchor_clarify(self):
        self.assert_clarifies('find photos of her dad')
        self.assert_clarifies('find photos of Unknown Child with her dad')
        self.assert_clarifies('find Sample Child with her dad and Sample Father with his dad')
        self.assert_clarifies('find Sample Child and Sample Child with her dad')

        self.graph['people'][2]['aliases'].append('Sample Child')
        self.f.kinship.install(self.graph)
        self.assert_clarifies('find photos of Sample Child with her dad')

    def test_unreviewed_parent_quoted_phrase_and_excluded_account_never_search_by_parent(self):
        self.graph['people'][2]['catalog_binding'] = {
            'person_id': '999', 'label': 'Unreviewed Fictional Parent'}
        self.f.kinship.install(self.graph)
        self.assert_clarifies('我想找Sample Child with her dad的照片')

        self.f.kinship.install(family_journey.three_person_graph())
        quoted = self.f.turn('找包含“示例儿童和她爸爸”的照片')
        self.assertEqual(quoted.status_code, 200, quoted.text)
        self.assertEqual(quoted.json()['kind'], 'results', quoted.json())
        self.assertNotIn('people', quoted.json()['filters'])

        self.assert_clarifies('find photos of Sample Child with her dad', token=SECOND)


if __name__ == '__main__':
    unittest.main()
