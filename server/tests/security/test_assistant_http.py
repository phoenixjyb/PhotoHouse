"""Protected read-only assistant contract on synthetic data and in-process ASGI."""
from contextlib import closing, contextmanager
import io
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
import wave
from urllib.parse import parse_qs

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))

from fastapi.testclient import TestClient
from app.access import discovery as d
from app.access.discovery_provider import MemoryIndexProvider
from app.access.discovery_transport import DiscoveryRuntime
from app.access.assistant_speech import LocalAssistantAsr, LocalAssistantTts
from app.access.transport import AccessRuntime, COOKIE, csrf_token
from app.access.service import AccessService
from app.main import create_app
from phone_discovery_fixture import create, reviewed, TOKEN, SECOND, OTHER, NOW

ORIGIN = 'https://photohouse.example.test'


class AssistantHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name) / 'synthetic.sqlite'
        with closing(sqlite3.connect(self.database)) as connection, connection:
            create(connection)
            index = reviewed(AccessService(connection, clock=lambda: NOW))
        self.access = AccessRuntime(self.connection, ORIGIN, clock=lambda: NOW)
        self.discovery = DiscoveryRuntime(self.access, MemoryIndexProvider((index,)), d.ReadBudget())
        self.app = create_app(access_runtime=self.access, discovery_runtime=self.discovery,
                              assistant_enabled=True)
        self.client = TestClient(self.app, base_url=ORIGIN)
        self.addCleanup(self.client.close)
        self.auth = {'Authorization': 'Bearer ' + TOKEN}

    @contextmanager
    def connection(self):
        connection = sqlite3.connect(self.database, timeout=.25)
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('PRAGMA query_only=ON')
        try:
            yield connection
        finally:
            connection.close()

    def update(self, sql):
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute(sql)

    def turn(self, words, context=None, headers=None, library='family-a'):
        return self.client.post('/assistant/v1/turns',
                                json={'library_id': library, 'text': words, 'context': context},
                                headers=self.auth if headers is None else headers)

    def test_capability_requires_current_library_and_explicit_enable(self):
        response = self.client.get('/assistant/v1/capabilities?library_id=family-a', headers=self.auth)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {'version': 1, 'enabled': True, 'text': True,
                                           'transcribe': False, 'speech': False,
                                           'max_audio_seconds': 0})
        for headers, library in [({}, 'family-a'), (self.auth, 'family-b'),
                                 ({'Authorization': 'Bearer ' + OTHER}, 'family-a')]:
            self.assertEqual(self.client.get('/assistant/v1/capabilities?library_id=' + library,
                                             headers=headers).status_code, 401)
        closed = TestClient(create_app(access_runtime=self.access,
                                       discovery_runtime=self.discovery), base_url=ORIGIN)
        self.addCleanup(closed.close)
        self.assertFalse(closed.get('/assistant/v1/capabilities?library_id=family-a',
                                    headers=self.auth).json()['enabled'])
        self.assertEqual(closed.post('/assistant/v1/turns', json={'library_id': 'family-a',
                         'text': '找照片', 'context': None}, headers=self.auth).status_code, 503)

    def test_find_refine_open_same_authorized_visible_order(self):
        first = self.turn('找示例儿童的照片')
        self.assertEqual(first.status_code, 200, first.text)
        body = first.json()
        self.assertEqual(body['kind'], 'results')
        self.assertEqual([item['id'] for item in body['items']], ['103', '101'])
        self.assertEqual(body['filters']['people']['ids'], ['301'])
        self.assertEqual(body['filters']['media'], ['image'])
        refined = self.turn('只看公园', body['context'])
        self.assertEqual(refined.status_code, 200, refined.text)
        self.assertEqual([item['id'] for item in refined.json()['items']], ['103'])
        opened = self.turn('打开第一个', refined.json()['context'])
        self.assertEqual(opened.status_code, 200, opened.text)
        self.assertEqual(opened.json()['effect'], {'type': 'open_asset', 'asset_id': '103'})
        self.assertNotIn('not-a-real-path', opened.text)

    def test_english_mixed_date_and_missing_context(self):
        self.assertEqual(self.turn('open the second result').json()['kind'], 'clarification')
        found = self.turn('find videos')
        self.assertEqual(found.status_code, 200, found.text)
        self.assertEqual([item['id'] for item in found.json()['items']], ['102'])
        found = self.turn('找2026年1月示例儿童的照片')
        self.assertEqual(found.status_code, 200, found.text)
        self.assertEqual([item['id'] for item in found.json()['items']], ['101'])
        self.assertEqual(found.json()['filters']['date'], {'from': '2026-01-01',
                                                           'to': '2026-01-31'})
        spoken = self.turn('给我看看去年九月示例儿童的照片')
        self.assertEqual(spoken.status_code, 200, spoken.text)
        self.assertEqual(spoken.json()['kind'], 'results')
        self.assertEqual(spoken.json()['filters']['date'], {'from': '2032-09-01',
                                                             'to': '2032-09-30'})
        # Unknown words must not quietly become a broad media-only query.
        unclear = self.turn('找去年夏天海边的照片')
        self.assertEqual(unclear.status_code, 200, unclear.text)
        self.assertEqual(unclear.json()['kind'], 'clarification')
        self.assertEqual(unclear.json()['items'], [])

    def test_spoken_followups_preserve_filters_and_visible_context(self):
        first = self.turn('帮我找示例儿童的照片').json()
        self.assertEqual(first['kind'], 'results')
        video = self.turn('那视频呢？', first['context']).json()
        self.assertEqual(video['kind'], 'results')
        self.assertEqual(video['filters']['people'], first['filters']['people'])
        self.assertEqual(video['filters']['media'], ['video'])
        photos = self.turn('照片呢', video['context']).json()
        self.assertEqual([item['id'] for item in photos['items']], ['103', '101'])
        dated = self.turn('那2026年呢？', photos['context']).json()
        self.assertEqual(dated['filters']['date'], {'from': '2026-01-01', 'to': '2026-12-31'})
        self.assertEqual(dated['filters']['people'], first['filters']['people'])
        self.assertEqual([item['id'] for item in dated['items']], ['101'])
        opened = self.turn('打开第一个', dated['context']).json()
        self.assertEqual(opened['effect'], {'type': 'open_asset', 'asset_id': '101'})

    def test_english_conversation_and_missing_context_are_explicit(self):
        first = self.turn('find photos').json()
        video = self.turn('what about videos?', first['context']).json()
        self.assertEqual(video['kind'], 'results')
        self.assertEqual([item['id'] for item in video['items']], ['102'])
        dated = self.turn('how about last year?', video['context']).json()
        self.assertEqual(dated['filters']['media'], ['video'])
        self.assertEqual(dated['filters']['date'], {'from': '2032-01-01', 'to': '2032-12-31'})
        for words in ('视频呢？', 'last year', '那照片呢'):
            missing = self.turn(words).json()
            self.assertEqual(missing['kind'], 'clarification')
            self.assertIsNone(missing['context'])
            self.assertEqual(missing['items'], [])
            self.assertIsNone(missing['effect'])

    def test_followup_unknowns_negation_and_invalid_dates_keep_prior_results(self):
        first = self.turn('找照片').json()
        for words in ('那删除视频呢', '只要没有登记的地方', '那不要照片',
                      '找2026年13月照片', '找去年13月照片'):
            with self.subTest(words=words):
                result = self.turn(words, first['context']).json()
                self.assertEqual(result['kind'], 'clarification')
                self.assertEqual(result['context'], first['context'])
                self.assertEqual(result['items'], first['items'])
                self.assertIsNone(result['effect'])
        unsupported = self.turn("don't show videos", first['context']).json()
        self.assertEqual(unsupported['kind'], 'unsupported')
        self.assertEqual(unsupported['context'], first['context'])
        self.assertIsNone(unsupported['effect'])
        self.assertEqual(self.turn('那视频呢', first['context'],
                                  headers={'Authorization': 'Bearer ' + SECOND}).status_code, 409)

    def test_stale_context_and_cross_library_denied(self):
        context = self.turn('找照片').json()['context']
        self.assertEqual(self.turn('打开第一个', context, library='family-b').status_code, 401)
        self.assertEqual(self.turn('打开第一个', context, headers={'Authorization': 'Bearer ' + SECOND}).status_code, 409)
        self.update("UPDATE access_sessions SET revoked=1 WHERE account_id='one'")
        self.assertEqual(self.turn('打开第一个', context).status_code, 401)

    def test_transport_and_closed_boundary(self):
        web = {'Cookie': COOKIE + '=' + TOKEN, 'Origin': ORIGIN}
        self.assertEqual(self.turn('找照片', headers=web).status_code, 403)
        accepted = self.turn('找照片', headers=dict(web, **{'X-CSRF-Token': csrf_token(TOKEN)}))
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(accepted.headers['cache-control'], 'no-store')
        for path in ('/assistant/v1/turns/extra', '/assistant/v1/capabilities/extra'):
            self.assertEqual(self.client.get(path, headers=self.auth).status_code, 403)
        self.assertEqual(self.client.get('/assistant/v1/turns', headers=self.auth).status_code, 403)
        self.assertEqual(self.turn('找照片', headers=dict(self.auth, Origin=ORIGIN)).status_code, 401)
        self.assertEqual(self.client.post('/assistant/v1/turns?token=bad',
                          json={'library_id':'family-a','text':'找照片','context':None},
                          headers=self.auth).status_code, 400)

    def test_transient_wav_to_reviewed_transcript(self):
        def provider(request):
            self.assertEqual(request.url.host, '127.0.0.1')
            self.assertEqual(request.headers['content-type'], 'audio/wav')
            self.assertTrue(request.content.startswith(b'RIFF'))
            return httpx.Response(200, json={'success': True, 'text': '找 示例儿童 的 照片'})
        self.app.state.assistant_asr = LocalAssistantAsr(
            url='http://127.0.0.1:7350/transcribe', model='local-test',
            transport=httpx.MockTransport(provider))
        capabilities = self.client.get('/assistant/v1/capabilities?library_id=family-a',
                                       headers=self.auth).json()
        self.assertTrue(capabilities['transcribe'])
        self.assertEqual(capabilities['max_audio_seconds'], 30)
        output = io.BytesIO()
        with wave.open(output, 'wb') as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
            wav.writeframes(b'\0\0' * 1600)
        headers = dict(self.auth, **{'Content-Type': 'audio/wav',
                                     'X-PhotoHouse-Library-Id': 'family-a'})
        response = self.client.post('/assistant/v1/transcribe', content=output.getvalue(),
                                    headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {'version': 1, 'text': '找 示例儿童 的 照片',
                                           'language': 'zh'})
        self.assertEqual(self.client.post('/assistant/v1/transcribe', content=b'bad',
                         headers=headers).status_code, 400)
        self.assertEqual(self.client.post('/assistant/v1/transcribe', content=output.getvalue(),
                         headers=dict(headers, **{'X-PhotoHouse-Library-Id': 'family-b'})).status_code, 401)
        self.assertEqual(self.client.get('/assistant/v1/transcribe', headers=self.auth).status_code, 403)

    def test_spoken_reply_is_grounded_in_current_result_context(self):
        original = io.BytesIO()
        with wave.open(original, 'wb') as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
            wav.writeframes(b'\0\0' * 1600)
        def provider(request):
            self.assertEqual(request.url.host, '127.0.0.1')
            self.assertEqual(parse_qs(request.content.decode())['text'], ['Found 2 results.'])
            return httpx.Response(200, json={'success': True,
                'audio_base64': __import__('base64').b64encode(original.getvalue()).decode()})
        self.app.state.assistant_tts = LocalAssistantTts(
            url='http://127.0.0.1:7350/tts', transport=httpx.MockTransport(provider))
        found = self.turn('find photos by Sample Child').json()
        context = found['context']
        body = {'library_id': 'family-a', 'context': context, 'language': 'en'}
        response = self.client.post('/assistant/v1/speech', json=body, headers=self.auth)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers['content-type'], 'audio/wav')
        self.assertEqual(response.content, original.getvalue())
        self.assertEqual(response.headers['cache-control'], 'no-store')
        self.assertEqual(self.client.post('/assistant/v1/speech', json=dict(body, library_id='family-b'),
                         headers=self.auth).status_code, 401)
        self.update("UPDATE access_memberships SET status='requested' WHERE account_id='one'")
        self.assertEqual(self.client.post('/assistant/v1/speech', json=body,
                         headers=self.auth).status_code, 401)

    def test_provider_response_budget_fails_closed(self):
        output = io.BytesIO()
        with wave.open(output, 'wb') as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
            wav.writeframes(b'\0\0' * 1600)
        self.app.state.assistant_asr = LocalAssistantAsr(
            url='http://127.0.0.1:7350/transcribe', model='local-test',
            transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b'x' * 9000)))
        response = self.client.post('/assistant/v1/transcribe', content=output.getvalue(),
            headers=dict(self.auth, **{'Content-Type': 'audio/wav',
                                       'X-PhotoHouse-Library-Id': 'family-a'}))
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('xxxxxxxx', response.text)


if __name__ == '__main__':
    unittest.main()
