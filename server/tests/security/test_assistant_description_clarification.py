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

    def send(self, thread, words, revision, request_id=None, version=None):
        headers = self.headers if version is None else {
            **self.headers, 'X-PhotoHouse-Search-Version': str(version)}
        return self.client.post(f'{self.base}/threads/{thread}/turns', headers=headers,
            json={'library_id': 'family-a', 'request_id': request_id or str(uuid.uuid4()),
                  'expected_revision': revision, 'text': words})

    def assert_description_guidance(self, reply, chinese=False):
        required = (('当时在做什么', '醒目的物品或地点', '完整查找句', '人物姓名', '拍摄日期')
                    if chinese else
                    ('what was happening', 'distinctive object or place', 'complete search',
                     'reviewed person', 'capture date'))
        for phrase in required:
            self.assertIn(phrase, reply.casefold())

    def assert_complete_query_example(self, reply, chinese=False):
        required = (('完整查找句', '找包含“红风筝”的照片', '人物、拍摄日期、标签或地点',
                     '未匹配的条件不会被忽略')
                    if chinese else
                    ('complete query', 'find photos containing "red kite"', 'reviewed person',
                     'capture date, tag, or place', 'unmatched conditions are not dropped'))
        for phrase in required:
            self.assertIn(phrase.casefold(), reply.casefold())

    def test_description_question_requests_a_complete_search_and_keeps_prior_results(self):
        cases = (
            ('more moments', False),
            ('更多时刻', True),
            ('more 更多moments', True),
        )
        expected_result_keys = {
            'version', 'kind', 'reply', 'context', 'filters', 'items', 'total',
            'has_more', 'effect', 'interpretation',
        }
        expected_envelope_keys = {
            'version', 'thread_id', 'request_id', 'status', 'revision',
            'recovered', 'error', 'result',
        }

        for refinement, chinese in cases:
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
                self.assert_description_guidance(result['reply'], chinese)
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
            ('I am looking for unfamiliar scenery', False),
            ('我想找陌生场景的照片', True),
            ('I am looking for 更多scenes', True),
        )
        expected_result_keys = {
            'version', 'kind', 'reply', 'context', 'filters', 'items', 'total',
            'has_more', 'effect', 'interpretation',
        }

        for query, chinese in cases:
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
                self.assert_description_guidance(result['reply'], chinese)
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

    def test_unmatched_details_get_a_complete_quoted_caption_query_example(self):
        cases = (
            ('find photos of Sample Child in September 2032 red coat purple dragon', False),
            ('找示例儿童2032年9月红外套紫色飞龙的照片', True),
        )
        for query, chinese in cases:
            with self.subTest(query=query):
                thread = self.new_thread()
                response = self.send(thread, query, 0)
                self.assertEqual(response.status_code, 200, response.text)
                result = response.json()['result']
                self.assertEqual(result['kind'], 'clarification', result)
                self.assert_complete_query_example(result['reply'], chinese)
                self.assertIsNone(result['context'])
                self.assertIsNone(result['filters'])
                self.assertEqual(result['items'], [])
                self.assertTrue(self.planner.calls)

    def test_intent_unavailable_offers_supported_search_without_service_details(self):
        cases = (
            ('find photos of Sample Child in September 2032', 'refine with red coat', False),
            ('找示例儿童2032年9月的照片', '再看红外套', True),
        )
        for initial_query, refinement, chinese in cases:
            with self.subTest(refinement=refinement):
                thread = self.new_thread()
                initial_response = self.send(thread, initial_query, 0)
                self.assertEqual(initial_response.status_code, 200, initial_response.text)
                initial = initial_response.json()['result']
                self.assertEqual(initial['kind'], 'results', initial)
                self.planner.calls.clear()
                self.planner.failure = True

                response = self.send(thread, refinement, 1)
                self.assertEqual(response.status_code, 200, response.text)
                result = response.json()['result']
                self.assertEqual(result['kind'], 'clarification', result)
                self.assertEqual(result['context'], initial['context'])
                self.assertEqual(result['filters'], initial['filters'])
                self.assertEqual(result['items'], initial['items'])
                if chinese:
                    for phrase in ('已登记姓名', '拍摄日期', '带引号的照片说明原文', '找包含“红风筝”的照片'):
                        self.assertIn(phrase, result['reply'])
                    self.assertNotIn('服务', result['reply'])
                else:
                    for phrase in ('reviewed person', 'capture date', 'quoted caption text',
                                   'find photos containing "red kite"'):
                        self.assertIn(phrase, result['reply'].casefold())
                    self.assertNotIn('local', result['reply'].casefold())
                    self.assertNotIn('service', result['reply'].casefold())
                self.assertEqual(len(self.planner.calls), 1)
                self.planner.failure = False

    def test_v2_without_intent_provider_keeps_complete_search_available_and_clarifies_residue(self):
        self.app.state.assistant_intent_planner = None
        thread = self.new_thread()
        initial_response = self.send(thread,
            'find photos of Sample Child in September 2032', 0, version=2)
        self.assertEqual(initial_response.status_code, 200, initial_response.text)
        initial = initial_response.json()['result']
        self.assertEqual((initial['version'], initial['kind']), (2, 'results'), initial)
        self.planner.calls.clear()

        response = self.send(thread,
            'find photos of Sample Child in September 2032 purple dragon', 1, version=2)
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()['result']
        self.assertEqual((result['version'], result['kind']), (2, 'clarification'), result)
        self.assertEqual(result['context'], initial['context'])
        self.assertEqual(result['filters'], initial['filters'])
        self.assertEqual(result['items'], initial['items'])
        self.assert_complete_query_example(result['reply'])
        self.assertEqual(self.planner.calls, [])

    def test_v2_examples_compile_and_complete_resubmission_keeps_explicit_filters(self):
        self.app.state.assistant_intent_planner = None
        standalone_examples = (
            ('find photos containing "red kite"', 'red kite'),
            ('找包含“红风筝”的照片', '红风筝'),
        )
        for query, literal in standalone_examples:
            with self.subTest(query=query):
                thread = self.new_thread()
                response = self.send(thread, query, 0, version=2)
                self.assertEqual(response.status_code, 200, response.text)
                result = response.json()['result']
                self.assertEqual((result['version'], result['kind']), (2, 'results'), result)
                self.assertEqual(result['filters']['text'], literal)
                self.assertEqual(result['filters']['media'], ['image'])
                self.assertEqual(self.planner.calls, [])

        complete_queries = (
            ('find photos of Sample Child in September 2032 containing "red coat"', 'red coat'),
            ('找示例儿童2032年9月包含“red coat”的照片', 'red coat'),
        )
        for query, literal in complete_queries:
            with self.subTest(complete_query=query):
                thread = self.new_thread()
                initial = self.send(thread,
                    'find photos of Sample Child in September 2032', 0, version=2)
                self.assertEqual(initial.status_code, 200, initial.text)
                prior = initial.json()['result']
                self.assertEqual(prior['kind'], 'results', prior)
                self.assertEqual(prior['filters']['people'], {'ids': ['301'], 'match': 'any'})
                self.assertEqual(prior['filters']['date'],
                                 {'from': '2032-09-01', 'to': '2032-09-30'})

                clarification = self.send(thread,
                    'find photos of Sample Child in September 2032 purple dragon', 1, version=2)
                self.assertEqual(clarification.status_code, 200, clarification.text)
                pending = clarification.json()['result']
                self.assertEqual(pending['kind'], 'clarification', pending)
                self.assertEqual(pending['context'], prior['context'])
                self.assertEqual(pending['filters'], prior['filters'])
                self.assert_complete_query_example(pending['reply'])

                response = self.send(thread, query, 2, version=2)
                self.assertEqual(response.status_code, 200, response.text)
                result = response.json()['result']
                self.assertEqual((result['version'], result['kind']), (2, 'results'), result)
                self.assertEqual(result['filters']['people'], {'ids': ['301'], 'match': 'any'})
                self.assertEqual(result['filters']['date'],
                                 {'from': '2032-09-01', 'to': '2032-09-30'})
                self.assertEqual(result['filters']['media'], ['image'])
                self.assertEqual(result['filters']['text'], literal)
                self.assertEqual([item['id'] for item in result['items']], ['101'])
                self.assertEqual(self.planner.calls, [])


if __name__ == '__main__':
    unittest.main()
