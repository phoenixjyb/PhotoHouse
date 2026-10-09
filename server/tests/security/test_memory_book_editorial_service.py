"""Synthetic checks for the default-off memoir editorial domain service."""
from contextlib import closing
import json
import sqlite3
import unittest
import uuid

from sqlalchemy import create_engine

import test_memory_books as book_fixture
from app import db as models
from app.access.metadata import migration_metadata
from app.access.memory_book_editorial import MemoryBookEditorial
from app.access.memory_book_editorial_schema import add_book_editorial_tables
from app.access.memory_contributions import MemoryContributions
from app.access.memory_source_refs import TABLE as SOURCE_REFS_TABLE
from app.access.service import AccessDenied, AccessService
from app.access.transport import TransportError


class MemoryBookEditorialServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        book_fixture.MemoryBookTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        book_fixture.MemoryBookTests.tearDownClass()

    def setUp(self):
        self.base = book_fixture.MemoryBookTests()
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.f = self.base.library_fixture
        self.owner = self.f.owner_token
        self.child_one = self.base.story('Editorial child one', assets='102')
        self.child_two = self.base.story('Editorial child two', assets='101')
        self.source_one = self._accepted_source(self.child_one)
        self.source_two = self._accepted_source(self.child_two)
        self.book = self.base.save(self.owner, self.base.body(
            [self.child_one, self.child_two], title='Editorial memoir'))
        self.book_id = self.book['id']
        self._install_editorial_schema()

    def _accepted_source(self, story_id, *, link=True):
        with self.f.connection() as db:
            access = AccessService(db, clock=lambda: self.f.now)
            created = MemoryContributions(access).create(
                self.f.member_token, 'family-a', story_id, {
                    'kind': 'text', 'text': 'synthetic family contribution',
                    'language': 'en', 'byline': 'synthetic', 'consent': '1',
                    'chapter_id': 'chapter-1', 'revision': '1',
                    'mutation_id': str(uuid.uuid4()),
                })
            accepted = MemoryContributions(access).review(
                self.owner, 'family-a', story_id, created['id'], 'accepted', 1)
            if link:
                db.execute(f'''INSERT INTO {SOURCE_REFS_TABLE}
                    (story_id,revision,chapter_id,ordinal,contribution_id)
                    VALUES(?,1,'chapter-1',0,?)''', (story_id, accepted['id']))
            db.commit()
            return accepted['id']

    def _install_editorial_schema(self):
        with self.f.connection() as db:
            names = {row[0] for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            version = db.execute('SELECT version_num FROM alembic_version').fetchone()[0]
        present = {'access_memory_book_editorial', 'access_memory_book_editorial_refs'} & names
        if not present:
            metadata = migration_metadata(models.Base.metadata)
            editorial, refs = add_book_editorial_tables(metadata)
            engine = create_engine(f'sqlite:///{self.f.path}')
            try:
                editorial.create(engine)
                refs.create(engine)
            finally:
                engine.dispose()
        elif present != {'access_memory_book_editorial', 'access_memory_book_editorial_refs'}:
            self.fail('synthetic editorial schema is partial')
        if version != 'b1d7e4a9c230':
            self.f.mutate("UPDATE alembic_version SET version_num='b1d7e4a9c230'")

    def _service(self, method, *args, token=None, library='family-a', enabled=True):
        with self.f.connection() as db:
            access = AccessService(db, clock=lambda: self.f.now)
            return getattr(MemoryBookEditorial(access, enabled=enabled), method)(
                token or self.owner, library, *args)

    def _request(self, *, revision='1', mutation_id=None, children=None,
                 introduction=None, transition_text='Our shared moment'):
        children = children or [
            {'story_id': self.child_one, 'revision': '1'},
            {'story_id': self.child_two, 'revision': '1'},
        ]
        introduction = introduction or [{
            'story_id': self.child_one, 'story_revision': '1',
            'chapter_id': 'chapter-1', 'contribution_id': self.source_one,
        }]
        return json.dumps({
            'version': 1, 'revision': revision,
            'mutation_id': mutation_id or str(uuid.uuid4()),
            'children': children,
            'introduction_source_refs': introduction,
            'transitions': [{
                'left_story_id': self.child_one, 'right_story_id': self.child_two,
                'text': transition_text,
                'source_refs': [{'story_id': self.child_two, 'story_revision': '1',
                    'chapter_id': 'chapter-1', 'contribution_id': self.source_two}],
            }],
        }, ensure_ascii=False, separators=(',', ':')).encode('utf-8')

    def test_default_off_and_exact_revision_table_gate(self):
        with self.assertRaises(TransportError) as disabled:
            self._service('get', self.book_id, enabled=False)
        self.assertEqual(disabled.exception.status, 503)
        self.f.mutate("UPDATE alembic_version SET version_num='a0c9d2e4f817'")
        with self.assertRaises(TransportError) as old_head:
            self._service('get', self.book_id, enabled=True)
        self.assertEqual(old_head.exception.status, 503)

    def test_save_reopen_keeps_legacy_dto_and_persists_only_opaque_refs(self):
        legacy_before = self.base.domain('get', self.owner, self.book_id)
        raw = self._request()
        saved = self._service('save', self.book_id, raw, enabled=True)
        self.assertEqual(saved['state'], 'current')
        self.assertEqual(saved['revision'], '2')
        self.assertEqual(saved['transitions'][0]['text'], 'Our shared moment')
        self.assertEqual(saved['introduction_source_refs'][0]['contribution_id'], self.source_one)
        legacy_after = self.base.domain('get', self.owner, self.book_id)
        self.assertEqual(set(legacy_before), set(legacy_after))
        self.assertEqual(legacy_after['introduction'], legacy_before['introduction'])
        self.assertEqual(legacy_after['revision'], '2')
        with self.f.connection() as db:
            transition_json = db.execute(
                'SELECT transitions_json FROM access_memory_book_editorial '
                'WHERE book_id=? AND book_revision=2', (self.book_id,)).fetchone()[0]
            refs = db.execute(
                'SELECT section_key,contribution_id FROM access_memory_book_editorial_refs '
                'WHERE book_id=? AND book_revision=2 ORDER BY section_key',
                (self.book_id,)).fetchall()
            self.assertNotIn(self.source_one, transition_json)
            self.assertNotIn(self.source_two, transition_json)
            self.assertEqual(len(refs), 2)
        reopened = self._service('get', self.book_id, enabled=True)
        self.assertEqual(reopened, saved)

    def test_idempotent_replay_and_namespaced_legacy_mutation_receipt(self):
        mutation_id = str(uuid.uuid4())
        raw = self._request(mutation_id=mutation_id)
        saved = self._service('save', self.book_id, raw, enabled=True)
        retry = self._service('save', self.book_id, raw, enabled=True)
        self.assertEqual(retry, saved)
        reformatted = json.dumps(json.loads(raw), indent=2, ensure_ascii=False).encode('utf-8')
        self.assertEqual(self._service('save', self.book_id, reformatted, enabled=True), saved)
        self.assertEqual(retry['revision'], '2')
        changed = self._request(mutation_id=mutation_id, transition_text='Changed')
        with self.assertRaises(TransportError) as reused:
            self._service('save', self.book_id, changed, enabled=True)
        self.assertEqual(reused.exception.status, 409)
        with self.f.connection() as db:
            self.assertEqual(db.execute(
                'SELECT count(*) FROM access_memory_book_editorial WHERE book_id=?',
                (self.book_id,)).fetchone()[0], 1)

    def test_viewer_read_owner_only_write_and_foreign_library_denial(self):
        self._service('save', self.book_id, self._request(), enabled=True)
        viewer_read = self._service('get', self.book_id, token=self.f.member_token,
                                    enabled=True)
        self.assertEqual(viewer_read['state'], 'current')
        with self.assertRaises(AccessDenied):
            self._service('save', self.book_id, self._request(),
                          token=self.f.member_token, enabled=True)
        self.f.mutate("UPDATE access_memberships SET role='contributor' WHERE account_id=?",
                      (self.f.member_id,))
        contributor_book = self.base.save(self.f.member_token,
            self.base.body([self.child_one, self.child_two], title='Contributor memoir'))
        self.assertEqual(self._service('save', contributor_book['id'],
            self._request(mutation_id=str(uuid.uuid4())), token=self.f.member_token,
            enabled=True)['state'], 'current')
        with self.assertRaises(AccessDenied):
            self._service('save', self.book_id,
                          self._request(mutation_id=str(uuid.uuid4())),
                          token=self.f.member_token, enabled=True)
        with self.assertRaises(AccessDenied):
            self._service('get', self.book_id, token=self.f.other_token,
                          library='family-b', enabled=True)

    def test_accepted_contribution_without_current_story_reference_is_not_eligible(self):
        unlinked = self._accepted_source(self.child_one, link=False)
        raw = self._request(introduction=[{
            'story_id': self.child_one, 'story_revision': '1',
            'chapter_id': 'chapter-1', 'contribution_id': unlinked,
        }])
        with self.assertRaises(TransportError) as rejected:
            self._service('save', self.book_id, raw, enabled=True)
        self.assertEqual(rejected.exception.status, 422)
        with self.f.connection() as db:
            self.assertEqual(db.execute(
                'SELECT revision FROM access_memory_books WHERE id=?',
                (self.book_id,)).fetchone()[0], 1)
            self.assertEqual(db.execute(
                'SELECT count(*) FROM access_memory_book_editorial WHERE book_id=?',
                (self.book_id,)).fetchone()[0], 0)

    def test_stale_child_revision_and_stale_book_revision_refuse_without_partial_rows(self):
        # First save advances the memoir revision to 2.
        self._service('save', self.book_id, self._request(), enabled=True)
        stale_book = self._request(revision='1', mutation_id=str(uuid.uuid4()))
        with self.assertRaises(TransportError) as conflict:
            self._service('save', self.book_id, stale_book, enabled=True)
        self.assertEqual(conflict.exception.status, 409)
        # Change the cited story after making an otherwise current book request.
        self.f.mutate("UPDATE access_memory_stories SET revision=revision+1 WHERE id=?",
                      (self.child_one,))
        self.assertEqual(self._service('get', self.book_id, enabled=True)['state'], 'source_changed')
        stale_child = self._request(revision='2', mutation_id=str(uuid.uuid4()))
        with self.assertRaises(TransportError) as changed:
            self._service('save', self.book_id, stale_child, enabled=True)
        self.assertEqual(changed.exception.status, 409)
        with self.f.connection() as db:
            self.assertEqual(db.execute(
                'SELECT revision FROM access_memory_books WHERE id=?',
                (self.book_id,)).fetchone()[0], 2)
            self.assertEqual(db.execute(
                'SELECT count(*) FROM access_memory_book_editorial WHERE book_id=?',
                (self.book_id,)).fetchone()[0], 1)

    def test_consent_revocation_hides_all_editorial_text_and_citations(self):
        self._service('save', self.book_id, self._request(), enabled=True)
        self.f.mutate('UPDATE access_memory_contributions SET local_processing_consent=0 WHERE id=?',
                      (self.source_two,))
        result = self._service('get', self.book_id, enabled=True)
        self.assertEqual(result['state'], 'source_changed')
        self.assertEqual(result['transitions'], [])
        self.assertEqual(result['introduction_source_refs'], [])

    def test_deletion_invalidation_is_hidden_on_reopen(self):
        self._service('save', self.book_id, self._request(), enabled=True)
        from app.access.memory_book_editorial_deletions import invalidate_for_contribution
        with self.f.connection() as db:
            db.execute('PRAGMA secure_delete=ON')
            db.execute('BEGIN IMMEDIATE')
            counts = invalidate_for_contribution(
                db, self.source_two, self.child_two, 'family-a')
            db.commit()
        self.assertEqual(counts.sidecars_invalidated, 1)
        result = self._service('get', self.book_id, enabled=True)
        self.assertEqual(result['state'], 'source_changed')
        self.assertEqual(result['transitions'], [])


if __name__ == '__main__':
    unittest.main()
