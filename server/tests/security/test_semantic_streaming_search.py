"""Generated-data checks for complete, bounded large-cohort semantic search."""
from contextlib import closing
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'tests/security')]

from app.main import create_app
from app.access.semantic_encoder import (JointSpaceBinding, LocalSemanticEncoder,
    TextVector, SemanticUnavailable)
from app.access.semantic_search import SemanticSearchRuntime
from app.access.semantic_streaming import (SemanticServingLimits,
    VECTOR_BATCH_SIZE, rank_semantic_batches)
from app.access.service import AccessService
from app.access.visual_candidates import VectorRecord, canonical_vector_checksum
from app.access.visual_vector_schema import create_visual_vector_schema
import test_assistant_joint_search as fixtures
import test_visual_vector_loader as vector_fixtures
from phone_discovery_fixture import SECOND, NOW, reviewed

IDENTITY = vector_fixtures.IDENTITY
BINDING = JointSpaceBinding(IDENTITY, replace(IDENTITY,
    artifact_sha256='c' * 64, preprocessing_sha256='d' * 64,
    model_version='text-v1'), 'e' * 64)
BASE = '/libraries/family-a/semantic-search/v1/query'
LIMITS = SemanticServingLimits(1024, 10000, 64 * 1024**2, 30.0)


class SemanticStreamingRankingTests(unittest.TestCase):
    def test_ranks_all_768_dimension_vectors_across_batches_with_stable_ties(self):
        identity = replace(IDENTITY, dimension=768)
        binding = JointSpaceBinding(identity, replace(identity,
            artifact_sha256='c' * 64, preprocessing_sha256='d' * 64,
            model_version='text-v1'), 'e' * 64)
        query = (1.0,) + (0.0,) * 767
        text = TextVector(binding.binding_sha256, 'f' * 64, query,
                          canonical_vector_checksum(query))
        records = []
        for aid in range(1, 770):
            vector = query if aid % 3 == 0 else ((0.0, 1.0) + (0.0,) * 766)
            records.append(VectorRecord(str(aid), identity, vector,
                                        canonical_vector_checksum(vector)))
        batches = tuple(tuple(records[index:index + VECTOR_BATCH_SIZE])
                        for index in range(0, len(records), VECTOR_BATCH_SIZE))
        checks = []
        ranked = rank_semantic_batches(text, binding, batches,
            expected_count=len(records), candidate_limit=1024,
            check=lambda: checks.append(None))
        self.assertEqual(len(ranked), 769)
        self.assertEqual([aid for aid, _ in ranked[:3]], ['3', '6', '9'])
        self.assertEqual([aid for aid, _ in ranked[-3:]], ['766', '767', '769'])
        self.assertEqual(len(checks), 1 + len(batches) + 2 * len(records) + 1)

    def test_refuses_oversized_batches_duplicates_and_incomplete_or_excess_cohorts(self):
        query = (1.0, 0.0)
        text = TextVector(BINDING.binding_sha256, 'f' * 64, query,
                          canonical_vector_checksum(query))
        records = tuple(VectorRecord(str(aid), IDENTITY, query,
                                     canonical_vector_checksum(query))
                        for aid in range(1, VECTOR_BATCH_SIZE + 2))
        bad_batches = (
            (records,),
            ((records[0], records[1]), (records[1],)),
            ((records[0],),),
            ((records[0], records[1]),),
        )
        expected = (len(records), 2, 2, 1)
        for batches, count in zip(bad_batches, expected):
            with self.subTest(batches=len(batches), count=count):
                with self.assertRaises(SemanticUnavailable):
                    rank_semantic_batches(text, BINDING, batches,
                        expected_count=count, candidate_limit=1024)

    def test_serving_limits_are_validated_and_share_the_discovery_slot_pool(self):
        invalid = ((512, 1, 1, 1), (100001, 1, 1, 1),
                   (513, 0, 1, 1), (513, 1, 0, 1),
                   (513, 1, 1, 0), (513, 1, 1, float('inf')),
                   (513, 1, 256 * 1024**2 + 1, 1),
                   (513, 1000001, 1, 1), (513, 1, 1, 120.01))
        for values in invalid:
            with self.subTest(values=values), self.assertRaises(ValueError):
                SemanticServingLimits(*values)

        fixture = fixtures.AssistantJointSearchTests(
            'test_text_union_dedup_reasons_and_authored_first_order')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        runtime = SemanticSearchRuntime(fixture.discovery_runtime,
            Path(tempfile.gettempdir()).resolve(),
            _unused_encoder(), pilot_owner_account_id='two', serving_limits=LIMITS)
        budget = runtime.budget
        self.assertIs(budget.slots, fixture.discovery_runtime.budget.slots)
        self.assertEqual((budget.rows, budget.source_bytes, budget.seconds),
                         (LIMITS.source_rows, LIMITS.source_bytes, LIMITS.search_seconds))
        self.assertEqual((budget.index_bytes, budget.response_bytes),
                         (fixture.discovery_runtime.budget.index_bytes,
                          fixture.discovery_runtime.budget.response_bytes))


