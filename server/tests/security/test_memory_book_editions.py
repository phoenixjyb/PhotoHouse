"""Synthetic lifecycle and fail-closed checks for reviewed memoir editions."""
import json
import unittest
import uuid

from sqlalchemy import create_engine

import test_memory_book_editorial_service as editorial_fixture
from app import db as models
from app.access.metadata import migration_metadata
from app.access.memory_book_edition_schema import (
    EDITION_TABLE, SOURCES_TABLE, add_book_edition_tables,
)
from app.access.memory_book_editions import MemoryBookEditions
from app.access.memory_jobs import MemoryJobs, context
from app.access.memory_narrative import validate_narrative
from app.access.service import AccessDenied, AccessService
from app.access.transport import TransportError


class MemoryBookEditionsTests(unittest.TestCase):
    """Reuse editorial's synthetic library, without enabling application routes."""

    @classmethod
    def setUpClass(cls):
        editorial_fixture.MemoryBookEditorialServiceTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        editorial_fixture.MemoryBookEditorialServiceTests.tearDownClass()

    def setUp(self):
        self.base = editorial_fixture.MemoryBookEditorialServiceTests()
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.f = self.base.f
        self.owner = self.base.owner
        self.book_id = self.base.book_id
        self.child_one = self.base.child_one
        self.child_two = self.base.child_two
        self._install_edition_schema()

    def _install_edition_schema(self):
        metadata = migration_metadata(models.Base.metadata)
        editions, sources = add_book_edition_tables(metadata)
        engine = create_engine(f'sqlite:///{self.f.path}')
        try:
            editions.create(engine, checkfirst=True)
            sources.create(engine, checkfirst=True)
        finally:
            engine.dispose()
        self.f.mutate("UPDATE alembic_version SET version_num='c2e6b8a1d490'")

    def _access(self, db):
        return AccessService(db, clock=lambda: self.f.now)

    def _book_revision(self):
        with self.f.connection() as db:
            return db.execute('SELECT revision FROM access_memory_books WHERE id=?',
                              (self.book_id,)).fetchone()[0]

    def _context_fingerprint(self, token, *, principal_neutral=False):
        with self.f.connection() as db:
            access = self._access(db)
            with access._transaction():
                member = access._require(token, 'family-a', 'library.read')
                _, fingerprint, _ = context(access, 'family-a', member, 'book',
                    self.book_id, principal_neutral_fingerprint=principal_neutral)
                return fingerprint

    def _edition(self, method, *args, token=None, library='family-a',
                 enabled=True, editorial_enabled=False, **kwargs):
        with self.f.connection() as db:
            service = MemoryBookEditions(self._access(db), enabled=enabled,
                                         editorial_enabled=editorial_enabled)
            return getattr(service, method)(token or self.owner, library, self.book_id,
                                            *args, **kwargs)

    def _queue_ready_job(self, *, token=None, editorial_context=False):
        token = token or self.owner
        with self.f.connection() as db:
            access = self._access(db)
            queued = MemoryJobs(access, editorial_enabled=editorial_context).narrative(
                token, 'family-a', 'book', self.book_id, str(self._book_revision()),
                str(uuid.uuid4()),
                'Prepare a reviewable family story', editorial_context=editorial_context)
            with access._transaction(write=True):
                member = access._require(token, 'family-a', 'story.write')
                bundle, fingerprint, _ = context(access, 'family-a', member, 'book',
                    self.book_id, editorial_context=editorial_context)
                chapters = []
                for chapter in bundle['chapters']:
                    refs = chapter['evidence_ids'][:1]
                    narration = 'A moment remembered together' if refs else ''
                    chapters.append({'id': chapter['id'], 'narration': narration,
                                     'source_ids': refs})
                output = validate_narrative({
                    'version': 1, 'title': 'A shared family story',
                    'chapters': chapters, 'questions': [], 'needs_review': True,
                }, bundle)
                db.execute('''UPDATE access_memory_jobs SET state='ready',output_json=?,
                    source_fingerprint=?,base_revision=?,updated_at=? WHERE id=?''',
                    (json.dumps(output, ensure_ascii=True, separators=(',', ':')),
                     fingerprint, bundle['target']['revision'], self.f.now, queued['id']))
            return queued['id'], bundle, output

    def _request(self, proposal, *, mutation_id=None, manuscript=None):
        return json.dumps({
            'version': proposal['version'],
            'revision': proposal['revision'],
            'mutation_id': mutation_id or str(uuid.uuid4()),
            'job_id': proposal['job_id'],
            'job_result_sha256': proposal['job_result_sha256'],
            'source_fingerprint': proposal['source_fingerprint'],
            'reviewed': True,
            'children': proposal['children'],
            'manuscript': manuscript or proposal['manuscript'],
        }, ensure_ascii=False, separators=(',', ':')).encode('utf-8')

    def _proposal(self, *, editorial_enabled=False, token=None):
        job_id, _, _ = self._queue_ready_job(token=token,
                                             editorial_context=editorial_enabled)
        return self._edition('proposal', job_id, editorial_enabled=editorial_enabled,
                             token=token), job_id

    def _saved(self, *, mutation_id=None, editorial_enabled=False):
        proposal, job_id = self._proposal(editorial_enabled=editorial_enabled)
        raw = self._request(proposal, mutation_id=mutation_id)
        receipt = self._edition('save', raw, editorial_enabled=editorial_enabled)
        return proposal, raw, receipt, job_id

    def test_default_off_and_missing_or_altered_schema_fail_closed(self):
        job_id, _, _ = self._queue_ready_job()
        with self.assertRaises(TransportError) as off:
            self._edition('proposal', job_id, enabled=False)
        self.assertEqual(off.exception.status, 503)
        self.f.mutate('DROP TRIGGER IF EXISTS trg_memory_book_edition_immutable')
        with self.assertRaises(TransportError) as drift:
            self._edition('proposal', job_id)
        self.assertEqual(drift.exception.status, 503)

    def test_explicit_review_persists_separate_from_needs_review_and_keeps_legacy_book(self):
        before = self.base.base.domain('get', self.owner, self.book_id)
        with self.f.connection() as db:
            revision_count = db.execute(
                'SELECT count(*) FROM access_memory_book_revisions WHERE book_id=?',
                (self.book_id,)).fetchone()[0]
        proposal, raw, receipt, _ = self._saved()
        self.assertEqual(receipt['state'], 'current')
        self.assertEqual(receipt['book_revision'], proposal['revision'])
        reopened = self._edition('get', receipt['id'])
        self.assertEqual(reopened['manuscript']['needs_review'], True)
        self.assertEqual(reopened['manuscript']['title'], proposal['manuscript']['title'])
        self.assertIn(b'"reviewed":true', raw)
        after = self.base.base.domain('get', self.owner, self.book_id)
        self.assertEqual(after, before)
        with self.f.connection() as db:
            self.assertEqual(db.execute(
                'SELECT count(*) FROM access_memory_book_revisions WHERE book_id=?',
                (self.book_id,)).fetchone()[0], revision_count)
            self.assertEqual(db.execute(
                f'SELECT count(*) FROM {EDITION_TABLE} WHERE id=?',
                (receipt['id'],)).fetchone()[0], 1)

    def test_member_cannot_adopt_owner_job_but_can_read_saved_edition(self):
        proposal, _, receipt, _ = self._saved()
        with self.assertRaises(AccessDenied):
            self._edition('save', self._request(proposal), token=self.f.member_token)
        opened = self._edition('get', receipt['id'], token=self.f.member_token)
        self.assertEqual(opened['state'], 'current')

    def test_shared_fingerprint_neutralizes_reader_role_without_changing_private_job_hash(self):
        job_id, _, _ = self._queue_ready_job()
        with self.f.connection() as db:
            private_job_fingerprint = db.execute(
                'SELECT source_fingerprint FROM access_memory_jobs WHERE id=?',
                (job_id,)).fetchone()[0]
        owner_private = self._context_fingerprint(self.owner)
        member_private = self._context_fingerprint(self.f.member_token)
        self.assertEqual(owner_private, private_job_fingerprint)
        self.assertNotEqual(member_private, private_job_fingerprint)
        owner_shared = self._context_fingerprint(self.owner, principal_neutral=True)
        member_shared = self._context_fingerprint(self.f.member_token, principal_neutral=True)
        self.assertEqual(owner_shared, member_shared)

    def test_save_retry_survives_job_pruning_and_changed_body_conflicts(self):
        proposal, raw, receipt, job_id = self._saved(mutation_id=str(uuid.uuid4()))
        self.f.mutate('DELETE FROM access_memory_jobs WHERE id=?', (job_id,))
        self.assertEqual(self._edition('save', raw), receipt)
        changed = json.loads(raw)
        changed['manuscript']['title'] = 'A different reviewed title'
        with self.assertRaises(TransportError) as conflict:
            self._edition('save', json.dumps(changed, ensure_ascii=False).encode('utf-8'))
        self.assertEqual(conflict.exception.status, 409)
        self.assertEqual(self._edition('get', receipt['id'])['manuscript']['title'],
                         proposal['manuscript']['title'])

    def test_expired_job_is_independent_of_saved_edition(self):
        _, _, receipt, job_id = self._saved()
        self.f.mutate('UPDATE access_memory_jobs SET expires_at=? WHERE id=?',
                      (self.f.now + 1, job_id))
        self.f.now += 2
        self.assertEqual(self._edition('get', receipt['id'])['state'], 'current')
        with self.assertRaises(AccessDenied):
            self._edition('proposal', job_id)

    def test_current_book_and_child_revision_changes_hide_retained_prose(self):
        _, _, receipt, _ = self._saved()
        self.base.base.save(self.owner, self.base.base.body(
            [self.child_one, self.child_two], title='Revised memoir', revision='1'),
            self.book_id)
        changed_book = self._edition('get', receipt['id'])
        self.assertEqual(changed_book['state'], 'source_changed')
        self.assertIsNone(changed_book['manuscript'])

        # A separate edition isolates child-revision invalidation.
        _, _, second_receipt, _ = self._saved()
        self.f.mutate('UPDATE access_memory_stories SET revision=revision+1 WHERE id=?',
                      (self.child_one,))
        changed_child = self._edition('get', second_receipt['id'])
        self.assertEqual(changed_child['state'], 'source_changed')
        self.assertIsNone(changed_child['manuscript'])

    def test_full_prompt_closure_includes_uncited_contribution_and_changed_source_hides(self):
        proposal, _, receipt, _ = self._saved()
        cited = {source for chapter in proposal['manuscript']['chapters']
                 for source in chapter['source_ids']}
        with self.f.connection() as db:
            refs = db.execute(f'''SELECT source_id,contribution_id FROM {SOURCES_TABLE}
                WHERE edition_id=?''', (receipt['id'],)).fetchall()
        uncited_contributions = [contribution_id for source_id, contribution_id in refs
                                 if contribution_id and source_id not in cited]
        self.assertTrue(uncited_contributions, 'fixture must include an uncited prompt source')
        self.f.mutate('UPDATE access_memory_contributions SET original_text=? WHERE id=?',
                      ('changed uncited prompt source', uncited_contributions[0]))
        opened = self._edition('get', receipt['id'])
        self.assertEqual(opened['state'], 'source_changed')
        self.assertIsNone(opened['manuscript'])

    def test_incomplete_persisted_source_closure_never_opens_prose(self):
        _, _, receipt, _ = self._saved()
        self.f.mutate(f'''DELETE FROM {SOURCES_TABLE} WHERE edition_id=? AND ordinal=(
            SELECT max(ordinal) FROM {SOURCES_TABLE} WHERE edition_id=?)''',
            (receipt['id'], receipt['id']))
        opened = self._edition('get', receipt['id'])
        self.assertEqual(opened['state'], 'source_changed')
        self.assertIsNone(opened['manuscript'])

    def test_editorial_profile_is_unavailable_when_its_flag_is_off(self):
        self.base._service('save', self.book_id, self.base._request(), enabled=True)
        job_id, _, _ = self._queue_ready_job(editorial_context=True)
        with self.assertRaises(TransportError) as disabled:
            self._edition('proposal', job_id, editorial_enabled=False)
        self.assertEqual(disabled.exception.status, 503)
        proposal = self._edition('proposal', job_id, editorial_enabled=True)
        self.assertEqual(proposal['context_profile'], 'memoir_editorial_v1')

    def test_review_and_all_proposal_bindings_are_required_before_any_new_save(self):
        proposal, _ = self._proposal()
        original = json.loads(self._request(proposal))
        cases = [
            ({'reviewed': False}, 400),
            ({'job_result_sha256': 'f' * 64}, 409),
            ({'source_fingerprint': 'e' * 64}, 409),
            ({'children': list(reversed(original['children']))}, 409),
            ({'revision': '2'}, 409),
        ]
        for changes, expected in cases:
            with self.subTest(changes=tuple(changes)):
                raw = json.dumps(original | changes).encode()
                with self.assertRaises(TransportError) as refused:
                    self._edition('save', raw)
                self.assertEqual(expected, refused.exception.status)
        with self.f.connection() as db:
            self.assertEqual(0, db.execute(f'SELECT count(*) FROM {EDITION_TABLE}').fetchone()[0])

    def test_family_review_can_edit_wording_without_mutating_the_model_job(self):
        proposal, job = self._proposal()
        manuscript = json.loads(json.dumps(proposal['manuscript']))
        manuscript['title'] = 'Our own reviewed title'
        manuscript['chapters'][0]['narration'] = 'We remember this moment; the exact date is uncertain.'
        receipt = self._edition('save', self._request(proposal, manuscript=manuscript))
        opened = self._edition('get', receipt['id'], token=self.f.member_token)
        self.assertEqual(manuscript, opened['manuscript'])
        with self.f.connection() as db:
            output = json.loads(db.execute('SELECT output_json FROM access_memory_jobs WHERE id=?',
                                           (job,)).fetchone()[0])
        self.assertEqual(proposal['manuscript'], output)

    def test_current_library_and_media_access_is_required_after_adoption(self):
        _, _, receipt, _ = self._saved()
        with self.assertRaises(AccessDenied):
            self._edition('get', receipt['id'], token=self.f.other_token)
        self.f.mutate("UPDATE access_asset_libraries SET library_id='family-b' WHERE asset_id=101")
        with self.assertRaises(AccessDenied):
            self._edition('get', receipt['id'])

    def test_paged_edition_list_is_content_free_and_does_not_expose_private_jobs(self):
        _, _, receipt, _ = self._saved()
        listing = self._edition('list', token=self.f.member_token)
        self.assertEqual(False, listing['has_more'])
        self.assertEqual(receipt['id'], listing['items'][0]['id'])
        self.assertEqual('current', listing['items'][0]['state'])
        self.assertIsNone(listing['items'][0]['manuscript'])
        self.assertNotIn('originating_job_id', listing['items'][0])
        with self.assertRaises(TransportError) as invalid_page:
            self._edition('list', page=True)
        self.assertEqual(400, invalid_page.exception.status)


if __name__ == '__main__':
    unittest.main()
