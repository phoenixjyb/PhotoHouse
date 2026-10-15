"""Generated protected conversations retain an unresolved date request."""
from dataclasses import replace
import unittest
import uuid

from app.access.assistant_workspace_store import initialize_v2
from phone_discovery_fixture import NOW, TOKEN, OTHER, SECOND, RELOGIN
import test_assistant_intent_search as intent_fixture


class AssistantPendingIntentTests(unittest.TestCase):
    connection = intent_fixture.AssistantIntentSearchTests.connection
    mutate = intent_fixture.AssistantIntentSearchTests.mutate
    install = intent_fixture.AssistantIntentSearchTests.install

    def setUp(self):
        intent_fixture.AssistantIntentSearchTests.setUp(self)
        self.now = [NOW]
        self.access = replace(self.access, clock=lambda: self.now[0])
        self.install(self.index)
        self.store = initialize_v2(self.database.parent.resolve() / 'pending-workspace.sqlite',
                                   clock=lambda: self.now[0])
        self.app.state.assistant_workspace_store = self.store
        self.app.state.assistant_workspace_healthy = True
        self.base = '/assistant/workspace/v1'
        self.headers = {'Authorization': 'Bearer ' + TOKEN, 'X-PhotoHouse-Search-Version': '3'}
        self.thread = self.new_thread()

    def new_thread(self):
        response = self.client.post(self.base + '/threads', json={'library_id': 'family-a'},
                                    headers={'Authorization': self.headers['Authorization']})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()['thread']['thread_id']

    def send(self, words, revision=0, *, thread=None, rid=None, headers=None):
        return self.client.post(f'{self.base}/threads/{thread or self.thread}/turns',
            headers=headers or self.headers,
            json={'library_id': 'family-a', 'request_id': rid or str(uuid.uuid4()),
                  'expected_revision': revision, 'text': words})

    def ask(self, words='find photos of Sample Child from childhood playing in snow red coat'):
        response = self.send(words)
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()['result']
        self.assertEqual((result['version'], result['kind']), (3, 'clarification'))
        self.assertIsNone(result['context'])
        self.assertNotIn('pending_intent', response.text)
        self.assertEqual(self.planner.calls, [])
        return response.json()

    def test_short_date_answer_retains_bilingual_request_and_original_inputs(self):
        queries = ('find photos of Sample Child from childhood playing in snow red coat',
                   '找示例儿童小时候玩雪红外套的照片',
                   'find示例儿童小时候playing in snow red coat的photos')
        for query in queries:
            with self.subTest(query=query):
                self.thread = self.new_thread()
                self.planner.calls.clear()
                asked = self.ask(query)
                response = self.send('September 2032', 1)
                self.assertEqual(response.status_code, 200, response.text)
                result = response.json()['result']
                self.assertEqual(result['kind'], 'results', result)
                self.assertEqual({item['id'] for item in result['items']}, {'101', '103'})
                self.assertEqual(result['filters']['people'], {'ids': ['301'], 'match': 'any'})
                self.assertEqual(result['filters']['media'], ['image'])
                self.assertEqual(result['filters']['date'], {'from': '2032-09-01', 'to': '2032-09-30'})
                self.assertEqual(len(result['filters']['descriptive']['concepts']), 2)
                self.assertEqual(len(self.planner.calls), 1)
                self.assertNotIn('September 2032', self.planner.calls[0][0])
                history = self.client.get(f'{self.base}/threads/{self.thread}?library_id=family-a',
                    headers={'Authorization': self.headers['Authorization']})
                self.assertEqual(history.status_code, 200, history.text)
                self.assertEqual([row['input_text'] for row in history.json()['exchanges']],
                                 [query, 'September 2032'])
                self.assertNotIn('pending_intent', history.text)
                readback = self.client.get(
                    f'{self.base}/threads/{self.thread}/requests/{asked["request_id"]}?library_id=family-a',
                    headers=self.headers)
                self.assertEqual(readback.status_code, 200, readback.text)
                self.assertNotIn('pending_intent', readback.text)

    def test_invalid_answer_keeps_the_original_question_without_extending_expiry(self):
        asked = self.ask()
        original = self.store.get_turn('one', 'family-a', self.thread,
                                       asked['request_id'])['result_summary']['pending_intent']
        self.now[0] += 10
        invalid = self.send('2018 and share everything', 1)
        self.assertEqual(invalid.status_code, 200, invalid.text)
        self.assertEqual(invalid.json()['result']['kind'], 'clarification')
        carried = self.store.get_turn('one', 'family-a', self.thread,
            invalid.json()['request_id'])['result_summary']['pending_intent']
        self.assertEqual(carried, original)
        valid = self.send('2032年9月', 2)
        self.assertEqual(valid.status_code, 200, valid.text)
        self.assertEqual(valid.json()['result']['kind'], 'results')
        self.assertEqual(len(self.planner.calls), 1)

    def test_request_recovery_replays_the_resolved_search_without_planning_again(self):
        self.ask()
        rid = str(uuid.uuid4())
        first = self.send('September 2032', 1, rid=rid)
        self.assertEqual(first.status_code, 200, first.text)
        calls = len(self.planner.calls)
        self.planner.failure = True
        replay = self.send('September 2032', 1, rid=rid)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertTrue(replay.json()['recovered'])
        self.assertEqual(replay.json()['result'], first.json()['result'])
        self.assertEqual(len(self.planner.calls), calls)

    def test_provider_outage_can_retry_the_same_answer_and_source_edit_during_planning_withholds(self):
        self.ask()
        self.planner.failure = True
        unavailable = self.send('September 2032', 1)
        self.assertEqual(unavailable.status_code, 200, unavailable.text)
        self.assertEqual(unavailable.json()['result']['kind'], 'clarification')
        saved = self.store.get_turn('one', 'family-a', self.thread,
            unavailable.json()['request_id'])['result_summary']
        self.assertIn('pending_intent', saved)
        self.planner.failure = False
        recovered = self.send('September 2032', 2)
        self.assertEqual(recovered.status_code, 200, recovered.text)
        self.assertEqual(recovered.json()['result']['kind'], 'results')
        self.assertEqual(len(self.planner.calls), 2)

        self.thread = self.new_thread()
        self.planner.calls.clear()
        self.ask()
        self.planner.before_reply = lambda: self.mutate(
            "UPDATE captions SET text='new evidence during the generated proposal' WHERE id=1")
        changed = self.send('September 2032', 1)
        self.assertEqual(changed.status_code, 409, changed.text)
        self.assertNotIn('items', changed.json())

    def test_expiry_explains_instead_of_reinterpreting_a_short_answer_as_a_broader_search(self):
        self.ask()
        self.now[0] += 901
        response = self.send('September 2032', 1)
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()['result']
        self.assertEqual(result['kind'], 'clarification')
        self.assertIn('expired', result['reply'])
        self.assertIsNone(result['context'])
        self.assertEqual(self.planner.calls, [])

    def test_source_session_membership_and_thread_changes_cannot_resume_old_request(self):
        self.ask()
        other = self.send('September 2032', 1,
            headers={**self.headers, 'Authorization': 'Bearer ' + OTHER})
        self.assertIn(other.status_code, (401, 403))
        other_account = self.send('September 2032', 1,
            headers={**self.headers, 'Authorization': 'Bearer ' + SECOND})
        self.assertEqual(other_account.status_code, 404, other_account.text)
        session = self.send('September 2032', 1,
            headers={**self.headers, 'Authorization': 'Bearer ' + RELOGIN})
        self.assertEqual(session.status_code, 409, session.text)
        self.assertEqual(self.planner.calls, [])
        another_thread = self.new_thread()
        fresh = self.send('September 2032', thread=another_thread)
        self.assertEqual(fresh.status_code, 200, fresh.text)
        self.assertEqual(fresh.json()['result']['kind'], 'clarification')
        self.assertIsNone(fresh.json()['result']['context'])
        self.mutate("UPDATE access_stories SET text='changed synthetic evidence' WHERE id='note-101'")
        changed = self.send('September 2032', 1)
        self.assertEqual(changed.status_code, 409, changed.text)
        self.assertEqual(self.planner.calls, [])
        independent = self.send('find photos of Sample Adult', 1)
        self.assertEqual(independent.status_code, 200, independent.text)
        self.assertEqual(independent.json()['result']['filters'],
                         {'media': ['image'], 'people': {'ids': ['302'], 'match': 'any'}})

    def test_quoted_time_phrase_is_literal_and_v2_does_not_create_pending_state(self):
        quoted = self.send('find photos containing "childhood"')
        self.assertEqual(quoted.status_code, 200, quoted.text)
        self.assertEqual(quoted.json()['result']['filters']['text'], 'childhood')
        v2 = self.send('find photos from childhood', thread=self.new_thread(),
                       headers={**self.headers, 'X-PhotoHouse-Search-Version': '2'})
        self.assertEqual(v2.status_code, 200, v2.text)
        self.assertEqual(v2.json()['result']['version'], 2)
        self.assertNotIn('pending_intent', self.store.get_turn('one', 'family-a',
            v2.json()['thread_id'], v2.json()['request_id'])['result_summary'])
