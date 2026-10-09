"""Protected transport and closed-boundary tests for edition source reads."""
import io
import unittest
import uuid
import wave

from fastapi.testclient import TestClient

import test_memory_book_editions as edition_fixture
from app.access.transport import AccessRuntime
from app.access.memory_contributions import MemoryContributions
from app.main import create_app


class MemoryBookEditionSourcesHttpTests(unittest.TestCase):
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
        runtime = AccessRuntime(self.f.connection, 'https://photohouse.test',
                                clock=lambda: self.f.now)
        common = {'access_runtime': runtime, 'memory_collaboration_enabled': True,
                  'memory_editions_enabled': True}
        self.c2_off = TestClient(create_app(access_runtime=runtime,
            memory_collaboration_enabled=True, memory_originals_enabled=True),
            base_url='https://photohouse.test')
        self.off = TestClient(create_app(**common), base_url='https://photohouse.test')
        self.on = TestClient(create_app(**common, memory_originals_enabled=True),
                             base_url='https://photohouse.test')
        self.addCleanup(self.c2_off.close)
        self.addCleanup(self.off.close)
        self.addCleanup(self.on.close)
        for client in (self.c2_off, self.off, self.on):
            client.headers['Sec-Fetch-Site'] = 'same-origin'

    def _get(self, client, url, token=None):
        return client.get(url, headers={'Authorization': 'Bearer ' +
                         (token or self.f.owner_token)})

    def _saved_audio_edition(self):
        audio = io.BytesIO()
        with wave.open(audio, 'wb') as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
            wav.writeframes(b'\0' * 320)
        payload = audio.getvalue()
        with self.f.connection() as db:
            access = edition_fixture.AccessService(db, clock=lambda: self.f.now)
            contributions = MemoryContributions(access)
            item = contributions.create(self.f.member_token, 'family-a', self.seed.child_one, {
                'kind': 'audio', 'text': '', 'language': 'en', 'byline': 'Family',
                'consent': '1', 'chapter_id': '', 'revision': '1',
                'mutation_id': str(uuid.uuid4()),
            }, payload)
            contributions.review(self.f.owner_token, 'family-a', self.seed.child_one,
                                 item['id'], 'accepted', 1)
            with access._transaction(write=True):
                db.execute('''UPDATE access_memory_contribution_derivations
                    SET state='ready',transcript='A current family transcript.'
                    WHERE contribution_id=?''', (item['id'],))
        _proposal, _raw, receipt, _job = self.seed._saved()
        base = (f'/memory-community/v1/books/{self.book_id}/editions/'
                f'{receipt["id"]}/sources?library=family-a')
        listed = self._get(self.on, base)
        self.assertEqual(listed.status_code, 200, listed.text)
        item = next(value for value in listed.json()['items']
                    if value['source_id'] == 'contribution-' + item['id'])
        source_path = base.split('?')[0] + '/' + item['source_id'] + '?library=family-a'
        return receipt, source_path, payload

    def test_originals_are_separately_gated_and_boundary_is_exact(self):
        _proposal, _raw, receipt, _job = self.seed._saved()
        base = (f'/memory-community/v1/books/{self.book_id}/editions/'
                f'{receipt["id"]}/sources?library=family-a')
        self.assertEqual(self._get(self.off, base).status_code, 503)
        listed = self._get(self.on, base)
        self.assertEqual(listed.status_code, 200, listed.text)
        item = next(value for value in listed.json()['items']
                    if value['source_id'].startswith('contribution-'))
        detail_path = base.split('?')[0] + '/' + item['source_id'] + '?library=family-a'
        detail = self._get(self.on, detail_path)
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(detail.json()['source']['origin'], 'contribution_text')
        self.assertEqual(self._get(self.on, detail_path, self.f.member_token).status_code, 200)
        self.assertEqual(self._get(self.on, detail_path,
            self.f.other_token).status_code, 401)
        self.assertEqual(self._get(self.on, detail_path.replace('/sources/', '/sources_extra/')).status_code, 403)
        self.assertEqual(detail.headers['cache-control'], 'no-store')

    def test_c2_off_rejects_an_authenticated_source_request(self):
        path = (f'/memory-community/v1/books/{self.book_id}/editions/'
                f'{uuid.uuid4()}/sources?library=family-a')
        response = self._get(self.c2_off, path)
        self.assertEqual(response.status_code, 503, response.text)

    def test_membership_and_child_media_revocation_deny_detail_and_audio(self):
        _receipt, source_path, payload = self._saved_audio_edition()
        member_detail = self._get(self.on, source_path, self.f.member_token)
        self.assertEqual(member_detail.status_code, 200, member_detail.text)
        audio_path = source_path.replace('?library=', '/audio?library=')
        member_audio = self._get(self.on, audio_path, self.f.member_token)
        self.assertEqual(member_audio.status_code, 200, member_audio.text)
        self.assertEqual(member_audio.content, payload)

        self.f.mutate('DELETE FROM access_memberships WHERE library_id=? AND account_id=?',
                      ('family-a', self.f.member_id))
        revoked_detail = self._get(self.on, source_path, self.f.member_token)
        revoked_audio = self._get(self.on, audio_path, self.f.member_token)
        self.assertEqual(revoked_detail.status_code, 401, revoked_detail.text)
        self.assertEqual(revoked_audio.status_code, 401, revoked_audio.text)
        self.assertNotEqual(revoked_audio.content, payload)

        self.f.mutate('DELETE FROM access_asset_libraries WHERE library_id=? AND asset_id=?',
                      ('family-a', 102))
        unlinked_detail = self._get(self.on, source_path)
        unlinked_audio = self._get(self.on, audio_path)
        self.assertEqual(unlinked_detail.status_code, 401, unlinked_detail.text)
        self.assertEqual(unlinked_audio.status_code, 401, unlinked_audio.text)
        self.assertNotEqual(unlinked_audio.content, payload)

    def test_changed_book_keeps_saved_revision_and_audio_returns_conflict_without_bytes(self):
        receipt, source_path, payload = self._saved_audio_edition()
        base_path, query = source_path.split('?', 1)
        list_path = base_path.rsplit('/sources/', 1)[0] + '/sources?' + query
        saved_revision = receipt['book_revision']
        self.seed.base.base.save(self.f.owner_token, self.seed.base.base.body(
            [self.seed.child_one, self.seed.child_two], title='Revised memoir', revision='1'),
            self.book_id)

        listed = self._get(self.on, list_path)
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual(listed.json()['state'], 'source_changed')
        self.assertEqual(listed.json()['book_revision'], saved_revision)
        detail = self._get(self.on, source_path)
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(detail.json()['state'], 'source_changed')
        self.assertEqual(detail.json()['book_revision'], saved_revision)
        audio = self._get(self.on, source_path.replace('?library=', '/audio?library='))
        self.assertEqual(audio.status_code, 409, audio.text)
        self.assertNotEqual(audio.content, payload)
