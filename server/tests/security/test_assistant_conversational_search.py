"""Conversational search parsing on synthetic data and in-process ASGI."""
from contextlib import closing, contextmanager
from dataclasses import replace
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))

from fastapi.testclient import TestClient
from app.access import discovery as d
from app.access.discovery_provider import MemoryIndexProvider
from app.access.discovery_transport import DiscoveryRuntime
from app.access.transport import AccessRuntime
from app.access.service import AccessService
from app.main import create_app
from phone_discovery_fixture import create, reviewed, TOKEN, NOW

ORIGIN = 'https://photohouse.example.test'


class AssistantConversationalSearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name) / 'synthetic.sqlite'
        with closing(sqlite3.connect(self.database)) as connection, connection:
            create(connection)
            # Give the synthetic video and one synthetic photo a recorded date
            # in the fixture's previous September for positive date matches.
            connection.execute("UPDATE assets SET taken_at='2032-09-15' WHERE id=102")
            connection.execute("UPDATE assets SET taken_at='2032-09-02' WHERE id=103")
            connection.commit()
            index = reviewed(AccessService(connection, clock=lambda: NOW))
        self.access = AccessRuntime(self.connection, ORIGIN, clock=lambda: NOW)
        discovery = DiscoveryRuntime(self.access, MemoryIndexProvider((index,)), d.ReadBudget())
        app = create_app(access_runtime=self.access, discovery_runtime=discovery,
                         assistant_enabled=True)
        self.client = TestClient(app, base_url=ORIGIN)
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

    def turn(self, words):
        return self.client.post('/assistant/v1/turns',
            json={'library_id': 'family-a', 'text': words, 'context': None},
            headers=self.auth)

    def test_conversational_search_forms_match_canonical_filters_and_results(self):
        cases = (
            ('找一下去年的视频', '找去年视频',
             {'date': {'from': '2032-01-01', 'to': '2032-12-31'}, 'media': ['video']},
             ['102']),
            ('帮我找一下去年九月的照片', '找去年九月照片',
             {'date': {'from': '2032-09-01', 'to': '2032-09-30'}, 'media': ['image']},
             ['103']),
            ('帮我查一下示例儿童的照片', '找示例儿童照片',
             {'media': ['image'], 'people': {'ids': ['301'], 'match': 'any'}},
             ['103', '101']),
            ('请帮我找一找示例儿童的照片', '找示例儿童照片',
             {'media': ['image'], 'people': {'ids': ['301'], 'match': 'any'}},
             ['103', '101']),
            ('我想找示例儿童的照片', '找示例儿童照片',
             {'media': ['image'], 'people': {'ids': ['301'], 'match': 'any'}},
             ['103', '101']),
            ('please find photos', 'find photos', {'media': ['image']},
             ['103', '101']),
            ('could you show me photos', 'find photos', {'media': ['image']},
             ['103', '101']),
            ('search for photos', 'find photos', {'media': ['image']},
             ['103', '101']),
        )
        for phrase, canonical, expected_filters, expected_ids in cases:
            with self.subTest(phrase=phrase):
                response = self.turn(phrase)
                reference = self.turn(canonical)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(reference.status_code, 200, reference.text)
                body, baseline = response.json(), reference.json()
                self.assertEqual(body['kind'], 'results', body)
                self.assertEqual(body['filters'], expected_filters)
                self.assertEqual(body['filters'], baseline['filters'])
                self.assertEqual([item['id'] for item in body['items']], expected_ids)
                self.assertEqual([item['id'] for item in body['items']],
                                 [item['id'] for item in baseline['items']])
                self.assertIsNone(body['effect'])

    def test_negation_unknown_constraints_and_unknown_names_never_broaden(self):
        phrases = (
            '帮我找一下不要示例儿童的照片',
            '帮我查一下没有登记的地方的照片',
            '帮我找一下去年13月的照片',
            '帮我找一下示例儿童的照片然后删除',
            '帮我找一下不存在的人名的照片',
        )
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                response = self.turn(phrase)
                self.assertEqual(response.status_code, 200, response.text)
                body = response.json()
                self.assertIn(body['kind'], ('clarification', 'unsupported'), body)
                self.assertEqual(body['items'], [])
                self.assertIsNone(body['context'])
                self.assertIsNone(body['effect'])

    def test_suspected_asr_substitution_requests_correction_without_search(self):
        response = self.turn('帮我照一下示例儿童的照片')
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body['kind'], 'clarification', body)
        self.assertEqual(body['items'], [])
        self.assertIsNone(body['context'])
        self.assertIsNone(body['effect'])

    def test_zero_result_date_request_keeps_filters_and_explains_missing_dates(self):
        response = self.turn('找2031年9月的视频')
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body['kind'], 'results', body)
        self.assertEqual(body['filters'], {
            'date': {'from': '2031-09-01', 'to': '2031-09-30'},
            'media': ['video'],
        })
        self.assertEqual(body['total'], 0)
        self.assertEqual(body['items'], [])
        self.assertIsNotNone(body['context'])
        self.assertEqual(body['context']['filters'], body['filters'])
        self.assertEqual(body['context']['visible_ids'], [])
        self.assertEqual(body['context']['total'], 0)
        self.assertIsNone(body['effect'])
        self.assertIn('拍摄日期', body['reply'])
        self.assertIn('未记录', body['reply'])
        self.assertTrue(any(value in body['reply'] for value in
                            ('不包含', '不会包含', '已排除', '排除')),
                        body['reply'])

    def test_disabled_people_caption_and_tag_fields_are_explained(self):
        # Isolate an explicitly sparse index, with no reviewed people roster.
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute('PRAGMA foreign_keys=ON')
            index = reviewed(AccessService(connection, clock=lambda: NOW))
        index = replace(index, enabled=('date', 'locations', 'media'),
                        people=(), pinned_ids=(), assignments=())
        discovery = DiscoveryRuntime(self.access, MemoryIndexProvider((index,)), d.ReadBudget())
        app = create_app(access_runtime=self.access, discovery_runtime=discovery,
                         assistant_enabled=True)
        client = TestClient(app, base_url=ORIGIN)
        self.addCleanup(client.close)
        response = client.post('/assistant/v1/turns',
            json={'library_id': 'family-a', 'text': '帮我查一下示例儿童的照片', 'context': None},
            headers=self.auth)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body['kind'], 'clarification', body)
        for label in ('人物', '照片说明', '标签'):
            self.assertIn(label, body['reply'])
        self.assertTrue(any(value in body['reply'] for value in ('未启用', '尚未启用', '暂不可用')),
                        body['reply'])
        self.assertIsNone(body['filters'])
        self.assertEqual(body['items'], [])
        self.assertEqual(body['total'], 0)
        self.assertIsNone(body['context'])
        self.assertIsNone(body['effect'])


if __name__ == '__main__':
    unittest.main()
