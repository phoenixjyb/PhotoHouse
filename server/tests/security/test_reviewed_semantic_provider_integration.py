"""Generated API integration for an exact reviewed semantic projection.

The model, filesystem artifacts, API, provider protocol, filtering and vector
ranking are exercised through existing generated fixtures. No installed ML,
network sockets, or real model artifacts are used.
"""
from contextlib import closing
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import time
import uuid
import unittest
from types import SimpleNamespace

import httpx
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts"),
               str(ROOT / "tests/security")]

import test_assistant_joint_search as joint_fixtures
import test_semantic_openclip as model_fixtures
import test_visual_vector_loader as vector_fixtures
import test_semantic_provider_transport as transport_fixtures
import test_assistant_scene_search as scene_fixtures
from app.access.semantic_encoder import JointSpaceBinding, LocalSemanticEncoder
from app.access.semantic_provider_transport import create_provider_app
from app.access.semantic_search import SemanticSearchRuntime
from app.access.visual_candidates import VectorSpaceIdentity
from app.access.visual_vector_schema import create_visual_vector_schema
from app.main import create_app
from semantic_reviewed_projection import (
    ReviewedProjection,
    ReviewedSemanticProvider,
    composition_recipe,
    reviewed_document_sha256,
)


ADAPTER_SHA256 = "f" * 64
REVIEW_REFERENCE_SHA256 = "a" * 64
MODEL_INPUT = "a child flying a kite"
ORIGINALS = (
    "孩子在放风筝",
    "find 放风筝的孩子 photos",
)


def _projection():
    document = {
        "schema": "photohouse.reviewed_scene_projection.v1",
        "policy": "exact_reviewed_only",
        "review": {"status": "operator_reviewed",
                   "reference_sha256": REVIEW_REFERENCE_SHA256},
        "entries": [
            {"original": original, "model_input": MODEL_INPUT}
            for original in (*ORIGINALS, MODEL_INPUT)
        ],
    }
    return ReviewedProjection(document,
                              expected_sha256=reviewed_document_sha256(document))


