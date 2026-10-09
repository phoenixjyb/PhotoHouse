"""Synthetic original identity, scope move and accepted-edition contracts."""
from contextlib import closing
from dataclasses import replace
import json
import sqlite3
import unittest
import uuid

import test_library_reads as library_fixture
import test_promotion as promotion_fixture
import test_memory_book_editions as edition_fixture
import test_memory_book_edition_provenance as provenance_fixture
from app.access.family_note_identity import (identity_enabled, resolve_note_identity,
    verify_family_note_identity_schema)
from app.access.family_note_identity_schema import (IDENTITIES, SCOPES, EDITION_NOTES, IDENTITY_REVISION)
from app.access.memory_book_edition_provenance import build_edition_provenance
from app.access.promotion import reassign_assets
from app.access.service import AccessService
from app.access.stories import Stories
from app.access.transport import TransportError


def body(**changes):
    return dict(title='Private synthetic title', text='Private original words', language='en',
                byline='Private byline', mutation_id=str(uuid.uuid4()), **changes)


class FamilyNoteIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        library_fixture.LibraryReadTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        library_fixture.LibraryReadTests.tearDownClass()

    def setUp(self):
        self.f = library_fixture.LibraryReadTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)

    def save(self, request=None, **kwargs):
        with self.f.connection() as db:
            return Stories(AccessService(db, clock=lambda: self.f.now)).save(
                self.f.owner_token, 'family-a', request or body(), **kwargs)

    def rows(self, sql, args=()):
        with self.f.connection() as db:
            return db.execute(sql, args).fetchall()

    def test_create_and_exact_retry_have_one_content_free_original_identity(self):
        request = body()
        note = self.save(request, asset_id=101)
        self.assertEqual(self.save(request, asset_id=101)['id'], note['id'])
        identities = self.rows(f'SELECT * FROM {IDENTITIES}')
        scopes = self.rows(f'SELECT * FROM {SCOPES}')
        self.assertEqual(len(identities), 1)
        self.assertEqual(len(scopes), 1)
        identity = identities[0]
        self.assertNotEqual(identity[0], note['id'])
        self.assertEqual(identity[1:3], (note['id'], 101))
        for value in request.values():
            self.assertNotIn(value, json.dumps([identities, scopes]))
        with self.f.connection() as db:
            with AccessService(db, clock=lambda: self.f.now)._transaction():
                pointer = resolve_note_identity(db, note['id'], 'family-a', '101')
        self.assertEqual((pointer.identity_id, pointer.scope_ordinal), (identity[0], 0))

    def test_soft_removal_retains_raw_history_and_identity(self):
        note = self.save(asset_id=101)
        pointer = self.rows(f'SELECT * FROM {IDENTITIES}')
        self.save({'revision': '1', 'mutation_id': str(uuid.uuid4())}, story_id=note['id'], delete=True)
        self.assertEqual(self.rows(f'SELECT * FROM {IDENTITIES}'), pointer)
        self.assertEqual(self.rows('SELECT text,deleted FROM access_story_revisions ORDER BY revision'),
                         [('Private original words', 0), ('Private original words', 1)])
        with self.f.connection() as db:
            with AccessService(db)._transaction():
                with self.assertRaises(TransportError):
                    resolve_note_identity(db, note['id'], 'family-a', 101)

    def test_original_binding_and_ledger_are_immutable(self):
        note = self.save(asset_id=101)
        for sql, args in (
            (f'DELETE FROM {IDENTITIES}', ()),
            (f'UPDATE {IDENTITIES} SET asset_id=102', ()),
            (f'DELETE FROM {SCOPES}', ()),
            (f"UPDATE {SCOPES} SET library_id='family-b'", ()),
            ('UPDATE access_stories SET asset_id=102 WHERE id=?', (note['id'],)),
            ('UPDATE access_stories SET id=? WHERE id=?', (str(uuid.uuid4()), note['id'])),
            ("UPDATE access_stories SET library_id='family-b' WHERE id=?", (note['id'],)),
            ('UPDATE access_stories SET author_id=? WHERE id=?', (self.f.member_id, note['id'])),
        ):
            with self.subTest(sql=sql), self.assertRaises(sqlite3.IntegrityError):
                self.f.mutate(sql, args)
        self.assertEqual(self.rows('SELECT id,asset_id,library_id FROM access_stories'),
                         [(note['id'], 101, 'family-a')])

    def test_identity_survives_parent_removal_and_blocks_insert_and_rename_reuse(self):
        note = self.save(asset_id=101)
        identity = self.rows(f'SELECT * FROM {IDENTITIES}')
        with self.f.connection() as db:
            db.execute('DELETE FROM access_story_revisions WHERE story_id=?', (note['id'],))
            db.execute('DELETE FROM access_stories WHERE id=?', (note['id'],))
            db.commit()
        self.assertEqual(self.rows(f'SELECT * FROM {IDENTITIES}'), identity)
        values = (note['id'], 101, 'family-a', identity[0][3], self.f.now, self.f.now)
        with self.assertRaises(sqlite3.IntegrityError):
            self.f.mutate('''INSERT INTO access_stories
                (id,asset_id,library_id,author_id,revision,title,text,language,byline,created_at,updated_at,deleted)
                VALUES(?,?,?,?,1,'','Different original','en','',?,?,0)''', values)
        # A legacy unbound row cannot be renamed into the reserved public UUID.
        legacy = str(uuid.uuid4())
        self.f.mutate('''INSERT INTO access_stories
            (id,asset_id,library_id,author_id,revision,title,text,language,byline,created_at,updated_at,deleted)
            VALUES(?,?,?,?,1,'','Legacy','en','',?,?,0)''', (legacy, *values[1:]))
        with self.assertRaises(sqlite3.IntegrityError):
            self.f.mutate('UPDATE access_stories SET id=? WHERE id=?', (note['id'], legacy))

    def test_failed_revision_write_rolls_back_identity_scope_and_original(self):
        self.f.mutate("CREATE TRIGGER synthetic_revision_failure BEFORE INSERT ON access_story_revisions "
                      "BEGIN SELECT RAISE(ABORT,'synthetic failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.save(asset_id=101)
        for table in (IDENTITIES, SCOPES, 'access_stories', 'access_story_revisions'):
            self.assertEqual(self.rows('SELECT count(*) FROM ' + table), [(0,)])
        self.assertEqual(self.rows("SELECT count(*) FROM access_audit WHERE action='story.create'"), [(0,)])

    def test_schema_drift_refuses_creation_without_repair_or_content_write(self):
        self.f.mutate('DROP TRIGGER trg_family_note_no_reuse')
        with self.assertRaises(TransportError) as refusal:
            self.save(asset_id=101)
        self.assertEqual(refusal.exception.status, 503)
        self.assertEqual(self.rows('SELECT count(*) FROM access_stories'), [(0,)])
        self.assertFalse(self.rows("SELECT 1 FROM sqlite_master WHERE name='trg_family_note_no_reuse'"))

    def test_fresh_resolution_requires_transaction_current_scope_asset_and_lineage(self):
        note = self.save(asset_id=101)
        with self.f.connection() as db:
            with self.assertRaises(TransportError):
                resolve_note_identity(db, note['id'], 'family-a', 101)
            with AccessService(db)._transaction():
                for library, asset in (('family-b', 101), ('family-a', 102)):
                    with self.subTest(library=library, asset=asset), self.assertRaises(TransportError):
                        resolve_note_identity(db, note['id'], library, asset)
        self.f.mutate("UPDATE assets SET status='deleted' WHERE id=101")
        with self.f.connection() as db:
            with AccessService(db)._transaction(), self.assertRaises(TransportError):
                resolve_note_identity(db, note['id'], 'family-a', 101)


class FamilyNoteMoveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        promotion_fixture.PromotionTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        promotion_fixture.PromotionTests.tearDownClass()

    def setUp(self):
        self.f = promotion_fixture.PromotionTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.f.make_owner_of_both()
        with closing(self.f.connection()) as db:
            self.note = Stories(AccessService(db, clock=lambda: promotion_fixture.NOW)).save(
                self.f.owner_token, 'family-a', body(), asset_id=900)
        self.plan = self.f.planned('reassign', library_id='family-b',
            operator_account_id=self.f.owner_id, asset_ids=[900])

    def apply(self):
        return reassign_assets(self.plan, review=self.f.review(self.plan), clock=lambda: promotion_fixture.NOW)

    def test_approved_move_appends_scope_without_rewriting_identity_or_raw_history(self):
        identity = [tuple(r) for r in self.f.rows(f'SELECT * FROM {IDENTITIES}')]
        revision = [tuple(r) for r in self.f.rows('SELECT * FROM access_story_revisions')]
        result = self.apply()
        self.assertEqual(result['stories_moved'], 1)
        self.assertEqual([tuple(r) for r in self.f.rows(f'SELECT * FROM {IDENTITIES}')], identity)
        self.assertEqual([tuple(r) for r in self.f.rows('SELECT * FROM access_story_revisions')], revision)
        scopes = self.f.rows(f'SELECT ordinal,from_library_id,library_id,plan_id FROM {SCOPES} ORDER BY ordinal')
        self.assertEqual([tuple(r) for r in scopes], [(0, None, 'family-a', None),
            (1, 'family-a', 'family-b', self.plan['plan']['plan_id'])])
        with closing(self.f.connection()) as db:
            with AccessService(db)._transaction():
                self.assertEqual(resolve_note_identity(db, self.note['id'], 'family-b', 900).scope_ordinal, 1)
                with self.assertRaises(TransportError):
                    resolve_note_identity(db, self.note['id'], 'family-a', 900)

    def test_mid_move_failure_rolls_back_scope_note_and_asset_membership(self):
        self.f.mutate("CREATE TRIGGER synthetic_move_failure BEFORE UPDATE ON access_stories "
            "BEGIN SELECT RAISE(ABORT,'synthetic move failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.apply()
        self.assertEqual(len(self.f.rows(f'SELECT * FROM {SCOPES}')), 1)
        self.assertEqual(self.f.rows('SELECT library_id FROM access_asset_libraries WHERE asset_id=900')[0][0], 'family-a')
        self.assertEqual(self.f.rows('SELECT library_id FROM access_stories WHERE id=?', (self.note['id'],))[0][0], 'family-a')

    def test_review_detects_lineage_drift_before_moving_asset(self):
        # Simulate privileged corruption; the original schema is restored exactly
        # so it is the sealed row history, rather than schema drift, that refuses.
        from app.access.family_note_identity_schema import sqlite_family_note_identity_contract
        trigger = 'trg_' + IDENTITIES + '_update'
        ddl = next(sql for kind, name, sql in sqlite_family_note_identity_contract() if name == trigger)
        self.f.mutate('DROP TRIGGER ' + trigger)
        # Changing immutable creation metadata requires no FK rewrite.
        self.f.mutate(f'UPDATE {IDENTITIES} SET created_at=created_at+1')
        self.f.mutate(ddl)
        with self.assertRaises(promotion_fixture.PlanRejected):
            self.apply()
        self.assertEqual(self.f.rows('SELECT library_id FROM access_asset_libraries WHERE asset_id=900')[0][0], 'family-a')

    def test_missing_historical_scope_refuses_fresh_identity_even_when_latest_scope_matches(self):
        self.apply()
        from app.access.family_note_identity_schema import sqlite_family_note_identity_contract
        trigger = 'trg_' + SCOPES + '_delete'
        ddl = next(sql for kind, name, sql in sqlite_family_note_identity_contract() if name == trigger)
        self.f.mutate('DROP TRIGGER ' + trigger)
        self.f.mutate(f'DELETE FROM {SCOPES} WHERE ordinal=0')
        self.f.mutate(ddl)
        with closing(self.f.connection()) as db:
            with AccessService(db)._transaction(), self.assertRaises(TransportError):
                resolve_note_identity(db, self.note['id'], 'family-b', 900)


class FamilyNoteEditionTests(unittest.TestCase):
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
        # The fixture keeps C2 behavior explicitly pinned; reselect the new
        # already-migrated synthetic template for these identity-specific tests.
        self.f.mutate('UPDATE alembic_version SET version_num=?', (IDENTITY_REVISION,))
        with self.f.connection() as db:
            self.note = Stories(AccessService(db, clock=lambda: self.f.now)).save(
                self.seed.owner, 'family-a', body(), asset_id=101)

    def test_saved_edition_binds_all_family_inputs_even_uncited_and_keeps_c2_contract(self):
        proposal, raw, receipt, _job = self.seed._saved()
        self.assertEqual(self.seed._edition('get', receipt['id'])['state'], 'current')
        with self.f.connection() as db:
            bindings = db.execute(f'''SELECT r.ordinal,r.identity_id,r.scope_ordinal,s.source_id,s.chapter_ids_json
                FROM {EDITION_NOTES} r JOIN access_memory_book_edition_sources s
                ON s.edition_id=r.edition_id AND s.ordinal=r.ordinal WHERE r.edition_id=?''', (receipt['id'],)).fetchall()
            self.assertEqual(len(bindings), 1)
            self.assertEqual(bindings[0][3], 'family-' + self.note['id'])
            self.assertEqual(bindings[0][2], 0)
            identity = db.execute(f'SELECT identity_id FROM {IDENTITIES} WHERE note_id=?', (self.note['id'],)).fetchone()[0]
            self.assertEqual(bindings[0][1], identity)
            from app.access.memory_book_edition_deletions import verify_edition_schema
            verify_edition_schema(db)
        cited = {s for chapter in proposal['manuscript']['chapters'] for s in chapter['source_ids']}
        self.assertNotIn('family-' + self.note['id'], cited)
        for private in ('identity_id', 'scope_ordinal'):
            self.assertNotIn(private, json.dumps(receipt))

    def test_memory_worker_admits_full_identity_schema_and_refuses_missing_lineage_guard(self):
        import run_memory_worker
        with self.f.connection() as db:
            self.assertTrue(run_memory_worker._check_schema(db, editorial_enabled=True))
            self.assertFalse(db.in_transaction)
        self.f.mutate('DROP TRIGGER trg_family_note_no_reuse')
        with self.f.connection() as db:
            self.assertFalse(run_memory_worker._check_schema(db, editorial_enabled=True))

    def test_missing_binding_hides_saved_prose_and_original_inspection(self):
        _proposal, _raw, receipt, _job = self.seed._saved()
        self.f.mutate(f'DELETE FROM {EDITION_NOTES} WHERE edition_id=?', (receipt['id'],))
        result = self.seed._edition('get', receipt['id'])
        self.assertEqual(result['state'], 'source_changed')
        self.assertIsNone(result['manuscript'])
        from app.access.memory_book_edition_sources import MemoryBookEditionSources
        from app.access.memory_book_editions import MemoryBookEditions
        with self.f.connection() as db:
            reader = MemoryBookEditionSources(MemoryBookEditions(AccessService(db, clock=lambda: self.f.now),
                enabled=True), originals_enabled=True)
            detail = reader.detail(self.seed.owner, 'family-a', self.seed.book_id, receipt['id'],
                                   'family-' + self.note['id'])
            self.assertEqual(detail['state'], 'source_changed')
            self.assertIsNone(detail['source'])

    def test_legacy_unbound_note_refuses_new_typed_proposal_without_backfill(self):
        # Removing the parent leaves the identity reserved; use a separate,
        # never-bound UUID for an existing historical source.
        note_id = str(uuid.uuid4())
        self.f.mutate('''INSERT INTO access_stories
            (id,asset_id,library_id,author_id,revision,title,text,language,byline,created_at,updated_at,deleted)
            VALUES(?,101,'family-a',?,1,'Legacy','Legacy family source','en','',1,1,0)''',
            (note_id, self.note['author_id']))
        job, _, _ = self.seed._queue_ready_job()
        with self.assertRaises(TransportError) as refused:
            self.seed._edition('proposal', job)
        self.assertEqual(refused.exception.status, 503)
        with self.f.connection() as db:
            self.assertIsNone(db.execute(f'SELECT 1 FROM {IDENTITIES} WHERE note_id=?', (note_id,)).fetchone())


class FamilyNotePureProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.seed = provenance_fixture.MemoirEditionProvenanceTests()
        self.seed.setUp()
        self.bundle = self.seed.bundle
        self.note_id = str(uuid.uuid4())
        from app.access.family_note_identity import FamilyNoteIdentity
        self.binding = FamilyNoteIdentity(str(uuid.uuid4()), self.note_id, '101', 0, self.bundle['library_id'])
        self.bundle['sources'].append({'id': 'family-' + self.note_id, 'kind': 'family',
            'asset_id': '101', 'text': 'Uncited original', 'author': 'Private label'})

    def build(self, bindings):
        return build_edition_provenance(self.bundle, self.seed.children,
            contribution_owners=self.seed.owners, family_note_identities=bindings)

    def test_uncited_note_has_typed_binding_and_changes_closure_without_copying_content(self):
        bound = self.build({self.note_id: self.binding})
        self.assertEqual(bound.sources[-1].chapter_ids, ())
        self.assertEqual(bound.sources[-1].family_note_identity, self.binding)
        old = self.build(None)
        self.assertIsNone(old.sources[-1].family_note_identity)
        self.assertNotEqual(bound.closure_digest, old.closure_digest)
        changed = self.build({self.note_id: replace(self.binding, identity_id=str(uuid.uuid4()))})
        self.assertNotEqual(bound.closure_digest, changed.closure_digest)

    def test_missing_wrong_asset_library_uuid_scope_or_untyped_pointer_is_refused(self):
        for binding in (None, 'opaque', replace(self.binding, asset_id='102'),
                        replace(self.binding, library_id='other'), replace(self.binding, identity_id='invalid'),
                        replace(self.binding, note_id=str(uuid.uuid4())), replace(self.binding, scope_ordinal=True)):
            with self.subTest(binding=binding), self.assertRaises(TransportError):
                self.build({self.note_id: binding})


if __name__ == '__main__':
    unittest.main()
