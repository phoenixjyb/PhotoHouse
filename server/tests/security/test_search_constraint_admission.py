"""Hard scene conditions never become approximate or affirmative evidence."""
from pathlib import Path
import sys
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import Mock, patch

SERVER = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(SERVER / 'backend'), str(SERVER / 'tests/security')]

from app.access import discovery as d
from app.access.search_policy import (requires_exclusion_clarification,
                                         requires_semantic_clarification)
from app.access.search_description import match_description
from app.access.search_text import normalize_sources
import test_assistant_query_plan as literal
import test_semantic_search as semantic
import test_assistant_scene_search as scene


ABSENCE_PAIRS = (
    ('不下雪时的草地', '下雪时的草地'),
    ('未下雪时的公园', '下雪时的公园'),
    ('狗没落在草地上', '狗落在草地上'),
    ('狗沒落到grass上', '狗落到grass上'),
    ('a dog isnʼt on grass', 'a dog is on grass'),
    ('a dog isn‘t on grass', 'a dog is on grass'),
    ('a dog isn‛t on grass', 'a dog is on grass'),
    ('a beach with zero dogs', 'a beach with two dogs'),
    ('grass minus the dogs', 'grass with dogs'),
    ('an area devoid of dogs', 'an area with dogs'),
    ('别带狗的公园照片', '带狗的公园照片'),
    ('零只狗的公园', '两只狗的公园'),
    ('0 dogs on grass', '2 dogs on grass'),
    ('0只dog在草地上', '2只dog在草地上'),
)
STRICT_PAIRS = (
    ('exactly two dogs on grass', 'two dogs on grass'),
    ('only one person', 'one person'),
    ('at most three people', 'three people'),
    ('at least 2 dogs', '2 dogs'),
    ('exactly2人在grass上', '2人在grass上'),
    ('only两只dog', '两只dog'),
    ('只有两个孩子在草地上', '两个孩子在草地上'),
    ('最多两辆车', '两辆车'),
    ('恰好一只猫', '一只猫'),
    ('a child alone', 'a child flying a kite'),
    ('only dogs on grass', 'dogs on grass'),
    ('仅两个人', '两个人'),
    ('exactly eleven dogs', 'eleven dogs'),
    ('at most eleven people', 'eleven people'),
    ('a single dog on grass', 'one dog on grass'),
)


class ConstraintPolicyTests(unittest.TestCase):
    def test_negative_and_strict_conditions_have_positive_controls(self):
        for pairs, check in ((ABSENCE_PAIRS, requires_exclusion_clarification),
                             (STRICT_PAIRS, requires_semantic_clarification)):
            for negative, positive in pairs:
                with self.subTest(negative=negative):
                    self.assertTrue(check(negative))
                    self.assertFalse(check(positive))
        for lexical in ('没落的建筑', '不倒翁', '未来的城市', '无锡的照片',
                        '特别有趣的照片', 'notebook', 'someone', 'stone', 'just flying a kite'):
            self.assertFalse(requires_semantic_clarification(lexical), lexical)

    def test_original_quoted_caption_and_media_rules_remain_independent(self):
        for negative, _ in ABSENCE_PAIRS + STRICT_PAIRS:
            result = literal.plan('find photos containing "' + negative + '"')
            self.assertEqual(result.status, 'ready', result)
            self.assertEqual(result.filters['text'], negative)
        for negative, _ in ABSENCE_PAIRS:
            result = literal.plan('find photos ' + negative)
            self.assertEqual(result.reason, 'unsupported_negation', result)
        for negative, _ in STRICT_PAIRS:
            result = literal.plan('find photos ' + negative)
            self.assertEqual(result.reason, 'unsupported_negation', result)
        result = literal.plan('find photos, not videos')
        self.assertEqual(result.filters, {'media': ['image']})

    def test_negative_metadata_cannot_supply_positive_scene_evidence(self):
        for source in ('generated_caption', 'edited_caption', 'photo_memory'):
            for negative, positive in ABSENCE_PAIRS:
                phrase = ('grass' if 'grass' in negative else '草地' if '草地' in negative
                          else '公园' if '公园' in negative else 'dogs')
                if phrase not in positive:
                    continue
                plan = {'version': 1, 'concepts': [
                    {'surface': phrase, 'alternatives': [phrase]}]}
                for content, expected in ((negative, False), (positive, True)):
                    with self.subTest(source=source, content=content):
                        sources = normalize_sources([{'source': source, 'source_id': '1',
                            'revision': 1, 'content': content}], lambda: None)
                        result = match_description(sources, plan)
                        self.assertEqual(result[0], expected)
                        if not expected:
                            self.assertEqual(result[1], [])
        # A separate affirmative clause still supplies its own evidence.
        sources = normalize_sources([{'source': 'edited_caption', 'source_id': '1',
            'revision': 1, 'content': 'No dogs on grass. A kite is flying.'}], lambda: None)
        self.assertTrue(match_description(sources, {'version': 1, 'concepts': [
            {'surface': 'kite', 'alternatives': ['kite']}]})[0])


