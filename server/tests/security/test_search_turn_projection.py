"""Turn-scoped reuse must preserve fresh authorization and source checks."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'tests/security')]

import test_assistant_joint_search as fixtures
from app.access import discovery as d
from app.access.assistant_search import AssistantSearchReads, SearchRuntime, _TURN_FACTS
from app.access.service import AccessDenied
from phone_discovery_fixture import TOKEN


class SearchTurnProjectionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.AssistantJointSearchTests(
            'test_text_union_dedup_reasons_and_authored_first_order')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_http_turn_builds_facts_once_and_next_turn_rebuilds(self):
        calls = []
        original = AssistantSearchReads._facts

        def counted(reader, *args):
            calls.append(1)
            return original(reader, *args)

        with patch.object(AssistantSearchReads, '_facts', counted):
            first = self.fixture.turn('找包含“海边”的照片')
            self.assertEqual(first.status_code, 200, first.text)
            self.assertEqual(first.json()['kind'], 'results')
            self.assertEqual(len(calls), 1)
            # Entity resolution and result reads still both read fresh source.
            self.assertGreaterEqual(sum('FROM access_stories' in sql
                                        for sql in self.fixture.trace), 2)
            second = self.fixture.turn('只看2032年9月', context=first.json()['context'])
            self.assertEqual(second.status_code, 200, second.text)
            self.assertEqual(second.json()['filters']['text'], '海边')
            self.assertEqual(len(calls), 2)
        self.assertIsNone(_TURN_FACTS.get())
        for internal in ('_asset_id', '_normalized_sources', 'normalized_text', 'quality'):
            self.assertNotIn(internal, second.text)

    def test_edited_note_invalidates_binding_even_with_cached_facts(self):
        engine = SearchRuntime(self.fixture.discovery_runtime)
        with engine.turn_scope():
            first = engine.call('entities', TOKEN, 'family-a', lambda: False, {'words': 'photos'})
            self.fixture.mutate("UPDATE access_stories SET text='new synthetic content', revision=2 WHERE id='note-101'")
            with self.assertRaises(d.DiscoveryChanged):
                engine.call('search', TOKEN, 'family-a', lambda: False,
                            {'binding': first['binding'], 'filters': {'text': '海边'}})
            current = engine.call('entities', TOKEN, 'family-a', lambda: False, {'words': 'photos'})
            self.assertNotEqual(current['binding'], first['binding'])
            result = engine.call('search', TOKEN, 'family-a', lambda: False,
                                 {'binding': current['binding'], 'filters': {'text': 'new synthetic content'}})
            self.assertEqual([item['id'] for item in result['items']], ['101'])
        self.assertIsNone(_TURN_FACTS.get())

    def test_revocation_and_cancellation_still_apply_and_scope_clears_on_error(self):
        engine = SearchRuntime(self.fixture.discovery_runtime)
        with self.assertRaises(AccessDenied):
            with engine.turn_scope():
                engine.call('entities', TOKEN, 'family-a', lambda: False, {'words': 'photos'})
                self.fixture.mutate("UPDATE access_memberships SET status='revoked' WHERE account_id='one'")
                with patch.object(engine.runtime.provider, 'get', side_effect=AssertionError('index before authorization')):
                    engine.call('entities', TOKEN, 'family-a', lambda: False, {'words': 'photos'})
        self.assertIsNone(_TURN_FACTS.get())
        self.fixture.mutate("UPDATE access_memberships SET status='approved' WHERE account_id='one'")
        with engine.turn_scope():
            engine.call('entities', TOKEN, 'family-a', lambda: False, {'words': 'photos'})
            with self.assertRaises(d.DiscoveryCancelled):
                engine.call('entities', TOKEN, 'family-a', lambda: True, {'words': 'photos'})

    def test_new_bilingual_queries_and_refinements_reach_http_search(self):
        first = self.fixture.turn('Could you show me photographs taken in September 2032 containing "海边"')
        self.assertEqual(first.status_code, 200, first.text)
        body = first.json()
        self.assertEqual(body['kind'], 'results', body)
        self.assertEqual(body['filters'], {'media': ['image'], 'text': '海边',
                         'date': {'from': '2032-09-01', 'to': '2032-09-30'}})
        next_turn = self.fixture.turn('昨天的照片呢', context=body['context']).json()
        self.assertEqual(next_turn['kind'], 'results', next_turn)
        self.assertEqual(next_turn['filters']['text'], '海边')
        self.assertEqual(next_turn['filters']['media'], ['image'])
        self.assertEqual(next_turn['filters']['date']['from'], next_turn['filters']['date']['to'])
        legacy = self.fixture.turn('find photos', v2=False).json()
        fresh = self.fixture.turn('Could you show photographs', context=legacy['context'])
        self.assertEqual(fresh.status_code, 200, fresh.text)
        self.assertEqual(fresh.json()['kind'], 'results')


if __name__ == '__main__':
    unittest.main()