class ReviewedSemanticProviderIntegrationTests(unittest.TestCase):
    def setUp(self):
        model_fixture = model_fixtures.SemanticOpenClipTests(
            "test_explicit_local_load_and_normalized_text_vector")
        model_fixture.setUp()
        self.addCleanup(model_fixture.doCleanups)
        self.model = model_fixture.load()

        inner_text = VectorSpaceIdentity(
            self.model._checkpoint_sha256, self.model._recipe_sha256,
            "synthetic-joint", "text-v1", 512, "unit_l2")
        image_identity = replace(inner_text, preprocessing_sha256="b" * 64,
                                 model_version="image-v1")
        self.inner_binding = JointSpaceBinding(image_identity, inner_text, "c" * 64)
        self.model.bind(self.inner_binding)
        self.projection = _projection()
        recipe = composition_recipe(self.inner_binding, self.projection, ADAPTER_SHA256)
        outer_text = replace(inner_text, preprocessing_sha256=recipe["recipe_sha256"])
        self.outer_binding = JointSpaceBinding(image_identity, outer_text, "d" * 64)
        self.reviewed = ReviewedSemanticProvider(
            self.model, self.projection, self.outer_binding,
            adapter_source_sha256=ADAPTER_SHA256)

        self.secret = "synthetic_provider_credential_" + "t" * 32
        provider_app = create_provider_app(self.reviewed, bearer_token=self.secret, port=8912)
        self.provider = TestClient(provider_app, base_url="http://127.0.0.1:8912",
                                   client=("127.0.0.1", 50000))
        self.addCleanup(self.provider.close)
        self.provider_requests = []
        self.provider_responses = []

        def bridge(request):
            self.provider_requests.append(request)
            response = self.provider.request(
                request.method, str(request.url), headers=dict(request.headers),
                content=request.content)
            self.provider_responses.append(response)
            return httpx.Response(response.status_code, headers=response.headers,
                                  content=response.content)

        self.encoder = LocalSemanticEncoder(
            self.outer_binding, "http://127.0.0.1:8912/v1/encode-text",
            transport=httpx.MockTransport(bridge), bearer_token=self.secret)

        fixture = joint_fixtures.AssistantJointSearchTests(
            "test_text_union_dedup_reasons_and_authored_first_order")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        directory = tempfile.TemporaryDirectory(prefix="reviewed-semantic-chain-")
        self.addCleanup(directory.cleanup)
        vector_root = Path(directory.name).resolve()
        with closing(sqlite3.connect(fixture.database)) as db, db:
            db.execute("ALTER TABLE assets ADD COLUMN hash_sha256 TEXT")
            create_visual_vector_schema(db)
            holder = SimpleNamespace(db=db, root=vector_root)
            for aid, vector in ((101, [0.0, 1.0] + [0.0] * 510),
                                (103, [1.0] + [0.0] * 511)):
                source_hash = hashlib.sha256(str(aid).encode()).hexdigest()
                db.execute("UPDATE assets SET hash_sha256=? WHERE id=?", (source_hash, aid))
                vector_fixtures.VisualVectorLoaderTests.add_vector(
                    holder, aid, vector, source_hash=source_hash,
                    identity=self.outer_binding.image_identity)
        runtime = SemanticSearchRuntime(fixture.discovery_runtime, vector_root, self.encoder)
        app = create_app(access_runtime=fixture.access,
                         discovery_runtime=fixture.discovery_runtime,
                         semantic_search_runtime=runtime)
        self.client = TestClient(app, base_url=joint_fixtures.ORIGIN)
        self.addCleanup(self.client.close)

        self.model_inputs = []
        tokenizer_encode = self.model._tokenizer.encode

        def observe_model_input(query):
            self.model_inputs.append(query)
            return tokenizer_encode(query)

        self.model._tokenizer.encode = observe_model_input

    def _query(self, query, *, filters=None, headers=None, library="family-a"):
        return self.client.post(
            f"/libraries/{library}/semantic-search/v1/query",
            headers=self.fixture.auth if headers is None else headers,
            json={"query": query, "filters": {} if filters is None else filters})

    def test_original_query_provenance_composes_with_reviewed_model_input_and_filters(self):
        results = []
        for original in ORIGINALS:
            response = self._query(original)
            self.assertEqual(response.status_code, 200, response.text)
            results.append(response)

        self.assertEqual(self.model_inputs, [MODEL_INPUT, MODEL_INPUT])
        self.assertEqual(len(self.provider_requests), 2)
        self.assertEqual(len(self.provider_responses), 2)
        parsed_requests = [json.loads(request.content) for request in self.provider_requests]
        parsed_responses = [response.json() for response in self.provider_responses]
        for original, request, response in zip(ORIGINALS, parsed_requests, parsed_responses):
            self.assertEqual(request["query"].encode("utf-8"), original.encode("utf-8"))
            self.assertEqual(request["binding_sha256"], self.outer_binding.binding_sha256)
            self.assertEqual(response["binding_sha256"], self.outer_binding.binding_sha256)
            self.assertEqual(response["query_sha256"], hashlib.sha256(
                original.encode("utf-8")).hexdigest())
            self.assertEqual(len(response["vector"]), 512)
        self.assertNotEqual(parsed_responses[0]["query_sha256"],
                            parsed_responses[1]["query_sha256"])
        self.assertEqual(parsed_responses[0]["vector"], parsed_responses[1]["vector"])
        self.assertEqual(parsed_responses[0]["checksum_sha256"],
                         parsed_responses[1]["checksum_sha256"])

        restricted = self._query(
            ORIGINALS[0], filters={"people": {"ids": ["301", "302"], "match": "all"}})
        self.assertEqual(restricted.status_code, 200, restricted.text)
        self.assertEqual([item["id"] for item in restricted.json()["items"]], ["103"])
        self.assertEqual(self.model_inputs, [MODEL_INPUT] * 3)
        self.assertEqual(self.model._tokenizer.cache, {"special": "baseline"})
        self.assertNotIn("vector", results[0].json()["items"][0])
        self.assertTrue(results[0].json()["semantic"]["needs_review"])
        for response in (*results, restricted):
            self.assertNotIn(MODEL_INPUT, response.text)
            self.assertNotIn(self.secret, response.text)
            for original in ORIGINALS:
                self.assertNotIn(original, response.text)

    def test_unreviewed_foreign_and_unauthenticated_requests_fail_before_model_use(self):
        unknown = "unreviewed private query"
        denied = self._query(unknown)
        self.assertEqual(denied.status_code, 422, denied.text)
        self.assertEqual(denied.json()['error'], 'scene_query_unsupported')
        self.assertEqual(self.model_inputs, [])
        self.assertNotIn(unknown, denied.text)
        self.assertNotIn(MODEL_INPUT, denied.text)
        self.assertNotIn(self.secret, denied.text)
        # An authorized query may reach the authenticated outer provider, but
        # the reviewed projection must refuse it before the inner model call.
        self.assertEqual(len(self.provider_requests), 1)
        self.assertEqual(json.loads(self.provider_requests[0].content)["query"], unknown)

        invalid_headers = {"Authorization": "Bearer " + "x" * 40}
        unauthenticated = self._query(ORIGINALS[0], headers=invalid_headers)
        self.assertIn(unauthenticated.status_code, (401, 403))
        foreign = self._query(ORIGINALS[0], library="family-b")
        self.assertIn(foreign.status_code, (401, 403, 404))
        self.assertEqual(self.model_inputs, [])
        self.assertEqual(len(self.provider_requests), 1)
        for response in (unauthenticated, foreign):
            self.assertNotIn(ORIGINALS[0], response.text)
            self.assertNotIn(MODEL_INPUT, response.text)
            self.assertNotIn(self.secret, response.text)
        self.assertEqual(self.model._tokenizer.cache, {"special": "baseline"})

    def test_old_direct_binding_is_rejected_before_any_model_call(self):
        with self.assertRaisesRegex(ValueError, "invalid_reviewed_semantic_provider"):
            ReviewedSemanticProvider(
                self.model, self.projection, self.inner_binding,
                adapter_source_sha256=ADAPTER_SHA256)
        self.assertEqual(self.model_inputs, [])
        self.assertEqual(self.provider_requests, [])


