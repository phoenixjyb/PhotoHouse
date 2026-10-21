"""Protected endpoint checks for explicitly selected bulk vector snapshots."""
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import test_semantic_streaming_search as legacy
from app.main import create_app
from app.access.semantic_bulk_vectors import write_bulk_vectors, BulkVectorStore
from app.access.semantic_search import SemanticSearchRuntime
from app.access.visual_vector_loader import _COLUMNS, _validated_rows
from phone_discovery_fixture import TOKEN, OTHER, SECOND


class SemanticBulkEndpointTests(unittest.TestCase):
    query = legacy.SemanticStreamingEndpointTests.query
    add_generated_cohort = legacy.SemanticStreamingEndpointTests.add_generated_cohort

    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='semantic-bulk-serving-')
        self.addCleanup(directory.cleanup)
        self.bulk_directory = Path(directory.name).resolve()
        self.generation = 0
        legacy.SemanticStreamingEndpointTests.setUp(self)

    def _install_runtime(self):
        legacy.SemanticStreamingEndpointTests._install_runtime(self)
        columns = ','.join('v.' + name for name in _COLUMNS.split(','))
        with closing(sqlite3.connect(self.fixture.database)) as db:
            rows = db.execute(f'''SELECT {columns} FROM image_vector_artifacts v
                JOIN access_asset_libraries m ON m.asset_id=v.asset_id
                JOIN assets a ON a.id=v.asset_id
                WHERE m.library_id='family-a' AND v.status='ready'
                AND (a.status IS NULL OR a.status='active') AND a.mime GLOB 'image/*'
                ORDER BY v.asset_id,v.record_id''').fetchall()
        self.records = tuple(sorted(_validated_rows(rows, legacy.IDENTITY).values(),
                                    key=lambda record: int(record.asset_id)))
        self.generation += 1
        self.bulk_path = self.bulk_directory / f'bulk-{self.generation}.phbv'
        self.store = write_bulk_vectors(self.bulk_path, self.root, self.records,
                                       legacy.IDENTITY, 'family-a')
        self.runtime = replace(self.runtime, bulk_vectors=self.store)
        self.client = self._client(self.runtime)

    def _client(self, runtime):
        client = TestClient(create_app(access_runtime=self.fixture.access,
            discovery_runtime=self.fixture.discovery_runtime, assistant_enabled=True,
            semantic_search_runtime=runtime), base_url=legacy.fixtures.ORIGIN)
        self.addCleanup(client.close)
        return client

    def test_bulk_matches_legacy_scores_order_and_paging_with_no_npy_query_reads(self):
        self.add_generated_cohort()
        baseline_client = self._client(replace(self.runtime, bulk_vectors=None))
        baseline = baseline_client.post(legacy.BASE,
            headers={'Authorization': 'Bearer ' + SECOND},
            json={'query': 'generated searchable family scene', 'filters': {}})
        self.assertEqual(baseline.status_code, 200, baseline.text)
        with patch('app.access.semantic_search._read_vector', side_effect=AssertionError('NPY query read')):
            first = self.query()
            repeated = self.query()
            second = self.query(page=2, binding=first.json()['binding'],
                                fingerprint=first.json()['fingerprint'])
        for response in (first, repeated, second):
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()['total'], 515)
        columns = lambda body: [(item['id'], item['semantic_score']) for item in body['items']]
        self.assertEqual(columns(first.json()), columns(baseline.json()))
        self.assertEqual(columns(first.json()), columns(repeated.json()))
        self.assertFalse({item['id'] for item in first.json()['items']} &
                         {item['id'] for item in second.json()['items']})
        self.assertNotIn(str(self.bulk_path), first.text)
        self.assertNotIn('file_sha256', first.text)

    def test_denials_and_exclusions_precede_bulk_io_and_provider(self):
        with patch.object(BulkVectorStore, 'snapshot', side_effect=AssertionError('bulk before gate')):
            for token in (TOKEN, OTHER, 'invalid'):
                with self.subTest(token=token):
                    self.assertIn(self.query(token=token).status_code, (401, 403))
            for text in ('no people', '没有人的照片', '没有people'):
                with self.subTest(text=text):
                    self.assertEqual(self.query(query=text).status_code, 422)
        self.assertEqual(self.calls, [])

    def test_bulk_hard_people_date_tags_place_text_and_empty_filters(self):
        cases = (
            ({'people': {'ids': ['301', '302'], 'match': 'all'}}, ['103']),
            ({'date': {'from': '2032-09-01', 'to': '2032-09-01'}}, ['101']),
            ({'tags': {'ids': ['501'], 'match': 'all'}}, ['103']),
            ({'locations': ['601'], 'text': 'Family beach'}, ['101']),
            ({'people': {'ids': ['301', '302'], 'match': 'all'},
              'date': {'from': '2032-09-01', 'to': '2032-09-01'}}, []),
        )
        for filters, expected in cases:
            with self.subTest(filters=filters):
                response = self.query(filters=filters)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual([item['id'] for item in response.json()['items']], expected)

    def test_corruption_before_provider_and_after_warm_cache_never_falls_back(self):
        warm = self.query()
        self.assertEqual(warm.status_code, 200, warm.text)
        calls = len(self.calls)
        raw = self.bulk_path.read_bytes()
        self.bulk_path.write_bytes(raw[:-1] + bytes([raw[-1] ^ 1]))
        with patch('app.access.semantic_search._read_vector', side_effect=AssertionError('unsafe fallback')):
            refused = self.query()
        self.assertEqual(refused.status_code, 503, refused.text)
        self.assertNotIn('items', refused.json())
        self.assertEqual(len(self.calls), calls)
        self.bulk_path.write_bytes(raw)
        self.assertEqual(self.query().status_code, 200)

    def test_change_during_encode_refuses_then_exact_restore_recovers(self):
        raw = self.bulk_path.read_bytes()
        self.during_encode = lambda: self.bulk_path.write_bytes(b'changed during encoding')
        response = self.query()
        self.assertEqual(response.status_code, 503, response.text)
        self.assertNotIn('items', response.json())
        self.assertEqual(len(self.calls), 1)
        self.bulk_path.write_bytes(raw)
        self.during_encode = None
        self.assertEqual(self.query().status_code, 200)

    def test_bulk_does_not_cache_membership_or_current_caption_or_asset_hash(self):
        self.assertEqual(self.query().status_code, 200)
        with closing(sqlite3.connect(self.fixture.database)) as db:
            original_captions = db.execute('SELECT id,text FROM captions WHERE asset_id=101').fetchall()
        self.during_encode = lambda: self.fixture.mutate(
            "UPDATE access_memberships SET status='revoked' WHERE account_id='two'")
        refused = self.query()
        self.assertEqual(refused.status_code, 401, refused.text)
        self.assertNotIn('items', refused.json())
        self.fixture.mutate("UPDATE access_memberships SET status='approved' WHERE account_id='two'")
        self.during_encode = lambda: self.fixture.mutate(
            "UPDATE captions SET text='changed while encoding' WHERE asset_id=101")
        changed = self.query()
        self.assertEqual(changed.status_code, 409, changed.text)
        self.assertNotIn('items', changed.json())
        self.during_encode = None
        for caption_id, text in original_captions:
            self.fixture.mutate('UPDATE captions SET text=? WHERE id=?', (text, caption_id))
        self.fixture.mutate("UPDATE assets SET hash_sha256='" + 'f' * 64 + "' WHERE id=101")
        before = len(self.calls)
        source = self.query()
        self.assertEqual(source.status_code, 503, source.text)
        self.assertEqual(len(self.calls), before)

    def test_bulk_io_budget_and_stale_full_cohort_refuse_before_provider(self):
        with patch('app.access.semantic_search.MAX_VECTOR_READ_BYTES', 1):
            refused = self.query()
        self.assertEqual(refused.status_code, 503, refused.text)
        self.assertEqual(self.calls, [])
        with closing(sqlite3.connect(self.fixture.database)) as db:
            legacy.vector_fixtures.VisualVectorLoaderTests.add_vector(
                SimpleNamespace(db=db, root=self.root), 101, (1.0, 0.0), source_hash='f' * 64)
        changed = self.query(filters={'tags': {'ids': ['501'], 'match': 'all'}})
        self.assertEqual(changed.status_code, 503, changed.text)
        self.assertEqual(self.calls, [])

    def test_bulk_requires_explicit_owner_limits_and_matching_identity(self):
        with self.assertRaises(ValueError):
            replace(self.runtime, serving_limits=None)
        with self.assertRaises(ValueError):
            replace(self.runtime, pilot_owner_account_id=None)
        with self.assertRaises(ValueError):
            replace(self.runtime, bulk_vectors=object())
        wrong = BulkVectorStore(self.bulk_path, 'a' * 64, 'family-a',
                                replace(legacy.IDENTITY, model_version='different'))
        with self.assertRaises(ValueError):
            replace(self.runtime, bulk_vectors=wrong)
