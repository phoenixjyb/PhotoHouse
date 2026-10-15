"""Read-only why-result behavior over current authorized card snapshots."""
import unittest
import uuid
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'tests' / 'security'))

from app.access import result_explanation
import test_assistant_http as v1_fixture
import test_assistant_joint_search as v2_fixture
import test_assistant_intent_search as v3_fixture
import test_assistant_workspace_turn_http as workspace_fixture
from app.access.assistant_workspace_store import initialize_v2
from phone_discovery_fixture import TOKEN, OTHER, NOW


class V1WhyResultHttpTests(unittest.TestCase):
    setUp = v1_fixture.AssistantHttpTests.setUp
    connection = v1_fixture.AssistantHttpTests.connection
    turn = v1_fixture.AssistantHttpTests.turn

    def test_visible_ordinal_explanation_is_read_only_and_open_still_opens(self):
        initial = self.turn('找示例儿童的照片').json()
        self.assertEqual([item['id'] for item in initial['items']], ['103', '101'])
        before = initial['items']

        why = self.turn('why the first result', initial['context'])
        self.assertEqual(why.status_code, 200, why.text)
        explained = why.json()
        self.assertEqual(explained['kind'], 'results')
        self.assertEqual(explained['context'], initial['context'])
        self.assertEqual(explained['filters'], initial['filters'])
        self.assertEqual(explained['items'], before)
        self.assertIsNone(explained['effect'])
        self.assertIn('Match explanation for result 1', explained['reply'])
        self.assertLessEqual(len(explained['reply'].encode('utf-8')), 600)

        opened = self.turn('open the first result', initial['context']).json()
        self.assertEqual(opened['kind'], 'open')
        self.assertEqual(opened['effect'], {'type': 'open_asset', 'asset_id': '103'})

    def test_missing_singleton_and_compounds_do_not_open(self):
        self.assertEqual(self.turn('why this photo').json()['kind'], 'clarification')
        initial = self.turn('找示例儿童的照片').json()
        for words in ('why this photo', 'why the third result',
                      'why the first result then open it', '"why the first result"'):
            with self.subTest(words=words):
                response = self.turn(words, initial['context'])
                self.assertEqual(response.status_code, 200, response.text)
                result = response.json()
                self.assertIn(result['kind'], ('clarification', 'unsupported'))
                self.assertEqual(result['context'], initial['context'])
                self.assertEqual(result['items'], initial['items'])
                self.assertIsNone(result['effect'])


class V2WhyResultHttpTests(unittest.TestCase):
    setUp = v2_fixture.AssistantJointSearchTests.setUp
    connection = v2_fixture.AssistantJointSearchTests.connection
    install = v2_fixture.AssistantJointSearchTests.install
    turn = v2_fixture.AssistantJointSearchTests.turn
    mutate = v2_fixture.AssistantJointSearchTests.mutate

    def test_singleton_typed_explanation_uses_only_current_source_classes(self):
        initial = self.turn('find photos containing "secret memory phrase"').json()
        self.assertEqual([item['id'] for item in initial['items']], ['101'])
        self.assertEqual(initial['context']['search_version'], 2)

        why = self.turn('why this photo', context=initial['context'])
        self.assertEqual(why.status_code, 200, why.text)
        explained = why.json()
        self.assertEqual((explained['kind'], explained['effect']), ('results', None))
        self.assertEqual(explained['context'], initial['context'])
        self.assertEqual(explained['filters'], initial['filters'])
        self.assertEqual(explained['items'], initial['items'])
        self.assertIn('saved photo memory', explained['reply'])
        self.assertIn('secret memory phrase', explained['reply'])
        self.assertLessEqual(len(explained['reply'].encode('utf-8')), 600)
        for hidden in ('note-101', 'PRIVATE', 'Family beach visit', 'revision'):
            self.assertNotIn(hidden, explained['reply'])

    def test_context_binding_fingerprint_membership_library_and_source_are_revalidated(self):
        initial = self.turn('find photos in September 2032').json()
        context = initial['context']
        altered = dict(context, fingerprint='0' * 64)
        stale_fingerprint = self.turn('why the first result', context=altered)
        self.assertEqual(stale_fingerprint.status_code, 409, stale_fingerprint.text)

        foreign_member = self.turn('why the first result', context=context, token=v2_fixture.OTHER)
        self.assertIn(foreign_member.status_code, (401, 403))
        foreign_library = self.client.post('/assistant/v1/turns',
            json={'library_id': 'family-b', 'text': 'why the first result', 'context': context},
            headers=self.auth)
        self.assertIn(foreign_library.status_code, (401, 403))

        self.mutate("UPDATE captions SET text='Changed synthetic source' WHERE id=1")
        changed = self.turn('why the first result', context=context)
        self.assertEqual(changed.status_code, 409, changed.text)


