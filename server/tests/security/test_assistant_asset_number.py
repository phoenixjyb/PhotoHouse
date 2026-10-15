"""Explicit ID retrieval remains library-scoped and recovery never navigates."""
from contextlib import closing
import sqlite3
import unittest

import test_assistant_http as http_fixture
import test_assistant_workspace_turn_http as workspace_fixture
from app.access.discovery_provider import MemoryIndexProvider
from app.access.service import AccessService
from phone_discovery_fixture import reviewed, NOW


class AssetNumberTests(unittest.TestCase):
    setUp = http_fixture.AssistantHttpTests.setUp
    connection = http_fixture.AssistantHttpTests.connection
    update = http_fixture.AssistantHttpTests.update
    turn = http_fixture.AssistantHttpTests.turn

    def test_exact_number_without_previous_search_and_ordinal_followup(self):
        for words in ('打开编号101', '请打开照片编号 101。', 'open asset id 101', 'show photo number 101'):
            with self.subTest(words=words):
                response = self.turn(words)
                self.assertEqual(response.status_code, 200, response.text)
                result = response.json()
                self.assertEqual(result['effect'], {'type': 'open_asset', 'asset_id': '101'})
                self.assertEqual([item['id'] for item in result['items']], ['101'])
                self.assertEqual((result['total'], result['has_more']), (1, False))
                self.assertEqual(self.turn('打开第一个', result['context']).json()['effect'], result['effect'])
        found = self.turn('查找编号102').json()
        self.assertEqual((found['kind'], found['effect']), ('results', None))
        self.assertEqual(found['items'][0]['kind'], 'video')

    def test_outside_first_page_is_looked_up_without_changing_public_facets(self):
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute('PRAGMA foreign_keys=ON')
            for aid in range(1000, 1030):
                db.execute('INSERT INTO assets VALUES(?,?,?, ?,8,8,NULL,NULL)',
                           (aid, 'synthetic-only', 'active', 'image/jpeg'))
                db.execute('INSERT INTO access_asset_libraries VALUES(?,?)', (aid, 'family-a'))
            db.commit()
            index = reviewed(AccessService(db, clock=lambda: NOW))
        object.__setattr__(self.discovery, 'provider', MemoryIndexProvider((index,)))
        first = self.turn('找照片').json()
        self.assertNotIn('101', first['context']['visible_ids'])
        result = self.turn('打开编号101', first['context'])
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()['effect']['asset_id'], '101')
        self.assertEqual(self.turn('打开第一个', result.json()['context']).status_code, 200)

    def test_hidden_foreign_and_unknown_numbers_have_same_non_disclosing_result(self):
        results = [self.turn('打开编号' + ident).json() for ident in ('201', '999', '888')]
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[1], results[2])
        self.assertEqual(results[0]['kind'], 'clarification')
        self.assertIsNone(results[0]['effect'])
        self.assertEqual(self.turn('打开编号201', library='family-b').status_code, 401)
        self.assertEqual(self.turn('打开编号101', headers={}).status_code, 401)

    def test_source_membership_and_context_tampering_are_rejected(self):
        context = self.turn('查找编号101').json()['context']
        tampered = dict(context, visible_ids=['201'])
        self.assertEqual(self.turn('打开第一个', tampered).status_code, 409)
        self.update("UPDATE assets SET status='hidden' WHERE id=101")
        self.assertEqual(self.turn('打开第一个', context).status_code, 409)

    def test_ambiguous_and_mutating_commands_never_open(self):
        for words in ('打开28222', '打开编号0', '打开编号0101', '打开编号9223372036854775808',
                      '打开编号101和102', '删除编号101', '打开编号101然后删除'):
            with self.subTest(words=words):
                self.assertIsNone(self.turn(words).json()['effect'])


class DurableAssetNumberTests(unittest.TestCase):
    setUp = workspace_fixture.AssistantWorkspaceTurnHttpTests.setUp
    connection = workspace_fixture.AssistantWorkspaceTurnHttpTests.connection
    _make_client = workspace_fixture.AssistantWorkspaceTurnHttpTests._make_client
    request = workspace_fixture.AssistantWorkspaceTurnHttpTests.request
    thread = workspace_fixture.AssistantWorkspaceTurnHttpTests.thread
    turn = workspace_fixture.AssistantWorkspaceTurnHttpTests.turn
    update = workspace_fixture.AssistantWorkspaceTurnHttpTests.update

    def test_recovery_returns_same_singleton_without_replaying_open(self):
        thread_id = self.thread()['thread_id']
        request_id = workspace_fixture.new_id()
        fresh = self.turn(thread_id, request_id=request_id, text='打开编号101')
        self.assertEqual(fresh.status_code, 200, fresh.text)
        self.assertEqual(fresh.json()['result']['effect']['asset_id'], '101')
        recovered = self.request('GET', f'/threads/{thread_id}/requests/{request_id}?library_id=family-a')
        self.assertEqual(recovered.status_code, 200, recovered.text)
        self.assertEqual([item['id'] for item in recovered.json()['result']['items']], ['101'])
        self.assertIsNone(recovered.json()['result']['effect'])
        self.assertEqual(recovered.json()['result']['kind'], 'results')
        replay = self.turn(thread_id, request_id=request_id, text='打开编号101')
        self.assertIsNone(replay.json()['result']['effect'])
        self.update("UPDATE assets SET status='hidden' WHERE id=101")
        self.assertEqual(self.request('GET', f'/threads/{thread_id}/requests/{request_id}?library_id=family-a').status_code, 409)
