"""Protected HTTP contract for separately retained, reviewed memoir editions."""
import json
import unittest
import uuid

from fastapi.testclient import TestClient

import test_memory_book_editions as edition_fixture
from app.access.memory_book_edition_deletions import invalidate_editions_for_contribution
from app.access.transport import AccessRuntime
from app.main import create_app


class MemoryBookEditionHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        edition_fixture.MemoryBookEditionsTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        edition_fixture.MemoryBookEditionsTests.tearDownClass()

    def setUp(self):
        self.seed = edition_fixture.MemoryBookEditionsTests()
        self.seed.setUp()
        self.addCleanup(self.seed.doCleanups)
        self.f = self.seed.f
        self.book_id = self.seed.book_id
        self.path = f'/memory-community/v1/books/{self.book_id}'
        runtime = AccessRuntime(self.f.connection, 'https://photohouse.test',
                                clock=lambda: self.f.now)
        common = {'access_runtime': runtime, 'memory_collaboration_enabled': True}
        self.disabled = TestClient(create_app(**common), base_url='https://photohouse.test',
                                   client=('192.0.2.41', 23461))
        self.addCleanup(self.disabled.close)
        self.enabled = TestClient(create_app(**common, memory_editions_enabled=True),
                                  base_url='https://photohouse.test',
                                  client=('192.0.2.41', 23461))
        self.addCleanup(self.enabled.close)
        for client in (self.disabled, self.enabled):
            client.headers['Sec-Fetch-Site'] = 'same-origin'

    @property
    def owner_headers(self):
        return {'Authorization': 'Bearer ' + self.f.owner_token}

    @property
    def member_headers(self):
        return {'Authorization': 'Bearer ' + self.f.member_token}

    def request(self, client, method, path, *, token=None, body=None, headers=None):
        request_headers = dict(headers or {'Authorization': 'Bearer ' +
                                           (token or self.f.owner_token)})
        if body is not None:
            request_headers.setdefault('Content-Type', 'application/json')
        return client.request(method, path, headers=request_headers, content=body)

    def query(self, suffix='', library='family-a'):
        return f'{suffix}?library={library}'

    def _draft(self, *, client=None, token=None):
        job_id, _, _ = self.seed._queue_ready_job()
        response = self.request(client or self.enabled, 'GET',
            self.query(f'{self.path}/editions/proposals/{job_id}'), token=token)
        return job_id, response

    def _save(self, *, client=None, token=None, mutation_id=None):
        job_id, proposal_response = self._draft(client=client, token=token)
        self.assertEqual(proposal_response.status_code, 200, proposal_response.text)
        proposal = proposal_response.json()
        raw = self.seed._request(proposal, mutation_id=mutation_id)
        saved = self.request(client or self.enabled, 'POST', self.query(f'{self.path}/editions'),
                             token=token, body=raw)
        return job_id, proposal, raw, saved

    def test_capabilities_authentication_default_off_and_exact_schema_gate(self):
        endpoint = self.query(f'{self.path}/edition-capabilities')
        self.assertEqual(self.disabled.get(endpoint).status_code, 401)
        response = self.request(self.disabled, 'GET', endpoint)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {'version': 1, 'enabled': False, 'can_save': False})
        self.assertEqual(self.request(self.disabled, 'GET',
            self.query(f'{self.path}/editions/proposals/{uuid.uuid4()}')).status_code, 503)
        self.assertEqual(self.request(self.disabled, 'GET',
            self.query(f'{self.path}/editions')).status_code, 503)
        self.assertEqual(self.request(self.disabled, 'GET',
            self.query(f'{self.path}/editions/{uuid.uuid4()}')).status_code, 503)
        self.assertEqual(self.request(self.disabled, 'POST',
            self.query(f'{self.path}/editions'), body=b'{}').status_code, 503)

        exact = self.request(self.enabled, 'GET', endpoint)
        self.assertEqual(exact.status_code, 200, exact.text)
        self.assertEqual(exact.json(), {'version': 1, 'enabled': True, 'can_save': True})
        self.f.mutate('DROP TRIGGER IF EXISTS trg_memory_book_edition_immutable')
        drift = self.request(self.enabled, 'GET', endpoint)
        self.assertEqual(drift.status_code, 503, drift.text)

    def test_create_app_requires_boolean_opt_in_and_collaboration(self):
        with self.assertRaises(ValueError):
            create_app(memory_collaboration_enabled=True, memory_editions_enabled=1)
        with self.assertRaises(ValueError):
            create_app(memory_editions_enabled=True)

    def test_proposal_save_get_list_member_and_wrong_library_contract(self):
        self.assertFalse(self.enabled.app.state.memory_generation_enabled)
        job_id, proposal_response = self._draft()
        self.assertEqual(proposal_response.status_code, 200, proposal_response.text)
        proposal = proposal_response.json()
        self.assertTrue(proposal['needs_review'])
        raw = self.seed._request(proposal)
        saved = self.request(self.enabled, 'POST', self.query(f'{self.path}/editions'), body=raw)
        self.assertEqual(saved.status_code, 200, saved.text)
        receipt = saved.json()
        self.assertEqual(receipt['book_id'], self.book_id)
        self.assertEqual(saved.headers['cache-control'], 'no-store')

        opened = self.request(self.enabled, 'GET',
            self.query(f'{self.path}/editions/{receipt["id"]}'))
        self.assertEqual(opened.status_code, 200, opened.text)
        self.assertEqual(opened.json()['manuscript'], proposal['manuscript'])
        listed = self.request(self.enabled, 'GET', self.query(f'{self.path}/editions'))
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual(len(listed.json()['items']), 1)
        self.assertIsNone(listed.json()['items'][0]['manuscript'])

        member_read = self.request(self.enabled, 'GET',
            self.query(f'{self.path}/editions/{receipt["id"]}'), headers=self.member_headers)
        self.assertEqual(member_read.status_code, 200, member_read.text)
        self.assertEqual(member_read.json()['state'], 'current')
        member_adopt = self.request(self.enabled, 'GET',
            self.query(f'{self.path}/editions/proposals/{job_id}'), headers=self.member_headers)
        self.assertNotEqual(member_adopt.status_code, 200)
        foreign = self.request(self.enabled, 'GET',
            self.query(f'{self.path}/editions/{receipt["id"]}', library='family-a'),
            headers={'Authorization': 'Bearer ' + self.f.other_token})
        self.assertNotEqual(foreign.status_code, 200)

    def test_membership_and_child_media_revocation_close_reads(self):
        _job_id, _proposal, _raw, saved = self._save()
        self.assertEqual(saved.status_code, 200, saved.text)
        edition_id = saved.json()['id']
        member_open = self.request(self.enabled, 'GET',
            self.query(f'{self.path}/editions/{edition_id}'), headers=self.member_headers)
        self.assertEqual(member_open.status_code, 200, member_open.text)
        self.f.mutate('DELETE FROM access_memberships WHERE library_id=? AND account_id=?',
                      ('family-a', self.f.member_id))
        revoked_member = self.request(self.enabled, 'GET',
            self.query(f'{self.path}/editions/{edition_id}'), headers=self.member_headers)
        self.assertEqual(revoked_member.status_code, 401, revoked_member.text)

        self.f.mutate('DELETE FROM access_asset_libraries WHERE library_id=? AND asset_id=?',
                      ('family-a', 102))
        revoked_media = self.request(self.enabled, 'GET',
            self.query(f'{self.path}/editions/{edition_id}'))
        self.assertEqual(revoked_media.status_code, 401, revoked_media.text)

    def test_exact_retry_after_job_prune_and_changed_body_conflict(self):
        job_id, _proposal, raw, saved = self._save(mutation_id=str(uuid.uuid4()))
        self.assertEqual(saved.status_code, 200, saved.text)
        self.f.mutate('DELETE FROM access_memory_jobs WHERE id=?', (job_id,))
        retry = self.request(self.enabled, 'POST', self.query(f'{self.path}/editions'), body=raw)
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertEqual(retry.json(), saved.json())
        changed = json.loads(raw)
        changed['manuscript']['title'] = 'Changed after review'
        conflict = self.request(self.enabled, 'POST', self.query(f'{self.path}/editions'),
            body=json.dumps(changed, ensure_ascii=False).encode('utf-8'))
        self.assertEqual(conflict.status_code, 409, conflict.text)

    def test_original_deletion_scrubs_saved_prose_and_reader_never_gets_stale_content(self):
        _job_id, _proposal, _raw, saved = self._save()
        self.assertEqual(saved.status_code, 200, saved.text)
        contribution_id = self.seed.base.source_one
        with self.f.connection() as db:
            db.execute('PRAGMA secure_delete=ON')
            db.execute('BEGIN IMMEDIATE')
            counts = invalidate_editions_for_contribution(
                db, contribution_id, self.seed.child_one, 'family-a')
            db.commit()
        self.assertEqual(counts.editions_scrubbed, 1)
        edition_id = saved.json()['id']
        opened = self.request(self.enabled, 'GET',
            self.query(f'{self.path}/editions/{edition_id}'))
        self.assertEqual(opened.status_code, 200, opened.text)
        self.assertEqual(opened.json()['state'], 'source_invalidated')
        self.assertIsNone(opened.json()['manuscript'])
        listed = self.request(self.enabled, 'GET', self.query(f'{self.path}/editions'))
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertIsNone(listed.json()['items'][0]['manuscript'])
        self.assertNotIn('A shared family story', opened.text)

    def test_save_prechecks_book_edit_before_reading_strict_bounded_body(self):
        endpoint = self.query(f'{self.path}/editions')
        unauthorized = self.request(self.enabled, 'POST', endpoint,
            headers=self.member_headers | {'Content-Type': 'text/plain'}, body=b'bad')
        self.assertNotEqual(unauthorized.status_code, 400)
        self.assertNotEqual(unauthorized.status_code, 200)

        job_id, proposal_response = self._draft()
        self.assertEqual(proposal_response.status_code, 200, proposal_response.text)
        raw = self.seed._request(proposal_response.json())
        duplicate = raw.replace(b'"version":1', b'"version":1,"version":1', 1)
        response = self.request(self.enabled, 'POST', endpoint, body=duplicate)
        self.assertEqual(response.status_code, 400, response.text)
        oversized = self.request(self.enabled, 'POST', endpoint,
            body=b' ' * (128 * 1024 + 1))
        self.assertEqual(oversized.status_code, 413, oversized.text)
        compressed = self.request(self.enabled, 'POST', endpoint,
            headers=self.owner_headers | {'Content-Type': 'application/json',
                                          'Content-Encoding': 'gzip'}, body=raw)
        self.assertEqual(compressed.status_code, 400, compressed.text)
        noncanonical_length = self.request(self.enabled, 'POST', endpoint,
            headers=self.owner_headers | {'Content-Type': 'application/json',
                                          'Content-Length': '01'}, body=b'{}')
        self.assertEqual(noncanonical_length.status_code, 400, noncanonical_length.text)
        excessive_length = self.request(self.enabled, 'POST', endpoint,
            headers=self.owner_headers | {'Content-Type': 'application/json',
                                          'Content-Length': str(128 * 1024 + 1)}, body=b'{}')
        self.assertEqual(excessive_length.status_code, 413, excessive_length.text)
        invalid_utf8 = self.request(self.enabled, 'POST', endpoint,
            body=b'{"invalid":"\xed\xa0\x80"}')
        self.assertEqual(invalid_utf8.status_code, 400, invalid_utf8.text)

        extra = self.request(self.enabled, 'GET', endpoint + '&ignored=1')
        self.assertEqual(extra.status_code, 400, extra.text)
        duplicate_query = self.request(self.enabled, 'GET', endpoint + '&library=family-a')
        self.assertEqual(duplicate_query.status_code, 400, duplicate_query.text)
        bad_page = self.request(self.enabled, 'GET',
            f'{self.path}/editions?library=family-a&page=00')
        self.assertEqual(bad_page.status_code, 400, bad_page.text)


if __name__ == '__main__':
    unittest.main()