class V3WhyResultHttpTests(unittest.TestCase):
    setUp = v3_fixture.AssistantIntentSearchTests.setUp
    connection = v3_fixture.AssistantIntentSearchTests.connection
    install = v3_fixture.AssistantIntentSearchTests.install
    intent = v3_fixture.AssistantIntentSearchTests.intent
    mutate = v3_fixture.AssistantIntentSearchTests.mutate

    def test_descriptive_explanation_keeps_card_order_and_never_calls_planner_again(self):
        initial = self.intent('find photos playing in snow red coat').json()
        self.assertEqual((initial['version'], initial['kind']), (3, 'results'))
        self.assertGreaterEqual(len(initial['items']), 2)
        calls = list(self.planner.calls)
        expected_items = initial['items']

        why = self.intent('why the first result', initial['context'])
        self.assertEqual(why.status_code, 200, why.text)
        explained = why.json()
        self.assertEqual((explained['version'], explained['kind']), (3, 'results'))
        self.assertEqual(explained['context'], initial['context'])
        self.assertEqual(explained['filters'], initial['filters'])
        self.assertEqual(explained['items'], expected_items)
        self.assertIsNone(explained['effect'])
        self.assertIn('Match explanation for result 1', explained['reply'])
        self.assertIn('playing in snow', explained['reply'])
        self.assertNotIn('红外套', explained['reply'])
        for hidden in ('caption-secret', 'note-101', 'A child playing',
                       'PRIVATE', 'source_id', 'alternative'):
            self.assertNotIn(hidden, explained['reply'])
        self.assertEqual(self.planner.calls, calls)

    def test_v3_context_and_current_membership_or_source_change_withhold_explanation(self):
        initial = self.intent('find photos playing in snow red coat').json()
        context = initial['context']
        foreign = self.intent('why the first result', context, token=OTHER)
        self.assertIn(foreign.status_code, (401, 403))
        wrong_library = self.client.post('/assistant/v1/turns',
            json={'library_id': 'family-b', 'text': 'why the first result', 'context': context},
            headers={'Authorization': 'Bearer ' + TOKEN,
                     'X-PhotoHouse-Search-Version': '3'})
        self.assertIn(wrong_library.status_code, (401, 403))

        self.mutate("UPDATE captions SET text='changed current source' WHERE id=1")
        changed = self.intent('why the first result', context)
        self.assertEqual(changed.status_code, 409, changed.text)


