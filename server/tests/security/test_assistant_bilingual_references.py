"""Bilingual pronouns retain selected people; guitar wording stays a scene."""
from contextlib import closing
import sqlite3
import unittest

from app.access.service import AccessService
from phone_discovery_fixture import NOW, reviewed
import test_assistant_intent_search as intent_fixture


class AssistantBilingualReferenceTests(unittest.TestCase):
    connection = intent_fixture.AssistantIntentSearchTests.connection
    mutate = intent_fixture.AssistantIntentSearchTests.mutate
    install = intent_fixture.AssistantIntentSearchTests.install
    intent = intent_fixture.AssistantIntentSearchTests.intent

    def setUp(self):
        intent_fixture.AssistantIntentSearchTests.setUp(self)
        self.mutate("UPDATE captions SET text='A child playing guitar.' WHERE id=1")
        self.mutate("UPDATE captions SET text='示例儿童弹吉他。' WHERE id=2")
        with closing(sqlite3.connect(self.database)) as db:
            db.execute('PRAGMA foreign_keys=ON')
            index = reviewed(AccessService(db, clock=lambda: NOW))
        self.install(index)
        self.planner.concepts = {
            'playing guitar': ['playing guitar', '弹吉他'],
            '弹吉他': ['playing guitar', '弹吉他'],
        }

    def test_new_guitar_search_and_singular_followups_preserve_hard_people_and_dates(self):
        for query in ('find photos of Sample Child playing guitar in September 2032',
                      '找示例儿童2032年9月弹吉他的照片'):
            with self.subTest(query=query):
                response = self.intent(query)
                self.assertEqual(response.status_code, 200, response.text)
                initial = response.json()
                self.assertEqual(initial['kind'], 'results', initial)
                self.assertEqual({item['id'] for item in initial['items']}, {'101', '103'})
                self.assertEqual(initial['filters']['people'], {'ids':['301'], 'match':'any'})
                for followup in ('she playing guitar photos', 'he playing guitar photos',
                                 '她弹吉他的照片', '他弹吉他的照片', 'she弹吉他photos'):
                    with self.subTest(followup=followup):
                        calls = len(self.planner.calls)
                        response = self.intent(followup, initial['context'])
                        self.assertEqual(response.status_code, 200, response.text)
                        result = response.json()
                        self.assertEqual(result['kind'], 'results', result)
                        self.assertEqual({item['id'] for item in result['items']}, {'101', '103'})
                        self.assertEqual({k:v for k,v in result['filters'].items() if k!='descriptive'},
                                         {k:v for k,v in initial['filters'].items() if k!='descriptive'})
                        self.assertIsNone(result['effect'])
                        self.assertEqual(len(self.planner.calls), calls + 1)

    def test_singular_reference_cannot_choose_from_multiple_people_or_a_fresh_search(self):
        response = self.intent('find photos of Sample Child and Sample Adult in September 2032')
        self.assertEqual(response.status_code, 200, response.text)
        initial = response.json()
        self.assertEqual(initial['kind'], 'results', initial)
        self.assertEqual(len(initial['filters']['people']['ids']), 2)
        for query, context in (
            ('she playing guitar photos', initial['context']),
            ('他弹吉他的照片', initial['context']),
            ('find photos where she playing guitar', None),
        ):
            with self.subTest(query=query):
                calls = len(self.planner.calls)
                response = self.intent(query, context)
                self.assertEqual(response.status_code, 200, response.text)
                result = response.json()
                self.assertEqual(result['kind'], 'clarification', result)
                self.assertEqual(result['context'], context)
                self.assertEqual(result['filters'], initial['filters'] if context else None)
                self.assertEqual(len(self.planner.calls), calls)
                self.assertIsNone(result['effect'])


if __name__ == '__main__':
    unittest.main()
