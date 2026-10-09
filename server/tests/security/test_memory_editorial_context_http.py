"""Explicit editorial model-context choice; synthetic protected HTTP only."""
import json
import unittest
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

import test_memory_book_editorial_service as fixture
from app.access.transport import AccessRuntime
from app.main import create_app


class EditorialContextHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.MemoryBookEditorialServiceTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        fixture.MemoryBookEditorialServiceTests.tearDownClass()

    def setUp(self):
        self.seed = fixture.MemoryBookEditorialServiceTests()
        self.seed.setUp()
        self.addCleanup(self.seed.doCleanups)
        self.f = self.seed.f
        saved = self.seed._service('save', self.seed.book_id, self.seed._request())
        self.revision = saved['revision']
        self.headers = {'Authorization': 'Bearer ' + self.f.owner_token}

    def client(self, *, editorial=False, generation=True):
        runtime = AccessRuntime(self.f.connection, 'https://photohouse.test', clock=lambda: self.f.now)
        client = TestClient(create_app(access_runtime=runtime,
            memory_collaboration_enabled=True, memory_generation_enabled=generation,
            memory_editorial_enabled=editorial), base_url='https://photohouse.test',
            client=('192.0.2.45', 23459))
        client.headers['Sec-Fetch-Site'] = 'same-origin'
        self.addCleanup(client.close)
        return client

    def body(self, *, target_type='book'):
        return {'target_type': target_type,
            'target_id': self.seed.book_id if target_type == 'book' else self.seed.child_one,
            'revision': self.revision if target_type == 'book' else '1',
            'mutation_id': str(uuid.uuid4()), 'instructions': 'Synthetic direction'}

    def test_choice_is_authenticated_default_off_and_strict(self):
        endpoint = '/memory-community/v1/jobs?library=family-a&editorial_context=1'
        disabled = self.client()
        with patch('httpx.Client', side_effect=AssertionError('provider forbidden')):
            self.assertEqual(disabled.post(endpoint, json=self.body()).status_code, 401)
            self.assertEqual(disabled.post(endpoint, headers=self.headers, json=self.body()).status_code, 503)
            enabled = self.client(editorial=True)
            for invalid in ('0', 'true', '', '2'):
                with self.subTest(value=invalid):
                    response = enabled.post('/memory-community/v1/jobs?library=family-a&editorial_context=' + invalid,
                        headers=self.headers, json=self.body())
                    self.assertEqual(response.status_code, 400)
            self.assertEqual(enabled.post(endpoint, headers=self.headers,
                json=self.body(target_type='story')).status_code, 400)
        with self.f.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM access_memory_jobs').fetchone()[0], 0)

    def test_book_choice_queues_only_profile_and_legacy_request_stays_v1(self):
        client = self.client(editorial=True)
        first = client.post('/memory-community/v1/jobs?library=family-a&editorial_context=1',
            headers=self.headers, json=self.body())
        self.assertEqual(first.status_code, 200, first.text)
        legacy = client.post('/memory-community/v1/jobs?library=family-a',
            headers=self.headers, json=self.body())
        self.assertEqual(legacy.status_code, 200, legacy.text)
        with self.f.connection() as db:
            chosen = json.loads(db.execute('SELECT input_json FROM access_memory_jobs WHERE id=?',
                (first.json()['id'],)).fetchone()[0])
            old = json.loads(db.execute('SELECT input_json FROM access_memory_jobs WHERE id=?',
                (legacy.json()['id'],)).fetchone()[0])
        self.assertEqual(chosen, {'instructions': 'Synthetic direction', 'context_profile': 'memoir_editorial_v1'})
        self.assertEqual(old, {'instructions': 'Synthetic direction'})

    def test_book_chat_choice_uses_same_explicit_route_and_generation_gate(self):
        client = self.client(editorial=True)
        conversation = client.post('/memory-community/v1/conversations?library=family-a',
            headers=self.headers, json={'id': str(uuid.uuid4()), 'target_type': 'book', 'target_id': self.seed.book_id})
        self.assertEqual(conversation.status_code, 200, conversation.text)
        path = '/memory-community/v1/conversations/' + conversation.json()['id'] + '/turns?library=family-a&editorial_context=1'
        body = {'revision': self.revision, 'mutation_id': str(uuid.uuid4()), 'text': 'Synthetic question'}
        disabled = self.client(editorial=True, generation=False)
        self.assertEqual(disabled.post(path, headers=self.headers, json=body).status_code, 503)
        accepted = client.post(path, headers=self.headers, json=body)
        self.assertEqual(accepted.status_code, 200, accepted.text)
        with self.f.connection() as db:
            controls = json.loads(db.execute('SELECT input_json FROM access_memory_jobs WHERE id=?',
                (accepted.json()['id'],)).fetchone()[0])
        self.assertEqual(set(controls), {'turn_id', 'context_profile'})
        self.assertEqual(controls['context_profile'], 'memoir_editorial_v1')

    def test_readonly_plan_counts_selected_context_without_provider_or_queue(self):
        path = '/memory-community/v1/books/' + self.seed.book_id + '/plan?library=family-a'
        client = self.client(editorial=True, generation=False)
        with patch('httpx.Client', side_effect=AssertionError('provider forbidden')):
            legacy = client.get(path, headers=self.headers)
            selected = client.get(path + '&editorial_context=1', headers=self.headers)
        self.assertEqual(legacy.status_code, 200, legacy.text)
        self.assertEqual(selected.status_code, 200, selected.text)
        self.assertNotIn('context_profile', legacy.json())
        self.assertNotIn('context_bytes', legacy.json()['whole'])
        plan = selected.json()
        self.assertEqual(plan['context_profile'], 'memoir_editorial_v1')
        self.assertEqual(plan['whole']['state'], 'within_limits')
        self.assertGreater(plan['whole']['context_bytes'], 0)
        self.assertLessEqual(plan['whole']['context_bytes'], plan['limits']['context_bytes'])
        self.assertFalse(plan['generated'])
        self.assertFalse(plan['queued'])
        self.assertNotIn('synthetic family contribution', selected.text)
        self.assertNotIn('Our shared moment', selected.text)
        with self.f.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM access_memory_jobs').fetchone()[0], 0)