class DurableV3WhyResultTests(unittest.TestCase):
    setUp = v3_fixture.AssistantIntentSearchTests.setUp
    connection = v3_fixture.AssistantIntentSearchTests.connection
    install = v3_fixture.AssistantIntentSearchTests.install
    mutate = v3_fixture.AssistantIntentSearchTests.mutate

    def setUp(self):
        v3_fixture.AssistantIntentSearchTests.setUp(self)
        self.store = initialize_v2(self.database.parent.resolve() / 'why-result-workspace.sqlite',
                                   clock=lambda: NOW)
        self.app.state.assistant_workspace_store = self.store
        self.app.state.assistant_workspace_healthy = True
        self.base = '/assistant/workspace/v1'
        self.workspace_headers = {
            'Authorization': 'Bearer ' + TOKEN,
            'X-PhotoHouse-Search-Version': '3',
        }
        opened = self.client.post(self.base + '/threads',
            json={'library_id': 'family-a'},
            headers={'Authorization': self.workspace_headers['Authorization']})
        self.assertEqual(opened.status_code, 201, opened.text)
        self.thread_id = opened.json()['thread']['thread_id']

    def _turn(self, text, revision, request_id):
        return self.client.post(
            '%s/threads/%s/turns' % (self.base, self.thread_id),
            headers=self.workspace_headers,
            json={'library_id': 'family-a', 'request_id': request_id,
                  'expected_revision': revision, 'text': text})

    def test_exact_recovery_preserves_reply_and_history_without_planner_replay(self):
        first_id, why_id = str(uuid.uuid4()), str(uuid.uuid4())
        first_response = self._turn('find photos playing in snow red coat', 0, first_id)
        self.assertEqual(first_response.status_code, 200, first_response.text)
        first = first_response.json()['result']
        self.assertEqual((first['version'], first['kind']), (3, 'results'))
        calls_before_why = len(self.planner.calls)

        why_response = self._turn('why the first result', 1, why_id)
        self.assertEqual(why_response.status_code, 200, why_response.text)
        why_result = why_response.json()['result']
        self.assertEqual((why_result['version'], why_result['kind']), (3, 'results'))
        self.assertEqual(why_result['items'], first['items'])
        self.assertEqual(why_result['context'], first['context'])
        self.assertIsNone(why_result['effect'])
        calls_after_why = len(self.planner.calls)
        self.assertEqual(calls_after_why, calls_before_why)

        readback = self.client.get(
            '%s/threads/%s/requests/%s?library_id=family-a' % (self.base, self.thread_id, why_id),
            headers=self.workspace_headers)
        self.assertEqual(readback.status_code, 200, readback.text)
        self.assertEqual(readback.json()['result'], why_result)
        self.assertEqual(len(self.planner.calls), calls_after_why)

        history = self.client.get(
            '%s/threads/%s?library_id=family-a' % (self.base, self.thread_id),
            headers={'Authorization': self.workspace_headers['Authorization']})
        self.assertEqual(history.status_code, 200, history.text)
        exchanges = history.json()['exchanges']
        self.assertEqual([row['input_text'] for row in exchanges],
                         ['find photos playing in snow red coat', 'why the first result'])
        self.assertEqual(len(exchanges), 2)


class ActualFormatterBudgetTests(unittest.TestCase):
    def test_all_slots_with_large_utf8_values_stay_within_reply_budget(self):
        filters = {
            'media': ['image', 'video'],
            'date': {'from': '2032-09-01', 'to': '2032-09-30'},
            'people': {'ids': ['301'], 'match': 'any'},
            'tags': {'ids': ['401'], 'match': 'all'},
            'locations': ['501'],
            'text': '家庭照片' * 250,
            'descriptive': {'version': 1, 'concepts': [
                {'surface': '雪地玩耍' * 10, 'alternatives': ['snow']},
                {'surface': '红色外套' * 10, 'alternatives': ['coat']},
            ]},
        }
        interpretation = {
            'people': [{'id': '301', 'label': '示例儿童' * 50}],
            'tags': [{'id': '401', 'label': '家庭回忆' * 50}],
            'locations': [{'id': '501', 'label': '上海公园' * 50}],
        }
        item = {'kind': 'image', 'taken_at': '2032-09-14T10:00:00Z',
                'match_reasons': [
                    {'source': 'reviewed_person', 'source_id': '301'},
                    {'source': 'capture_date', 'value': '2032-09-14'},
                    {'source': 'photo_memory', 'source_id': 'private-id'},
                ]}
        reply = result_explanation.explain_result(item, 1, filters, interpretation, 'zh')
        self.assertLessEqual(len(reply.encode('utf-8')), 600)
        self.assertIn('第1项的匹配说明', reply)
        self.assertNotIn('private-id', reply)


if __name__ == '__main__':
    unittest.main()
