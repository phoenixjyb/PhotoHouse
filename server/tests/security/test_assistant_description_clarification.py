"""A vague scene clarification must preserve an existing result set."""
from dataclasses import replace
import unittest
import uuid

from app.access.assistant_workspace_store import initialize_v2
from phone_discovery_fixture import NOW, TOKEN
import test_assistant_intent_search as intent_fixture


class AssistantDescriptionClarificationTests(unittest.TestCase):
    connection = intent_fixture.AssistantIntentSearchTests.connection
    mutate = intent_fixture.AssistantIntentSearchTests.mutate
    install = intent_fixture.AssistantIntentSearchTests.install

    def setUp(self):
        intent_fixture.AssistantIntentSearchTests.setUp(self)
        self.now = [NOW]
        self.access = replace(self.access, clock=lambda: self.now[0])
        self.install(self.index)
        self.store = initialize_v2(self.database.parent.resolve() / 'description-workspace.sqlite',
                                   clock=lambda: self.now[0])
        self.app.state.assistant_workspace_store = self.store
        self.app.state.assistant_workspace_healthy = True
        self.base = '/assistant/workspace/v1'
        self.headers = {'Authorization': 'Bearer ' + TOKEN,
                        'X-PhotoHouse-Search-Version': '3'}

    def new_thread(self):
        response = self.client.post(self.base + '/threads', json={'library_id': 'family-a'},
                                    headers={'Authorization': self.headers['Authorization']})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()['thread']['thread_id']

    def send(self, thread, words, revision, request_id=None):
        return self.client.post(f'{self.base}/threads/{thread}/turns', headers=self.headers,
            json={'library_id': 'family-a', 'request_id': request_id or str(uuid.uuid4()),
                  'expected_revision': revision, 'text': words})

    def test_description_question_requests_a_complete_search_and_keeps_prior_results(self):
        cases = (
            ('more moments',
             'Please restate the complete search, including the scene, activity or object; '
             'include any person and capture date you want.'),
            ('更多时刻',
             '请重新说完整的查找条件，包括想找的场景、活动或物品；如果需要，也请写明人物和拍摄日期。'),
            ('more 更多moments',
             '请重新说完整的查找条件，包括想找的场景、活动或物品；如果需要，也请写明人物和拍摄日期。'),
        )
        expected_result_keys = {
            'version', 'kind', 'reply', 'context', 'filters', 'items', 'total',
            'has_more', 'effect', 'interpretation',
        }
        expected_envelope_keys = {
            'version', 'thread_id', 'request_id', 'status', 'revision',
            'recovered', 'error', 'result',
        }

        for refinement, expected_reply in cases:
            with self.subTest(refinement=refinement):
                thread = self.new_thread()
                initial_response = self.send(thread,
                    'find photos of Sample Child in September 2032', 0)
                self.assertEqual(initial_response.status_code, 200, initial_response.text)
                initial = initial_response.json()['result']
                self.assertEqual((initial['version'], initial['kind']), (3, 'results'), initial)
                self.assertTrue(initial['items'])
                self.planner.concepts = {}
                self.planner.calls.clear()

                request_id = str(uuid.uuid4())
                response = self.send(thread, refinement, 1, request_id)
                self.assertEqual(response.status_code, 200, response.text)
                envelope = response.json()
                self.assertEqual(set(envelope), expected_envelope_keys)
                self.assertEqual(envelope['status'], 'completed')
                result = envelope['result']
                self.assertEqual(set(result), expected_result_keys)
                self.assertEqual((result['version'], result['kind']), (3, 'clarification'))
                self.assertEqual(result['reply'], expected_reply)
                self.assertEqual(result['context'], initial['context'])
                self.assertEqual(result['filters'], initial['filters'])
                self.assertEqual(result['items'], initial['items'])
                self.assertEqual([item['id'] for item in result['items']],
                                 [item['id'] for item in initial['items']])
                self.assertEqual((result['total'], result['has_more']),
                                 (initial['total'], initial['has_more']))
                self.assertIsNone(result['effect'])
                self.assertEqual(len(self.planner.calls), 1)
                self.assertNotIn('pending_intent', response.text)

                recovered = self.client.get(
                    f'{self.base}/threads/{thread}/requests/{request_id}?library_id=family-a',
                    headers=self.headers)
                self.assertEqual(recovered.status_code, 200, recovered.text)
                self.assertTrue(recovered.json()['recovered'])
                self.assertEqual(recovered.json()['result'], result)
                self.assertEqual(len(self.planner.calls), 1)

    def test_new_search_description_question_does_not_retain_previous_result_scope(self):
        cases = (
            ('I am looking for unfamiliar scenery',
             'Please restate the complete search, including the scene, activity or object; '
             'include any person and capture date you want.'),
            ('我想找陌生场景的照片',
             '请重新说完整的查找条件，包括想找的场景、活动或物品；如果需要，也请写明人物和拍摄日期。'),
            ('I am looking for 更多scenes',
             '请重新说完整的查找条件，包括想找的场景、活动或物品；如果需要，也请写明人物和拍摄日期。'),
        )
        expected_result_keys = {
            'version', 'kind', 'reply', 'context', 'filters', 'items', 'total',
            'has_more', 'effect', 'interpretation',
        }

        for query, expected_reply in cases:
            with self.subTest(query=query):
                thread = self.new_thread()
                initial = self.send(thread,
                    'find photos of Sample Child in September 2032', 0)
                self.assertEqual(initial.status_code, 200, initial.text)
                prior = initial.json()['result']
                self.assertEqual((prior['version'], prior['kind']), (3, 'results'), prior)
                self.assertTrue(prior['filters'])
                self.assertTrue(prior['items'])

                self.planner.concepts = {}
                self.planner.calls.clear()
                request_id = str(uuid.uuid4())
                response = self.send(thread, query, 1, request_id)
                self.assertEqual(response.status_code, 200, response.text)
                envelope = response.json()
                result = envelope['result']
                self.assertEqual(set(result), expected_result_keys)
                self.assertEqual((result['version'], result['kind']), (3, 'clarification'))
                self.assertEqual(result['reply'], expected_reply)
                self.assertIsNone(result['context'])
                self.assertIsNone(result['filters'])
                self.assertEqual(result['items'], [])
                self.assertEqual(result['total'], 0)
                self.assertFalse(result['has_more'])
                self.assertIsNone(result['effect'])
                self.assertEqual(len(self.planner.calls), 1)
                self.assertNotIn('pending_intent', response.text)

                recovered = self.client.get(
                    f'{self.base}/threads/{thread}/requests/{request_id}?library_id=family-a',
                    headers=self.headers)
                self.assertEqual(recovered.status_code, 200, recovered.text)
                self.assertTrue(recovered.json()['recovered'])
                self.assertEqual(recovered.json()['result'], result)
                self.assertEqual(len(self.planner.calls), 1)


if __name__ == '__main__':
    unittest.main()