class ReviewedProviderConversationAndDeadlineTests(unittest.TestCase):
    def wrapper(self, inner, original=ORIGINALS[0]):
        document = {"schema": "photohouse.reviewed_scene_projection.v1",
            "policy": "exact_reviewed_only",
            "review": {"status": "operator_reviewed", "reference_sha256": "a"*64},
            "entries": [{"original": original, "model_input": MODEL_INPUT}]}
        projection = ReviewedProjection(document, expected_sha256=reviewed_document_sha256(document))
        recipe = composition_recipe(inner.binding, projection, ADAPTER_SHA256)
        binding = JointSpaceBinding(inner.binding.image_identity,
            replace(inner.binding.text_identity, preprocessing_sha256=recipe["recipe_sha256"]), "6"*64)
        return ReviewedSemanticProvider(inner, projection, binding,
            adapter_source_sha256=ADAPTER_SHA256)

    def test_v4_conversation_keeps_original_and_hard_scope_and_never_reencodes_replay(self):
        fixture = scene_fixtures.AssistantSceneSearchTests(
            'test_post_retry_and_get_recovery_keep_order_and_never_reencode')
        fixture.setUp(); self.addCleanup(fixture.doCleanups)
        inner = transport_fixtures.FakeProvider(); inner.binding = fixture.pilot.encoder.binding
        wrapper = self.wrapper(inner)
        provider = TestClient(create_provider_app(wrapper, bearer_token=transport_fixtures.TOKEN,
            port=8912), base_url='http://127.0.0.1:8912', client=('127.0.0.1', 50000))
        self.addCleanup(provider.close)
        def bridge(request):
            reply = provider.request(request.method, str(request.url),
                headers=dict(request.headers), content=request.content)
            return httpx.Response(reply.status_code, headers=reply.headers, content=reply.content)
        encoder = LocalSemanticEncoder(wrapper.binding,
            'http://127.0.0.1:8912/v1/encode-text', transport=httpx.MockTransport(bridge),
            bearer_token=transport_fixtures.TOKEN)
        fixture.app.state.semantic_search_runtime = replace(fixture.pilot.runtime, encoder=encoder)
        base = fixture.scope('find photos of Sample Child in September 2032 containing "Family beach"')
        rid = str(uuid.uuid4())
        first = fixture.send(ORIGINALS[0], 1, scene=True, rid=rid)
        self.assertEqual(first.status_code, 200, first.text)
        result = first.json()['result']
        self.assertEqual(result['context']['scene']['query'], ORIGINALS[0])
        self.assertEqual(result['filters'], base['filters'])
        self.assertEqual([x['id'] for x in result['items']], ['101'])
        self.assertEqual(inner.calls, [MODEL_INPUT])
        for reply in (fixture.read(rid), fixture.send(ORIGINALS[0], 1, scene=True, rid=rid)):
            self.assertEqual(reply.status_code, 200, reply.text)
            self.assertTrue(reply.json()['recovered'])
            self.assertEqual(reply.json()['result'], result)
        self.assertEqual(inner.calls, [MODEL_INPUT])

    def test_timeout_keeps_both_leases_until_worker_drains_then_recovers(self):
        release = threading.Event()
        inner = transport_fixtures.FakeProvider(delay=release)
        wrapper = self.wrapper(inner)
        app = create_provider_app(wrapper, bearer_token=transport_fixtures.TOKEN,
                                  port=8912, seconds=0.1)
        body = {'version': 1, 'binding_sha256': wrapper.binding.binding_sha256,
                'query': ORIGINALS[0]}
        headers = {'authorization': 'Bearer '+transport_fixtures.TOKEN}
        try:
            with TestClient(app, base_url='http://127.0.0.1:8912',
                            client=('127.0.0.1', 50000)) as client:
                first = client.post('/v1/encode-text', json=body, headers=headers)
                self.assertEqual(first.status_code, 504)
                self.assertFalse(inner.finished.is_set())
                busy = client.post('/v1/encode-text', json=body, headers=headers)
                self.assertEqual(busy.status_code, 429)
                self.assertEqual(inner.calls, [MODEL_INPUT])
                release.set(); self.assertTrue(inner.finished.wait(1.0))
                deadline = time.monotonic()+1.0
                while True:
                    recovered = client.post('/v1/encode-text', json=body, headers=headers)
                    if recovered.status_code != 429 or time.monotonic() >= deadline:
                        break
                    time.sleep(0.01)
                self.assertEqual(recovered.status_code, 200, recovered.text)
                self.assertEqual(inner.calls, [MODEL_INPUT, MODEL_INPUT])
                self.assertEqual(recovered.json()['query_sha256'],
                                 hashlib.sha256(ORIGINALS[0].encode()).hexdigest())
        finally:
            release.set()


if __name__ == "__main__":
    unittest.main()
