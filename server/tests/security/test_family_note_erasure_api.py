"""Synthetic HTTP authority, CAS and default-off family-note erasure checks."""
from pathlib import Path
import tempfile
import unittest
import uuid

from fastapi.testclient import TestClient
import test_library_reads as fixture
from app.access.original_deletions import OriginalDeletionJournal
from app.access.runtime import ExistingDatabase
from app.access.service import AccessService
from app.access.stories import Stories
from app.access.transport import AccessRuntime
from app.main import create_app


class FamilyNoteErasureApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.LibraryReadTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        fixture.LibraryReadTests.tearDownClass()

    def setUp(self):
        self.f = fixture.LibraryReadTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.tmp = tempfile.TemporaryDirectory(prefix='photohouse-note-erasure-')
        self.addCleanup(self.tmp.cleanup)
        self.journal = OriginalDeletionJournal.initialize(Path(self.tmp.name).resolve() / 'ledger.sqlite',
                                                         str(uuid.uuid4()), format_version=2)
        with self.f.connection() as db:
            self.journal.bind(db)
        self.database = ExistingDatabase(self.f.path.resolve(), original_deletions=self.journal)
        self.runtime = AccessRuntime(self.database, 'https://photohouse.test', clock=lambda: self.f.now)
        with self.database() as db:
            self.note = Stories(AccessService(db, clock=lambda: self.f.now)).save(self.f.owner_token,
                'family-a', dict(title='Synthetic', text='Raw original secret', language='en',
                                 byline='Relative', mutation_id=str(uuid.uuid4())), asset_id=101)
        self.path = '/stories/' + self.note['id'] + '/original?library=family-a'

    def client(self, enabled=False):
        client = TestClient(create_app(access_runtime=self.runtime,
                family_note_erasure_enabled=enabled), base_url='https://photohouse.test')
        self.addCleanup(client.close)
        return client

    def erase(self, client, revision='1', token=None, path=None):
        return client.request('DELETE', path or self.path, json={'revision': revision},
                              headers={'Authorization': 'Bearer ' + (token or self.f.owner_token)})

    def rows(self, query):
        with self.database() as db:
            return db.execute(query).fetchall()

    def test_default_off_and_explicit_boolean(self):
        self.assertEqual(self.erase(self.client()).status_code, 503)
        self.assertEqual(self.journal.head()[1], 0)
        for flag in (1, 'true', None):
            with self.subTest(flag=flag), self.assertRaises(ValueError):
                create_app(family_note_erasure_enabled=flag)

    def test_owner_purges_history_and_exact_retry_is_idempotent(self):
        client = self.client(True)
        result = self.erase(client)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json(), {'deleted': True, 'id': self.note['id']})
        self.assertEqual(self.erase(client).json(), result.json())
        self.assertEqual(self.journal.head()[1], 1)
        self.assertEqual(self.rows('SELECT count(*) FROM access_stories'), [(0,)])
        self.assertEqual(self.rows('SELECT count(*) FROM access_story_revisions'), [(0,)])
        self.assertEqual(self.rows('SELECT count(*) FROM access_family_note_identities'), [(1,)])
        self.assertEqual(self.rows("SELECT count(*) FROM access_audit WHERE action='story.original_erase'"), [(1,)])
        self.assertEqual(self.erase(client, revision='2').status_code, 409)

    def test_member_foreign_library_and_revision_refuse_before_append(self):
        client = self.client(True)
        self.assertEqual(self.erase(client, token=self.f.member_token).status_code, 401)
        self.assertEqual(self.erase(client, path=self.path.replace('family-a', 'family-b')).status_code, 401)
        self.assertEqual(self.erase(client, revision='2').status_code, 409)
        for revision in (1, True, '01', '0'):
            with self.subTest(revision=revision):
                self.assertEqual(self.erase(client, revision=revision).status_code, 400)
        self.assertEqual(self.journal.head()[1], 0)
        self.assertEqual(self.rows('SELECT count(*) FROM access_stories'), [(1,)])

    def test_current_owner_cannot_erase_editions_in_another_historical_scope(self):
        with self.database() as db:
            db.execute('BEGIN IMMEDIATE')
            identity = db.execute('SELECT identity_id FROM access_family_note_identities WHERE note_id=?',
                                   (self.note['id'],)).fetchone()[0]
            db.execute("INSERT INTO access_family_note_scopes VALUES(?,1,'family-a','family-b',?,?,?)",
                       (identity, str(uuid.uuid4()), 'a' * 64, self.f.now))
            db.execute("UPDATE access_stories SET library_id='family-b' WHERE id=?", (self.note['id'],))
            db.execute("UPDATE access_asset_libraries SET library_id='family-b' WHERE asset_id=101")
            db.commit()
        result = self.erase(self.client(True), token=self.f.other_token,
                            path=self.path.replace('family-a', 'family-b'))
        self.assertEqual(result.status_code, 401)
        self.assertEqual(self.journal.head()[1], 0)
        self.assertEqual(self.rows('SELECT count(*) FROM access_stories'), [(1,)])

    def test_revoked_asset_membership_refuses_without_append(self):
        self.f.mutate("DELETE FROM access_asset_libraries WHERE asset_id=101")
        self.assertEqual(self.erase(self.client(True)).status_code, 401)
        self.assertEqual(self.journal.head()[1], 0)

    def test_browser_cookie_requires_csrf_before_erasure(self):
        from app.access.transport import COOKIE, csrf_token
        client = self.client(True)
        client.cookies.set(COOKIE, self.f.owner_token)
        headers = {'Origin': 'https://photohouse.test', 'Sec-Fetch-Site': 'same-origin'}
        denied = client.request('DELETE', self.path, json={'revision': '1'}, headers=headers)
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(self.journal.head()[1], 0)
        result = client.request('DELETE', self.path, json={'revision': '1'},
                                headers=dict(headers, **{'X-CSRF-Token': csrf_token(self.f.owner_token)}))
        self.assertEqual(result.status_code, 200, result.text)

    def test_schema_drift_refuses_without_durable_tombstone(self):
        self.f.mutate('DROP TRIGGER trg_family_note_no_reuse')
        result = self.erase(self.client(True))
        self.assertEqual(result.status_code, 503, result.text)
        self.assertEqual(self.journal.head()[1], 0)
        self.assertNotIn('Raw original secret', result.text)

    def test_soft_removed_note_can_be_permanently_erased(self):
        with self.database() as db:
            Stories(AccessService(db, clock=lambda: self.f.now)).save(self.f.owner_token, 'family-a',
                {'revision': '1', 'mutation_id': str(uuid.uuid4())}, story_id=self.note['id'], delete=True)
        result = self.erase(self.client(True), revision='2')
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(self.rows('SELECT count(*) FROM access_story_revisions'), [(0,)])

    def test_failure_after_purge_rolls_back_primary_and_replay_finishes_durable_delete(self):
        from unittest.mock import patch
        from app.access.family_note_deletions import erase_family_note_original
        from app.access.original_deletions import OriginalDeletionError
        def fail_after_purge(db, record):
            erase_family_note_original(db, record)
            raise OriginalDeletionError('synthetic failure after purge')
        client = self.client(True)
        with patch('app.access.family_note_deletions.erase_family_note_original', side_effect=fail_after_purge):
            result = self.erase(client)
        self.assertEqual(result.status_code, 503)
        self.assertEqual(self.journal.head()[1], 1)
        with self.f.connection() as db:
            self.assertEqual(db.execute('SELECT text FROM access_stories').fetchone(), ('Raw original secret',))
            self.assertEqual(db.execute('SELECT count(*) FROM access_story_revisions').fetchone(), (1,))
            self.assertEqual(db.execute('SELECT applied_seq FROM access_original_deletion_state').fetchone(), (0,))
            self.assertEqual(db.execute("SELECT count(*) FROM access_audit WHERE action='story.original_erase'").fetchone(), (0,))
            self.journal.replay(db)
        self.assertEqual(self.erase(client).status_code, 200)
        self.assertEqual(self.rows('SELECT count(*) FROM access_stories'), [(0,)])

    def test_pending_marker_closes_api_until_offline_replay(self):
        with self.database() as db:
            db.execute('PRAGMA secure_delete=ON')
            db.execute('BEGIN IMMEDIATE')
            self.journal.append(db, 'family_note', {'id': self.note['id'], 'revision': 1}, self.f.now)
            db.rollback()
        client = self.client(True)
        self.assertEqual(self.erase(client).status_code, 503)
        with self.f.connection() as db:
            self.journal.replay(db)
        self.assertEqual(self.erase(client).status_code, 200)
