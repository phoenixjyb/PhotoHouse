"""Generated workspace scene ranking: strict scope, durable order, no model replay."""
from contextlib import closing
from copy import deepcopy
from dataclasses import replace
import sqlite3
from types import SimpleNamespace
import unittest
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import create_app
from app.access import discovery as d
from app.access.assistant_scene_search import context_value, _scope
from app.access.assistant_workspace_store import initialize_v2, _result_summary
from app.access.semantic_encoder import LocalSemanticEncoder
from phone_discovery_fixture import TOKEN, OTHER, NOW, reviewed
from app.access.service import AccessService
import test_semantic_search as semantic_fixture
import test_assistant_kinship as kinship_fixture

BASE = '/assistant/workspace/v1'


class AssistantSceneSearchTests(unittest.TestCase):
    def setUp(self):
        self.pilot = semantic_fixture.SemanticSearchTests('test_membership_precedes_body_provider_and_path_reads')
        self.pilot.setUp()
        self.addCleanup(self.pilot.doCleanups)
        self.source = self.pilot.fixture
        self.store = initialize_v2(self.pilot.root / 'workspace.sqlite', clock=lambda: NOW)
        self.app = create_app(access_runtime=self.source.access,
            discovery_runtime=self.source.discovery_runtime, assistant_enabled=True,
            assistant_workspace_store=self.store, semantic_search_runtime=self.pilot.runtime,
            assistant_semantic_search_enabled=True)
        self.client = TestClient(self.app, base_url='https://photohouse.example.test')
        self.addCleanup(self.client.close)
        self.auth = {'Authorization': 'Bearer ' + TOKEN}
        self.headers = self.auth | {'X-PhotoHouse-Search-Version': '4'}
        self.thread = self.client.post(BASE + '/threads', headers=self.auth,
            json={'library_id': 'family-a'}).json()['thread']['thread_id']

    def send(self, text, revision=0, *, scene=False, rid=None, extra=None, headers=None):
        body = {'library_id': 'family-a', 'request_id': rid or str(uuid.uuid4()),
                'expected_revision': revision, 'text': text}
        if scene:
            body['accepts'] = ['scene_search_v1']
        body.update(extra or {})
        return self.client.post(f'{BASE}/threads/{self.thread}/turns',
            headers=headers or (self.headers if scene else self.auth | {'X-PhotoHouse-Search-Version': '2'}),
            json=body)

    def scope(self, text='find photos of Sample Child in September 2032'):
        response = self.send(text)
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()['result']
        self.assertEqual(result['kind'], 'results', result)
        self.assertIsNotNone(result['context'])
        return result

    def read(self, rid, headers=None):
        return self.client.get(f'{BASE}/threads/{self.thread}/requests/{rid}?library_id=family-a',
                               headers=headers or self.headers)

    def enable_request_source_snapshot(self):
        from app.access.semantic_request_snapshot import NativeSnapshotDatabase
        from app.access.transport import AccessRuntime
        with closing(sqlite3.connect(self.source.database)) as db:
            self.assertEqual(db.execute('PRAGMA journal_mode=WAL').fetchone(), ('wal',))
        access = AccessRuntime(NativeSnapshotDatabase(self.source.database.resolve()),
            self.source.access.web_origin, clock=self.source.access.clock)
        discovery = replace(self.pilot.runtime.discovery, access=access)
        self.pilot.runtime = replace(self.pilot.runtime, discovery=discovery,
            request_source_snapshot=True)
        self.app.state.access_runtime = access
        self.app.state.discovery_runtime = discovery
        self.app.state.semantic_search_runtime = self.pilot.runtime
        self.pilot.client.app.state.access_runtime = access
        self.pilot.client.app.state.discovery_runtime = discovery
        self.pilot.client.app.state.semantic_search_runtime = self.pilot.runtime

    def test_opt_in_is_separate_and_closed_default_does_not_admit_v4(self):
        legacy = self.client.get(BASE + '/capabilities?library_id=family-a', headers=self.auth).json()
        self.assertNotIn('scene_search', legacy)
        response = self.client.get(BASE + '/scene-search-capabilities?library_id=family-a', headers=self.auth)
        self.assertEqual(response.json(), {'version': 1, 'available': True,
                                          'search_version': 4, 'media': ['image']})
        self.app.state.assistant_semantic_search_enabled = False
        self.assertFalse(self.client.get(BASE + '/scene-search-capabilities?library_id=family-a',
                                         headers=self.auth).json()['available'])
        self.assertEqual(self.send('a kite', scene=True).status_code, 400)
        self.assertEqual(self.pilot.calls, [])
        for kwargs in ({'assistant_semantic_search_enabled': True},
                       {'assistant_semantic_search_enabled': 'yes'}):
            with self.assertRaises(ValueError):
                create_app(**kwargs)

    def test_english_chinese_and_mixed_scene_wording_keeps_all_hard_filters(self):
        base = self.scope('find photos of Sample Child in September 2032 containing "Family beach"')
        self.assertEqual(base['filters']['people'], {'ids': ['301'], 'match': 'any'})
        self.assertEqual(base['filters']['text'], 'Family beach')
        scenes = ('a child flying a bright kite', '孩子在桥旁放风筝', '孩子 beside a blue bridge 放风筝')
        for revision, query in enumerate(scenes, 1):
            with self.subTest(query=query):
                response = self.send(query, revision, scene=True)
                self.assertEqual(response.status_code, 200, response.text)
                result = response.json()['result']
                self.assertEqual(result['version'], 4)
                self.assertEqual(result['filters'], base['filters'])
                self.assertEqual([x['id'] for x in result['items']], ['101'])
                self.assertEqual(result['context']['scene']['query'], query)
                self.assertEqual(result['semantic']['coverage'], 'complete_eligible_images')
                self.assertTrue(result['semantic']['needs_review'])
                self.assertIsNone(result['effect'])
                self.assertEqual(self.pilot.calls[-1]['query'], query)
                self.assertEqual(set(self.pilot.calls[-1]), {'version', 'binding_sha256', 'query'})
                self.assertEqual(len(self.pilot.calls), revision)
                self.assertNotIn(str(self.pilot.root), response.text)
                self.assertNotIn('vector', response.text)

    def test_post_retry_and_get_recovery_keep_order_and_never_reencode(self):
        self.enable_request_source_snapshot()
        base = self.scope()
        rid = str(uuid.uuid4())
        first = self.send('a child flying a kite', 1, scene=True, rid=rid)
        self.assertEqual(first.status_code, 200, first.text)
        result = first.json()['result']
        self.assertEqual([x['id'] for x in result['items']], ['103', '101'])
        self.assertEqual(result['filters'], base['filters'])
        with patch.object(type(self.pilot.encoder), 'encode', side_effect=AssertionError('model replay')):
            for response in (self.read(rid), self.send('a child flying a kite', 1, scene=True, rid=rid)):
                self.assertEqual(response.status_code, 200, response.text)
                self.assertTrue(response.json()['recovered'])
                self.assertEqual(response.json()['result'], result)
        self.assertEqual(len(self.pilot.calls), 1)
        legacy = self.read(rid, self.auth | {'X-PhotoHouse-Search-Version': '2'})
        self.assertEqual(legacy.status_code, 409, legacy.text)
        self.assertNotIn('items', legacy.text)
        self.assertEqual(legacy.headers['cache-control'], 'no-store')

    def test_768d_roundoff_score_is_bounded_for_workspace_and_snapshot_recovery(self):
        import hashlib
        import json
        import math
        import httpx
        from app.access.semantic_encoder import JointSpaceBinding, LocalSemanticEncoder
        from app.access.semantic_search import _present_semantic_score
        from app.access.visual_candidates import VectorSpaceIdentity, canonical_vector_checksum
        import test_visual_vector_loader as vector_fixture

        vector = (1 / math.sqrt(5),) * 5 + (0.0,) * 763
        image = VectorSpaceIdentity('a' * 64, 'b' * 64, 'synthetic-space',
                                    'synthetic-v1', 768, 'unit_l2')
        text = replace(image, artifact_sha256='c' * 64,
                       preprocessing_sha256='d' * 64, model_version='text-v1')
        binding = JointSpaceBinding(image, text, 'e' * 64)
        checksum = canonical_vector_checksum(vector)

        original_identity = vector_fixture.IDENTITY
        original_add_vector = vector_fixture.VisualVectorLoaderTests.add_vector
        original_semantic_identity = semantic_fixture.IDENTITY
        original_semantic_binding = semantic_fixture.BINDING
        original_runtime_class = semantic_fixture.SemanticSearchRuntime
        original_token = globals()['TOKEN']
        calls = []
        scenario = None

        def add_768(self, asset_id, _original_vector, **kwargs):
            kwargs['identity'] = image
            return original_add_vector(self, asset_id, vector, **kwargs)

        def make_pilot_runtime(discovery, root, encoder):
            with discovery.access.connection_factory() as connection:
                owner_id = AccessService(connection, clock=discovery.access.clock)._require(
                    TOKEN, 'family-a', 'library.read')['account_id']
            return original_runtime_class(discovery, root, encoder,
                                          pilot_owner_account_id=owner_id)

        def provider(request):
            body = json.loads(request.content)
            calls.append(body)
            return httpx.Response(200, json={'version': 1,
                'binding_sha256': binding.binding_sha256,
                'query_sha256': hashlib.sha256(body['query'].encode('utf-8')).hexdigest(),
                'vector': list(vector), 'checksum_sha256': checksum})

        try:
            TOKEN = semantic_fixture.SECOND
            globals()['TOKEN'] = TOKEN
            vector_fixture.IDENTITY = image
            semantic_fixture.IDENTITY = image
            semantic_fixture.BINDING = binding
            semantic_fixture.SemanticSearchRuntime = make_pilot_runtime
            with patch.object(vector_fixture.VisualVectorLoaderTests, 'add_vector', add_768):
                scenario = AssistantSceneSearchTests(
                    'test_post_retry_and_get_recovery_keep_order_and_never_reencode')
                scenario.setUp()
            encoder = LocalSemanticEncoder(binding, 'http://127.0.0.1:43210/v1/encode-text',
                                           transport=httpx.MockTransport(provider))
            scenario.pilot.encoder = encoder
            scenario.pilot.runtime = replace(scenario.pilot.runtime, encoder=encoder)
            scenario.enable_request_source_snapshot()

            direct = scenario.pilot.query(query='same vector', filters={}, token=TOKEN)
            self.assertEqual(direct.status_code, 200, direct.text)
            direct_result = direct.json()
            self.assertEqual([item['id'] for item in direct_result['items']], ['101', '103'])
            self.assertEqual([item['semantic_score'] for item in direct_result['items']], [1.0, 1.0])
            base = scenario.scope()
            rid = 'f09dbe5d-802c-4cf9-9068-bb1ecac94312'
            first = scenario.send('same vector', revision=1, scene=True, rid=rid)
            self.assertEqual(first.status_code, 200, first.text)
            result = first.json()['result']
            self.assertEqual([item['id'] for item in result['items']], ['101', '103'])
            self.assertEqual([item['semantic_score'] for item in result['items']], [1.0, 1.0])
            self.assertEqual(result['context']['scene']['scores'], [1.0, 1.0])
            self.assertEqual(len(calls), 2)

            with patch('app.access.semantic_search._present_semantic_score',
                       wraps=_present_semantic_score) as score_guard, \
                    patch.object(type(encoder), 'encode', side_effect=AssertionError('model replay')):
                recovered = scenario.read(rid)
                self.assertEqual(recovered.status_code, 200, recovered.text)
                self.assertTrue(recovered.json()['recovered'])
                self.assertEqual(recovered.json()['result'], result)
                retried = scenario.send('same vector', revision=1, scene=True, rid=rid)
                self.assertEqual(retried.status_code, 200, retried.text)
                self.assertTrue(retried.json()['recovered'])
                self.assertEqual(retried.json()['result'], result)
            self.assertGreaterEqual(score_guard.call_count, 2)
            self.assertTrue(all(call.args == (1.0,) for call in score_guard.call_args_list))
            self.assertEqual(len(calls), 2)
            self.assertGreater(base['total'], 0)
        finally:
            if scenario is not None:
                scenario.doCleanups()
            globals()['TOKEN'] = original_token
            vector_fixture.IDENTITY = original_identity
            semantic_fixture.IDENTITY = original_semantic_identity
            semantic_fixture.BINDING = original_semantic_binding
            semantic_fixture.SemanticSearchRuntime = original_runtime_class

    def test_an_empty_hard_scope_never_calls_encoder(self):
        base = self.scope('find photos of Sample Adult in 2020')
        self.assertEqual(base['total'], 0)
        response = self.send('a bright kite', 1, scene=True)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['result']['items'], [])
        self.assertEqual(self.pilot.calls, [])
        self.assertEqual(self.read(response.json()['request_id']).status_code, 200)

    def test_disabled_tracking_has_no_receipt_identity_header(self):
        self.scope()
        response = self.send('a blue bridge', 1, scene=True)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers['X-PhotoHouse-Tracking'], 'disabled')
        self.assertNotIn('X-PhotoHouse-Request-Id', response.headers)
        self.assertNotIn('X-PhotoHouse-Receipt-Status', response.headers)
        self.assertIn('request_id', response.json())

    def test_unreviewed_scope_media_and_unnegotiated_body_are_refused(self):
        self.assertEqual(self.send('a bright kite', scene=True).status_code, 409)
        self.scope('find videos')
        self.assertEqual(self.send('a bright kite', 1, scene=True).status_code, 400)
        self.assertEqual(self.send('a bright kite', 1, headers=self.headers).status_code, 400)
        self.assertEqual(self.send('a bright kite', 1, scene=True,
            headers=self.auth | {'X-PhotoHouse-Search-Version': '2'}).status_code, 400)
        self.assertEqual(self.send('a bright kite', 1, scene=True,
            extra={'context': {}}).status_code, 400)
        self.assertEqual(self.pilot.calls, [])
        direct = self.client.post('/assistant/v1/turns', headers=self.headers,
            json={'library_id': 'family-a', 'text': 'find photos', 'context': None})
        self.assertEqual(direct.status_code, 400)

    def test_unresolved_hard_conditions_cannot_be_bypassed_with_scene_search(self):
        base = self.scope()
        pending = self.send('only photos of Unknown Stranger', 1)
        self.assertEqual(pending.status_code, 200, pending.text)
        self.assertEqual(pending.json()['result']['kind'], 'clarification')
        self.assertEqual(pending.json()['result']['context'], base['context'])
        scene = self.send('a kite', 2, scene=True)
        self.assertEqual(scene.status_code, 409, scene.text)
        self.assertEqual(self.pilot.calls, [])
        resolved = self.send('find photos of Sample Child in September 2032', 2)
        self.assertEqual(resolved.status_code, 200, resolved.text)
        resumed = self.send('a kite', 3, scene=True)
        self.assertEqual(resumed.status_code, 200, resumed.text)
        self.assertEqual(len(self.pilot.calls), 1)

    def test_membership_precedes_metadata_and_encoder(self):
        self.scope()
        with patch.object(type(self.source.discovery_runtime.provider), 'get',
                          side_effect=AssertionError('metadata before membership')):
            response = self.send('a bright kite', 1, scene=True,
                headers={'Authorization': 'Bearer ' + OTHER, 'X-PhotoHouse-Search-Version': '4'})
        self.assertEqual(response.status_code, 401, response.text)
        self.assertEqual(self.pilot.calls, [])

    def test_public_pilot_cannot_supply_a_trusted_ranking_snapshot(self):
        response = self.client.post('/libraries/family-a/semantic-search/v1/query',
            headers=self.auth, json={'query': 'a kite', 'filters': {},
                'server_snapshot': [['103', 1.0], ['101', 0.0]]})
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(self.pilot.calls, [])

    def test_changes_during_encoding_withhold_results_and_preserve_prior_context(self):
        self.enable_request_source_snapshot()
        self.scope()
        self.pilot.during_encode = lambda: self.source.mutate(
            "UPDATE access_stories SET revision=2,text='changed' WHERE id='note-101'")
        response = self.send('a bright kite', 1, scene=True)
        self.assertEqual(response.status_code, 409, response.text)
        self.assertNotIn('items', response.text)
        self.assertEqual(self.store.get_thread('one', 'family-a', self.thread)['thread']['revision'], 1)
        with closing(sqlite3.connect(self.source.database)) as db:
            self.assertEqual(db.execute(
                "SELECT revision,text FROM access_stories WHERE id='note-101'").fetchone(),
                (2, 'changed'))

    def test_membership_revocation_commits_during_snapshot_request_and_withholds_cards(self):
        self.enable_request_source_snapshot()
        self.scope()
        self.pilot.during_encode = lambda: self.source.mutate(
            "UPDATE access_memberships SET status='revoked' WHERE account_id='one'")
        response = self.send('a bright kite', 1, scene=True)
        self.assertEqual(response.status_code, 401, response.text)
        self.assertNotIn('items', response.text)
        with closing(sqlite3.connect(self.source.database)) as db:
            self.assertEqual(db.execute(
                "SELECT status FROM access_memberships WHERE account_id='one'").fetchone(),
                ('revoked',))

    def test_recovery_refuses_changed_source_vector_and_encoder_identity_without_model(self):
        self.scope()
        initial = self.send('a kite', 1, scene=True).json()
        rid = initial['request_id']
        path = self.pilot.files['101'][0]
        raw = path.read_bytes()
        path.write_bytes(b'corrupt')
        response = self.read(rid)
        self.assertEqual(response.status_code, 503, response.text)
        self.assertNotIn('items', response.text)
        path.write_bytes(raw)
        self.assertEqual(self.read(rid).status_code, 200)
        self.source.mutate("UPDATE access_stories SET revision=2,text='changed' WHERE id='note-101'")
        self.assertEqual(self.read(rid).status_code, 409)
        self.assertEqual(len(self.pilot.calls), 1)

    def test_recovery_rechecks_joint_identity_and_revocation_without_encoder(self):
        self.scope()
        rid = self.send('a kite', 1, scene=True).json()['request_id']
        changed = replace(self.pilot.encoder.binding, qualification_sha256='f'*64)
        self.app.state.semantic_search_runtime = replace(self.pilot.runtime,
            encoder=LocalSemanticEncoder(changed, 'http://127.0.0.1:43210/v1/encode-text'))
        with patch.object(LocalSemanticEncoder, 'encode', side_effect=AssertionError('model replay')):
            self.assertEqual(self.read(rid).status_code, 409)
            self.app.state.semantic_search_runtime = self.pilot.runtime
            self.source.mutate("UPDATE access_memberships SET status='revoked' WHERE account_id='one'")
            self.assertEqual(self.read(rid).status_code, 401)
        self.assertEqual(len(self.pilot.calls), 1)

    def test_graph_bound_v3_scope_is_rechecked_before_after_and_on_recovery(self):
        provider = kinship_fixture.MutableKinshipProvider()
        provider.install(kinship_fixture.assistant_graph())
        self.app.state.assistant_kinship_provider = provider
        def no_planner(*_args, **_kwargs):
            raise AssertionError('A reviewed hard query does not need a model')
        self.app.state.assistant_intent_planner = SimpleNamespace(propose=no_planner)
        response = self.send('找妈妈的照片', headers=self.auth | {'X-PhotoHouse-Search-Version': '3'})
        self.assertEqual(response.status_code, 200, response.text)
        base = response.json()['result']
        self.assertEqual((base['version'], base['kind']), (3, 'results'))
        self.assertEqual(base['filters']['people'], {'ids': ['302'], 'match': 'any'})
        changed = kinship_fixture.assistant_graph(revision='graph-revised')
        provider.install(changed)
        self.assertEqual(self.send('桥旁放风筝', 1, scene=True).status_code, 409)
        self.assertEqual(self.pilot.calls, [])
        provider.install(kinship_fixture.assistant_graph())
        result = self.send('桥旁放风筝', 1, scene=True)
        self.assertEqual(result.status_code, 200, result.text)
        rid = result.json()['request_id']
        provider.graph = None
        self.assertEqual(self.read(rid).status_code, 409)
        provider.install(kinship_fixture.assistant_graph())
        self.assertEqual(self.read(rid).status_code, 200)
        self.pilot.during_encode = lambda: provider.install(changed)
        self.assertEqual(self.send('a child near a bridge', 2, scene=True).status_code, 409)
        self.assertEqual(len(self.pilot.calls), 2)

    def test_full_cohort_integrity_is_rechecked_even_outside_the_saved_first_page(self):
        with closing(sqlite3.connect(self.source.database)) as db, db:
            db.execute('PRAGMA foreign_keys=ON')
            holder = SimpleNamespace(db=db, root=self.pilot.root)
            for aid in range(1000, 1025):
                db.execute('INSERT INTO assets(id,status,mime,hash_sha256) VALUES(?,?,?,?)',
                           (aid, 'active', 'image/jpeg', 'f'*64))
                db.execute('INSERT INTO access_asset_libraries VALUES(?,?)', (aid, 'family-a'))
                semantic_fixture.vector_fixtures.VisualVectorLoaderTests.add_vector(
                    holder, aid, (1.0, 0.0), source_hash='f'*64)
            db.commit()
            index = reviewed(AccessService(db, clock=lambda: NOW))
        with patch.object(self.source.discovery_runtime.provider, 'get', return_value=index):
            self.scope('find photos')
            response = self.send('a kite', 1, scene=True)
            self.assertEqual(response.status_code, 200, response.text)
            result = response.json()['result']
            self.assertEqual((result['total'], len(result['items']), result['has_more']), (27, 20, True))
            self.assertNotIn('101', result['context']['visible_ids'])
            rid = response.json()['request_id']
            recovered = self.read(rid)
            self.assertEqual(recovered.status_code, 200, recovered.text)
            self.assertEqual(recovered.json()['result'], result)
            self.pilot.files['101'][0].write_bytes(b'corrupt outside saved page')
            failed = self.read(rid)
            self.assertEqual(failed.status_code, 503, failed.text)
            self.assertNotIn('items', failed.text)
            self.assertEqual(len(self.pilot.calls), 1)

    def test_out_of_scope_vectors_are_never_read_through_the_workspace_bridge(self):
        self.scope('find photos of Sample Adult')
        self.pilot.files['101'][0].write_bytes(b'corrupt excluded vector')
        seen = []
        original = semantic_fixture._read_vector
        def checked(root, artifact):
            seen.append(artifact.asset_id)
            return original(root, artifact)
        with patch('app.access.semantic_search._read_vector', checked):
            response = self.send('a kite', 1, scene=True)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(set(seen), {'103'})
        self.assertEqual([x['id'] for x in response.json()['result']['items']], ['103'])

    def test_scene_turn_deadline_refuses_without_encoder_work(self):
        self.scope()
        clock = iter([0, 0, 0, 20])
        self.pilot.runtime.discovery.budget.clock = lambda: next(clock, 20)
        response = self.send('a kite', 1, scene=True)
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(self.pilot.calls, [])

    def test_legacy_refinement_cannot_drop_a_scene_but_a_full_new_search_can_leave_it(self):
        self.scope()
        self.assertEqual(self.send('a kite', 1, scene=True).status_code, 200)
        self.assertEqual(self.send('only videos', 2).status_code, 409)
        fresh = self.send('find videos', 2)
        self.assertEqual(fresh.status_code, 200, fresh.text)
        self.assertEqual(fresh.json()['result']['version'], 2)
        self.assertEqual(fresh.json()['result']['filters'], {'media': ['video']})
        self.assertEqual(len(self.pilot.calls), 1)

    def test_context_and_store_refuse_malformed_snapshot_and_implicit_scope_changes(self):
        self.scope()
        response = self.send('a kite', 1, scene=True)
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()['result']
        context = result['context']
        mutations = [lambda x: x['scene']['scores'].append(0),
                     lambda x: x['scene'].__setitem__('scores', [True, 0]),
                     lambda x: x['scene'].__setitem__('scores', [float('nan'), 0]),
                     lambda x: x['scene'].__setitem__('scores', [1.1, 0]),
                     lambda x: x['scene'].__setitem__('query', 'x'*513),
                     lambda x: x['scene']['scope'].__setitem__('search_version', 4),
                     lambda x: x['scene']['scope'].__setitem__('library_id', 'family-b'),
                     lambda x: x['filters'].pop('people'),
                     lambda x: x.__setitem__('visible_ids', ['103', '103'])]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                changed = deepcopy(context)
                mutate(changed)
                with self.assertRaises(ValueError):
                    context_value(changed, 'family-a')
        summary = {k: v for k, v in result.items() if k not in ('items', 'interpretation', 'semantic')}
        self.assertEqual(_result_summary(summary, 'family-a')['version'], 4)
        for extra in ({'effect': {'type': 'open_asset', 'asset_id': '103'}, 'kind': 'open'},
                      {'version': 3}, {'kind': 'clarification'}):
            with self.assertRaises(ValueError):
                _result_summary(summary | extra, 'family-a')
        scope = deepcopy(context['scene']['scope'])
        scope['search_version'] = 3
        scope['filters']['descriptive'] = {'version': 1, 'concepts': []}
        with self.assertRaises(ValueError):
            _scope(scope, 'family-a')
        singleton = deepcopy(context['scene']['scope'])
        singleton.update(filters={}, visible_ids=['103'], total=1,
            fingerprint=d.assistant_asset_fingerprint(singleton['binding'], '103'))
        with self.assertRaises(ValueError):
            _scope(singleton, 'family-a')

