"""Generated full API -> authenticated provider -> text-tower adapter chain.

Only the optional ML library objects are stand-ins. Both ASGI applications,
the HTTP client/protocol, checksum/identity checks and image ranking are real.
No socket is opened and no installed model is loaded.
"""
from contextlib import closing
from dataclasses import replace
import hashlib
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest

import httpx
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'backend'), str(ROOT/'scripts'), str(ROOT/'tests/security')]

import test_assistant_joint_search as joint_fixtures
import test_semantic_openclip as model_fixtures
import test_visual_vector_loader as vector_fixtures
from app.access.semantic_encoder import JointSpaceBinding, LocalSemanticEncoder
from app.access.semantic_provider_transport import create_provider_app
from app.access.semantic_search import SemanticSearchRuntime
from app.access.visual_candidates import VectorSpaceIdentity
from app.access.visual_vector_schema import create_visual_vector_schema
from app.main import create_app


class SemanticProviderIntegrationTests(unittest.TestCase):
    def test_full_generated_chain_keeps_hard_constraints_and_uses_authenticated_provider(self):
        model_fixture = model_fixtures.SemanticOpenClipTests('test_explicit_local_load_and_normalized_text_vector')
        model_fixture.setUp(); self.addCleanup(model_fixture.doCleanups)
        model = model_fixture.load()
        text_identity = VectorSpaceIdentity(model._checkpoint_sha256, model._recipe_sha256,
                                            'synthetic-joint', 'text-v1', 512, 'unit_l2')
        image_identity = replace(text_identity, preprocessing_sha256='b'*64, model_version='image-v1')
        binding = JointSpaceBinding(image_identity, text_identity, 'c'*64)
        model.bind(binding)
        secret = 'synthetic_provider_credential_'+'t'*32
        provider = TestClient(create_provider_app(model, bearer_token=secret, port=8912),
            base_url='http://127.0.0.1:8912', client=('127.0.0.1', 50000))
        self.addCleanup(provider.close)
        provider_requests = []
        def bridge(request):
            provider_requests.append(request)
            response = provider.request(request.method, str(request.url),
                                         headers=dict(request.headers), content=request.content)
            return httpx.Response(response.status_code, headers=response.headers, content=response.content)
        encoder = LocalSemanticEncoder(binding, 'http://127.0.0.1:8912/v1/encode-text',
            transport=httpx.MockTransport(bridge), bearer_token=secret)
        fixture = joint_fixtures.AssistantJointSearchTests('test_text_union_dedup_reasons_and_authored_first_order')
        fixture.setUp(); self.addCleanup(fixture.doCleanups)
        directory = tempfile.TemporaryDirectory(prefix='semantic-chain-artifacts-')
        self.addCleanup(directory.cleanup)
        vector_root = Path(directory.name).resolve()
        with closing(sqlite3.connect(fixture.database)) as db, db:
            db.execute('ALTER TABLE assets ADD COLUMN hash_sha256 TEXT')
            create_visual_vector_schema(db)
            holder = SimpleNamespace(db=db, root=vector_root)
            for aid, vector in ((101, [0.0, 1.0]+[0.0]*510), (103, [1.0]+[0.0]*511)):
                source_hash = hashlib.sha256(str(aid).encode()).hexdigest()
                db.execute('UPDATE assets SET hash_sha256=? WHERE id=?', (source_hash, aid))
                vector_fixtures.VisualVectorLoaderTests.add_vector(holder, aid, vector,
                    source_hash=source_hash, identity=image_identity)
        runtime = SemanticSearchRuntime(fixture.discovery_runtime, vector_root, encoder)
        client = TestClient(create_app(access_runtime=fixture.access, discovery_runtime=fixture.discovery_runtime,
                            semantic_search_runtime=runtime), base_url=joint_fixtures.ORIGIN)
        self.addCleanup(client.close)
        response = client.post('/libraries/family-a/semantic-search/v1/query', headers=fixture.auth,
                                json={'query': 'a child flying a kite', 'filters': {}})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([item['id'] for item in response.json()['items']], ['101', '103'])
        restricted = client.post('/libraries/family-a/semantic-search/v1/query', headers=fixture.auth,
            json={'query': 'a child flying a kite',
                  'filters': {'people': {'ids': ['301', '302'], 'match': 'all'}}})
        self.assertEqual(restricted.status_code, 200, restricted.text)
        self.assertEqual([item['id'] for item in restricted.json()['items']], ['103'])
        self.assertEqual(len(provider_requests), 2)
        self.assertEqual(provider_requests[0].headers['authorization'], 'Bearer '+secret)
        self.assertNotIn(secret.encode(), provider_requests[0].content)
        self.assertEqual(model._tokenizer.cache, {'special': 'baseline'})
        self.assertNotIn('vector', response.json()['items'][0])
        self.assertTrue(response.json()['semantic']['needs_review'])


if __name__ == '__main__': unittest.main()
