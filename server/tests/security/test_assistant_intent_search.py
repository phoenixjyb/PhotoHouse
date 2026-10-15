"""Protected intent-to-evidence conversations over generated records only."""
from contextlib import closing
import sqlite3
import unittest
import uuid

from fastapi.testclient import TestClient

from app.access.assistant_workspace_store import initialize_v2
from app.access.discovery_provider import MemoryIndexProvider
from app.access.search_intent import IntentUnavailable
from app.access.service import AccessService
from app.main import create_app
from phone_discovery_fixture import NOW, TOKEN, OTHER, reviewed
import test_assistant_joint_search as joint_fixture

ORIGIN = joint_fixture.ORIGIN


class FixturePlanner:
    def __init__(self):
        self.calls = []
        self.before_reply = lambda: None
        self.failure = False
        self.concepts = {
            'playing in snow': ['playing in snow', '在雪地玩'],
            '玩雪': ['playing in snow', '在雪地玩'],
            'red coat': ['red coat', '红外套'],
            '红外套': ['red coat', '红外套'],
        }

    def propose(self, query, today, has_previous_search):
        self.calls.append((query, today, has_previous_search))
        self.before_reply()
        if self.failure:
            raise IntentUnavailable()
        concepts = []
        for surface, alternatives in self.concepts.items():
            start = query.find(surface)
            if start >= 0:
                concepts.append({'start': start, 'end': start + len(surface),
                                 'alternatives': alternatives})
        if not concepts:
            return {'version': 1, 'status': 'clarification', 'concepts': [], 'question': 'description'}
        return {'version': 1, 'status': 'ready',
                'concepts': sorted(concepts, key=lambda item: item['start']), 'question': None}


