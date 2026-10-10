"""HTTP grouping contracts with generated media/vector fixtures only."""
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from fastapi.testclient import TestClient
import test_memory_groups as fixture
import test_visual_vector_loader as vectors
from app.main import create_app
from app.access.memory_group_transport import GroupVectorConfiguration
from app.access.transport import COOKIE, csrf_token
from app.access.visual_vector_schema import create_visual_vector_schema


class MemoryGroupRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): fixture.MemoryGroupTests.setUpClass()

    @classmethod
    def tearDownClass(cls): fixture.MemoryGroupTests.tearDownClass()

    def setUp(self):
        self.base = fixture.MemoryGroupTests()
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.f = self.base.f
        self.runtime = self.f.client.app.state.access_runtime
        directory = tempfile.TemporaryDirectory(prefix='group-route-vectors-')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.config = GroupVectorConfiguration(self.root, vectors.IDENTITY)
        self.client = self.build(vectors_config=self.config)
        self.owner_headers = {'Authorization': 'Bearer ' + self.base.owner}
        self.member_headers = {'Authorization': 'Bearer ' + self.base.member}

    def build(self, *, enabled=True, vectors_config=None):
        return TestClient(create_app(access_runtime=self.runtime,
            memory_groups_enabled=enabled, memory_group_vectors=vectors_config),
            base_url='https://photohouse.test', client=('192.0.2.20', 23456))

    def request(self, method, path, body=None, *, headers=None, library='family-a', client=None):
        return (client or self.client).request(method, path + '?library=' + library,
            headers=self.owner_headers if headers is None else headers, json=body)

    def install_vectors(self):
        with self.f.connection() as db:
            create_visual_vector_schema(db)
            db.execute('UPDATE assets SET hash_sha256=?,taken_at=? WHERE id=101',
                       (vectors.SOURCE_A, '2026-01-01T10:00:00+08:00'))
            db.execute('UPDATE assets SET hash_sha256=?,taken_at=? WHERE id=102',
                       (vectors.SOURCE_B, '2026-01-01T11:00:00+08:00'))
            db.commit()
            helper = SimpleNamespace(db=db, root=self.root)
            vectors.VisualVectorLoaderTests.add_vector(helper, 101, (1.0, 0.0))
            vectors.VisualVectorLoaderTests.add_vector(helper, 102, (0.99503719, 0.09950372))

    def test_default_off_and_authorization_precede_availability(self):
        off = self.build(enabled=False)
        caps = self.request('GET', '/memory-groups/capabilities', client=off)
        self.assertEqual(caps.status_code, 200, caps.text)
        self.assertFalse(caps.json()['enabled'])
        self.assertEqual(self.request('GET', '/assets/101/memory-groups', client=off).status_code, 503)
        self.assertEqual(self.request('GET', '/memory-groups/capabilities', headers={}).status_code, 401)
        self.assertEqual(self.request('GET', '/memory-groups/capabilities', library='family-b').status_code, 401)
        manual = self.request('GET', '/memory-groups/capabilities', client=self.build()).json()
        self.assertTrue(manual['manual'])
        self.assertFalse(manual['suggestions'])

    def test_real_loader_combines_time_and_similarity_and_exclusions(self):
        self.install_vectors()
        body = {'asset_ids': '101', 'excluded_asset_ids': ''}
        result = self.request('POST', '/memory-groups/proposals', body)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.headers['cache-control'], 'no-store')
        self.assertEqual([row['id'] for row in result.json()['items']], ['102'])
        self.assertEqual(result.json()['items'][0]['thumbnail_url'], '/assets/102/thumbnail?library=family-a')
        self.assertEqual(result.json()['items'][0]['matched_seed_asset_id'], '101')
        self.assertTrue(result.json()['needs_review'])
        self.assertNotIn('synthetic-space', result.text)
        self.assertNotIn(str(self.root), result.text)
        body['excluded_asset_ids'] = '102'
        self.assertEqual(self.request('POST', '/memory-groups/proposals', body).json()['items'], [])
        body['excluded_asset_ids'] = ''
        self.f.mutate("UPDATE assets SET taken_at='2026-01-03T11:00:00+08:00' WHERE id=102")
        self.assertEqual(self.request('POST', '/memory-groups/proposals', body).json()['items'], [])

    def test_unavailable_still_checks_all_seeds_and_never_saves_a_group(self):
        self.f.trace.clear()
        body = {'asset_ids': '101', 'excluded_asset_ids': ''}
        response = self.request('POST', '/memory-groups/proposals', body)
        self.assertEqual(response.json()['status'], 'unavailable')
        self.assertFalse(any(sql.lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE'))
                             for sql in self.f.trace))
        body['asset_ids'] = '101,201'
        self.assertEqual(self.request('POST', '/memory-groups/proposals', body).status_code, 401)
        self.assertEqual(self.request('POST', '/memory-groups/proposals', body,
                                     client=self.build()).status_code, 401)

    def test_save_share_latest_source_and_manual_edit(self):
        note = self.base.note()
        body = self.base.body(sources=note['id'])
        created = self.request('POST', '/memory-groups', body)
        self.assertEqual(created.status_code, 201, created.text)
        group = created.json()
        shared = self.request('GET', '/assets/102/memory-groups', headers=self.member_headers)
        self.assertEqual(shared.json()['items'][0]['sources'][0]['text'], note['text'])
        self.assertEqual(shared.json()['items'][0]['sources'][0]['author_id'], note['author_id'])
        self.base.edit_note(note, revision=note['revision'], title='Edited', text='New original words')
        current = self.request('GET', '/memory-groups/' + group['id']).json()
        self.assertEqual(current['sources'][0]['text'], 'New original words')
        body.update(asset_ids='101', excluded_asset_ids='102', revision=group['revision'],
                    mutation_id=self.base.body()['mutation_id'])
        updated = self.request('PUT', '/memory-groups/' + group['id'], body)
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()['excluded_asset_ids'], ['102'])
        self.assertEqual(self.request('GET', '/assets/102/memory-groups').json()['items'], [])
        repeat = self.request('PUT', '/memory-groups/' + group['id'], body)
        self.assertEqual(repeat.json()['revision'], updated.json()['revision'])
        stale = dict(body, mutation_id=self.base.body()['mutation_id'])
        self.assertEqual(self.request('PUT', '/memory-groups/' + group['id'], stale).status_code, 409)

    def test_csrf_revocation_and_whole_group_authorization(self):
        body = self.base.body()
        cookie = {'Cookie': COOKIE + '=' + self.base.owner}
        self.assertEqual(self.request('POST', '/memory-groups', body, headers=cookie).status_code, 403)
        cookie.update(Origin='https://photohouse.test', **{'X-CSRF-Token': csrf_token(self.base.owner)})
        created = self.request('POST', '/memory-groups', body, headers=cookie)
        self.assertEqual(created.status_code, 201, created.text)
        self.f.mutate("UPDATE assets SET status='deleted' WHERE id=102")
        self.assertEqual(self.request('GET', '/memory-groups/' + created.json()['id']).status_code, 401)
        self.assertEqual(self.request('GET', '/assets/101/memory-groups').json()['items'], [])
        self.f.mutate("UPDATE access_memberships SET status='revoked' WHERE account_id=? AND library_id='family-a'",
                      (self.f.member_id,))
        self.assertEqual(self.request('GET', '/assets/101/memory-groups', headers=self.member_headers).status_code, 401)

    def test_explicit_config_and_unknown_routes_are_refused(self):
        for kwargs in ({'memory_groups_enabled': 1},
                       {'memory_group_vectors': self.config},
                       {'memory_groups_enabled': True, 'memory_group_vectors': object()}):
            with self.assertRaises(ValueError): create_app(**kwargs)
        self.assertEqual(self.request('DELETE', '/memory-groups/' + 'a' * 36).status_code, 403)
        self.assertEqual(self.request('POST', '/memory-groups/proposals',
            {'asset_ids': '0101', 'excluded_asset_ids': ''}).status_code, 400)
