"""An unbound semantic first page derives its binding in the ranking read."""
import hashlib
import json
from dataclasses import replace
from unittest import TestCase
from unittest.mock import patch

import httpx

import test_semantic_search as semantic
from app.access.semantic_encoder import LocalSemanticEncoder
from phone_discovery_fixture import TOKEN


class SemanticInitialSearchTests(TestCase):
    setUp = semantic.SemanticSearchTests.setUp
    query = semantic.SemanticSearchTests.query

    def test_unbound_first_page_uses_current_ranking_binding_and_one_fewer_read(self):
        provider = self.fixture.discovery_runtime.provider
        with patch.object(provider, 'get', wraps=provider.get) as get:
            first = self.query(page_size=1)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(get.call_count, 2)  # ranking source pass and final fresh pass

        current = first.json()
        with patch.object(provider, 'get', wraps=provider.get) as get:
            bound = self.query(page_size=1, binding=current['binding'])
        self.assertEqual(bound.status_code, 200, bound.text)
        self.assertEqual(get.call_count, 2)
        bound_body = bound.json()
        self.assertEqual(current['binding'], bound_body['binding'])
        self.assertEqual(current['fingerprint'], bound_body['fingerprint'])
        self.assertEqual(current['items'], bound_body['items'])

    def test_generic_discovery_search_still_requires_a_binding(self):
        from app.access.discovery import DiscoveryInvalid

        with patch.object(type(self.encoder), 'encode',
                          side_effect=AssertionError('generic discovery must not encode')):
            with self.assertRaises(DiscoveryInvalid):
                self.fixture.discovery_runtime.call(
                    'search', TOKEN, 'family-a', lambda: False,
                    {'binding': None, 'filters': {}})
        self.assertEqual(self.calls, [])

    def test_provider_unsupported_after_source_change_is_not_returned_as_stale_422(self):
        def reject_after_change(request):
            body = json.loads(request.content)
            self.fixture.mutate(
                "UPDATE access_stories SET revision=2,text='changed' WHERE id='note-101'")
            return httpx.Response(422, json={
                'version': 1,
                'error': 'unsupported_query',
                'binding_sha256': semantic.BINDING.binding_sha256,
                'query_sha256': hashlib.sha256(body['query'].encode()).hexdigest(),
            })

        self.encoder = LocalSemanticEncoder(semantic.BINDING,
            'http://127.0.0.1:43210/v1/encode-text',
            transport=httpx.MockTransport(reject_after_change))
        self.runtime = replace(self.runtime, encoder=self.encoder)
        self.client.app.state.semantic_search_runtime = self.runtime

        response = self.query()
        self.assertEqual(response.status_code, 409, response.text)
        self.assertNotIn('items', response.json())

    def test_heuristic_unsupported_refusal_still_compares_the_fresh_binding(self):
        def refuse_after_change(_query):
            self.fixture.mutate(
                "UPDATE access_stories SET revision=2,text='changed' WHERE id='note-101'")
            return True

        with patch('app.access.semantic_search.requires_semantic_clarification',
                   side_effect=refuse_after_change):
            response = self.query(query='a child flying a kite')
        self.assertEqual(response.status_code, 409, response.text)
        self.assertNotIn('items', response.json())
        self.assertEqual(self.calls, [])

    def test_unsupported_without_a_captured_binding_fails_closed_without_final_unbound_read(self):
        from app.access.semantic_search import SemanticSearchReads, SemanticUnsupported

        provider = self.fixture.discovery_runtime.provider

        def unobserved_action(*_args, **_kwargs):
            def refuse(_index, _facts, _context, _member, _check):
                raise SemanticUnsupported()
            return refuse

        with patch.object(SemanticSearchReads, '_search_action', side_effect=unobserved_action), \
                patch.object(provider, 'get', wraps=provider.get) as get:
            response = self.query()
        self.assertEqual(response.status_code, 503, response.text)
        self.assertNotIn('items', response.json())
        self.assertEqual(get.call_count, 1)
        self.assertEqual(self.calls, [])

    def test_fingerprint_pagination_and_server_snapshot_paths_keep_their_guards(self):
        provider = self.fixture.discovery_runtime.provider
        first = self.query(page_size=1).json()

        # A fingerprint without a supplied binding keeps the binding-read path.
        with patch.object(provider, 'get', wraps=provider.get) as get:
            fingerprint_only = self.query(page_size=1, fingerprint=first['fingerprint'])
        self.assertEqual(fingerprint_only.status_code, 200, fingerprint_only.text)
        self.assertEqual(get.call_count, 3)

        # Missing page-two fingerprint is still rejected before the encoder.
        before = len(self.calls)
        self.assertEqual(self.query(page=2, binding=first['binding']).status_code, 400)
        self.assertEqual(len(self.calls), before)

        complete = self.query().json()
        snapshot = tuple((item['id'], item['semantic_score']) for item in complete['items'])
        recovery_values = {'query': 'a child flying a kite', 'filters': {'media': ['image']},
                           'binding': complete['binding'], 'fingerprint': complete['fingerprint'],
                           'page_size': 20}
        calls_before = len(self.calls)
        with patch.object(type(self.encoder), 'encode', side_effect=AssertionError('model replay')):
            restored = self.runtime._restore_server_snapshot(
                TOKEN, 'family-a', lambda: False, recovery_values, snapshot)
        self.assertEqual(restored['binding'], complete['binding'])
        self.assertEqual([item['id'] for item in restored['items']],
                         [item['id'] for item in complete['items']])
        self.assertEqual(len(self.calls), calls_before)


if __name__ == '__main__':
    import unittest
    unittest.main()