class AssistantIntentSearchTests(unittest.TestCase):
    connection = joint_fixture.AssistantJointSearchTests.connection
    mutate = joint_fixture.AssistantJointSearchTests.mutate
    turn = joint_fixture.AssistantJointSearchTests.turn

    def setUp(self):
        self.planner = FixturePlanner()
        joint_fixture.AssistantJointSearchTests.setUp(self)
        self.mutate("UPDATE captions SET text='A child playing in snow wearing a red coat' WHERE id=1")
        self.mutate("UPDATE captions SET text='示例儿童穿红外套在雪地玩' WHERE id=2")
        with closing(sqlite3.connect(self.database)) as db:
            db.execute('PRAGMA foreign_keys=ON')
            index = reviewed(AccessService(db, clock=lambda: NOW))
        self.install(index)

    def install(self, index):
        joint_fixture.AssistantJointSearchTests.install(self, index)
        self.app.state.assistant_intent_planner = self.planner

    def intent(self, words, context=None, token=TOKEN):
        return self.client.post('/assistant/v1/turns',
            json={'library_id': 'family-a', 'text': words, 'context': context},
            headers={'Authorization': 'Bearer ' + token, 'X-PhotoHouse-Search-Version': '3'})

    def test_bilingual_concepts_retrieve_current_evidence_under_all_hard_filters(self):
        for query in ('find photos of Sample Child playing in snow red coat in September 2032',
                      '找示例儿童2032年9月玩雪红外套的照片',
                      'find示例儿童2032年9月玩雪red coat的photos'):
            with self.subTest(query=query):
                response = self.intent(query)
                self.assertEqual(response.status_code, 200, response.text)
                result = response.json()
                self.assertEqual((result['version'], result['kind']), (3, 'results'), result)
                self.assertEqual(result['context']['search_version'], 3)
                self.assertEqual(result['filters']['people'], {'ids': ['301'], 'match': 'any'})
                self.assertEqual(result['filters']['media'], ['image'])
                self.assertEqual(result['filters']['date'], {'from': '2032-09-01', 'to': '2032-09-30'})
                self.assertEqual({item['id'] for item in result['items']}, {'101', '103'})
                self.assertEqual(len(result['filters']['descriptive']['concepts']), 2)
                self.assertIsNone(result['effect'])
                self.assertNotIn('Foreign', str(result))

    def test_description_alone_is_a_readonly_search_and_quotes_remain_an_independent_literal(self):
        found = self.intent('playing in snow red coat').json()
        self.assertEqual(found['kind'], 'results', found)
        self.assertEqual({item['id'] for item in found['items']}, {'101', '103'})
        literal = self.intent('find photos playing in snow red coat containing "secret memory phrase"').json()
        self.assertEqual(literal['kind'], 'results', literal)
        self.assertEqual(literal['filters']['text'], 'secret memory phrase')
        self.assertEqual([item['id'] for item in literal['items']], ['101'])
        calls = len(self.planner.calls)
        refined = self.intent('September 2032', literal['context']).json()
        self.assertEqual(refined['kind'], 'results', refined)
        self.assertEqual(refined['filters']['text'], literal['filters']['text'])
        self.assertEqual(refined['filters']['descriptive'], literal['filters']['descriptive'])
        self.assertEqual(len(self.planner.calls), calls)

    def test_negated_scene_evidence_is_excluded_while_quoted_text_remains_literal(self):
        self.mutate("UPDATE captions SET text='Not playing in snow wearing a red coat.' WHERE id=1")
        self.mutate("UPDATE captions SET text='没有在雪地玩，也没穿红外套。' WHERE id=2")
        with closing(sqlite3.connect(self.database)) as db:
            db.execute('PRAGMA foreign_keys=ON')
            index = reviewed(AccessService(db, clock=lambda: NOW))
        self.install(index)
        scene = self.intent('find photos of Sample Child playing in snow red coat in September 2032')
        self.assertEqual(scene.status_code, 200, scene.text)
        self.assertEqual(scene.json()['kind'], 'results')
        self.assertEqual(scene.json()['items'], [])
        self.assertEqual(scene.json()['total'], 0)
        literal = self.intent('find photos containing "Not playing in snow"')
        self.assertEqual(literal.status_code, 200, literal.text)
        self.assertEqual([item['id'] for item in literal.json()['items']], ['101'])
        self.assertIsNone(literal.json()['effect'])

    def test_model_cannot_consume_reviewed_names_dates_media_or_unknown_residue(self):
        for surface in ('Sample Child', 'September 2032', 'photos'):
            with self.subTest(surface=surface):
                self.planner.concepts = {surface: ['playing in snow']}
                result = self.intent('find photos of Sample Child in September 2032').json()
                # A complete deterministic query needs no model at all.
                self.assertEqual(result['kind'], 'results', result)
                self.assertEqual(self.planner.calls, [])
                result = self.intent('find photos of Sample Child in September 2032 unknown clue').json()
                self.assertEqual(result['kind'], 'clarification', result)
                self.assertIsNone(result['context'])
                self.assertEqual(result['items'], [])
                self.planner.calls.clear()
        self.planner.concepts = {'playing in snow': ['playing in snow']}
        result = self.intent('find photos playing in snow unfamiliar extra condition').json()
        self.assertEqual(result['kind'], 'clarification', result)
        self.assertEqual(result['items'], [])

    def test_provider_outage_keeps_scope_and_source_changes_during_planning_withhold_results(self):
        initial = self.intent('find photos in September 2032').json()
        self.assertEqual(initial['kind'], 'results', initial)
        self.planner.failure = True
        result = self.intent('red coat', initial['context']).json()
        self.assertEqual(result['kind'], 'clarification', result)
        self.assertEqual(result['context'], initial['context'])
        self.assertEqual(result['filters'], initial['filters'])
        self.planner.failure = False
        self.planner.before_reply = lambda: self.mutate("UPDATE captions SET text='changed synthetic source' WHERE id=1")
        changed = self.intent('playing in snow')
        self.assertEqual(changed.status_code, 409, changed.text)

    def test_membership_is_checked_before_provider_and_rechecked_after_it(self):
        denied = self.intent('playing in snow', token=OTHER)
        self.assertIn(denied.status_code, (401, 403))
        self.assertEqual(self.planner.calls, [])
        self.planner.before_reply = lambda: self.mutate(
            "UPDATE access_memberships SET status='revoked' WHERE account_id='one'")
        denied = self.intent('playing in snow')
        self.assertIn(denied.status_code, (401, 403))
        self.assertNotIn('playing in snow', denied.text)

    def test_v3_is_explicit_and_unconfigured_servers_keep_v2_available(self):
        self.app.state.assistant_intent_planner = None
        response = self.intent('playing in snow')
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(response.json()['error'], 'search_version_unsupported')
        legacy = self.turn('find photos').json()
        self.assertEqual(legacy['version'], 2)
        self.assertNotIn('descriptive', legacy['filters'])

    def test_conversational_openings_are_new_searches_and_do_not_require_a_model_for_hard_filters(self):
        for query in ('I am looking for photos of Sample Adult',
                      '  I’m looking for photos of Sample Adult',
                      'do we have photos of Sample Adult?', '我想看看示例成人的照片'):
            with self.subTest(query=query):
                result = self.intent(query).json()
                self.assertEqual(result['kind'], 'results', result)
                self.assertEqual(result['filters'], {'media': ['image'],
                                                     'people': {'ids': ['302'], 'match': 'any'}})
                self.assertEqual([item['id'] for item in result['items']], ['103'])
        self.assertEqual(self.planner.calls, [])

    def test_new_search_can_refresh_a_stale_snapshot_without_reusing_its_constraints(self):
        initial = self.intent('find photos of Sample Adult').json()
        self.assertEqual(initial['kind'], 'results', initial)
        # A current-text projection invalidates old result bindings, while a
        # fresh independent search can still read the authorized library.
        self.mutate("UPDATE access_stories SET text='new generated fixture note' WHERE id='note-101'")
        stale = self.intent('September 2032', initial['context'])
        self.assertEqual(stale.status_code, 409, stale.text)
        fresh = self.intent('find photos', initial['context'])
        self.assertEqual(fresh.status_code, 200, fresh.text)
        self.assertEqual(fresh.json()['filters'], {'media': ['image']})

    def test_saved_v3_turn_recovery_retains_plan_without_calling_the_model_again(self):
        store = initialize_v2(self.database.parent.resolve() / 'intent-workspace.sqlite', clock=lambda: NOW)
        self.app.state.assistant_workspace_store = store
        self.app.state.assistant_workspace_healthy = True
        headers = {'Authorization': 'Bearer ' + TOKEN, 'X-PhotoHouse-Search-Version': '3'}
        base = '/assistant/workspace/v1'
        caps = self.client.get(base + '/capabilities?library_id=family-a', headers=headers)
        self.assertEqual(caps.status_code, 200, caps.text)
        self.assertEqual(caps.json()['search']['version'], 3)
        thread = self.client.post(base + '/threads', json={'library_id': 'family-a'},
                                  headers={'Authorization': 'Bearer ' + TOKEN}).json()['thread']['thread_id']
        rid = str(uuid.uuid4())
        submitted = self.client.post(f'{base}/threads/{thread}/turns', headers=headers,
            json={'library_id': 'family-a', 'request_id': rid, 'expected_revision': 0,
                  'text': 'find photos playing in snow red coat'})
        self.assertEqual(submitted.status_code, 200, submitted.text)
        result = submitted.json()['result']
        self.assertEqual((result['version'], result['kind']), (3, 'results'), result)
        calls = len(self.planner.calls)
        self.planner.failure = True
        recovered = self.client.get(f'{base}/threads/{thread}/requests/{rid}?library_id=family-a', headers=headers)
        self.assertEqual(recovered.status_code, 200, recovered.text)
        self.assertEqual(recovered.json()['result'], result)
        self.assertEqual(len(self.planner.calls), calls)
        self.mutate("UPDATE captions SET text='changed synthetic source' WHERE id=1")
        stale = self.client.get(f'{base}/threads/{thread}/requests/{rid}?library_id=family-a', headers=headers)
        self.assertEqual(stale.status_code, 409, stale.text)

    def test_v3_readback_keeps_saved_v2_binding_and_protocol(self):
        store = initialize_v2(self.database.parent.resolve() / 'legacy-intent-workspace.sqlite', clock=lambda: NOW)
        self.app.state.assistant_workspace_store = store
        self.app.state.assistant_workspace_healthy = True
        base = '/assistant/workspace/v1'
        auth = {'Authorization': 'Bearer ' + TOKEN}
        thread = self.client.post(base + '/threads', json={'library_id': 'family-a'},
                                  headers=auth).json()['thread']['thread_id']
        rid = str(uuid.uuid4())
        response = self.client.post(f'{base}/threads/{thread}/turns',
            headers={**auth, 'X-PhotoHouse-Search-Version': '2'},
            json={'library_id': 'family-a', 'request_id': rid, 'expected_revision': 0,
                  'text': 'find photos of Sample Child in September 2032'})
        self.assertEqual(response.status_code, 200, response.text)
        original = response.json()['result']
        recovered = self.client.get(f'{base}/threads/{thread}/requests/{rid}?library_id=family-a',
                                    headers={**auth, 'X-PhotoHouse-Search-Version': '3'})
        self.assertEqual(recovered.status_code, 200, recovered.text)
        self.assertTrue(recovered.json()['recovered'])
        self.assertEqual(recovered.json()['result'], original)
        self.assertEqual(original['context']['search_version'], 2)
        self.assertEqual(self.planner.calls, [])

    def test_paired_scene_correction_retrieves_other_evidence_and_keeps_every_hard_filter(self):
        self.planner.concepts.update({'blue coat': ['blue coat', '蓝外套'],
                                      '蓝外套': ['blue coat', '蓝外套']})
        self.mutate("UPDATE captions SET text='示例儿童穿蓝外套在雪地玩' WHERE id=2")
        with closing(sqlite3.connect(self.database)) as db:
            db.execute('PRAGMA foreign_keys=ON')
            index = reviewed(AccessService(db, clock=lambda: NOW))
        self.install(index)
        for query, correction, old, new in (
            ('find photos of Sample Child in September 2032 playing in snow red coat containing "海边"',
             'not red coat, but blue coat', 'red coat', 'blue coat'),
            ('找示例儿童2032年9月玩雪红外套的照片包含"海边"',
             '不是红外套，是蓝外套', '红外套', '蓝外套'),
            ('find示例儿童2032年9月玩雪red coat的photos包含"海边"',
             '不是red coat，是蓝外套', 'red coat', '蓝外套'),
        ):
            with self.subTest(correction=correction):
                initial = self.intent(query).json()
                self.assertEqual(initial['kind'], 'results', initial)
                self.assertEqual([item['id'] for item in initial['items']], ['101'])
                calls = len(self.planner.calls)
                response = self.intent(correction, initial['context'])
                self.assertEqual(response.status_code, 200, response.text)
                result = response.json()
                self.assertEqual(result['kind'], 'results', result)
                self.assertEqual([item['id'] for item in result['items']], ['103'])
                self.assertEqual({k: v for k, v in result['filters'].items() if k != 'descriptive'},
                                 {k: v for k, v in initial['filters'].items() if k != 'descriptive'})
                before = initial['filters']['descriptive']['concepts']
                after = result['filters']['descriptive']['concepts']
                self.assertEqual(len(before), len(after))
                self.assertEqual([c for c in before if c['surface'] != old],
                                 [c for c in after if c['surface'] != new])
                self.assertEqual(len(self.planner.calls), calls + 1)
                self.assertEqual(self.planner.calls[-1][0], new)
                self.assertIsNone(result['effect'])

    def test_failed_scene_correction_preserves_scope_and_revalidates_authorization(self):
        self.planner.concepts['blue coat'] = ['blue coat', '蓝外套']
        initial = self.intent('find photos of Sample Child in September 2032 playing in snow red coat').json()
        self.assertEqual(initial['kind'], 'results', initial)
        self.planner.calls.clear()
        mismatch = self.intent('not green coat, but blue coat', initial['context']).json()
        self.assertEqual(mismatch['kind'], 'clarification', mismatch)
        self.assertEqual(mismatch['context'], initial['context'])
        self.assertEqual(mismatch['filters'], initial['filters'])
        self.assertEqual(self.planner.calls, [])
        self.planner.failure = True
        unavailable = self.intent('not red coat, but blue coat', initial['context']).json()
        self.assertEqual(unavailable['kind'], 'clarification', unavailable)
        self.assertEqual(unavailable['filters'], initial['filters'])
        self.assertEqual(unavailable['items'], initial['items'])
        self.assertEqual(len(self.planner.calls), 1)
        self.planner.failure = False
        calls = len(self.planner.calls)
        denied = self.intent('not red coat, but blue coat', initial['context'], token=OTHER)
        self.assertIn(denied.status_code, (401, 403))
        self.assertEqual(len(self.planner.calls), calls)
        self.planner.before_reply = lambda: self.mutate("UPDATE captions SET text='changed synthetic scene' WHERE id=1")
        changed = self.intent('not red coat, but blue coat', initial['context'])
        self.assertEqual(changed.status_code, 409, changed.text)
        self.assertNotIn('blue coat', changed.text)

    def test_explicit_clue_removal_repairs_empty_results_without_losing_hard_filters(self):
        self.planner.concepts['green coat'] = ['green coat', '绿外套']
        for removal in ('remove the "green coat" clue', '去掉“green coat”这条线索',
                        'please remove green coat clue', '请去掉green coat这条线索'):
            with self.subTest(removal=removal):
                initial = self.intent('find photos of Sample Child in September 2032 '
                                      'playing in snow green coat containing "海边"').json()
                self.assertEqual(initial['kind'], 'results', initial)
                self.assertEqual(initial['items'], [])
                self.assertEqual(initial['total'], 0)
                calls = len(self.planner.calls)
                self.planner.failure = True
                response = self.intent(removal, initial['context'])
                self.planner.failure = False
                self.assertEqual(response.status_code, 200, response.text)
                result = response.json()
                self.assertEqual(result['kind'], 'results', result)
                self.assertTrue(result['items'])
                self.assertEqual({key: value for key, value in result['filters'].items()
                                  if key != 'descriptive'},
                                 {key: value for key, value in initial['filters'].items()
                                  if key != 'descriptive'})
                self.assertEqual([c['surface'] for c in result['filters']['descriptive']['concepts']],
                                 ['playing in snow'])
                self.assertEqual(len(self.planner.calls), calls)
                self.assertIsNone(result['effect'])

    def test_clue_removal_refuses_unknown_targets_and_rechecks_current_access_and_source(self):
        initial = self.intent('find photos of Sample Child in September 2032 playing in snow red coat').json()
        self.assertEqual(initial['kind'], 'results', initial)
        calls = len(self.planner.calls)
        mismatch = self.intent('remove the "green coat" clue', initial['context']).json()
        self.assertEqual(mismatch['kind'], 'clarification', mismatch)
        self.assertEqual(mismatch['context'], initial['context'])
        self.assertEqual(mismatch['filters'], initial['filters'])
        self.assertEqual(mismatch['items'], initial['items'])
        denied = self.intent('remove the "red coat" clue', initial['context'], token=OTHER)
        self.assertIn(denied.status_code, (401, 403))
        self.mutate("UPDATE captions SET text='changed synthetic scene' WHERE id=1")
        changed = self.intent('remove the "red coat" clue', initial['context'])
        self.assertEqual(changed.status_code, 409, changed.text)
        self.assertEqual(len(self.planner.calls), calls)

    def test_saved_clue_removal_replays_without_model_call_or_duplicate_history(self):
        store = initialize_v2(self.database.parent.resolve() / 'clue-removal-workspace.sqlite', clock=lambda: NOW)
        self.app.state.assistant_workspace_store = store
        self.app.state.assistant_workspace_healthy = True
        headers = {'Authorization': 'Bearer ' + TOKEN, 'X-PhotoHouse-Search-Version': '3'}
        base = '/assistant/workspace/v1'
        thread = self.client.post(base + '/threads', json={'library_id': 'family-a'},
            headers={'Authorization': headers['Authorization']}).json()['thread']['thread_id']
        def send(words, revision, rid):
            return self.client.post(f'{base}/threads/{thread}/turns', headers=headers,
                json={'library_id': 'family-a', 'request_id': rid,
                      'expected_revision': revision, 'text': words})
        original_query = 'find photos of Sample Child in September 2032 playing in snow red coat'
        first = send(original_query, 0, str(uuid.uuid4()))
        self.assertEqual(first.status_code, 200, first.text)
        calls = len(self.planner.calls)
        self.planner.failure = True
        removal, rid = 'remove the "red coat" clue', str(uuid.uuid4())
        response = send(removal, 1, rid)
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()['result']
        self.assertEqual(result['kind'], 'results', result)
        self.assertEqual([c['surface'] for c in result['filters']['descriptive']['concepts']],
                         ['playing in snow'])
        recovered = send(removal, 1, rid)
        self.assertEqual(recovered.status_code, 200, recovered.text)
        self.assertTrue(recovered.json()['recovered'])
        self.assertEqual(recovered.json()['result'], result)
        self.assertEqual(len(self.planner.calls), calls)
        history = self.client.get(f'{base}/threads/{thread}?library_id=family-a',
            headers={'Authorization': headers['Authorization']})
        self.assertEqual(history.status_code, 200, history.text)
        self.assertEqual([row['input_text'] for row in history.json()['exchanges']],
                         [original_query, removal])

    def test_saved_scene_correction_replays_without_another_model_call(self):
        self.planner.concepts['blue coat'] = ['blue coat', '蓝外套']
        store = initialize_v2(self.database.parent.resolve() / 'correction-workspace.sqlite', clock=lambda: NOW)
        self.app.state.assistant_workspace_store = store
        self.app.state.assistant_workspace_healthy = True
        headers = {'Authorization': 'Bearer ' + TOKEN, 'X-PhotoHouse-Search-Version': '3'}
        base = '/assistant/workspace/v1'
        thread_response = self.client.post(base + '/threads', json={'library_id': 'family-a'},
            headers={'Authorization': headers['Authorization']})
        self.assertEqual(thread_response.status_code, 201, thread_response.text)
        thread = thread_response.json()['thread']['thread_id']
        def send(words, revision, rid):
            return self.client.post(f'{base}/threads/{thread}/turns', headers=headers,
                json={'library_id': 'family-a', 'request_id': rid,
                      'expected_revision': revision, 'text': words})
        original_query = 'find photos of Sample Child in September 2032 playing in snow red coat'
        first = send(original_query, 0, str(uuid.uuid4()))
        self.assertEqual(first.status_code, 200, first.text)
        correction = 'not red coat, but blue coat'
        rid = str(uuid.uuid4())
        response = send(correction, 1, rid)
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()['result']
        self.assertEqual(result['kind'], 'results', result)
        self.assertEqual(result['filters']['descriptive']['concepts'][-1]['surface'], 'blue coat')
        calls = len(self.planner.calls)
        self.planner.failure = True
        recovered = send(correction, 1, rid)
        self.assertEqual(recovered.status_code, 200, recovered.text)
        self.assertTrue(recovered.json()['recovered'])
        self.assertEqual(recovered.json()['result'], result)
        self.assertEqual(len(self.planner.calls), calls)
        history = self.client.get(f'{base}/threads/{thread}?library_id=family-a',
            headers={'Authorization': headers['Authorization']})
        self.assertEqual(history.status_code, 200, history.text)
        self.assertEqual([row['input_text'] for row in history.json()['exchanges']],
                         [original_query, correction])
