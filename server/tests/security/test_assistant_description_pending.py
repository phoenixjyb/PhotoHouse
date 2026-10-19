"""Quote-only description answers preserve an exact v3 result scope."""
from dataclasses import replace
from pathlib import Path
import sys
import unittest
import uuid

SERVER = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(SERVER / 'backend'), str(SERVER / 'tests/security')]

from app.access.assistant_workspace_store import _result_summary, initialize_v2
from app.access.search_pending import PENDING_TTL_SECONDS, description_context_digest
from phone_discovery_fixture import NOW, TOKEN
import test_assistant_intent_search as intent_fixture


class AssistantDescriptionPendingTests(unittest.TestCase):
    connection = intent_fixture.AssistantIntentSearchTests.connection
    mutate = intent_fixture.AssistantIntentSearchTests.mutate
    install = intent_fixture.AssistantIntentSearchTests.install

    def setUp(self):
        intent_fixture.AssistantIntentSearchTests.setUp(self)
        self.now = [NOW]
        self.access = replace(self.access, clock=lambda: self.now[0])
        self.install(self.index)
        self.store = initialize_v2(self.database.parent.resolve() / 'description-pending.sqlite',
                                   clock=lambda: self.now[0])
        self.app.state.assistant_workspace_store = self.store
        self.app.state.assistant_workspace_healthy = True
        self.base = '/assistant/workspace/v1'
        self.headers = {'Authorization': 'Bearer ' + TOKEN,
                        'X-PhotoHouse-Search-Version': '3'}
        self.thread = self.new_thread()

    def new_thread(self):
        response = self.client.post(self.base + '/threads', json={'library_id': 'family-a'},
                                    headers={'Authorization': self.headers['Authorization']})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()['thread']['thread_id']

    def send(self, words, revision, *, thread=None, rid=None):
        return self.client.post(f'{self.base}/threads/{thread or self.thread}/turns',
            headers=self.headers,
            json={'library_id': 'family-a', 'request_id': rid or str(uuid.uuid4()),
                  'expected_revision': revision, 'text': words})

    def search_and_ask(self):
        initial = self.send('find photos of Sample Child in September 2032 playing in snow', 0)
        self.assertEqual(initial.status_code, 200, initial.text)
        prior = initial.json()['result']
        self.assertEqual(prior['kind'], 'results', prior)
        self.assertEqual(prior['version'], 3)
        self.assertTrue(prior['context']['visible_ids'])
        self.planner.calls.clear()
        asked = self.send('more moments', 1)
        self.assertEqual(asked.status_code, 200, asked.text)
        self.assertEqual(asked.json()['result']['kind'], 'clarification')
        self.assertEqual(asked.json()['result']['context'], prior['context'])
        self.assertEqual(asked.json()['result']['filters'], prior['filters'])
        self.assertEqual(len(self.planner.calls), 1)
        self.assertNotIn('pending_intent', asked.text)
        pending = self.store.get_turn('one', 'family-a', self.thread,
                                      asked.json()['request_id'])['result_summary']['pending_intent']
        self.assertEqual(pending['question'], 'description')
        self.assertEqual(pending['query'], 'more moments')
        self.assertEqual(pending['binding'], prior['context']['binding'])
        self.assertEqual(pending['context_digest'], description_context_digest(prior['context']))
        return prior, asked, pending

    def test_quote_answer_adds_one_clue_and_keeps_all_original_filters(self):
        prior, _asked, pending = self.search_and_ask()
        self.planner.concepts['red coat'] = ['red coat', '红外套']
        self.planner.calls.clear()
        response = self.send('“red coat”', 2)
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()['result']
        self.assertEqual(result['kind'], 'results', result)
        self.assertEqual(result['filters']['people'], prior['filters']['people'])
        self.assertEqual(result['filters']['date'], prior['filters']['date'])
        self.assertEqual(result['filters']['media'], prior['filters']['media'])
        concepts = result['filters']['descriptive']['concepts']
        prior_surfaces = [item['surface'] for item in prior['filters']['descriptive']['concepts']]
        self.assertEqual([item['surface'] for item in concepts[:-1]], prior_surfaces)
        self.assertEqual(concepts[-1]['surface'], 'red coat')
        self.assertEqual(len(self.planner.calls), 1)
        self.assertNotIn('pending_intent', response.text)
        history = self.client.get(f'{self.base}/threads/{self.thread}?library_id=family-a',
                                  headers={'Authorization': self.headers['Authorization']})
        self.assertEqual(history.status_code, 200, history.text)
        self.assertEqual([row['input_text'] for row in history.json()['exchanges']],
                         ['find photos of Sample Child in September 2032 playing in snow',
                          'more moments', '“red coat”'])
        self.assertNotIn('pending_intent', history.text)
        recovered = self.client.get(
            f'{self.base}/threads/{self.thread}/requests/{response.json()["request_id"]}?library_id=family-a',
            headers=self.headers)
        self.assertEqual(recovered.status_code, 200, recovered.text)
        self.assertTrue(recovered.json()['recovered'])
        self.assertEqual(recovered.json()['result'], result)
        self.assertEqual(len(self.planner.calls), 1)

    def test_invalid_answers_keep_exact_pending_and_do_not_change_scope(self):
        prior, _asked, pending = self.search_and_ask()
        self.planner.calls.clear()
        stale = self.send('“red coat”', 1)
        self.assertEqual(stale.status_code, 409, stale.text)
        for answer in ('red coat', '"red coat" and September 2032', '“share all photos”',
                       '“Sample Child”', '“September 2032”'):
            with self.subTest(answer=answer):
                revision = self.store.get_thread('one', 'family-a', self.thread)['thread']['revision']
                response = self.send(answer, revision)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()['result']['kind'], 'clarification')
                self.assertIn('context', response.json()['result'])
                self.assertIsNone(response.json()['result']['effect'])
                stored = self.store.get_turn('one', 'family-a', self.thread,
                    response.json()['request_id'])['result_summary']['pending_intent']
                self.assertEqual(stored, pending)
        self.assertEqual(self.planner.calls, [])

        summary = dict(version=3, kind='clarification', reply='Please add one clue.',
                       context=prior['context'], filters=prior['filters'],
                       total=prior['total'], has_more=prior['has_more'], effect=None,
                       pending_intent={**pending, 'context_digest': '0' * 64})
        with self.assertRaises(ValueError):
            _result_summary(summary, 'family-a')

    def test_expiry_and_new_search_clear_pending_without_reinterpreting_answer(self):
        _prior, _asked, pending = self.search_and_ask()
        self.planner.calls.clear()
        self.now[0] += PENDING_TTL_SECONDS + 1
        expired = self.send('“red coat”', 2)
        self.assertEqual(expired.status_code, 200, expired.text)
        self.assertEqual(expired.json()['result']['kind'], 'clarification')
        self.assertIsNone(self.store.get_turn('one', 'family-a', self.thread,
            expired.json()['request_id'])['result_summary'].get('pending_intent'))
        self.assertEqual(self.planner.calls, [])

        thread = self.new_thread()
        first = self.send('find photos of Sample Child in September 2032 playing in snow', 0,
                          thread=thread)
        self.assertEqual(first.status_code, 200, first.text)
        self.planner.calls.clear()
        ask = self.send('more moments', 1, thread=thread)
        self.assertEqual(ask.status_code, 200, ask.text)
        self.assertIn('pending_intent', self.store.get_turn('one', 'family-a', thread,
            ask.json()['request_id'])['result_summary'])
        new_search = self.send('find photos of Sample Child in September 2032 red coat', 2,
                               thread=thread)
        self.assertEqual(new_search.status_code, 200, new_search.text)
        summary = self.store.get_turn('one', 'family-a', thread,
                                      new_search.json()['request_id'])['result_summary']
        self.assertNotIn('pending_intent', summary)

    def test_foreign_thread_cannot_resume_another_threads_pending_question(self):
        self.search_and_ask()
        foreign = self.new_thread()
        request = self.store.begin_turn('one', 'family-a', foreign, str(uuid.uuid4()),
                                        0, '“red coat”')
        self.assertNotIn('pending_intent', request)

    def test_source_change_withholds_pending_answer_before_planning(self):
        self.search_and_ask()
        self.planner.calls.clear()
        self.mutate("UPDATE captions SET text='changed source after clarification' WHERE id=1")
        response = self.send('“red coat”', 2)
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(self.planner.calls, [])
        self.assertNotIn('red coat', response.text)

    def test_revoked_membership_withholds_pending_answer_before_planning(self):
        self.search_and_ask()
        self.planner.calls.clear()
        self.mutate("UPDATE access_memberships SET status='revoked' WHERE account_id='one'")
        response = self.send('“red coat”', 2)
        self.assertEqual(response.status_code, 401, response.text)
        self.assertEqual(self.planner.calls, [])
        self.assertNotIn('red coat', response.text)

    def test_planner_outage_keeps_exact_pending_and_filters(self):
        prior, _asked, pending = self.search_and_ask()
        self.planner.failure = True
        response = self.send('“red coat”', 2)
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()['result']
        self.assertEqual(result['kind'], 'clarification')
        self.assertEqual(result['filters'], prior['filters'])
        stored = self.store.get_turn('one', 'family-a', self.thread,
            response.json()['request_id'])['result_summary']['pending_intent']
        self.assertEqual(stored, pending)


if __name__ == '__main__':
    unittest.main()
