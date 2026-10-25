"""Explicit semantic API over generated SQLite and immutable vector artifacts."""
from contextlib import closing
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'tests/security')]

from app.main import create_app
from app.access import discovery as d
from app.access.discovery_transport import DiscoveryRuntime
from app.access.service import AccessService
from app.access.semantic_encoder import JointSpaceBinding, LocalSemanticEncoder
from app.access.semantic_search import SemanticSearchRuntime
from app.access.visual_candidates import canonical_vector_checksum
from app.access.visual_vector_schema import create_visual_vector_schema
from app.access.visual_vector_loader import _read_vector
import test_assistant_joint_search as fixtures
import test_visual_vector_loader as vector_fixtures
IDENTITY = vector_fixtures.IDENTITY
from phone_discovery_fixture import OTHER, SECOND, TOKEN, NOW, reviewed

BASE = '/libraries/family-a/semantic-search/v1/query'
BINDING = JointSpaceBinding(IDENTITY, replace(IDENTITY, artifact_sha256='c'*64,
                          preprocessing_sha256='d'*64, model_version='text-v1'), 'e'*64)


class SemanticSearchTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.AssistantJointSearchTests('test_text_union_dedup_reasons_and_authored_first_order')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        directory = tempfile.TemporaryDirectory(prefix='semantic-search-vectors-')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.files = {}
        with closing(sqlite3.connect(self.fixture.database)) as db, db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('ALTER TABLE assets ADD COLUMN hash_sha256 TEXT')
            for aid, in db.execute('SELECT id FROM assets').fetchall():
                db.execute('UPDATE assets SET hash_sha256=? WHERE id=?', (hashlib.sha256(str(aid).encode()).hexdigest(), aid))
            create_visual_vector_schema(db)
            holder = SimpleNamespace(db=db, root=self.root)
            for aid, vector in ((101, (0.0, 1.0)), (103, (1.0, 0.0)),
                                (201, (1.0, 0.0)), (999, (1.0, 0.0))):
                path, record = vector_fixtures.VisualVectorLoaderTests.add_vector(holder, aid, vector,
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

        self.encoder = LocalSemanticEncoder(BINDING, 'http://127.0.0.1:43210/v1/encode-text',
                                           transport=httpx.MockTransport(provider))
        self.runtime = SemanticSearchRuntime(self.fixture.discovery_runtime, self.root, self.encoder)
        app = create_app(access_runtime=self.fixture.access, discovery_runtime=self.fixture.discovery_runtime,
                         assistant_enabled=True, semantic_search_runtime=self.runtime)
        self.client = TestClient(app, base_url=fixtures.ORIGIN)
        self.addCleanup(self.client.close)

    def query(self, *, query='a child flying a kite', filters=None, token=TOKEN, **kwargs):
        return self.client.post(BASE, headers={'Authorization': 'Bearer ' + token},
                                json={'query': query, 'filters': filters or {}, **kwargs})

    def _query_with_caption_digest_count(self, *, query, filters, force_eager=False, **request_kwargs):
        from app.access import semantic_search

        with closing(sqlite3.connect(self.fixture.database)) as db:
            caption_ids = {row[0] for row in db.execute('SELECT id FROM captions')}
        original_digest = d.digest
        caption_digests = []

        def counted(value):
            if (type(value) is tuple and len(value) == 7 and value[0] in caption_ids):
                caption_digests.append(value[0])
            return original_digest(value)

        original_reader = semantic_search.SemanticSearchReads

        def eager_reader(*args, **kwargs):
            # The eager comparison is the general facts path, so keep its
            # runtime mode coherent with its full text projection.
            kwargs['text_projection_required'] = True
            kwargs['media_only_facts'] = False
            return original_reader(*args, **kwargs)

        with patch('app.access.discovery.digest', side_effect=counted):
            if force_eager:
                with patch.object(semantic_search, 'SemanticSearchReads', side_effect=eager_reader):
                    response = self.query(query=query, filters=filters, **request_kwargs)
            else:
                response = self.query(query=query, filters=filters, **request_kwargs)
        return response, caption_digests

    def _assistant_reader(self, *, cache=None, text_projection_required=True):
        from app.access.assistant_search import AssistantSearchReads

        with closing(sqlite3.connect(self.fixture.database)) as db:
            db.execute('PRAGMA foreign_keys=ON')
            access = AccessService(db, clock=lambda: NOW)
            return AssistantSearchReads(access, self.fixture.discovery_runtime.provider,
                d.ReadBudget(), facts_cache=cache,
                text_projection_required=text_projection_required)

    def test_projection_cache_is_mode_bound_and_non_boolean_modes_are_invalid(self):
        cache = {}
        reader = self._assistant_reader(cache=cache, text_projection_required=False)
        calls = []

        def derive(*_args):
            calls.append(reader._text_projection_required)
            return {'derived_mode': reader._text_projection_required}

        reader._facts = derive
        minimal = reader._prepared_facts(None, None, None, None, lambda: None, 'same-binding')
        reader._text_projection_required = True
        eager = reader._prepared_facts(None, None, None, None, lambda: None, 'same-binding')
        self.assertEqual(calls, [False, True])
        self.assertEqual(minimal, {'derived_mode': False})
        self.assertEqual(eager, {'derived_mode': True})
        self.assertIs(cache['text_projection_required'], True)

        from app.access.assistant_search import AssistantSearchReads
        with closing(sqlite3.connect(self.fixture.database)) as db:
            db.execute('PRAGMA foreign_keys=ON')
            with self.assertRaises(d.DiscoveryInvalid):
                AssistantSearchReads(AccessService(db, clock=lambda: NOW),
                    self.fixture.discovery_runtime.provider, d.ReadBudget(),
                    text_projection_required=1)

    def test_projection_mode_change_during_derivation_clears_cache_and_refuses(self):
        cache = {'binding': 'previous', 'text_projection_required': False, 'facts': 'old'}
        reader = self._assistant_reader(cache=cache, text_projection_required=False)

        def switch_mode(*_args):
            reader._text_projection_required = True
            return 'partially-derived'

        reader._facts = switch_mode
        with self.assertRaises(d.DiscoveryUnavailable):
            reader._prepared_facts(None, None, None, None, lambda: None, 'new-binding')
        self.assertEqual(cache, {})

        minimal = self._assistant_reader(text_projection_required=False)
        with self.assertRaises(d.DiscoveryUnavailable):
            minimal._content_match({'text_sources': []}, {'text': 'family beach'})

    def test_cancellation_is_checked_before_cached_facts_are_reused(self):
        cache = {'binding': 'same-binding', 'text_projection_required': False,
                 'facts': 'cached'}
        reader = self._assistant_reader(cache=cache, text_projection_required=False)
        reader._facts = lambda *_args: self.fail('cache miss unexpectedly derived facts')

        def cancelled():
            raise d.DiscoveryCancelled()

        with self.assertRaises(d.DiscoveryCancelled):
            reader._prepared_facts(None, None, None, None, cancelled, 'same-binding')
        self.assertEqual(cache['facts'], 'cached')

    def test_minimal_text_projection_matches_eager_semantic_results(self):
        # These requests exercise English, Chinese, mixed-language queries and
        # hard filters. With no literal text filter, the semantic reader can
        # skip caption/note fact derivation while preserving the same result.
        cases = (
            ('a child flying a kite', {}),
            ('海边的孩子', {'date': {'from': '2032-09-01', 'to': '2032-09-01'}}),
            ('Family beach 家庭海边', {'people': {'ids': ['301'], 'match': 'all'}}),
            ('family beach', {'tags': {'ids': ['501'], 'match': 'all'}}),
            ('孩子在海边', {'locations': ['601']}),
        )
        for query, filters in cases:
            with self.subTest(query=query, filters=filters):
                minimal, minimal_caption_digests = self._query_with_caption_digest_count(
                    query=query, filters=filters)
                eager, eager_caption_digests = self._query_with_caption_digest_count(
                    query=query, filters=filters, force_eager=True)
                self.assertEqual(minimal.status_code, 200, minimal.text)
                self.assertEqual(eager.status_code, 200, eager.text)
                self.assertEqual(minimal.json(), eager.json())
                self.assertEqual(minimal_caption_digests, [])
                self.assertGreater(len(eager_caption_digests), 0)

    def test_minimal_projection_preserves_pagination_binding_and_fingerprint(self):
        first_minimal, _ = self._query_with_caption_digest_count(
            query='scene', filters={}, page_size=1)
        first_eager, _ = self._query_with_caption_digest_count(
            query='scene', filters={}, force_eager=True, page_size=1)
        self.assertEqual(first_minimal.status_code, 200, first_minimal.text)
        self.assertEqual(first_minimal.json(), first_eager.json())
        page_args = {'page': 2, 'page_size': 1,
                     'binding': first_minimal.json()['binding'],
                     'fingerprint': first_minimal.json()['fingerprint']}
        page_minimal, _ = self._query_with_caption_digest_count(
            query='scene', filters={}, **page_args)
        page_eager, _ = self._query_with_caption_digest_count(
            query='scene', filters={}, force_eager=True, **page_args)
        self.assertEqual(page_minimal.status_code, 200, page_minimal.text)
        self.assertEqual(page_minimal.json(), page_eager.json())
        self.assertEqual([item['id'] for item in page_minimal.json()['items']], ['101'])

    def test_literal_text_filters_keep_caption_and_note_fallback_eager(self):
        # Explicit literal filters must still project current captions and
        # saved notes, including note-only matches.
        for literal, expected_id in (('Family beach', '101'), ('secret memory phrase', '101')):
            with self.subTest(literal=literal):
                response, caption_digests = self._query_with_caption_digest_count(
                    query='scene', filters={'text': literal})
                eager, _ = self._query_with_caption_digest_count(
                    query='scene', filters={'text': literal}, force_eager=True)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(eager.status_code, 200, eager.text)
                self.assertEqual(response.json(), eager.json())
                self.assertGreater(len(caption_digests), 0)
                self.assertEqual([item['id'] for item in response.json()['items']], [expected_id])

    def test_caption_and_deleted_note_mutation_during_encoding_withhold_cards(self):
        self.during_encode = lambda: self.fixture.mutate(
            "UPDATE captions SET text='changed while encoding' WHERE id=1")
        caption_change = self.query()
        self.assertEqual(caption_change.status_code, 409, caption_change.text)
        self.assertNotIn('items', caption_change.json())
        self.during_encode = None
        self.fixture.mutate("UPDATE captions SET text='海边 Ｆａｍｉｌｙ Beach Day 示例儿童' WHERE id=1")

        self.during_encode = lambda: self.fixture.mutate(
            "UPDATE access_stories SET deleted=1,revision=2 WHERE id='note-101'")
        note_delete = self.query()
        self.assertEqual(note_delete.status_code, 409, note_delete.text)
        self.assertNotIn('items', note_delete.json())
        self.during_encode = None

    def test_ordinary_assistant_search_keeps_eager_text_projection(self):
        with closing(sqlite3.connect(self.fixture.database)) as db:
            caption_ids = {row[0] for row in db.execute('SELECT id FROM captions')}
        original_digest = d.digest
        caption_digests = []

        def counted(value):
            if type(value) is tuple and len(value) == 7 and value[0] in caption_ids:
                caption_digests.append(value[0])
            return original_digest(value)

        with patch('app.access.discovery.digest', side_effect=counted):
            response = self.fixture.turn('find photos containing "Family beach"')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertGreater(len(caption_digests), 0)

    def test_semantic_scores_replace_literal_eligibility_only_on_the_explicit_api(self):
        seen = []
        def checked(root, artifact):
            seen.append(artifact.asset_id)
            return _read_vector(root, artifact)
        with patch('app.access.semantic_search._read_vector', checked):
            response = self.query()
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual([item['id'] for item in body['items']], ['103', '101'])
        self.assertEqual(set(seen), {'101', '103'})
        self.assertEqual(body['filters'], {'media': ['image']})
        self.assertEqual(body['semantic'], {'mode': 'text_to_image', 'score_kind': 'cosine',
                         'coverage': 'complete_eligible_images', 'candidate_count': 2, 'needs_review': True})
        self.assertGreater(body['items'][0]['semantic_score'], body['items'][1]['semantic_score'])
        self.assertEqual(set(self.calls[0]), {'version', 'query', 'binding_sha256'})
        self.assertEqual(response.headers['cache-control'], 'no-store')
        for private in ('vector', 'qualification_sha256', str(self.root), 'Foreign caption secret'):
            self.assertNotIn(private, response.text)
        literal = self.fixture.turn('find photos containing "a child flying a kite"').json()
        self.assertEqual(literal['total'], 0)

    def test_score_presentation_guard_preserves_ranker_values_and_only_clamps_endpoint_roundoff(self):
        from app.access import discovery as discovery_module
        from app.access.semantic_encoder import JointSpaceBinding, TextVector, rank_semantic
        from app.access.semantic_search import _SCORE_PRESENTATION_ROUNDOFF, _present_semantic_score
        from app.access.visual_candidates import (
            VectorRecord, VectorSpaceIdentity, _canonical_components, _score,
            canonical_vector_checksum,
        )
        import test_semantic_bulk_vectors as bulk_fixtures

        ulp = math.ulp(1.0)
        guard = 16 * ulp
        self.assertEqual(_SCORE_PRESENTATION_ROUNDOFF, guard)
        in_range = math.nextafter(1.0, 0.0)
        self.assertIs(_present_semantic_score(in_range), in_range,
                      'in-range float values are returned without conversion or rounding')
        for raw, expected in ((1.0 + guard, 1.0), (-1.0 - guard, -1.0),
                              (math.nextafter(1.0, 0.0), math.nextafter(1.0, 0.0)),
                              (-1.0, -1.0), (0.375, 0.375), (1, 1)):
            with self.subTest(raw=raw):
                self.assertEqual(_present_semantic_score(raw), expected)
        for raw in (math.nextafter(1.0 + guard, math.inf),
                    math.nextafter(-1.0 - guard, -math.inf), 1.01, -1.01,
                    math.nan, math.inf, -math.inf, True, False, '1.0', None, 10**400):
            with self.subTest(rejected=repr(raw)):
                with self.assertRaises(discovery_module.DiscoveryUnavailable):
                    _present_semantic_score(raw)

        image = VectorSpaceIdentity('a' * 64, 'b' * 64, 'synthetic-score-space',
                                    'synthetic-v1', 768, 'unit_l2')
        text = replace(image, artifact_sha256='c' * 64,
                       preprocessing_sha256='d' * 64, model_version='text-v1')
        binding = JointSpaceBinding(image, text, 'e' * 64)
        vector = (1 / math.sqrt(5),) * 5 + (0.0,) * 763
        checksum = canonical_vector_checksum(vector)
        record = VectorRecord('101', image, vector, checksum)
        canonical = _canonical_components(record, image)
        raw_score = _score(canonical, canonical)
        query = TextVector(binding.binding_sha256, hashlib.sha256(b'same vector').hexdigest(),
                           vector, checksum)
        scalar = rank_semantic(query, binding, (record,))
        self.assertEqual(scalar, (('101', raw_score),))
        self.assertEqual(raw_score, 1.0000000000000002)
        self.assertEqual(_present_semantic_score(raw_score), 1.0)

        bulk = bulk_fixtures.SemanticBulkVectorTests()
        bulk.setUp()
        try:
            store, artifacts = bulk.build(((101, 'a', vector),), image)
            snapshot = store.snapshot(artifacts, library_id='family-a')
            self.assertEqual(snapshot.rank(canonical, ('101',)), (('101', raw_score),))
        finally:
            bulk.doCleanups()

        identity4096 = replace(image, dimension=4096)
        vector4096 = (1 / math.sqrt(5),) * 5 + (0.0,) * 4091
        record4096 = VectorRecord('4096', identity4096, vector4096,
                                  canonical_vector_checksum(vector4096))
        canonical4096 = _canonical_components(record4096, identity4096)
        raw4096 = _score(canonical4096, canonical4096)
        self.assertGreaterEqual(raw4096, 1.0)
        self.assertLessEqual(raw4096, 1.0 + guard)
        self.assertEqual(_present_semantic_score(raw4096), 1.0)

    def test_presented_roundoff_ties_keep_raw_rank_order_and_invalid_scores_refuse(self):
        import math
        from app.access.semantic_search import _SCORE_PRESENTATION_ROUNDOFF

        higher_raw = 1.0 + 2 * math.ulp(1.0)
        lower_raw = 1.0 + math.ulp(1.0)
        self.assertLess(higher_raw, 1.0 + _SCORE_PRESENTATION_ROUNDOFF)
        with patch('app.access.semantic_search.rank_semantic',
                   return_value=(('103', higher_raw), ('101', lower_raw))):
            response = self.query()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([item['id'] for item in response.json()['items']], ['103', '101'])
        self.assertEqual([item['semantic_score'] for item in response.json()['items']], [1.0, 1.0])

        outside = 1.0 + 17 * math.ulp(1.0)
        with patch('app.access.semantic_search.rank_semantic', return_value=(('103', outside),)):
            refused = self.query()
        self.assertEqual(refused.status_code, 503, refused.text)
        self.assertNotIn('items', refused.json())

    def test_score_presentation_policy_binding_rejects_previous_version_before_encoding(self):
        from app.access.semantic_search import SemanticSearchReads

        original = SemanticSearchReads._extra_source_fresh
        def legacy_binding(reader, *args, **kwargs):
            value = original(reader, *args, **kwargs)
            value.pop('score_presentation_policy')
            return value

        with patch.object(SemanticSearchReads, '_extra_source_fresh', legacy_binding):
            first = self.query()
        self.assertEqual(first.status_code, 200, first.text)
        old = first.json()
        self.assertEqual(len(self.calls), 1)
        stale = self.query(binding=old['binding'], fingerprint=old['fingerprint'])
        self.assertEqual(stale.status_code, 409, stale.text)
        self.assertNotIn('items', stale.json())
        self.assertEqual(len(self.calls), 1, 'stale presentation binding is rejected before encoding')

    def test_people_date_location_tags_and_literal_text_are_joint_hard_filters(self):
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
                seen = []
                def checked(root, artifact):
                    seen.append(artifact.asset_id)
                    return _read_vector(root, artifact)
                before = len(self.calls)
                with patch('app.access.semantic_search._read_vector', checked):
                    response = self.query(filters=filters)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual([item['id'] for item in response.json()['items']], expected)
                self.assertEqual(set(seen), set(expected))
                self.assertEqual(len(self.calls)-before, int(bool(expected)))

    def test_missing_corrupt_or_stale_eligible_artifact_refuses_without_partial_results(self):
        self.files['101'][0].write_bytes(b'corrupt')
        response = self.query()
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(self.calls, [])
        # A corrupt image outside an explicit person filter is never read.
        response = self.query(filters={'people': {'ids': ['302'], 'match': 'all'}})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([item['id'] for item in response.json()['items']], ['103'])
        self.files['103'][0].unlink()
        self.assertEqual(self.query(filters={'people': {'ids': ['302'], 'match': 'all'}}).status_code, 503)

    def test_source_digest_mismatch_refuses_before_encoder(self):
        self.fixture.mutate('UPDATE assets SET hash_sha256=? WHERE id=101', ('f'*64,))
        self.assertEqual(self.query().status_code, 503)
        self.assertEqual(self.calls, [])

    def test_unknown_person_or_video_mode_is_invalid_and_never_calls_encoder(self):
        for filters in ({'people': {'ids': ['401'], 'match': 'any'}}, {'media': ['video']},
                        {'text': 'x'*513}, {'unknown': True}):
            self.assertEqual(self.query(filters=filters).status_code, 400)
        self.assertEqual(self.calls, [])

    def test_oversized_eligible_cohort_refuses_before_vector_files_and_encoder(self):
        with closing(sqlite3.connect(self.fixture.database)) as db, db:
            db.execute('PRAGMA foreign_keys=ON')
            for aid in range(1000, 1513):
                db.execute('INSERT INTO assets(id,status,mime,hash_sha256) VALUES(?,?,?,?)',
                           (aid, 'active', 'image/jpeg', 'f'*64))
                db.execute('INSERT INTO access_asset_libraries VALUES(?,?)', (aid, 'family-a'))
            db.commit()
            index = reviewed(AccessService(db, clock=lambda: NOW))
        provider = self.fixture.discovery_runtime.provider
        with patch.object(provider, 'get', return_value=index), patch(
                'app.access.semantic_search._read_vector', side_effect=AssertionError('truncated cohort')):
            response = self.query()
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(self.calls, [])

    def test_membership_precedes_body_provider_and_path_reads(self):
        with patch.object(type(self.fixture.discovery_runtime.provider), 'get', side_effect=AssertionError('metadata before auth')):
            denied = self.query(token=OTHER)
            anonymous = self.client.post(BASE, content=b'not-json')
        self.assertEqual(denied.status_code, 401, denied.text)
        self.assertEqual(anonymous.status_code, 401, anonymous.text)
        self.assertEqual(self.calls, [])

    def test_pilot_owner_requires_exact_approved_owner_before_provider(self):
        self.runtime = replace(self.runtime, pilot_owner_account_id='two')
        self.client.app.state.semantic_search_runtime = self.runtime
        with patch.object(type(self.fixture.discovery_runtime.provider), 'get',
                          side_effect=AssertionError('metadata before owner authorization')):
            for token in (TOKEN, OTHER, 'invalid-token'):
                response = self.query(token=token)
                self.assertEqual(response.status_code, 401, response.text)
            malformed = self.client.post(BASE,
                headers={'Authorization': 'Bearer ' + TOKEN}, content=b'not-json')
            self.assertEqual(malformed.status_code, 401, malformed.text)
        self.assertEqual(self.calls, [])
        self.fixture.mutate("UPDATE access_memberships SET role='owner' WHERE account_id='one'")
        self.assertEqual(self.query(token=TOKEN).status_code, 401)
        self.fixture.mutate("UPDATE access_memberships SET role='viewer' WHERE account_id='one'")
        self.assertEqual(self.query(token=SECOND).status_code, 200)

    def test_pilot_owner_session_revocation_and_role_downgrade_withhold_cards(self):
        self.runtime = replace(self.runtime, pilot_owner_account_id='two')
        self.client.app.state.semantic_search_runtime = self.runtime
        self.during_encode = lambda: self.fixture.mutate(
            "UPDATE access_memberships SET role='viewer' WHERE account_id='two'")
        response = self.query(token=SECOND)
        self.assertEqual(response.status_code, 401, response.text)
        self.assertNotIn('items', response.json())
        self.during_encode = None
        self.fixture.mutate("UPDATE access_memberships SET role='owner' WHERE account_id='two'")
        from app.access.credentials import session_digest
        self.during_encode = lambda: self.fixture.mutate(
            'UPDATE access_sessions SET revoked=1 WHERE digest=?', (session_digest(SECOND),))
        revoked = self.query(token=SECOND)
        self.assertEqual(revoked.status_code, 401, revoked.text)
        self.assertNotIn('items', revoked.json())
        self.assertEqual(len(self.calls), 2)

    def test_restored_snapshot_rechecks_owner_before_releasing_ranking(self):
        from app.access.service import AccessDenied
        self.runtime = replace(self.runtime, pilot_owner_account_id='two')
        original_authorize = self.runtime.authorize
        checks = 0
        def revoke_before_release(token, library):
            nonlocal checks
            checks += 1
            if checks == 2:
                self.fixture.mutate("UPDATE access_memberships SET role='viewer' WHERE account_id='two'")
            return original_authorize(token, library)
        with patch.object(type(self.runtime), 'authorize', autospec=True,
                          side_effect=lambda _runtime, token, library: revoke_before_release(token, library)):
            with self.assertRaises(AccessDenied):
                self.runtime._restore_server_snapshot(SECOND, 'family-a', lambda: False,
                    {'query': 'scene', 'filters': {}}, (('103', 0.9), ('101', 0.1)))
        self.assertEqual(checks, 2)
        self.assertEqual(self.calls, [])

    def test_pagination_is_bound_to_query_and_current_source(self):
        first = self.query(page_size=1).json()
        self.assertEqual(first['total'], 2)
        self.assertTrue(first['has_more'])
        second = self.query(page=2, page_size=1, binding=first['binding'], fingerprint=first['fingerprint'])
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual([item['id'] for item in second.json()['items']], ['101'])
        changed = self.query(query='different query', page=2, page_size=1,
                             binding=first['binding'], fingerprint=first['fingerprint'])
        self.assertEqual(changed.status_code, 409, changed.text)
        self.assertEqual(self.query(page=2).status_code, 400)

    def test_revocation_during_encoding_withholds_cards(self):
        self.during_encode = lambda: self.fixture.mutate("UPDATE access_memberships SET status='revoked' WHERE account_id='one'")
        response = self.query()
        self.assertEqual(response.status_code, 401, response.text)
        self.assertNotIn('items', response.json())

    def test_source_change_during_encoding_withholds_cards(self):
        self.during_encode = lambda: self.fixture.mutate("UPDATE access_stories SET revision=2,text='changed' WHERE id='note-101'")
        response = self.query()
        self.assertEqual(response.status_code, 409, response.text)
        self.assertNotIn('items', response.json())

    def test_new_request_rebuilds_literal_facts_and_refuses_previous_source_binding(self):
        first = self.query(filters={'text': 'secret memory phrase'})
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual([item['id'] for item in first.json()['items']], ['101'])
        self.fixture.mutate("UPDATE access_stories SET text='fresh garden phrase',revision=2 WHERE id='note-101'")
        stale = self.query(filters={'text': 'secret memory phrase'}, binding=first.json()['binding'])
        self.assertEqual(stale.status_code, 409, stale.text)
        self.assertNotIn('items', stale.json())
        old = self.query(filters={'text': 'secret memory phrase'})
        self.assertEqual(old.status_code, 200, old.text)
        self.assertEqual(old.json()['items'], [])
        current = self.query(filters={'text': 'fresh garden phrase'})
        self.assertEqual(current.status_code, 200, current.text)
        self.assertEqual([item['id'] for item in current.json()['items']], ['101'])

    def test_aggregate_deadline_and_cancellation_apply_before_provider(self):
        cancelled = lambda: True
        with self.assertRaises(d.DiscoveryCancelled):
            self.runtime.call('search', TOKEN, 'family-a', cancelled, {'query': 'scene', 'filters': {}})
        clock = iter([0, 1, 20])
        self.runtime.discovery.budget.clock = lambda: next(clock, 20)
        with self.assertRaises(d.DiscoveryUnavailable):
            self.runtime.call('search', TOKEN, 'family-a', lambda: False, {'query': 'scene', 'filters': {}})
        self.assertEqual(self.calls, [])

    def test_invalid_json_limits_and_route_neighbours_are_refused(self):
        auth = {'Authorization': 'Bearer '+TOKEN, 'content-type': 'application/json'}
        for raw in ('{"query":"scene","query":"other","filters":{}}',
                    '{"query":"scene","filters":{},"extra":true}',
                    '{"query":NaN,"filters":{}}'):
            self.assertEqual(self.client.post(BASE, headers=auth, content=raw).status_code, 400)
        self.assertEqual(self.query(page_size=21).status_code, 400)
        self.assertEqual(self.query(query='x'*513).status_code, 400)
        self.assertEqual(self.query(query='scene\nextra').status_code, 400)
        for method, path in (('get', BASE), ('post', BASE+'/extra'), ('post', BASE+'/')):
            self.assertNotEqual(getattr(self.client, method)(path, headers=auth).status_code, 200)
        self.assertEqual(self.calls, [])

    def test_cookie_csrf_and_query_string_credentials_cannot_bypass_admission(self):
        from app.access.transport import COOKIE, csrf_token
        cookie = {'Cookie': COOKIE+'='+TOKEN, 'Origin': fixtures.ORIGIN,
                  'Sec-Fetch-Site': 'same-origin'}
        denied = self.client.post(BASE, headers=cookie, json={'query': 'scene', 'filters': {}})
        self.assertEqual(denied.status_code, 403, denied.text)
        allowed = self.client.post(BASE, headers={**cookie, 'X-CSRF-Token': csrf_token(TOKEN)},
                                   json={'query': 'scene', 'filters': {}})
        self.assertEqual(allowed.status_code, 200, allowed.text)
        self.assertNotEqual(self.client.post(BASE+'?token='+TOKEN,
            json={'query': 'scene', 'filters': {}}).status_code, 200)

    def test_route_is_unmounted_by_default_and_configuration_must_match(self):
        response = self.fixture.client.post(BASE, headers=self.fixture.auth, json={'query': 'scene', 'filters': {}})
        self.assertNotEqual(response.status_code, 200)
        self.assertNotIn(BASE.replace('family-a', '{library_id}'), [r.path for r in self.fixture.client.app.routes])
        with self.assertRaises(ValueError):
            create_app(semantic_search_runtime=self.runtime)