class SemanticConstraintTests(unittest.TestCase):
    setUp = semantic.SemanticSearchTests.setUp
    query = semantic.SemanticSearchTests.query

    def test_constraints_refuse_before_file_reads_or_encoder_even_with_no_candidates(self):
        with patch('app.access.semantic_search._read_vector', side_effect=AssertionError('vector read')):
            for negative, _ in ABSENCE_PAIRS + STRICT_PAIRS:
                for filters in ({}, {'date': {'from': '1900-01-01', 'to': '1900-01-01'}}):
                    response = self.query(query=negative, filters=filters)
                    self.assertEqual(response.status_code, 422, response.text)
                    self.assertEqual(response.json()['error'], 'scene_query_unsupported')
        self.assertEqual(self.calls, [])

    def test_positive_controls_preserve_exact_encoder_input_and_hard_filters(self):
        filters = {'people': {'ids': ['301'], 'match': 'all'},
                   'date': {'from': '2032-09-01', 'to': '2032-09-30'}}
        for _, positive in ABSENCE_PAIRS + STRICT_PAIRS:
            response = self.query(query=positive, filters=filters)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()['filters'], {**filters, 'media': ['image']})
            self.assertEqual(self.calls[-1]['query'], positive)

    def test_previous_admission_policy_invalidates_stored_ranking(self):
        with patch('app.access.semantic_search.EXCLUSION_POLICY_VERSION', 1):
            old = self.query(query='a child flying a kite').json()
        count = len(self.calls)
        snapshot = tuple((item['id'], item['semantic_score']) for item in old['items'])
        with self.assertRaises(d.DiscoveryChanged):
            self.runtime._restore_server_snapshot(semantic.TOKEN, 'family-a', lambda: False,
                {'query': 'a child flying a kite', 'filters': {}, 'binding': old['binding']}, snapshot)
        self.assertEqual(len(self.calls), count)


class WorkspaceConstraintTests(unittest.TestCase):
    setUp = scene.AssistantSceneSearchTests.setUp
    send = scene.AssistantSceneSearchTests.send
    scope = scene.AssistantSceneSearchTests.scope
    read = scene.AssistantSceneSearchTests.read

    def test_v3_exact_count_creates_private_pending_without_intent_inference(self):
        planner = SimpleNamespace(propose=Mock(side_effect=AssertionError('intent inference')))
        self.app.state.assistant_intent_planner = planner
        headers = self.auth | {'X-PhotoHouse-Search-Version': '3'}
        original = 'find photos with exactly eleven dogs'
        response = self.send(original, headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()['result']
        self.assertEqual(result['kind'], 'clarification')
        self.assertIn('exact counts', result['reply'])
        self.assertIsNone(result['context'])
        self.assertNotIn('pending_intent', response.text)
        state = self.store.get_turn('one', 'family-a', self.thread,
            response.json()['request_id'])['result_summary']['pending_intent']
        self.assertEqual(state['query'], original)
        continued = self.send('red coats', 1, headers=headers)
        self.assertEqual(continued.status_code, 200, continued.text)
        self.assertEqual(continued.json()['result']['kind'], 'clarification')
        carried = self.store.get_turn('one', 'family-a', self.thread,
            continued.json()['request_id'])['result_summary']['pending_intent']
        self.assertEqual(carried, state)
        planner.propose.assert_not_called()

    def test_strict_condition_failed_receipts_recover_without_changing_scope(self):
        base = self.scope()
        for query in ('exactly two dogs on grass', '只有两个孩子', '没落在grass上的狗'):
            rid = str(uuid.uuid4())
            first = self.send(query, 1, scene=True, rid=rid)
            self.assertEqual(first.status_code, 200, first.text)
            receipt = first.json()
            self.assertEqual(receipt['status'], 'failed')
            self.assertEqual(receipt['error'], 'scene_query_unsupported')
            self.assertEqual(receipt['revision'], 1)
            self.assertIsNone(receipt['result'])
            self.assertEqual(self.read(rid).json(), {**receipt, 'recovered': True})
            self.assertEqual(self.send(query, 1, scene=True, rid=rid).json(),
                             {**receipt, 'recovered': True})
        detail = self.client.get(f'{scene.BASE}/threads/{self.thread}?library_id=family-a',
                                 headers=self.auth).json()
        restored = self.read(detail['latest_request_id']).json()['result']
        self.assertEqual(restored['context'], base['context'])
        self.assertEqual(restored['filters'], base['filters'])
        self.assertEqual(self.pilot.calls, [])


if __name__ == '__main__':
    unittest.main()
