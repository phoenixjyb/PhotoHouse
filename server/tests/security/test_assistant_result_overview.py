"""Current-card narration stays bounded, contextual and read-only."""
import io
from urllib.parse import parse_qs
import unittest
import wave

import httpx
import test_assistant_http as fixture
import test_assistant_workspace_turn_http as workspace_fixture
from app.access import assistant
from app.access.assistant_speech import LocalAssistantTts


class OverviewFormattingTests(unittest.TestCase):
    def test_first_three_order_kind_and_recorded_dates_only(self):
        items = [dict(id=str(i), kind=k, taken_at=d) for i, k, d in (
            (91, 'other', '2026-01-02'), (12, 'image', None),
            (85, 'video', '2024-02-29T23:30:00-05:00'), (2, 'image', '2020-03-04'))]
        for language in ('zh', 'en'):
            with self.subTest(language=language):
                reply = assistant._result_overview(dict(total=1000, items=items), language)
                self.assertLessEqual(len(reply.encode('utf-8')), 600)
                self.assertIn('1000', reply)
                self.assertNotIn('2020', reply)
                self.assertNotIn('2024-03-01', reply)
        zh = assistant._result_overview(dict(total=1000, items=items), 'zh')
        self.assertIn('第1项是素材', zh)
        self.assertIn('第2项是照片', zh)
        self.assertIn('第3项是视频', zh)
        self.assertIn('2024年2月29日', zh)
        self.assertIn('打开第2项', zh)
        self.assertNotIn('拍摄于', zh)

    def test_invalid_and_missing_dates_do_not_use_hints_captions_or_paths(self):
        for day in (None, '', '2026-02-29', '2026-01-02 delete', '\ud800', 1, True):
            item = dict(kind='image', taken_at=day, date_hint={'kind':'received', 'value':'2026-09-23'},
                        caption='UNTRUSTED_STORY', path='PRIVATE_PATH', filename='wechat_20260923.jpg')
            reply = assistant._result_overview(dict(total=1, items=[item]), 'en')
            self.assertIn('Found 1 result.', reply)
            self.assertIn('date not recorded', reply)
            for secret in ('2026-09-23', 'UNTRUSTED_STORY', 'PRIVATE_PATH', 'wechat_', 'delete'):
                self.assertNotIn(secret, reply)

    def test_empty_and_other_only_results_offer_refinement_without_opening(self):
        self.assertIn('adjusting the search', assistant._result_overview(dict(total=0, items=[]), 'en'))
        reply = assistant._result_overview(dict(total=1, items=[dict(kind='other', taken_at=None)]), 'zh')
        self.assertNotIn('打开', reply)
        self.assertIn('补充查找条件', reply)


