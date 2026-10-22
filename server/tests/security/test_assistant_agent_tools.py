"""Protected tool facade checks against generated PhotoHouse domain data."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'tests' / 'security')]

from app.access import assistant_workspace_transport as workspace_transport
from app.access import discovery as d
from app.access.assistant import AssistantChanged
from app.access.assistant_search import SearchRuntime
from app.access.assistant_agent_tools import AgentToolError, AgentTools
from app.access.assistant_workspace_store import _card_refs, _result_summary
import test_assistant_joint_search as fixture_module
from phone_discovery_fixture import TOKEN, NOW


class AssistantAgentToolTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_module.AssistantJointSearchTests(
            'test_text_union_dedup_reasons_and_authored_first_order')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.checks = []
        self.tools = AgentTools(
            engine=SearchRuntime(self.fixture.discovery_runtime), token=TOKEN,
            library='family-a', words='find photos in 2032', context=None,
            pending_intent=None, clock=lambda: 2032 * 365 * 24 * 60 * 60,
            language='en', check=lambda: self.checks.append('checked'))

    def test_real_capabilities_and_canonical_search_are_bounded_and_repeat_stably(self):
        capability = self.tools.dispatch('get_search_capabilities', {})
        self.assertEqual(capability['search_version'], 2)
        self.assertIn('date', capability['enabled'])
        self.assertNotIn('binding', capability)

        with patch.object(workspace_transport, '_workspace_search_turn',
                           wraps=workspace_transport._workspace_search_turn) as turn:
            first = self.tools.dispatch('search_media', {})
            second = self.tools.dispatch('search_media', {})
        self.assertEqual(turn.call_count, 1)
        self.assertEqual(first['outcome_handle'], second['outcome_handle'])
        self.assertLessEqual(len(json.dumps(first, ensure_ascii=False).encode()), 16 * 1024)
        self.assertTrue(first['items'])
        self.assertEqual(first['items'][0]['position'], 1)
        self.assertNotIn('id', first['items'][0])
        self.assertNotIn('binding', first)
        self.assertGreater(len(self.checks), 3)

        selected = self.tools.resolve({'outcome_handle': first['outcome_handle']})
        self.assertEqual(len(selected.cards()), first['total'])
        self.assertTrue(selected.summary()['context'])
        summary = selected.summary()
        self.assertEqual(set(summary), {'version', 'kind', 'reply', 'context', 'filters',
                                        'total', 'has_more', 'effect'})
        self.assertEqual(_result_summary(summary, 'family-a'), summary)
        references = _card_refs(selected.cards())
        self.assertEqual(references[0], {
            'type': 'media', 'id': '103',
            'revision': summary['context']['binding'],
            'fingerprint': summary['context']['fingerprint']})
        self.assertEqual(selected.items()[0]['id'], '103')
        # Detached reads cannot mutate the facade's private authoritative copy.
        selected.items()[0]['id'] = 'tampered'
        self.assertEqual(self.tools.resolve({'outcome_handle': first['outcome_handle']})
                         .items()[0]['id'], '103')

    def test_selector_is_exact_run_scoped_and_revalidates_source_binding(self):
        projection = self.tools.dispatch('search_media', {})
        handle = projection['outcome_handle']
        for bad in ({}, {'outcome_handle': handle, 'asset_id': '103'},
                    {'outcome_handle': 3}):
            with self.subTest(selector=bad), self.assertRaises(AgentToolError):
                self.tools.resolve(bad)

        other_run = AgentTools(
            engine=SearchRuntime(self.fixture.discovery_runtime), token=TOKEN,
            library='family-a', words='find photos in 2032', context=None,
            pending_intent=None, clock=lambda: 2032 * 365 * 24 * 60 * 60,
            language='en', check=lambda: None)
        other_run.dispatch('search_media', {})
        with self.assertRaises(AgentToolError):
            other_run.resolve({'outcome_handle': handle})

        self.fixture.mutate("UPDATE assets SET taken_at='2032-09-03' WHERE id=103")
        with self.assertRaises((AssistantChanged, d.DiscoveryChanged)):
            self.tools.resolve({'outcome_handle': handle})

    def test_contextless_date_pending_keeps_its_binding_through_resolution(self):
        tools = AgentTools(
            engine=SearchRuntime(self.fixture.discovery_runtime), token=TOKEN,
            library='family-a', words='find photos from childhood', context=None,
            pending_intent=None, clock=lambda: NOW, language='en', check=lambda: None)
        projection = tools.dispatch('search_media', {})
        outcome = tools.resolve({'outcome_handle': projection['outcome_handle']})
        self.assertEqual(outcome.summary()['kind'], 'clarification')
        self.assertIsNone(outcome.summary()['context'])
        pending = outcome.summary()['pending_intent']
        self.assertEqual(pending['question'], 'date')
        # The binding is read-protected even when no result context exists.
        self.fixture.mutate("UPDATE assets SET taken_at='2025-03-01' WHERE id=103")
        with self.assertRaises((AssistantChanged, d.DiscoveryChanged)):
            tools.resolve({'outcome_handle': projection['outcome_handle']})

    def test_new_date_pending_that_expires_during_run_is_refused(self):
        clock_values = iter((NOW, NOW, NOW + 16 * 60))
        tools = AgentTools(
            engine=SearchRuntime(self.fixture.discovery_runtime), token=TOKEN,
            library='family-a', words='find photos from childhood', context=None,
            pending_intent=None, clock=lambda: next(clock_values), language='en',
            check=lambda: None)
        with self.assertRaises(AssistantChanged):
            tools.dispatch('search_media', {})

    def test_expired_incoming_date_question_returns_host_expiry_clarification(self):
        from app.access.assistant_workspace_transport import _workspace_search_turn

        _initial, pending = _workspace_search_turn(
            SearchRuntime(self.fixture.discovery_runtime), TOKEN, 'family-a',
            'find photos from childhood', None, lambda: NOW, language='en')
        self.assertEqual(pending['question'], 'date')
        expired_now = pending['created_at'] + 16 * 60
        tools = AgentTools(
            engine=SearchRuntime(self.fixture.discovery_runtime), token=TOKEN,
            library='family-a', words='about two years ago', context=None,
            pending_intent=pending, clock=lambda: expired_now, language='en',
            check=lambda: None)
        projection = tools.dispatch('search_media', {})
        outcome = tools.resolve({'outcome_handle': projection['outcome_handle']})
        self.assertEqual(outcome.summary()['kind'], 'clarification')
        self.assertNotIn('pending_intent', outcome.summary())
        self.assertIn('expired', outcome.summary()['reply'])

    def test_ordinal_open_becomes_read_only_result_with_store_references(self):
        from app.access.assistant_workspace_transport import _workspace_search_turn

        engine = SearchRuntime(self.fixture.discovery_runtime)
        prior, _pending = _workspace_search_turn(
            engine, TOKEN, 'family-a', 'find photos in 2032', None,
            lambda: NOW, language='en')
        self.assertGreater(prior['total'], 0)
        tools = AgentTools(
            engine=engine, token=TOKEN, library='family-a',
            words='open first result', context=prior['context'], pending_intent=None,
            clock=lambda: NOW, language='en', check=lambda: None)
        projection = tools.dispatch('search_media', {})
        outcome = tools.resolve({'outcome_handle': projection['outcome_handle']})
        self.assertEqual(projection['kind'], 'results')
        self.assertEqual(outcome.summary()['kind'], 'results')
        self.assertIsNone(outcome.summary()['effect'])
        self.assertEqual(outcome.summary()['reply'], 'Select a result to open it.')
        self.assertEqual(outcome.items()[0]['id'], prior['items'][0]['id'])
        self.assertEqual(outcome.cards()[0]['id'], prior['items'][0]['id'])
        self.assertEqual(_result_summary(outcome.summary(), 'family-a'), outcome.summary())

    def test_dispatch_rejects_unreviewed_names_and_nonempty_search_arguments(self):
        with self.assertRaises(AgentToolError):
            self.tools.dispatch('search_media', {'query': 'find everything'})
        with self.assertRaises(AgentToolError):
            self.tools.dispatch('open_asset', {'asset_id': '103'})
        with self.assertRaises(AgentToolError):
            self.tools.dispatch('inspect_current_results', {})


if __name__ == '__main__':
    unittest.main()
