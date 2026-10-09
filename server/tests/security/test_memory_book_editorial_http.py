"""Protected HTTP integration for the default-off memoir editorial sidecar."""
import json
import unittest
import uuid

from fastapi.testclient import TestClient

import test_memory_book_editorial_service as seed_fixture
from app.access.transport import AccessRuntime
from app.main import create_app


class MemoryBookEditorialHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        seed_fixture.MemoryBookEditorialServiceTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        seed_fixture.MemoryBookEditorialServiceTests.tearDownClass()

    def setUp(self):
        self.seed = seed_fixture.MemoryBookEditorialServiceTests()
        self.seed.setUp()
        self.addCleanup(self.seed.doCleanups)
        self.f = self.seed.f
        self.path = f'/memory-community/v1/books/{self.seed.book_id}'
        self.disabled = self.f.client
        runtime = AccessRuntime(self.f.connection, 'https://photohouse.test',
                                clock=lambda: self.f.now)
        self.enabled = TestClient(create_app(
            access_runtime=runtime,
            memory_collaboration_enabled=True,
            memory_editorial_enabled=True,
        ), base_url='https://photohouse.test', client=('192.0.2.31', 23458))
        self.enabled.headers['Sec-Fetch-Site'] = 'same-origin'
        self.addCleanup(self.enabled.close)

    @property
    def owner_headers(self):
        return {'Authorization': 'Bearer ' + self.f.owner_token}

    def put(self, client, body, *, query='?library=family-a', headers=None):
        request_headers = dict(self.owner_headers if headers is None else headers)
        request_headers.setdefault('Content-Type', 'application/json')
        return client.put(self.path + '/editorial' + query,
                          headers=request_headers, content=body)

    def test_default_off_and_authenticated_owner_roundtrip_is_additive(self):
        endpoint = self.path + '/editorial?library=family-a'
        self.assertEqual(self.disabled.get(endpoint).status_code, 401)
        self.assertEqual(self.disabled.get(endpoint, headers=self.owner_headers).status_code, 503)
        self.assertEqual(self.enabled.get(endpoint).status_code, 401)
        capabilities = self.disabled.get(
            '/memory-community/v1/capabilities?library=family-a',
            headers=self.owner_headers)
        self.assertEqual(capabilities.status_code, 200, capabilities.text)
        self.assertEqual(set(capabilities.json()), {
            'version', 'enabled', 'contributions_enabled', 'generation_enabled',
            'conversation_retention_days', 'audio_format', 'max_audio_seconds',
            'max_text_bytes', 'original_retention',
        })

        legacy_before = self.enabled.get(self.path + '?library=family-a',
                                         headers=self.owner_headers)
        self.assertEqual(legacy_before.status_code, 200, legacy_before.text)
        legacy_before_json = legacy_before.json()
        raw = self.seed._request()
        saved = self.put(self.enabled, raw)
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json()['state'], 'current')
        self.assertEqual(saved.json()['revision'], '2')

        # A separate TestClient and database connection reopens the sidecar.
        runtime = AccessRuntime(self.f.connection, 'https://photohouse.test',
                                clock=lambda: self.f.now)
        reopened_client = TestClient(create_app(
            access_runtime=runtime,
            memory_collaboration_enabled=True,
            memory_editorial_enabled=True,
        ), base_url='https://photohouse.test', client=('192.0.2.31', 23458))
        self.addCleanup(reopened_client.close)
        reopened_client.headers['Sec-Fetch-Site'] = 'same-origin'
        reopened = reopened_client.get(endpoint, headers=self.owner_headers)
        self.assertEqual(reopened.status_code, 200, reopened.text)
        self.assertEqual(reopened.json(), saved.json())

        legacy_after = self.enabled.get(self.path + '?library=family-a',
                                        headers=self.owner_headers)
        self.assertEqual(legacy_after.status_code, 200, legacy_after.text)
        self.assertEqual(set(legacy_after.json()), set(legacy_before_json))
        self.assertEqual(legacy_after.json()['introduction'], legacy_before_json['introduction'])
        with self.f.connection() as db:
            row = db.execute('SELECT content,revision FROM access_memory_books WHERE id=?',
                             (self.seed.book_id,)).fetchone()
            self.assertEqual(row[0], json.dumps({
                'kind': 'memoir', 'title': 'Editorial memoir', 'language': 'en',
                'introduction': 'Opening words',
                'story_ids': [self.seed.child_one, self.seed.child_two],
            }, ensure_ascii=False, sort_keys=True, separators=(',', ':')))
            self.assertEqual(row[1], 2)

    def test_viewer_read_owner_write_cross_library_denial_and_stale_conflict(self):
        endpoint = self.path + '/editorial?library=family-a'
        raw = self.seed._request(mutation_id=str(uuid.uuid4()))
        written = self.put(self.enabled, raw)
        self.assertEqual(written.status_code, 200, written.text)
        viewer = {'Authorization': 'Bearer ' + self.f.member_token}
        self.assertEqual(self.enabled.get(endpoint, headers=viewer).status_code, 200)
        self.assertNotEqual(self.put(self.enabled, self.seed._request(), headers=viewer).status_code, 200)
        foreign = {'Authorization': 'Bearer ' + self.f.other_token}
        self.assertEqual(self.enabled.get(
            self.path + '/editorial?library=family-b', headers=foreign).status_code, 401)

        stale = self.seed._request(revision='1', mutation_id=str(uuid.uuid4()))
        conflict = self.put(self.enabled, stale)
        self.assertEqual(conflict.status_code, 409, conflict.text)
        replay = self.put(self.enabled, raw)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json(), written.json())
        with self.f.connection() as db:
            self.assertEqual(db.execute(
                'SELECT revision FROM access_memory_books WHERE id=?',
                (self.seed.book_id,)).fetchone()[0], 2)

    def test_put_rejects_malformed_content_type_encoding_oversize_and_extra_query(self):
        endpoint = self.path + '/editorial?library=family-a'
        raw = self.seed._request()
        for headers, expected in (
            ({'Content-Type': 'text/plain'}, 400),
            ({'Content-Type': 'application/json', 'Content-Encoding': 'gzip'}, 400),
        ):
            response = self.enabled.put(endpoint, headers=self.owner_headers | headers,
                                        content=raw)
            self.assertEqual(response.status_code, expected, response.text)
        malformed = self.enabled.put(endpoint,
            headers=self.owner_headers | {'Content-Type': 'application/json'}, content=b'{')
        self.assertEqual(malformed.status_code, 400, malformed.text)
        oversized = self.enabled.put(endpoint,
            headers=self.owner_headers | {'Content-Type': 'application/json'},
            content=b' ' * 65_537)
        self.assertEqual(oversized.status_code, 413, oversized.text)
        extra_query = self.enabled.get(
            self.path + '/editorial?library=family-a&unexpected=1',
            headers=self.owner_headers)
        self.assertEqual(extra_query.status_code, 400, extra_query.text)


if __name__ == '__main__':
    unittest.main()
