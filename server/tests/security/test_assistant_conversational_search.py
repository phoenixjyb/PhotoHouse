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
from app.access.discovery_provider import MemoryIndexProvider, ReviewedPlace
from app.access.discovery_transport import DiscoveryRuntime
from app.access.transport import AccessRuntime
from app.access.service import AccessService
from app.main import create_app
from phone_discovery_fixture import create, reviewed, TOKEN, OTHER, NOW

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
        self.index = index
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

    def turn(self, words, *, context=None, version=None, token=TOKEN):
        headers = {'Authorization': 'Bearer ' + token}
        if version is not None:
            headers['X-PhotoHouse-Search-Version'] = str(version)
        return self.client.post('/assistant/v1/turns',
            json={'library_id': 'family-a', 'text': words, 'context': context},
            headers=headers)

    def enable_v2_text_schema(self):
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute('''CREATE TABLE IF NOT EXISTS access_stories (
                id TEXT PRIMARY KEY, asset_id INTEGER NOT NULL, library_id TEXT NOT NULL,
                author_id TEXT NOT NULL, revision INTEGER NOT NULL, title TEXT NOT NULL,
                text TEXT NOT NULL, updated_at INTEGER NOT NULL, deleted INTEGER NOT NULL DEFAULT 0)''')

    def test_bare_reviewed_location_followups_keep_people_date_and_media(self):
        self.enable_v2_text_schema()
        cases = (
            ('find photos of Sample Child from September 2032 containing "Family"',
             'Example region', 'Family'),
            ('找示例儿童2032年9月照片', '示例地区', None),
        )
        for initial_words, location_answer, text_filter in cases:
            with self.subTest(location_answer=location_answer):
                initial_response = self.turn(initial_words, version=2)
                self.assertEqual(initial_response.status_code, 200, initial_response.text)
                initial = initial_response.json()
                self.assertEqual(initial['kind'], 'results', initial)
                self.assertEqual([item['id'] for item in initial['items']], ['103'])
                expected_initial = {
                    'media': ['image'],
                    'people': {'ids': ['301'], 'match': 'any'},
                    'date': {'from': '2032-09-01', 'to': '2032-09-30'},
                }
                if text_filter is not None:
                    expected_initial['text'] = text_filter
                self.assertEqual(initial['filters'], expected_initial)

                result_response = self.turn(location_answer, context=initial['context'], version=2)
                self.assertEqual(result_response.status_code, 200, result_response.text)
                result = result_response.json()
                self.assertEqual(result['kind'], 'results', result)
                self.assertEqual(result['filters'], {
                    **initial['filters'], 'locations': ['601'],
                })
                self.assertEqual([item['id'] for item in result['items']], ['103'])
                self.assertEqual(result['context']['filters'], result['filters'])
                self.assertIsNone(result['effect'])

    def test_bare_location_followup_narrows_results_and_rejects_stale_context(self):
        self.enable_v2_text_schema()
        index = replace(
            self.index,
            places=(*self.index.places,
                    ReviewedPlace('family-a', '602', 'Other region / 其他地区')),
            regions=tuple(('101', '602') if asset_id == '101' else (asset_id, place_id)
                          for asset_id, place_id in self.index.regions),
        )
        discovery = DiscoveryRuntime(self.access, MemoryIndexProvider((index,)), d.ReadBudget())
        app = create_app(access_runtime=self.access, discovery_runtime=discovery,
                         assistant_enabled=True)
        client = TestClient(app, base_url=ORIGIN)
        self.addCleanup(client.close)

        initial_response = client.post('/assistant/v1/turns',
            json={'library_id': 'family-a', 'text': 'find photos of Sample Child', 'context': None},
            headers={**self.auth, 'X-PhotoHouse-Search-Version': '2'})
        self.assertEqual(initial_response.status_code, 200, initial_response.text)
        initial = initial_response.json()
        self.assertEqual(initial['kind'], 'results', initial)
        self.assertEqual([item['id'] for item in initial['items']], ['103', '101'])

        narrowed_response = client.post('/assistant/v1/turns',
            json={'library_id': 'family-a', 'text': 'Example region', 'context': initial['context']},
            headers={**self.auth, 'X-PhotoHouse-Search-Version': '2'})
        self.assertEqual(narrowed_response.status_code, 200, narrowed_response.text)
        narrowed = narrowed_response.json()
        self.assertEqual(narrowed['kind'], 'results', narrowed)
        self.assertEqual(narrowed['filters'], {
            **initial['filters'], 'locations': ['601'],
        })
        self.assertEqual([item['id'] for item in narrowed['items']], ['103'])

        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute("UPDATE assets SET status='hidden' WHERE id=103")
        stale_response = client.post('/assistant/v1/turns',
            json={'library_id': 'family-a', 'text': 'Example region', 'context': narrowed['context']},
            headers={**self.auth, 'X-PhotoHouse-Search-Version': '2'})
        self.assertEqual(stale_response.status_code, 409, stale_response.text)

    def test_bare_location_answer_rejects_unknown_extra_and_unresolved_phrases(self):
        self.enable_v2_text_schema()
        initial = self.turn('find photos', version=2).json()
        self.assertEqual(initial['kind'], 'results', initial)
        for words in (
            'Unknownland',
            'Example region Park',
            'Example region September 2032',
            'Example region then open the first photo',
        ):
            with self.subTest(words=words):
                result = self.turn(words, context=initial['context'], version=2).json()
                self.assertIn(result['kind'], ('unsupported', 'clarification'), result)
                self.assertEqual(result['filters'], initial['filters'])
                self.assertEqual(result['items'], initial['items'])
                self.assertEqual(result['context'], initial['context'])
                self.assertIsNone(result['effect'])

        no_context = self.turn('Example region', version=2).json()
        self.assertNotEqual(no_context['kind'], 'results', no_context)
        self.assertIsNone(no_context['context'])

        denied = self.turn('Example region', context=initial['context'],
                           version=2, token=OTHER)
        self.assertNotEqual(denied.status_code, 200)

    def test_ambiguous_bare_location_answer_keeps_current_results(self):
        self.enable_v2_text_schema()
        index = replace(self.index, places=(
            *self.index.places,
            ReviewedPlace('family-a', '602', 'Example region / 示例地区'),
        ))
        discovery = DiscoveryRuntime(self.access, MemoryIndexProvider((index,)), d.ReadBudget())
        app = create_app(access_runtime=self.access, discovery_runtime=discovery,
                         assistant_enabled=True)
        client = TestClient(app, base_url=ORIGIN)
        self.addCleanup(client.close)
        initial_response = client.post('/assistant/v1/turns',
            json={'library_id': 'family-a', 'text': 'find photos', 'context': None},
            headers={**self.auth, 'X-PhotoHouse-Search-Version': '2'})
        self.assertEqual(initial_response.status_code, 200, initial_response.text)
        initial = initial_response.json()
        result_response = client.post('/assistant/v1/turns',
            json={'library_id': 'family-a', 'text': '示例地区', 'context': initial['context']},
            headers={**self.auth, 'X-PhotoHouse-Search-Version': '2'})
        self.assertEqual(result_response.status_code, 200, result_response.text)
        result = result_response.json()
        self.assertEqual(result['kind'], 'clarification', result)
        self.assertEqual(result['filters'], initial['filters'])
        self.assertEqual(result['items'], initial['items'])
        self.assertEqual(result['context'], initial['context'])
        self.assertIsNone(result['effect'])

    def test_conversational_search_forms_match_canonical_filters_and_results(self):
        cases = (
            ('找一下去年的视频', '找去年视频',
             {'date': {'from': '2032-01-01', 'to': '2032-12-31'}, 'media': ['video']},
             ['102']),
            ('帮我找一下去年九月的照片', '找去年九月照片',
             {'date': {'from': '2032-09-01', 'to': '2032-09-30'}, 'media': ['image']},
             ['103']),
            ('帮我找一下去年九月份的照片', '找去年九月照片',
             {'date': {'from': '2032-09-01', 'to': '2032-09-30'}, 'media': ['image']},
             ['103']),
            ('帮我找一下2025年9月份的照片', '找2025年9月照片',
             {'date': {'from': '2025-09-01', 'to': '2025-09-30'}, 'media': ['image']},
             []),
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

    def test_multiround_month_person_and_media_refinements_keep_other_filters(self):
        cases = (
            ('找示例儿童的照片', '去年九月份',
             {'media': ['image'], 'people': {'ids': ['301'], 'match': 'any'},
              'date': {'from': '2032-09-01', 'to': '2032-09-30'}}, ['103']),
            ('找去年九月份的照片', '再找示例儿童',
             {'media': ['image'], 'people': {'ids': ['301'], 'match': 'any'},
              'date': {'from': '2032-09-01', 'to': '2032-09-30'}}, ['103']),
            ('找去年的视频', '只看照片',
             {'media': ['image'], 'date': {'from': '2032-01-01', 'to': '2032-12-31'}}, ['103']),
        )
        for initial, refinement, expected_filters, expected_ids in cases:
            with self.subTest(initial=initial, refinement=refinement):
                first_response = self.turn(initial)
                self.assertEqual(first_response.status_code, 200, first_response.text)
                first = first_response.json()
                self.assertEqual(first['kind'], 'results', first)
                result = self.turn(refinement, context=first['context'])
                self.assertEqual(result.status_code, 200, result.text)
                body = result.json()
                self.assertEqual(body['kind'], 'results', body)
                self.assertEqual(body['filters'], expected_filters)
                self.assertEqual([item['id'] for item in body['items']], expected_ids)
                self.assertEqual(body['context']['filters'], expected_filters)
                self.assertEqual(body['context']['visible_ids'], expected_ids)
                self.assertIsNone(body['effect'])

        # A rejected refinement keeps the prior snapshot usable for recovery.
        initial_response = self.turn('找示例儿童的照片')
        self.assertEqual(initial_response.status_code, 200, initial_response.text)
        initial = initial_response.json()
        rejected = self.turn('不要', context=initial['context']).json()
        self.assertIn(rejected['kind'], ('clarification', 'unsupported'), rejected)
        self.assertEqual(rejected['context'], initial['context'])
        recovered = self.turn('去年九月份', context=initial['context']).json()
        self.assertEqual(recovered['kind'], 'results', recovered)
        self.assertEqual(recovered['filters']['date'],
                         {'from': '2032-09-01', 'to': '2032-09-30'})

    def test_keep_person_filter_directive_preserves_reviewed_person_in_same_session(self):
        self.enable_v2_text_schema()
        first_response = self.turn('find photos of Sample Child from September 2032', version=2)
        self.assertEqual(first_response.status_code, 200, first_response.text)
        first = first_response.json()
        self.assertEqual(first['kind'], 'results', first)
        self.assertEqual(first['filters']['people'], {'ids': ['301'], 'match': 'any'})

        videos_response = self.turn('only videos', context=first['context'], version=2)
        self.assertEqual(videos_response.status_code, 200, videos_response.text)
        videos = videos_response.json()
        self.assertEqual(videos['kind'], 'results', videos)
        self.assertEqual(videos['filters']['people'], first['filters']['people'])
        self.assertEqual(videos['filters']['media'], ['video'])

        result_response = self.turn('make it October, keep the person filter',
                                    context=videos['context'], version=2)
        self.assertEqual(result_response.status_code, 200, result_response.text)
        result = result_response.json()
        self.assertEqual(result['kind'], 'results', result)
        self.assertEqual(result['filters'], {
            'media': ['video'], 'people': {'ids': ['301'], 'match': 'any'},
            'date': {'from': '2032-10-01', 'to': '2032-10-31'},
        })
        self.assertEqual(result['context']['filters'], result['filters'])

        conflict = self.turn('make it October, keep the person filter for Sample Adult',
                             context=videos['context'], version=2).json()
        self.assertEqual(conflict['kind'], 'clarification', conflict)
        self.assertEqual(conflict['filters'], videos['filters'])
        self.assertEqual(conflict['context'], videos['context'])

    def test_keep_people_words_inside_content_remain_literal(self):
        self.enable_v2_text_schema()
        for words, text in (
                ('find photos containing keep the same people', 'keep the same people'),
                ('find photos containing "keep the same people"', 'keep the same people'),
                ('找包含“保留人物条件”的照片', '保留人物条件')):
            with self.subTest(words=words):
                response = self.turn(words, version=2)
                self.assertEqual(response.status_code, 200, response.text)
                body = response.json()
                self.assertEqual(body['kind'], 'results', body)
                self.assertEqual(body['filters'], {'media': ['image'], 'text': text})
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

    def test_v2_unquoted_content_cues_retrieve_exact_synthetic_caption_with_hard_filters(self):
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute("UPDATE captions SET text='birthday cake 切蛋糕' WHERE id=2")
            connection.execute('''CREATE TABLE access_stories (
                id TEXT PRIMARY KEY, asset_id INTEGER NOT NULL, library_id TEXT NOT NULL,
                author_id TEXT NOT NULL, revision INTEGER NOT NULL, title TEXT NOT NULL,
                text TEXT NOT NULL, updated_at INTEGER NOT NULL, deleted INTEGER NOT NULL DEFAULT 0)''')
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute('PRAGMA foreign_keys=ON')
            index = reviewed(AccessService(connection, clock=lambda: NOW))
        discovery = DiscoveryRuntime(self.access, MemoryIndexProvider((index,)), d.ReadBudget())
        app = create_app(access_runtime=self.access, discovery_runtime=discovery,
                         assistant_enabled=True)
        client = TestClient(app, base_url=ORIGIN)
        self.addCleanup(client.close)
        cases = (
            ('find photos of Sample Child from September 2032 containing birthday cake',
             {'media': ['image'], 'people': {'ids': ['301'], 'match': 'any'},
              'date': {'from': '2032-09-01', 'to': '2032-09-30'}, 'text': 'birthday cake'}),
            ("I'm looking for photos of Sample Child from September 2032 containing birthday cake",
             {'media': ['image'], 'people': {'ids': ['301'], 'match': 'any'},
              'date': {'from': '2032-09-01', 'to': '2032-09-30'}, 'text': 'birthday cake'}),
            ('请找示例儿童2032年9月包含切蛋糕的照片',
             {'media': ['image'], 'people': {'ids': ['301'], 'match': 'any'},
              'date': {'from': '2032-09-01', 'to': '2032-09-30'}, 'text': '切蛋糕'}),
            ('还有没有示例儿童2032年9月照片包含切蛋糕',
             {'media': ['image'], 'people': {'ids': ['301'], 'match': 'any'},
              'date': {'from': '2032-09-01', 'to': '2032-09-30'}, 'text': '切蛋糕'}),
            ('can you pull up Sample Child 2032年9月照片包含切蛋糕',
             {'media': ['image'], 'people': {'ids': ['301'], 'match': 'any'},
              'date': {'from': '2032-09-01', 'to': '2032-09-30'}, 'text': '切蛋糕'}),
            ('find示例儿童2032年9月photos containing切蛋糕',
             {'media': ['image'], 'people': {'ids': ['301'], 'match': 'any'},
              'date': {'from': '2032-09-01', 'to': '2032-09-30'}, 'text': '切蛋糕'}),
        )
        for words, expected_filters in cases:
            with self.subTest(words=words):
                response = client.post('/assistant/v1/turns',
                    json={'library_id': 'family-a', 'text': words, 'context': None},
                    headers={**self.auth, 'X-PhotoHouse-Search-Version': '2'})
                self.assertEqual(response.status_code, 200, response.text)
                result = response.json()
                self.assertEqual(result['kind'], 'results', result)
                self.assertEqual(result['filters'], expected_filters)
                self.assertEqual([item['id'] for item in result['items']], ['103'])
                self.assertIsNone(result['effect'])

        prior = result
        for words in (
            'find photos containing birthday cake; open all photos',
            '找照片包含切蛋糕；打开第一张',
            '找照片包含切蛋糕然后帮我打开第一张',
            'find photos containing birthday cake then could you please open the first photo',
        ):
            with self.subTest(followup=words):
                response = client.post('/assistant/v1/turns',
                    json={'library_id': 'family-a', 'text': words,
                          'context': prior['context']},
                    headers={**self.auth, 'X-PhotoHouse-Search-Version': '2'})
                self.assertEqual(response.status_code, 200, response.text)
                followup = response.json()
                self.assertEqual(followup['kind'], 'clarification', followup)
                self.assertEqual(followup['filters'], prior['filters'])
                self.assertEqual(followup['items'], prior['items'])
                self.assertEqual(followup['context'], prior['context'])
                self.assertIsNone(followup['effect'])

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
