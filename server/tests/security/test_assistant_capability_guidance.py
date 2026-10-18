"""Capability-aware refusal on generated libraries and owned conversations."""
from contextlib import closing
from dataclasses import asdict
import sqlite3
import unittest
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient
import test_assistant_joint_search as fixture
from app.access import discovery as d
from app.access.assistant import _search_clarification_guidance
from app.access.assistant_search import SearchRuntime
from app.access.discovery_provider import ProjectedIndex
from app.access.assistant_workspace_store import initialize_v2
from app.main import create_app


class QuestionPlanner:
    def __init__(self, question='person'):
        self.question = question

    def propose(self, query, today, has_previous_search):
        return {'version': 1, 'status': 'clarification', 'concepts': [], 'question': self.question}


class AssistantCapabilityGuidanceTests(unittest.TestCase):
    connection = fixture.AssistantJointSearchTests.connection
    install = fixture.AssistantJointSearchTests.install
    mutate = fixture.AssistantJointSearchTests.mutate

    def setUp(self):
        fixture.AssistantJointSearchTests.setUp(self)
        with closing(sqlite3.connect(self.database)) as db:
            db.execute('PRAGMA query_only=ON')
            source = d.projected_source('family-a', lambda sql, args: db.execute(sql, args).fetchall(),
                                        ('date', 'media'))
        record = asdict(self.index)
        record.update(enabled=('date', 'media'), people=(), pinned_ids=(), assignments=(),
                      places=(), regions=(), source_digest=d.digest(source))
        self.install(ProjectedIndex(**record))
        self.planner = QuestionPlanner()
        self.app.state.assistant_intent_planner = self.planner

    def assert_guidance(self, result, chinese):
        self.assertEqual(result['kind'], 'clarification', result)
        self.assertIsNone(result['effect'])
        reply = result['reply']
        for phrase in (('尚未启用人物检索', '已记录的拍摄日期', '照片或视频类型', '照片留言', '条件没有被忽略')
                       if chinese else ('People search is not enabled', 'recorded capture dates',
                                        'photo or video type', 'photo-memory', 'no conditions were dropped')):
            self.assertIn(phrase, reply)
        for phrase in (('请发送完整查找句', '已登记人物', '已登记标签', '已登记地点') if chinese else
                       ('Send the complete query', 'reviewed people', 'reviewed tags', 'reviewed places')):
            self.assertNotIn(phrase, reply)

    def test_full_person_date_queries_use_actual_capabilities_without_searching(self):
        original = SearchRuntime.call
        for version in ('2', '3'):
            for words, chinese in (('帮我找一下2032年的示例儿童的照片', True),
                                   ('find photos of River in 2032', False),
                                   ('find 2032年River的photos', True)):
                calls = []
                def counted(runtime, operation, *args, **kwargs):
                    calls.append(operation)
                    return original(runtime, operation, *args, **kwargs)
                with self.subTest(version=version, words=words), patch.object(SearchRuntime, 'call', counted):
                    response = self.client.post('/assistant/v1/turns', headers=self.auth |
                        {'X-PhotoHouse-Search-Version': version},
                        json={'library_id': 'family-a', 'text': words, 'context': None})
                self.assertEqual(response.status_code, 200, response.text)
                result = response.json()
                self.assert_guidance(result, chinese)
                self.assertEqual(result['items'], [])
                self.assertIsNone(result['context'])
                self.assertNotIn('search', calls, 'unresolved person must not become a date-only search')

    def test_clarification_preserves_previous_results_and_filters(self):
        for version in ('2', '3'):
            headers = self.auth | {'X-PhotoHouse-Search-Version': version}
            previous = self.client.post('/assistant/v1/turns', headers=headers,
                json={'library_id': 'family-a', 'text': 'find photos in 2032', 'context': None}).json()
            self.assertEqual(previous['kind'], 'results', previous)
            result = self.client.post('/assistant/v1/turns', headers=headers,
                json={'library_id': 'family-a', 'text': 'only River', 'context': previous['context']}).json()
            self.assert_guidance(result, False)
            for key in ('context', 'filters', 'items', 'total', 'has_more'):
                self.assertEqual(result[key], previous[key], key)

    def test_owned_clarification_recovery_keeps_identical_guidance(self):
        store = initialize_v2(self.database.parent.resolve() / 'workspace.sqlite')
        client = TestClient(create_app(access_runtime=self.access, discovery_runtime=self.discovery_runtime,
            assistant_enabled=True, assistant_workspace_store=store, assistant_intent_planner=self.planner),
            base_url=fixture.ORIGIN)
        self.addCleanup(client.close)
        base = '/assistant/workspace/v1'
        for version in ('2', '3'):
            headers = self.auth | {'X-PhotoHouse-Search-Version': version}
            for words, chinese in (('找2032年示例儿童的照片', True), ('find River photos from 2032', False)):
                with self.subTest(version=version, words=words):
                    created = client.post(base + '/threads', headers=self.auth,
                                          json={'library_id': 'family-a'})
                    self.assertIn(created.status_code, (200, 201), created.text)
                    thread = created.json()['thread']['thread_id']
                    rid = str(uuid.uuid4())
                    response = client.post(base + f'/threads/{thread}/turns', headers=headers,
                        json={'library_id': 'family-a', 'request_id': rid, 'expected_revision': 0, 'text': words})
                    self.assertEqual(response.status_code, 200, response.text)
                    result = response.json()['result']
                    self.assert_guidance(result, chinese)
                    self.assertEqual(result['items'], [])
                    recovered = client.get(base + f'/threads/{thread}/requests/{rid}?library_id=family-a', headers=headers)
                    self.assertEqual(recovered.status_code, 200, recovered.text)
                    self.assertEqual(recovered.json()['result'], result)

    def test_guidance_never_advertises_disabled_facets_or_text(self):
        for lang in ('zh', 'en'):
            reply = _search_clarification_guidance({'media'}, lang)
            for phrase in ('已记录的拍摄日期', '已有说明', '已登记地点', '已登记标签',
                           'recorded capture dates', 'photo-memory', 'reviewed places', 'reviewed tags'):
                self.assertNotIn(phrase, reply)
            self.assertLessEqual(len(reply.encode('utf-8')), 600)
