"""Generated partial-library serving: visible coverage without narrowing discovery."""
from contextlib import closing
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
import unittest
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

import test_semantic_bulk_search as bulk
import test_semantic_streaming_search as fixture
from app.main import create_app
from app.access.assistant_workspace_store import initialize_v2
from app.access.semantic_eligibility import SemanticEligibilityStore
from phone_discovery_fixture import TOKEN, OTHER, SECOND, NOW


class SemanticEligibilityEndpointTests(unittest.TestCase):
    query = bulk.SemanticBulkEndpointTests.query
    _client = bulk.SemanticBulkEndpointTests._client
    _install_runtime = bulk.SemanticBulkEndpointTests._install_runtime

    def setUp(self):
        bulk.SemanticBulkEndpointTests.setUp(self)
        with closing(sqlite3.connect(self.fixture.database)) as db, db:
            for aid in range(1000, 1065):
                digest = hashlib.sha256(f'omitted-{aid}'.encode()).hexdigest()
                db.execute('''INSERT INTO assets(id,path,status,mime,width,height,duration_sec,taken_at,hash_sha256)
                    VALUES(?,?,'active','image/jpeg',64,64,NULL,'2034-01-01',?)''',
                    (aid, f'synthetic/{aid}.jpg', digest))
                db.execute('INSERT INTO access_asset_libraries VALUES(?,?)', (aid, 'family-a'))
                db.execute('INSERT INTO captions VALUES(?,?,?,0,0)',
                           (2000 + aid, aid, 'generated omitted photos'))
        self._install_runtime()
        self.strict_runtime = self.runtime
        with closing(sqlite3.connect(self.fixture.database)) as db:
            hashes = dict((str(aid), digest) for aid, digest in db.execute('''
                SELECT a.id,a.hash_sha256 FROM assets a JOIN access_asset_libraries m ON m.asset_id=a.id
                WHERE m.library_id='family-a' AND a.mime GLOB 'image/*' AND a.status='active' ORDER BY a.id'''))
        eligible = {record.asset_id for record in self.records}
        self.document = {'format_version': 1, 'operator_reviewed': True,
            'library_id': 'family-a', 'binding_sha256': self.encoder.binding.binding_sha256,
            'bulk_sha256': self.store.file_sha256, 'index_evidence_sha256': 'e' * 64,
            'eligible': [{'asset_id': record.asset_id, 'source_sha256': hashes[record.asset_id],
                          'record_id': record.record_id} for record in self.records],
            'omitted': [{'asset_id': aid, 'source_sha256': digest,
                         'reason': 'source_missing' if aid == '1064' else 'preparation_unavailable'}
                        for aid, digest in hashes.items() if aid not in eligible]}
        self.policy_path = self.bulk_directory / 'eligibility.json'
        self.select_policy(self.document)

    def select_policy(self, doc):
        payload = json.dumps(doc, sort_keys=True).encode()
        self.policy_path.write_bytes(payload)
        self.policy_path.chmod(0o600)
        self.policy = SemanticEligibilityStore(self.policy_path, hashlib.sha256(payload).hexdigest(),
            'family-a', self.encoder.binding.binding_sha256, self.store.file_sha256,
            Path(__file__).resolve().parents[3])
        self.runtime = replace(self.strict_runtime, eligibility=self.policy)
        self.client = self._client(self.runtime)

    def test_65_omissions_are_explicit_and_ordinary_literal_search_retains_them(self):
        with patch('app.access.semantic_search._read_vector', side_effect=AssertionError('NPY fallback')):
            response = self.query()
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body['total'], 2)
        self.assertEqual(body['semantic']['coverage_details'], {
            'version': 1, 'policy_sha256': self.policy.file_sha256, 'state': 'partial',
            'catalog_images': 67, 'searchable_images': 2, 'omitted_images': 65,
            'matched_omitted_images': 65})
        ordinary = self.fixture.turn('find photos containing "generated omitted photos"', token=SECOND)
        self.assertEqual(ordinary.status_code, 200, ordinary.text)
        self.assertEqual(ordinary.json()['total'], 65)
        self.assertEqual(len(self.calls), 1)
        for secret in (str(self.policy_path), str(self.bulk_path), 'source_missing', 'source_sha256'):
            self.assertNotIn(secret, response.text)

    def test_exact_current_eligibility_rows_are_reused_only_within_each_source_read(self):
        from app.access import semantic_search
        with patch.object(semantic_search, '_validated_rows',
                          wraps=semantic_search._validated_rows) as validate:
            response = self.query()
        self.assertEqual(response.status_code, 200, response.text)
        # The ranking generation and final source recheck each validate their
        # newly read cohort. _artifacts reuses the ranking generation after
        # policy validation instead of parsing those exact rows a second time.
        self.assertEqual(validate.call_count, 2)
        self.assertTrue(all(len(call.args[0]) == len(self.records)
                            for call in validate.call_args_list))

    def test_changed_rows_and_failed_fresh_source_cannot_reuse_prior_generation(self):
        from app.access import semantic_search
        original = semantic_search.SemanticSearchReads._extra_source
        calls = [0]

        def changed_row(reader, *args, **kwargs):
            result = original(reader, *args, **kwargs)
            calls[0] += 1
            # Mutate the rows after eligibility validation in the ranking
            # generation, before _artifacts can pair them with that policy.
            if calls[0] == 1:
                rows = list(reader._vector_rows)
                changed = list(rows[0])
                changed[14] += 1
                rows[0] = tuple(changed)
                reader._vector_rows = rows
            return result

        with patch.object(semantic_search.SemanticSearchReads, '_extra_source', changed_row):
            refused = self.query()
        self.assertEqual(refused.status_code, 503, refused.text)
        self.assertEqual(self.calls, [])

        original = semantic_search.SemanticSearchReads._extra_source
        calls = [0]
        readers = []
        prior_generations = []

        def fail_fresh_source(reader, *args, **kwargs):
            readers.append(reader)
            calls[0] += 1
            # The ranking pass has populated a valid generation. Fail the
            # subsequent fresh source reread and prove it is cleared.
            if calls[0] == 2:
                prior_generations.append(reader._eligibility_bulk_generation)
                self.assertIsNotNone(reader._eligibility_bulk_generation)
                with patch.object(semantic_search, 'verify_visual_vector_schema',
                                  return_value=False):
                    return original(reader, *args, **kwargs)
            return original(reader, *args, **kwargs)

        with patch.object(semantic_search.SemanticSearchReads, '_extra_source', fail_fresh_source):
            failed = self.query()
        self.assertEqual(failed.status_code, 503, failed.text)
        self.assertNotIn('items', failed.json())
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(len(prior_generations), 1)
        self.assertIsNone(readers[-1]._eligibility_bulk_generation)

    def test_current_identity_change_cannot_reuse_generation_or_open_bulk(self):
        from app.access import semantic_search
        original = semantic_search.SemanticSearchReads._extra_source
        calls = [0]
        changed = []

        def change_identity(reader, *args, **kwargs):
            result = original(reader, *args, **kwargs)
            calls[0] += 1
            # Change the bound identity after the ranking generation captures
            # it, before artifacts or the provider can be used.
            if calls[0] == 1:
                identity = reader.encoder.binding.image_identity
                changed.append((identity, identity.model_version))
                object.__setattr__(identity, 'model_version', 'changed-generation')
            return result

        try:
            with patch.object(semantic_search.SemanticSearchReads, '_extra_source', change_identity), \
                    patch.object(semantic_search.BulkVectorStore, 'snapshot') as snapshot:
                refused = self.query()
            self.assertEqual(refused.status_code, 503, refused.text)
            snapshot.assert_not_called()
            self.assertEqual(self.calls, [])
        finally:
            for identity, version in changed:
                object.__setattr__(identity, 'model_version', version)

    def test_legacy_strict_runtime_still_refuses_unindexed_candidates(self):
        self.client = self._client(self.strict_runtime)
        self.assertEqual(self.query().status_code, 503)
        self.assertEqual(self.calls, [])

    def test_complete_reviewed_partition_has_complete_coverage(self):
        self.fixture.mutate("UPDATE assets SET status='deleted' WHERE id BETWEEN 1000 AND 1064")
        self._install_runtime()
        self.strict_runtime = self.runtime
        document = deepcopy(self.document)
        document.update(bulk_sha256=self.store.file_sha256, omitted=[])
        self.select_policy(document)
        response = self.query()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['semantic']['coverage_details'], {
            'version': 1, 'policy_sha256': self.policy.file_sha256, 'state': 'complete',
            'catalog_images': 2, 'searchable_images': 2, 'omitted_images': 0,
            'matched_omitted_images': 0})

    def test_hard_filters_apply_before_eligibility_and_empty_subset_never_encodes(self):
        cases = (({'people': {'ids': ['301', '302'], 'match': 'all'}}, ['103'], 0),
                 ({'date': {'from': '2034-01-01', 'to': '2034-01-01'}}, [], 65),
                 ({'text': 'generated omitted photos'}, [], 65),
                 ({'locations': ['601'], 'text': 'Family beach'}, ['101'], 0))
        for filters, ids, omitted in cases:
            with self.subTest(filters=filters):
                before = len(self.calls)
                response = self.query(filters=filters)
                self.assertEqual(response.status_code, 200, response.text)
                body = response.json()
                self.assertEqual([item['id'] for item in body['items']], ids)
                self.assertEqual(body['semantic']['coverage_details']['matched_omitted_images'], omitted)
                self.assertEqual(len(self.calls) - before, int(bool(ids)))

    def test_owner_and_exclusion_gates_precede_policy_and_bulk_payload_reads(self):
        with patch.object(SemanticEligibilityStore, 'read_and_validate',
                          side_effect=AssertionError('policy before authorization')):
            for token in (TOKEN, OTHER, 'invalid'):
                self.assertIn(self.query(token=token).status_code, (401, 403))
        # Negation must never invoke an encoder or score/restore a partial cohort.
        self.assertEqual(self.query(query='没有人的照片').status_code, 422)
        self.assertEqual(self.calls, [])

    def test_unreviewed_unknown_duplicate_and_changed_source_policies_refuse_globally(self):
        changes = []
        doc = deepcopy(self.document)
        doc['operator_reviewed'] = False
        changes.append(doc)
        doc = deepcopy(self.document)
        doc['omitted'][0]['asset_id'] = '999999'
        changes.append(doc)
        doc = deepcopy(self.document)
        doc['omitted'].append(doc['omitted'][0])
        changes.append(doc)
        doc = deepcopy(self.document)
        doc['omitted'][0]['source_sha256'] = 'f' * 64
        changes.append(doc)
        for doc in changes:
            with self.subTest(change=changes.index(doc)):
                self.select_policy(doc)
                response = self.query(filters={'tags': {'ids': ['501'], 'match': 'all'}})
                self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(self.calls, [])

    def test_policy_change_during_encoding_and_after_warm_cache_refuses(self):
        original = self.policy_path.read_bytes()
        self.assertEqual(self.query().status_code, 200)
        self.during_encode = lambda: self.policy_path.write_bytes(original + b' ')
        changed = self.query()
        self.assertEqual(changed.status_code, 503, changed.text)
        self.assertNotIn('items', changed.json())
        before = len(self.calls)
        self.during_encode = None
        self.assertEqual(self.query().status_code, 503)
        self.assertEqual(len(self.calls), before)
        self.policy_path.write_bytes(original)
        self.assertEqual(self.query().status_code, 200)

    def test_omitted_source_change_and_new_ready_artifact_refuse_even_filtered_out(self):
        self.fixture.mutate("UPDATE assets SET hash_sha256=? WHERE id=1000", ('f' * 64,))
        response = self.query(filters={'tags': {'ids': ['501'], 'match': 'all'}})
        self.assertEqual(response.status_code, 503, response.text)
        self.fixture.mutate("UPDATE assets SET hash_sha256=? WHERE id=1000",
                            (self.document['omitted'][0]['source_sha256'],))
        with closing(sqlite3.connect(self.fixture.database)) as db:
            fixture.vector_fixtures.VisualVectorLoaderTests.add_vector(SimpleNamespace(db=db, root=self.root),
                1001, (1.0, 0.0), source_hash=self.document['omitted'][1]['source_sha256'])
        self.assertEqual(self.query().status_code, 503)
        self.assertEqual(self.calls, [])

    def test_omitted_hash_or_membership_change_during_encode_releases_no_cards(self):
        self.during_encode = lambda: self.fixture.mutate(
            "UPDATE assets SET hash_sha256=? WHERE id=1000", ('f' * 64,))
        response = self.query()
        self.assertEqual(response.status_code, 503, response.text)
        self.assertNotIn('items', response.json())
        self.fixture.mutate("UPDATE assets SET hash_sha256=? WHERE id=1000",
                            (self.document['omitted'][0]['source_sha256'],))
        self.during_encode = lambda: self.fixture.mutate(
            "UPDATE access_memberships SET status='revoked' WHERE account_id='two'")
        response = self.query()
        self.assertEqual(response.status_code, 401, response.text)
        self.assertNotIn('items', response.json())

    def test_changed_review_receipt_invalidates_existing_page_binding(self):
        first = self.query(page_size=1)
        self.assertEqual(first.status_code, 200, first.text)
        old = first.json()
        second = self.query(page=2, page_size=1, binding=old['binding'], fingerprint=old['fingerprint'])
        self.assertEqual(second.status_code, 200, second.text)
        self.assertNotEqual(old['items'][0]['id'], second.json()['items'][0]['id'])
        changed = deepcopy(self.document)
        changed['index_evidence_sha256'] = 'd' * 64
        self.select_policy(changed)
        calls = len(self.calls)
        stale = self.query(page=2, page_size=1, binding=old['binding'], fingerprint=old['fingerprint'])
        self.assertEqual(stale.status_code, 409, stale.text)
        self.assertEqual(len(self.calls), calls)

    def test_corrupt_bulk_refuses_even_when_only_omitted_photos_match(self):
        self.bulk_path.write_bytes(b'corrupt bulk')
        response = self.query(filters={'text': 'generated omitted photos'})
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(self.calls, [])

    def test_policy_read_budget_is_enforced_before_inference(self):
        with patch('app.access.semantic_search.MAX_POLICY_READ_BYTES', 1):
            self.assertEqual(self.query().status_code, 503)
        self.assertEqual(self.calls, [])

    def test_runtime_requires_matching_bulk_binding_and_owner_limits(self):
        for values in ({'bulk_vectors': None}, {'pilot_owner_account_id': None},
                       {'eligibility': object()}, {'serving_limits': None}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                replace(self.runtime, **values)

    def test_workspace_discloses_partial_empty_scope_and_recovers_without_encoding(self):
        store = initialize_v2(self.bulk_directory / 'workspace.sqlite', clock=lambda: NOW)
        client = TestClient(create_app(access_runtime=self.fixture.access,
            discovery_runtime=self.fixture.discovery_runtime, assistant_enabled=True,
            assistant_workspace_store=store, semantic_search_runtime=self.runtime,
            assistant_semantic_search_enabled=True), base_url=fixture.fixtures.ORIGIN)
        self.addCleanup(client.close)
        auth = {'Authorization': 'Bearer ' + SECOND}
        base = '/assistant/workspace/v1'
        for words, scene, expected in (('find photos in 2034', 'a kite', 'No matches in the searchable'),
                                       ('找2034年的照片', '风筝', '在可语义检索的照片中未找到')):
            thread = client.post(base + '/threads', headers=auth,
                                 json={'library_id': 'family-a'}).json()['thread']['thread_id']
            path = f'{base}/threads/{thread}/turns'
            scoped = client.post(path, headers=auth | {'X-PhotoHouse-Search-Version': '2'},
                json={'library_id': 'family-a', 'request_id': str(uuid.uuid4()),
                      'expected_revision': 0, 'text': words})
            self.assertEqual(scoped.status_code, 200, scoped.text)
            rid = str(uuid.uuid4())
            headers = auth | {'X-PhotoHouse-Search-Version': '4'}
            response = client.post(path, headers=headers,
                json={'library_id': 'family-a', 'request_id': rid,
                      'expected_revision': 1, 'text': scene, 'accepts': ['scene_search_v1']})
            self.assertEqual(response.status_code, 200, response.text)
            result = response.json()['result']
            self.assertEqual(result['total'], 0)
            self.assertIn(expected, result['reply'])
            self.assertIn('65', result['reply'])
            with patch.object(type(self.encoder), 'encode', side_effect=AssertionError('model replay')):
                restored = client.get(f'{base}/threads/{thread}/requests/{rid}?library_id=family-a',
                                      headers=headers)
            self.assertEqual(restored.status_code, 200, restored.text)
            self.assertEqual(restored.json()['result'], result)
        self.assertEqual(self.calls, [])
