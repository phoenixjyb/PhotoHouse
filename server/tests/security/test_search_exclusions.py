"""Exclusion admission uses synthetic text and local generated media only."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

SERVER = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(SERVER / 'backend'), str(SERVER / 'tests/security')]

from app.access import discovery as d
from app.access.search_exclusions import (requires_exclusion_clarification,
    explicit_media_exclusion, exclusion_reply)
import test_assistant_query_plan as literal
import test_semantic_search as semantic
from phone_discovery_fixture import OTHER


NEGATIVE_QUERIES = (
    'A dog that is not on grass', '不在草地上的狗', '不在grass上的dog',
    'A dog that is not on a boat', '不在船上的狗', '不在boat上的dog',
    'A phone not being held by a person', '没有人拿着的手机', '没有人holding的phone',
)
POSITIVE_QUERIES = (
    'A dog on grass', '在草地上的狗', '在grass上的dog',
    'A dog on a boat', '在船上的狗', '在boat上的dog',
    'A phone being held by a person', '有人拿着的手机', '有人holding的phone',
)
PROHIBITION_QUERIES = (
    '花园照片里不得有其他人', '照片里不准出现狗', '照片里不許有狗',
    '照片里甭有狗', '照片里甭要狗', '除了狗的花园照片',
    '花园照片除狗之外', '花园照片除狗以外', '除去狗的花园照片',
    'a garden excepting dogs', 'garden photos, dogs excepted',
    'a garden free from dogs', 'garden photos omitting dogs',
    'garden photos, omit dogs', 'garden photos with dogs omitted',
    'a garden photo that omits dogs', '不许狗出现在照片里',
    'a garden photo with omission of dogs',
    '花园里不准有 dogs', 'garden free from 狗',
)


class ExclusionPolicyTests(unittest.TestCase):
    def test_bilingual_mixed_and_contracted_cues(self):
        for query in NEGATIVE_QUERIES + PROHIBITION_QUERIES + (
            'no dog', "a dog isn't on grass", 'dog-free beach', 'non-smoking room',
            'flowers rather than trees', 'without snow', 'except dogs',
            '不要狗', '不是草地', '不带狗', '无人草地', '没有snow的照片',
            'ＮＯ dog', 'a person who doesn’t hold a phone', 'not only dogs',
            'Photos lacking grass', 'lack of snow', 'an absence of grass',
            'grass is absent', 'cannot see a dog', '没看见红色汽车',
            '无红色汽车的照片', '無紅色汽車', '未曾穿红衣', '从未看见狗',
        ):
            with self.subTest(query=query):
                self.assertTrue(requires_exclusion_clarification(query))
        for query in POSITIVE_QUERIES + ('a notebook', 'Nottingham', '不错的照片',
                                         '不倒翁', '无锡的照片', '没落的建筑',
                                         '不得了的美景', 'a freeform sculpture',
                                         '室外的除尘工作'):
            with self.subTest(query=query):
                self.assertFalse(requires_exclusion_clarification(query))

    def test_explicit_positive_media_counterpart_only(self):
        for query, expected in (
            ('find photos, not videos', 'image'), ('找照片，不要视频', 'image'),
            ('find videos without photos', 'video'), ('找视频，排除photos', 'video'),
            ('find photos containing "cake", not videos', 'image'),
        ):
            with self.subTest(query=query):
                result = literal.plan(query)
                self.assertEqual(result.status, 'ready', result)
                self.assertEqual(result.filters['media'], [expected])
        for query in ('exclude videos', 'find photos not photos',
                      'find photos not video games', 'find photos without dogs',
                      'find photos, not videos without dogs'):
            with self.subTest(query=query):
                self.assertEqual(literal.plan(query).reason, 'unsupported_negation')
        query = 'find photos, not videos'
        entities = {**literal.ENTITIES, 'groups': {'people': ['301'], 'tags': [], 'locations': []},
                    'labels': ['not videos']}
        self.assertEqual(literal.plan(query, entities=entities).reason, 'ambiguous_media_entity')

    def test_literal_quotes_are_opaque_but_other_conditions_are_not(self):
        for query in NEGATIVE_QUERIES + PROHIBITION_QUERIES:
            with self.subTest(query=query):
                result = literal.plan('find photos containing "' + query + '"')
                self.assertEqual(result.status, 'ready', result)
                self.assertEqual(result.filters['text'], query)
                self.assertEqual(literal.plan('find photos ' + query).reason, 'unsupported_negation')
        self.assertIn('complete', exclusion_reply('en', expired=True))
        self.assertIn('完整', exclusion_reply('zh', continuation=True))


class SemanticExclusionAdmissionTests(unittest.TestCase):
    setUp = semantic.SemanticSearchTests.setUp
    query = semantic.SemanticSearchTests.query

    def test_negative_scene_cues_refuse_before_vectors_or_encoder(self):
        with patch('app.access.semantic_search._read_vector', side_effect=AssertionError('vector read')):
            for query in NEGATIVE_QUERIES + PROHIBITION_QUERIES + ('"not on a boat"', 'Photos lacking grass',
                    'an absence of grass', '没看见红色汽车', '无红色汽车的照片'):
                with self.subTest(query=query):
                    response = self.query(query=query)
                    self.assertEqual(response.status_code, 422, response.text)
                    self.assertEqual(response.json()['error'], 'scene_query_unsupported')
        self.assertEqual(self.calls, [])

    def test_nine_positive_controls_still_reach_encoder(self):
        for query in POSITIVE_QUERIES:
            with self.subTest(query=query):
                response = self.query(query=query)
                self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(self.calls), len(POSITIVE_QUERIES))

    def test_authorization_precedes_exclusion_and_snapshot_cannot_bypass_it(self):
        for query in (NEGATIVE_QUERIES[0], PROHIBITION_QUERIES[0]):
            with self.subTest(query=query):
                response = self.query(query=query, token=OTHER)
                self.assertEqual(response.status_code, 401, response.text)
                with self.assertRaises(d.DiscoveryQueryUnsupported):
                    self.runtime._restore_server_snapshot(semantic.TOKEN, 'family-a', lambda: False,
                        {'query': query, 'filters': {}}, ())
        self.assertEqual(self.calls, [])

    def test_policy_change_invalidates_bound_ranking_before_encoder(self):
        with patch('app.access.semantic_search.EXCLUSION_POLICY_VERSION', 2):
            previous = self.query(query=POSITIVE_QUERIES[0])
        self.assertEqual(previous.status_code, 200, previous.text)
        calls_before = len(self.calls)
        with patch('app.access.semantic_search.EXCLUSION_POLICY_VERSION', 3):
            changed = self.query(query=POSITIVE_QUERIES[0],
                                 binding=previous.json()['binding'])
        self.assertEqual(changed.status_code, 409, changed.text)
        self.assertEqual(len(self.calls), calls_before)


if __name__ == '__main__':
    unittest.main()
