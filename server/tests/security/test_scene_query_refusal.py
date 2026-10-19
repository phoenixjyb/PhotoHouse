"""Generated full reviewed-provider chain and durable scene rewording receipts."""
from dataclasses import replace
import json
from pathlib import Path
import sys
import unittest
import uuid
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'backend'), str(ROOT/'scripts'), str(ROOT/'tests/security')]
import test_assistant_scene_search as scenes
import test_reviewed_semantic_provider_integration as integration
import test_semantic_provider_transport as transport
from app.access.assistant_journal import initialize as initialize_journal
from app.access.assistant_workspace_store import WorkspaceStoreUnavailable
from app.access.semantic_encoder import LocalSemanticEncoder
from app.access.semantic_provider_transport import create_provider_app


class SceneQueryRefusalTests(unittest.TestCase):
    def setUp(self):
        self.fixture = scenes.AssistantSceneSearchTests(
            'test_post_retry_and_get_recovery_keep_order_and_never_reencode')
        self.fixture.setUp(); self.addCleanup(self.fixture.doCleanups)
        self.inner = transport.FakeProvider()
        self.inner.binding = self.fixture.pilot.encoder.binding
        self.wrapper = integration.ReviewedProviderConversationAndDeadlineTests().wrapper(self.inner)
        provider = TestClient(create_provider_app(self.wrapper, bearer_token=transport.TOKEN, port=8912),
            base_url='http://127.0.0.1:8912', client=('127.0.0.1', 50000))
        self.addCleanup(provider.close)
        self.requests = []
        self.during_encode = None
        def bridge(request):
            self.requests.append(request)
            if self.during_encode: self.during_encode()
            response = provider.request(request.method, str(request.url),
                headers=dict(request.headers), content=request.content)
            return httpx.Response(response.status_code, headers=response.headers, content=response.content)
        encoder = LocalSemanticEncoder(self.wrapper.binding, 'http://127.0.0.1:8912/v1/encode-text',
            transport=httpx.MockTransport(bridge), bearer_token=transport.TOKEN)
        self.fixture.app.state.semantic_search_runtime = replace(self.fixture.pilot.runtime, encoder=encoder)
        self.base = self.fixture.scope('find photos of Sample Child in September 2032 containing "Family beach"')
        self.unknown = '孩子在桥边 maybe 玩什么来着'

    def refused(self, rid=None):
        return self.fixture.send(self.unknown, 1, scene=True, rid=rid)

    def test_application_exclusion_refusal_is_durable_without_provider_or_vector_reads(self):
        for query in ('a dog not on grass', '不在船上的狗', '没有人holding的phone'):
            with self.subTest(query=query):
                rid = str(uuid.uuid4())
                with patch('app.access.semantic_search._read_vector',
                           side_effect=AssertionError('vector read')):
                    response = self.fixture.send(query, 1, scene=True, rid=rid)
                    self.assertEqual(response.status_code, 200, response.text)
                    result = response.json()
                    self.assertEqual(result['status'], 'failed')
                    self.assertEqual(result['error'], 'scene_query_unsupported')
                    self.assertEqual(result['revision'], 1)
                    self.assertIsNone(result['result'])
                    self.assertNotIn(query, response.text)
                    recovered = self.fixture.read(rid)
                    replayed = self.fixture.send(query, 1, scene=True, rid=rid)
                    self.assertEqual(recovered.json(), {**result, 'recovered': True})
                    self.assertEqual(replayed.json(), recovered.json())
        self.assertEqual(self.requests, [])
        self.assertEqual(self.inner.calls, [])

    def test_stale_scope_precedes_application_exclusion_refusal(self):
        self.fixture.source.mutate(
            "UPDATE access_stories SET revision=2,text='changed' WHERE id='note-101'")
        response = self.fixture.send('a dog not on grass', 1, scene=True)
        self.assertEqual(response.status_code, 409, response.text)
        self.assertNotIn('scene_query_unsupported', response.text)
        self.assertEqual(self.requests, [])

    def test_failed_receipt_preserves_previous_scope_and_explicit_reword_succeeds(self):
        rid = str(uuid.uuid4())
        first = self.refused(rid)
        self.assertEqual(first.status_code, 200, first.text)
        value = first.json()
        self.assertEqual(value['status'], 'failed')
        self.assertEqual(value['error'], 'scene_query_unsupported')
        self.assertEqual(value['revision'], 1)
        self.assertFalse(value['recovered'])
        self.assertIsNone(value['result'])
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.requests[0].headers['x-photohouse-semantic-refusal'], '1')
        self.assertEqual(self.inner.calls, [])
        self.assertNotIn(self.unknown, first.text)
        self.assertNotIn(integration.MODEL_INPUT, first.text)
        self.assertEqual(first.headers['cache-control'], 'no-store')
        self.assertEqual(first.headers['x-photohouse-tracking'], 'disabled')
        self.assertNotIn('x-photohouse-request-id', first.headers)
        detail_response = self.fixture.client.get(f'{scenes.BASE}/threads/{self.fixture.thread}?library_id=family-a',
            headers=self.fixture.auth)
        self.assertEqual(detail_response.status_code, 200, detail_response.text)
        detail = detail_response.json()
        self.assertEqual(detail['thread']['revision'], 1)
        self.assertNotEqual(detail['latest_request_id'], rid)
        original = self.fixture.read(detail['latest_request_id'])
        self.assertEqual(original.status_code, 200, original.text)
        self.assertEqual(original.json()['result']['context'], self.base['context'])
        self.assertEqual(len(self.requests), 1)
        reworded = self.fixture.send(integration.ORIGINALS[0], 1, scene=True)
        self.assertEqual(reworded.status_code, 200, reworded.text)
        self.assertEqual(reworded.json()['revision'], 2)
        self.assertEqual(reworded.json()['result']['filters'], self.base['filters'])
        self.assertEqual(reworded.json()['result']['context']['scene']['query'], integration.ORIGINALS[0])
        self.assertEqual(self.inner.calls, [integration.MODEL_INPUT])

    def test_lost_reply_get_and_same_post_recover_failure_without_provider_replay(self):
        rid = str(uuid.uuid4())
        first = self.refused(rid)
        self.assertEqual(first.json()['status'], 'failed')
        for response in (self.fixture.read(rid), self.refused(rid)):
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json(), {**first.json(), 'recovered': True})
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.inner.calls, [])
        changed = self.fixture.send('different words', 1, scene=True, rid=rid)
        self.assertEqual(changed.status_code, 409)
        self.assertEqual(len(self.requests), 1)

    def test_legacy_negotiation_never_receives_new_failed_enum(self):
        rid = str(uuid.uuid4()); self.refused(rid)
        for version in ('1', '2', '3'):
            response = self.fixture.read(rid, self.fixture.auth | {'X-PhotoHouse-Search-Version': version})
            self.assertEqual(response.status_code, 400, response.text)
            self.assertEqual(response.json()['error'], 'search_version_unsupported')
            self.assertNotIn('scene_query_unsupported', response.text)
        self.assertEqual(len(self.requests), 1)

    def test_generic_encoder_failure_does_not_become_rewording_receipt(self):
        self.inner.failure = True
        rid = str(uuid.uuid4())
        response = self.fixture.send(integration.ORIGINALS[0], 1, scene=True, rid=rid)
        self.assertEqual(response.status_code, 503, response.text)
        recovery = self.fixture.read(rid)
        self.assertEqual(recovery.status_code, 200, recovery.text)
        self.assertEqual(recovery.json()['error'], 'assistant_unavailable')
        self.assertNotIn('scene_query_unsupported', response.text + recovery.text)

    def test_unconfirmed_store_failure_retains_pending_request_instead_of_claiming_refusal(self):
        rid = str(uuid.uuid4())
        with patch.object(self.fixture.store, 'fail_turn', side_effect=WorkspaceStoreUnavailable):
            response = self.refused(rid)
        self.assertEqual(response.status_code, 503, response.text)
        recovered = self.fixture.read(rid)
        self.assertEqual(recovered.status_code, 200, recovered.text)
        self.assertEqual(recovered.json()['status'], 'pending')
        self.assertIsNone(recovered.json()['error'])
        self.assertEqual(len(self.requests), 1)

    def test_membership_revocation_during_refusal_takes_precedence(self):
        self.during_encode = lambda: self.fixture.source.mutate(
            "UPDATE access_memberships SET status='revoked' WHERE account_id='one'")
        response = self.refused()
        self.assertEqual(response.status_code, 401, response.text)
        self.assertNotIn('scene_query_unsupported', response.text)
        self.assertNotIn('items', response.text)

    def test_source_change_during_refusal_takes_precedence(self):
        self.during_encode = lambda: self.fixture.source.mutate(
            "UPDATE access_stories SET revision=2,text='changed' WHERE id='note-101'")
        rid = str(uuid.uuid4()); response = self.refused(rid)
        self.assertEqual(response.status_code, 409, response.text)
        self.assertNotIn('scene_query_unsupported', response.text)
        recovery = self.fixture.read(rid)
        self.assertEqual(recovery.json()['error'], 'context_changed')

    def test_direct_semantic_api_reports_only_safe_rewording_code(self):
        response = self.fixture.client.post('/libraries/family-a/semantic-search/v1/query',
            headers=self.fixture.auth, json={'query': self.unknown, 'filters': self.base['filters']})
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(response.json(), {'error': 'scene_query_unsupported',
            'detail': 'Reword the scene description'})
        self.assertNotIn(self.unknown, response.text)
        self.assertEqual(self.inner.calls, [])

    def test_workspace_failure_does_not_claim_journal_finalization_when_unconfirmed(self):
        journal = initialize_journal(self.fixture.pilot.root/'refusal-journal.sqlite')
        journal.clock = lambda: scenes.NOW
        self.fixture.app.state.assistant_journal = journal
        self.fixture.app.state.assistant_journal_healthy = True
        original = journal.finish
        for fail in (False, True):
            with self.subTest(finish_fails=fail):
                rid = str(uuid.uuid4())
                with patch.object(journal, 'finish', side_effect=RuntimeError('private fault') if fail else original):
                    response = self.refused(rid)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()['error'], 'scene_query_unsupported')
                self.assertEqual(response.headers['x-photohouse-tracking'], 'enabled')
                self.assertEqual(response.headers['x-photohouse-request-id'], rid)
                self.assertEqual(response.headers['x-photohouse-receipt-status'], 'received' if fail else 'failed')
                self.assertEqual(journal.get(rid, 'one', 'family-a')['status'], 'received' if fail else 'failed')
                count = len(self.requests)
                recovery = self.fixture.read(rid)
                self.assertEqual(recovery.status_code, 200, recovery.text)
                self.assertEqual(recovery.json()['status'], 'failed')
                self.assertEqual(len(self.requests), count)