class ContextualOverviewTests(unittest.TestCase):
    setUp = fixture.AssistantHttpTests.setUp
    connection = fixture.AssistantHttpTests.connection
    update = fixture.AssistantHttpTests.update
    turn = fixture.AssistantHttpTests.turn

    def test_search_and_followup_keep_the_same_card_order_and_context(self):
        first = self.turn('找照片').json()
        self.assertIn('日期记录', first['reply'])
        for words in ('介绍这些结果', '请介绍一下这些照片。', '这些照片是什么时候拍的', '这些照片是哪天拍的？',
                      'describe these results', 'please tell me about these results',
                      'when were these photos taken?', 'what date were these photos taken?'):
            response = self.turn(words, first['context'])
            self.assertEqual(response.status_code, 200, response.text)
            result = response.json()
            self.assertEqual(result['kind'], 'results')
            self.assertEqual(result['context'], first['context'])
            self.assertEqual(result['items'], first['items'])
            self.assertEqual(result['filters'], first['filters'])
            self.assertIsNone(result['effect'])
            self.assertLessEqual(len(result['reply'].encode('utf-8')), 600)
        opened = self.turn('打开第二个', first['context']).json()
        self.assertEqual(opened['effect']['asset_id'], first['items'][1]['id'])

    def test_no_context_and_compound_actions_do_not_start_a_search_or_open(self):
        missing = self.turn('介绍这些结果').json()
        self.assertEqual((missing['kind'], missing['context'], missing['items']), ('clarification', None, []))
        first = self.turn('找照片').json()
        for words in ('介绍这些结果然后删除', 'describe these results and share them',
                      'when were these photos taken and delete them'):
            result = self.turn(words, first['context']).json()
            self.assertEqual(result['kind'], 'unsupported')
            self.assertEqual(result['context'], first['context'])
            self.assertIsNone(result['effect'])

    def test_singleton_and_empty_contexts_are_not_replaced_by_catalog_searches(self):
        exact = self.turn('查找编号102').json()
        explained = self.turn('介绍这些结果', exact['context']).json()
        self.assertEqual([item['id'] for item in explained['items']], ['102'])
        self.assertEqual(explained['context'], exact['context'])
        self.assertIn('视频', explained['reply'])
        self.assertIn('日期未记录', explained['reply'])
        empty = self.turn('找2099年照片').json()
        response = self.turn('介绍这些结果', empty['context']).json()
        self.assertEqual((response['total'], response['items']), (0, []))
        self.assertEqual(response['filters'], empty['filters'])

    def test_changed_sources_and_foreign_libraries_are_refused(self):
        context = self.turn('找照片').json()['context']
        self.assertEqual(self.turn('介绍这些结果', context, library='family-b').status_code, 401)
        self.update("UPDATE assets SET status='hidden' WHERE id=101")
        self.assertEqual(self.turn('介绍这些结果', context).status_code, 409)

    def test_speech_uses_current_metadata_and_refuses_source_change_during_synthesis(self):
        raw = io.BytesIO()
        with wave.open(raw, 'wb') as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
            wav.writeframes(b'\0\0' * 1600)
        requests = []
        mutate = [False]
        def provider(request):
            requests.append(parse_qs(request.content.decode())['text'][0])
            if mutate[0]:
                self.update("UPDATE assets SET status='hidden' WHERE id=101")
            return httpx.Response(200, content=raw.getvalue(), headers={'content-type':'audio/wav'})
        self.app.state.assistant_tts = LocalAssistantTts(url='http://127.0.0.1:7350/tts',
                                                       transport=httpx.MockTransport(provider))
        found = self.turn('找照片').json()
        body = {'library_id':'family-a', 'context':found['context'], 'language':'zh'}
        response = self.client.post('/assistant/v1/speech', json=body, headers=self.auth)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(requests[0], found['reply'])
        mutate[0] = True
        changed = self.client.post('/assistant/v1/speech', json=body, headers=self.auth)
        self.assertEqual(changed.status_code, 409, changed.text)
        self.assertNotEqual(changed.headers['content-type'], 'audio/wav')


class DurableOverviewTests(unittest.TestCase):
    setUp = workspace_fixture.AssistantWorkspaceTurnHttpTests.setUp
    connection = workspace_fixture.AssistantWorkspaceTurnHttpTests.connection
    _make_client = workspace_fixture.AssistantWorkspaceTurnHttpTests._make_client
    request = workspace_fixture.AssistantWorkspaceTurnHttpTests.request
    thread = workspace_fixture.AssistantWorkspaceTurnHttpTests.thread
    turn = workspace_fixture.AssistantWorkspaceTurnHttpTests.turn
    update = workspace_fixture.AssistantWorkspaceTurnHttpTests.update

    def test_durable_followup_and_recovery_preserve_reply_without_effects(self):
        thread = self.thread()['thread_id']
        first = self.turn(thread).json()
        identifier = workspace_fixture.new_id()
        fresh = self.turn(thread, identifier, first['revision'], '介绍这些结果').json()
        self.assertIn('日期记录', fresh['result']['reply'])
        recovered = self.request('GET', f'/threads/{thread}/requests/{identifier}?library_id=family-a')
        self.assertEqual(recovered.status_code, 200, recovered.text)
        self.assertEqual(recovered.json()['result']['reply'], fresh['result']['reply'])
        self.assertEqual(recovered.json()['result']['items'], fresh['result']['items'])
        self.assertIsNone(recovered.json()['result']['effect'])
        self.update("UPDATE assets SET status='hidden' WHERE id=101")
        self.assertEqual(self.request('GET', f'/threads/{thread}/requests/{identifier}?library_id=family-a').status_code, 409)


if __name__ == '__main__':
    unittest.main()
