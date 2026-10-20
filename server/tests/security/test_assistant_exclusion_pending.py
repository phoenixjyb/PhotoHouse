"""Durable continuity for bounded v2/v3 exclusion clarifications."""
from dataclasses import replace
from pathlib import Path
import sys
import unittest
import uuid
from unittest.mock import patch

SERVER = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(SERVER / 'backend'), str(SERVER / 'tests/security')]

from app.access.assistant_workspace_store import _result_summary, initialize_v2
from app.access.search_pending import PENDING_TTL_SECONDS
from phone_discovery_fixture import NOW, TOKEN
import test_assistant_intent_search as intent_fixture


class AssistantExclusionPendingTests(unittest.TestCase):
    connection = intent_fixture.AssistantIntentSearchTests.connection
    mutate = intent_fixture.AssistantIntentSearchTests.mutate
    install = intent_fixture.AssistantIntentSearchTests.install

    def setUp(self):
        intent_fixture.AssistantIntentSearchTests.setUp(self)
        self.now = [NOW]
        self.access = replace(self.access, clock=lambda: self.now[0])
        self.install(self.index)
        self.store = initialize_v2(self.database.parent.resolve() / 'exclusion-pending.sqlite',
                                   clock=lambda: self.now[0])
        self.app.state.assistant_workspace_store = self.store
        self.app.state.assistant_workspace_healthy = True
        self.base = '/assistant/workspace/v1'
        self.headers = {'Authorization': 'Bearer ' + TOKEN,
                        'X-PhotoHouse-Search-Version': '3'}
        response = self.client.post(self.base + '/threads', json={'library_id': 'family-a'},
                                    headers={'Authorization': self.headers['Authorization']})
        self.assertEqual(response.status_code, 201, response.text)
        self.thread = response.json()['thread']['thread_id']

    def send(self, words, revision, *, rid=None):
        return self.client.post(f'{self.base}/threads/{self.thread}/turns',
            headers=self.headers,
            json={'library_id': 'family-a', 'request_id': rid or str(uuid.uuid4()),
                  'expected_revision': revision, 'text': words})

    def ask(self):
        searched = self.send('find photos of Sample Child in September 2032', 0)
        self.assertEqual(searched.status_code, 200, searched.text)
        prior = searched.json()['result']
        self.assertEqual(prior['kind'], 'results', prior)
        original = 'find photos of a dog that is not on grass'
        reply = {'version': 3, 'kind': 'clarification',
                 'reply': 'Please clarify the excluded condition.',
                 'context': prior['context'], 'filters': prior['filters'],
                 'items': [], 'total': prior['total'],
                 'has_more': prior['has_more'], 'effect': None}

        def planned(*args, **kwargs):
            kwargs['planner_outcome'].update(status='clarification',
                                             reason='unsupported_negation',
                                             binding=prior['context']['binding'])
            return {**reply, 'items': prior['items']}

        with patch('app.access.assistant._turn', side_effect=planned) as ordinary_turn:
            asked = self.send(original, 1)
        self.assertEqual(asked.status_code, 200, asked.text)
        ordinary_turn.assert_called_once()
        public = asked.json()['result']
        self.assertEqual(public['kind'], 'clarification')
        self.assertEqual(public['context'], prior['context'])
        self.assertEqual(public['filters'], prior['filters'])
        self.assertNotIn('pending_intent', asked.text)
        request_id = asked.json()['request_id']
        stored = self.store.get_turn('one', 'family-a', self.thread,
                                     request_id)['result_summary']['pending_intent']
        self.assertEqual(stored['question'], 'exclusion')
        self.assertEqual(stored['query'], original)
        self.assertEqual(stored['binding'], prior['context']['binding'])
        return prior, asked, stored

    def test_private_pending_survives_get_replay_and_short_answers_without_planning(self):
        prior, asked, pending = self.ask()
        request_id = asked.json()['request_id']
        recovered = self.client.get(
            f'{self.base}/threads/{self.thread}/requests/{request_id}?library_id=family-a',
            headers=self.headers)
        self.assertEqual(recovered.status_code, 200, recovered.text)
        self.assertEqual(recovered.json()['result']['kind'], 'clarification')
        self.assertNotIn('pending_intent', recovered.text)

        self.planner.calls.clear()
        before = self.store.get_thread('one', 'family-a', self.thread)['thread']['revision']
        followup = self.send('red coats', before)
        self.assertEqual(followup.status_code, 200, followup.text)
        result = followup.json()['result']
        self.assertEqual(result['kind'], 'clarification')
        self.assertEqual(result['context'], prior['context'])
        self.assertEqual(result['filters'], prior['filters'])
        self.assertTrue(result['items'])
        self.assertTrue(result['reply'])
        next_pending = self.store.get_turn('one', 'family-a', self.thread,
            followup.json()['request_id'])['result_summary']['pending_intent']
        self.assertEqual(next_pending, pending)
        self.assertEqual(self.planner.calls, [])

    def test_private_pending_schema_is_durable_but_absent_from_get_and_history(self):
        _prior, asked, pending = self.ask()
        request_id = asked.json()['request_id']
        stored = self.store.get_turn('one', 'family-a', self.thread, request_id)
        self.assertEqual(stored['result_summary']['pending_intent'], pending)
        recovered = self.client.get(
            f'{self.base}/threads/{self.thread}/requests/{request_id}?library_id=family-a',
            headers=self.headers)
        self.assertEqual(recovered.status_code, 200, recovered.text)
        self.assertNotIn('pending_intent', recovered.text)
        history = self.client.get(f'{self.base}/threads/{self.thread}?library_id=family-a',
            headers={'Authorization': self.headers['Authorization']})
        self.assertEqual(history.status_code, 200, history.text)
        self.assertNotIn('pending_intent', history.text)

    def test_store_rejects_exclusion_pending_scope_or_summary_mutations(self):
        prior, asked, pending = self.ask()
        summary = self.store.get_turn('one', 'family-a', self.thread,
            asked.json()['request_id'])['result_summary']
        self.assertEqual(_result_summary(summary, 'family-a')['pending_intent'], pending)
        changes = (
            {'version': 4},
            {'kind': 'results'},
            {'pending_intent': {**pending, 'binding': 'f' * 64}},
            {'pending_intent': {**pending, 'context_digest': '0' * 64}},
            {'context': {**prior['context'], 'fingerprint': 'd' * 64}},
        )
        for change in changes:
            with self.subTest(change=change):
                with self.assertRaises(ValueError):
                    _result_summary({**summary, **change}, 'family-a')

    def test_real_v2_and_v3_negation_plans_create_pending_without_intent_model(self):
        for version in ('2', '3'):
            with self.subTest(version=version):
                response = self.client.post(self.base + '/threads',
                    json={'library_id': 'family-a'},
                    headers={'Authorization': self.headers['Authorization']})
                thread = response.json()['thread']['thread_id']
                self.planner.calls.clear()
                original = 'find photos of a dog that is not on grass'
                result = self.client.post(f'{self.base}/threads/{thread}/turns',
                    headers={'Authorization': self.headers['Authorization'],
                             'X-PhotoHouse-Search-Version': version},
                    json={'library_id': 'family-a', 'request_id': str(uuid.uuid4()),
                          'expected_revision': 0, 'text': original})
                self.assertEqual(result.status_code, 200, result.text)
                self.assertEqual(result.json()['result']['kind'], 'clarification')
                self.assertEqual(result.json()['result']['context'], None)
                self.assertIn('exclusion', result.json()['result']['reply'].lower())
                stored = self.store.get_turn('one', 'family-a', thread,
                    result.json()['request_id'])['result_summary']['pending_intent']
                self.assertEqual(stored['query'], original)
                self.assertEqual(stored['question'], 'exclusion')
                self.assertEqual(self.planner.calls, [])

    def test_expiry_keeps_guard_until_a_complete_new_search(self):
        _prior, _asked, pending = self.ask()
        self.now[0] += PENDING_TTL_SECONDS + 1
        self.planner.calls.clear()
        expired = self.send('red coats', 2)
        self.assertEqual(expired.status_code, 200, expired.text)
        self.assertEqual(expired.json()['result']['kind'], 'clarification')
        self.assertIn('complete', expired.json()['result']['reply'].lower())
        carried = self.store.get_turn('one', 'family-a', self.thread,
            expired.json()['request_id'])['result_summary']['pending_intent']
        self.assertEqual(carried, pending)
        self.assertEqual(self.planner.calls, [])

        fresh = self.send('find photos of Sample Child in September 2032', 3)
        self.assertEqual(fresh.status_code, 200, fresh.text)
        summary = self.store.get_turn('one', 'family-a', self.thread,
                                      fresh.json()['request_id'])['result_summary']
        self.assertNotIn('pending_intent', summary)

    def test_pending_short_answer_refuses_changed_source(self):
        self.ask()
        self.planner.calls.clear()
        self.mutate("UPDATE captions SET text='changed after exclusion clarification' WHERE id=1")
        stale = self.send('red coats', 2)
        self.assertEqual(stale.status_code, 409, stale.text)
        self.assertEqual(self.planner.calls, [])

    def test_pending_short_answer_refuses_revoked_membership(self):
        self.ask()
        self.planner.calls.clear()
        self.mutate("UPDATE access_memberships SET status='revoked' WHERE account_id='one'")
        denied = self.send('red coats', 2)
        self.assertEqual(denied.status_code, 401, denied.text)
        self.assertNotIn('red coats', denied.text)
        self.assertEqual(self.planner.calls, [])


if __name__ == '__main__':
    unittest.main()