def _unused_encoder():
    """Build a valid encoder without making a network call."""
    from app.access.semantic_encoder import LocalSemanticEncoder
    return LocalSemanticEncoder(BINDING, 'http://127.0.0.1:43210/v1/encode-text',
                                transport=httpx.MockTransport(lambda _request: httpx.Response(500)))


class SemanticStreamingEndpointTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.AssistantJointSearchTests(
            'test_text_union_dedup_reasons_and_authored_first_order')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        directory = tempfile.TemporaryDirectory(prefix='semantic-streaming-vectors-')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.files = {}
        with closing(sqlite3.connect(self.fixture.database)) as db, db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('ALTER TABLE assets ADD COLUMN hash_sha256 TEXT')
            for aid, in db.execute('SELECT id FROM assets').fetchall():
                db.execute('UPDATE assets SET hash_sha256=? WHERE id=?',
                           (hashlib.sha256(str(aid).encode()).hexdigest(), aid))
            create_visual_vector_schema(db)
            holder = SimpleNamespace(db=db, root=self.root)
            for aid, vector in ((101, (0.0, 1.0)), (103, (1.0, 0.0)),
                                (201, (1.0, 0.0)), (999, (1.0, 0.0))):
                path, record = vector_fixtures.VisualVectorLoaderTests.add_vector(
                    holder, aid, vector,
                    source_hash=hashlib.sha256(str(aid).encode()).hexdigest())
                self.files[str(aid)] = (path, record)
        self.calls = []
        self.during_encode = None

        def provider(request):
            body = json.loads(request.content)
            self.calls.append(body)
            if self.during_encode is not None:
                self.during_encode()
            vector = [1.0, 0.0]
            return httpx.Response(200, json={'version': 1,
                'binding_sha256': BINDING.binding_sha256,
                'query_sha256': hashlib.sha256(body['query'].encode()).hexdigest(),
                'vector': vector, 'checksum_sha256': canonical_vector_checksum(vector)})

        self.encoder = LocalSemanticEncoder(BINDING,
            'http://127.0.0.1:43210/v1/encode-text',
            transport=httpx.MockTransport(provider))
        self._install_runtime()

    def _install_runtime(self):
        with closing(sqlite3.connect(self.fixture.database)) as db:
            db.execute('PRAGMA foreign_keys=ON')
            index = reviewed(AccessService(db, clock=lambda: NOW))
        self.fixture.install(index)
        self.runtime = SemanticSearchRuntime(self.fixture.discovery_runtime,
            self.root, self.encoder, pilot_owner_account_id='two', serving_limits=LIMITS)
        app = create_app(access_runtime=self.fixture.access,
            discovery_runtime=self.fixture.discovery_runtime, assistant_enabled=True,
            semantic_search_runtime=self.runtime)
        self.client = TestClient(app, base_url=fixtures.ORIGIN)
        self.addCleanup(self.client.close)

    def query(self, *, query='generated searchable family scene', filters=None,
              token=SECOND, **kwargs):
        return self.client.post(BASE, headers={'Authorization': 'Bearer ' + token},
            json={'query': query, 'filters': filters or {}, **kwargs})

    def add_generated_cohort(self, count=513, *, final_vector=None, final_component_hash=None):
        with closing(sqlite3.connect(self.fixture.database)) as db, db:
            holder = SimpleNamespace(db=db, root=self.root)
            for offset in range(count):
                aid = 1000 + offset
                source_hash = hashlib.sha256(f'generated-{aid}'.encode()).hexdigest()
                day = '2033-05-01' if offset < 7 else '2033-05-02'
                db.execute('''INSERT INTO assets(id,path,status,mime,width,height,duration_sec,taken_at,hash_sha256)
                    VALUES(?,?,?,?,?,?,?,?,?)''',
                    (aid, f'synthetic/{aid}.jpg', 'active', 'image/jpeg', 64, 64,
                     None, day, source_hash))
                db.execute('INSERT INTO access_asset_libraries VALUES(?,?)',
                           (aid, 'family-a'))
                db.execute('INSERT INTO captions VALUES(?,?,?,0,0)',
                           (2000 + offset, aid, 'generated searchable family scene'))
                vector = (1.0, 0.0) if offset % 2 == 0 else (0.0, 1.0)
                if offset == count - 1 and final_vector is not None:
                    vector = final_vector
                path, record = vector_fixtures.VisualVectorLoaderTests.add_vector(
                    holder, aid, vector, source_hash=source_hash,
                    component_hash=final_component_hash if offset == count - 1 else None)
                self.files[str(aid)] = (path, record)
        self._install_runtime()

    def test_513_generated_vectors_support_full_cohort_paging_and_hard_filter_exclusion(self):
        self.add_generated_cohort()
        first = self.query(page_size=20)
        self.assertEqual(first.status_code, 200, first.text)
        body = first.json()
        self.assertEqual(body['semantic']['candidate_count'], 515)
        self.assertEqual(body['total'], 515)
        self.assertTrue(body['has_more'])
        self.assertEqual(len(body['items']), 20)
        second = self.query(page=2, page_size=20, binding=body['binding'],
                            fingerprint=body['fingerprint'])
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(len(second.json()['items']), 20)
        self.assertEqual(set(item['id'] for item in body['items']).intersection(
                         item['id'] for item in second.json()['items']), set())

        seen = []
        from app.access import semantic_search
        original = semantic_search._read_vector
        def checked(root, artifact, **kwargs):
            seen.append(artifact.asset_id)
            return original(root, artifact, **kwargs)
        with patch('app.access.semantic_search._read_vector', checked):
            filtered = self.query(filters={'date': {
                'from': '2033-05-01', 'to': '2033-05-01'}})
        self.assertEqual(filtered.status_code, 200, filtered.text)
        self.assertEqual(filtered.json()['semantic']['candidate_count'], 7)
        self.assertEqual(len(seen), 14)
        self.assertEqual(set(seen), {str(aid) for aid in range(1000, 1007)})

    def test_vector_io_budget_is_charged_before_file_payload_reads(self):
        self.add_generated_cohort()
        with patch('app.access.semantic_search.MAX_VECTOR_READ_BYTES', 1):
            response = self.query()
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(self.calls, [])

    def test_valid_container_with_wrong_component_checksum_refuses_before_provider(self):
        self.add_generated_cohort(final_component_hash='f' * 64)
        # The original NPY and its container checksum remain valid. Metadata
        # claims a different component checksum when the artifact is created.
        response = self.query()
        self.assertEqual(response.status_code, 503, response.text)
        self.assertNotIn('items', response.json())
        self.assertEqual(self.calls, [])

    def test_matching_container_and_component_checksums_do_not_admit_nonunit_tail(self):
        self.add_generated_cohort(final_vector=(2.0, 0.0))
        response = self.query()
        self.assertEqual(response.status_code, 503, response.text)
        self.assertNotIn('items', response.json())
        self.assertEqual(self.calls, [])

    def test_scene_context_above_512_restores_without_provider_replay(self):
        from app.access.assistant_scene_search import SceneSearchRuntime, context_value
        self.add_generated_cohort()
        base = self.fixture.turn('find photos', token=SECOND).json()
        self.assertEqual(base['kind'], 'results', base)
        scene = SceneSearchRuntime(self.runtime)
        result = scene.search(SECOND, 'family-a', 'a generated scene', base['context'])
        self.assertEqual(result['total'], 515)
        ctx = context_value(result['context'], 'family-a')
        self.assertEqual(ctx['total'], 515)
        before = len(self.calls)
        from app.access.assistant_workspace_store import _result_summary
        restored = scene.restore(SECOND, 'family-a', _result_summary({k: result[k] for k in (
            'version', 'kind', 'reply', 'context', 'filters', 'total', 'has_more', 'effect')}, 'family-a'))
        self.assertEqual(restored['total'], 515)
        self.assertEqual([x['id'] for x in restored['items']], [x['id'] for x in result['items']])
        self.assertEqual(len(self.calls), before)

    def test_corrupt_tail_refuses_before_provider_and_revocation_during_encode_withholds_cards(self):
        self.add_generated_cohort()
        final_path, _ = self.files['1512']
        original_bytes = final_path.read_bytes()
        final_path.write_bytes(b'corrupt tail')
        refused = self.query()
        self.assertEqual(refused.status_code, 503, refused.text)
        self.assertEqual(self.calls, [])
        final_path.write_bytes(original_bytes)

        self.during_encode = lambda: self.fixture.mutate(
            "UPDATE access_memberships SET status='revoked' WHERE account_id='two'")
        response = self.query()
        self.assertEqual(response.status_code, 401, response.text)
        self.assertNotIn('items', response.json())
        self.assertEqual(len(self.calls), 1)

        self.fixture.mutate("UPDATE access_memberships SET status='approved' WHERE account_id='two'")
        self.during_encode = lambda: self.fixture.mutate(
            "UPDATE captions SET text='changed after vector validation' WHERE id=2000")
        changed = self.query()
        self.assertEqual(changed.status_code, 409, changed.text)
        self.assertNotIn('items', changed.json())
        self.assertEqual(len(self.calls), 2)


if __name__ == '__main__':
    unittest.main()
