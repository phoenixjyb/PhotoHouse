"""Synthetic family-note erasure and restore-journal contracts."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
import uuid

from sqlalchemy import create_engine

import test_memory_book_editions as edition_fixture
from app import db as models
from app.access.family_note_deletions import erase_family_note_original, prepare_family_tombstone
from app.access.family_note_identity_schema import (
    EDITION_NOTES, IDENTITIES, IDENTITY_REVISION, SCOPES,
    add_family_note_identity_tables,
)
from app.access.memory_jobs import MemoryJobs
from app.access.memory_book_edition_schema import add_book_edition_tables
from app.access.metadata import migration_metadata
from app.access.original_deletions import OriginalDeletionError, OriginalDeletionJournal
from app.access.service import AccessService
from app.access.stories import Stories


def _uuid():
    return str(uuid.uuid4())


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _snapshot(source, target):
    with closing(sqlite3.connect(source)) as src, closing(sqlite3.connect(target)) as dst:
        src.backup(dst)


class FamilyNoteDeletionTests(unittest.TestCase):
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
        self._install_identity_schema()

        self.temp = tempfile.TemporaryDirectory(prefix='photohouse-family-delete-')
        self.addCleanup(self.temp.cleanup)
        os.chmod(self.temp.name, 0o700)
        self.root = Path(self.temp.name).resolve()
        self.namespace = _uuid()
        self.journal_path = self.root / 'journal.sqlite'
        self.journal = OriginalDeletionJournal.initialize(self.journal_path, self.namespace)
        with self.f.connection() as db:
            # The memoir fixture seeds original contributions for unrelated
            # tests. Clear them so this journal is bound while both original
            # collections are empty, before this case creates its note/editions.
            db.execute('DELETE FROM access_memory_contributions')
            db.execute('DELETE FROM access_upload_annotations')
            db.commit()
            self.journal.bind(db)

        with self.f.connection() as db:
            self.note = Stories(AccessService(db, clock=lambda: self.f.now)).save(
                self.seed.owner, 'family-a', self._note_body(), asset_id=101)

    @staticmethod
    def _note_body(text='Private family note source'):
        return {'title': 'Private title', 'text': text, 'language': 'en',
                'byline': 'Private byline', 'mutation_id': _uuid()}

    def _install_identity_schema(self):
        metadata = migration_metadata(models.Base.metadata)
        add_book_edition_tables(metadata)
        tables = add_family_note_identity_tables(metadata)
        engine = create_engine('sqlite:///' + str(self.f.path))
        try:
            for table in tables:
                table.create(engine, checkfirst=True)
        finally:
            engine.dispose()
        self.f.mutate('UPDATE alembic_version SET version_num=?', (IDENTITY_REVISION,))

    def _move_note(self):
        """Apply the schema's legal lineage transition for the synthetic asset."""
        with self.f.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            identity = db.execute(f'SELECT identity_id FROM {IDENTITIES} WHERE note_id=?',
                                  (self.note['id'],)).fetchone()[0]
            now = self.f.now + 1
            db.execute(f'INSERT INTO {SCOPES} VALUES(?,1,\'family-a\',\'family-b\',?,?,?)',
                       (identity, _uuid(), 'a' * 64, now))
            db.execute("UPDATE access_asset_libraries SET library_id='family-b' "
                       "WHERE asset_id=101 AND library_id='family-a'")
            db.execute("UPDATE access_stories SET library_id='family-b' WHERE id=?",
                       (self.note['id'],))
            db.commit()

    def _upgrade_journal(self):
        ledger = self.journal._connect()
        try:
            version = ledger.execute('SELECT format FROM journal_meta WHERE id=1').fetchone()[0]
        finally:
            ledger.close()
        if version.endswith('v2'):
            return
        with self.f.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            self.journal.upgrade_family_format(db, expected_head=self.journal.head())
            db.commit()

    def _live_erase(self, *, occurred_at=None, expected_revision=None):
        self._upgrade_journal()
        with self.f.connection() as db:
            db.execute('PRAGMA secure_delete=ON')
            db.execute('BEGIN IMMEDIATE')
            revision = db.execute('SELECT revision FROM access_stories WHERE id=?',
                                  (self.note['id'],)).fetchone()[0]
            candidate = prepare_family_tombstone(db, self.note['id'],
                revision if expected_revision is None else expected_revision,
                self.f.now if occurred_at is None else occurred_at)
            row = {'id': self.note['id'], 'revision': revision if expected_revision is None
                   else expected_revision}
            receipt = self.journal.append(db, 'family_note', row, candidate['occurred_at'])
            erase_family_note_original(db, candidate)
            db.commit()
            return receipt

    def _edit_note(self, *, revision=1, text='Edited private family note'):
        request = self._note_body(text)
        request['revision'] = str(revision)
        with self.f.connection() as db:
            return Stories(AccessService(db, clock=lambda: self.f.now)).save(
                self.seed.owner, 'family-a', request, story_id=self.note['id'])

    def _restore(self, backup):
        restored_path = self.root / ('restore-' + _uuid() + '.sqlite')
        shutil.copyfile(backup, restored_path)
        db = sqlite3.connect(restored_path)
        db.execute('PRAGMA foreign_keys=ON')
        return restored_path, db

    def _marker(self, db):
        return tuple(db.execute('SELECT applied_seq,applied_digest '
                                'FROM access_original_deletion_state WHERE id=1').fetchone())

    def test_live_erasure_scrubs_note_and_revision_bytes_but_reserves_identity(self):
        note_id = self.note['id']
        text_value = 'Private family note source'
        record = self._live_erase()
        self.assertNotIn(text_value.encode(), self.f.path.read_bytes())
        self.assertNotIn(text_value.encode(), self.journal_path.read_bytes())
        with self.f.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM access_stories WHERE id=?',
                                        (note_id,)).fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT count(*) FROM access_story_revisions WHERE story_id=?',
                                        (note_id,)).fetchone()[0], 0)
            self.assertEqual(db.execute(f'SELECT count(*) FROM {IDENTITIES} WHERE note_id=?',
                                        (note_id,)).fetchone()[0], 1)
            self.assertEqual(db.execute(f'SELECT count(*) FROM {SCOPES} WHERE identity_id='
                f'(SELECT identity_id FROM {IDENTITIES} WHERE note_id=?)', (note_id,)).fetchone()[0], 1)
            self.journal.assert_current(db)

    def test_owner_erasure_preserves_unrelated_originals_and_revisions(self):
        upload_id = _uuid()
        upload_text = 'Unrelated protected upload original'
        contribution_text = 'Unrelated memory contribution original'
        note_text = 'Unrelated raw family note original'
        with self.f.connection() as db:
            db.execute('''INSERT INTO access_upload_annotations
                (id,author_id,library_id,batch,asset_id,kind,original_text,original_audio,
                 mime,duration_ms,sha256,language,consent,mutation_id,request_digest,created_at)
                VALUES(?,?,? ,?,?,'text',?,NULL,NULL,NULL,?,'en',0,?,?,?)''',
                (upload_id, self.f.member_id, 'family-a', _uuid().replace('-', ''), 101,
                 upload_text, _sha(upload_text.encode()), _uuid(), 'b' * 64, self.f.now))
            db.execute('''INSERT INTO access_annotation_derivations
                (annotation_id,revision,state,created_at,updated_at)
                VALUES (?,1,'held',?,?)''', (upload_id, self.f.now, self.f.now))
            db.commit()

        with self.f.connection() as db:
            access = AccessService(db, clock=lambda: self.f.now)
            from app.access.memory_contributions import MemoryContributions
            contribution = MemoryContributions(access).create(
                self.f.member_token, 'family-a', self.seed.child_one, {
                    'kind': 'text', 'text': contribution_text, 'language': 'en',
                    'byline': 'Synthetic contributor', 'consent': '1',
                    'chapter_id': 'chapter-1', 'revision': '1',
                    'mutation_id': _uuid(),
                })
            MemoryContributions(access).review(
                self.seed.owner, 'family-a', self.seed.child_one,
                contribution['id'], 'accepted', 1)
            db.commit()

        with self.f.connection() as db:
            separate_note = Stories(AccessService(db, clock=lambda: self.f.now)).save(
                self.seed.owner, 'family-a', self._note_body(note_text), asset_id=102)

        table_rows = {
            'access_upload_annotations': ('id', upload_id),
            'access_annotation_derivations': ('annotation_id', upload_id),
            'access_memory_contributions': ('id', contribution['id']),
            'access_memory_contribution_derivations': ('contribution_id', contribution['id']),
            'access_stories': ('id', separate_note['id']),
            'access_story_revisions': ('story_id', separate_note['id']),
            IDENTITIES: ('note_id', separate_note['id']),
        }
        snapshots = {}
        with self.f.connection() as db:
            unrelated_identity = db.execute(
                f'SELECT identity_id FROM {IDENTITIES} WHERE note_id=?',
                (separate_note['id'],)).fetchone()[0]
            table_rows[SCOPES] = ('identity_id', unrelated_identity)
            for table, (column, value) in table_rows.items():
                snapshots[table] = db.execute(
                    f'SELECT * FROM {table} WHERE {column}=? ORDER BY rowid', (value,)
                ).fetchall()
            self.assertEqual(len(snapshots['access_upload_annotations']), 1)
            self.assertEqual(len(snapshots['access_memory_contributions']), 1)
            self.assertEqual(len(snapshots['access_stories']), 1)
            self.assertEqual(len(snapshots['access_story_revisions']), 1)
        backup = self.root / 'independent-originals-before-erase.sqlite'
        _snapshot(self.f.path, backup)

        self._upgrade_journal()
        with self.f.connection() as db:
            access = AccessService(db, clock=lambda: self.f.now)
            access.original_deletions = self.journal
            result = Stories(access, erasure_enabled=True).erase_original(
                self.seed.owner, 'family-a', self.note['id'], '1')
            self.assertEqual(result, {'deleted': True, 'id': self.note['id']})

        with self.f.connection() as db:
            for table, (column, value) in table_rows.items():
                current = db.execute(
                    f'SELECT * FROM {table} WHERE {column}=? ORDER BY rowid', (value,)
                ).fetchall()
                self.assertEqual(current, snapshots[table], table)
            self.assertEqual(db.execute('SELECT count(*) FROM access_stories WHERE id=?',
                                        (self.note['id'],)).fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT count(*) FROM access_story_revisions WHERE story_id=?',
                                        (self.note['id'],)).fetchone()[0], 0)
            self.assertEqual(db.execute(f'SELECT count(*) FROM {IDENTITIES} WHERE note_id=?',
                                        (self.note['id'],)).fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT original_text FROM access_upload_annotations WHERE id=?',
                                        (upload_id,)).fetchone()[0], upload_text)
            self.assertEqual(db.execute('SELECT original_text FROM access_memory_contributions WHERE id=?',
                                        (contribution['id'],)).fetchone()[0], contribution_text)
            self.assertEqual(db.execute('SELECT text FROM access_stories WHERE id=?',
                                        (separate_note['id'],)).fetchone()[0], note_text)
            self.journal.assert_current(db)

        _, restored = self._restore(backup)
        with closing(restored):
            self.assertEqual(self.journal.replay(restored)[3], 1)
            for table, (column, value) in table_rows.items():
                current = restored.execute(
                    f'SELECT * FROM {table} WHERE {column}=? ORDER BY rowid', (value,)
                ).fetchall()
                self.assertEqual(current, snapshots[table], 'replay preserved ' + table)
            self.assertEqual(restored.execute('SELECT count(*) FROM access_stories WHERE id=?',
                                              (self.note['id'],)).fetchone()[0], 0)
            self.assertEqual(restored.execute('SELECT count(*) FROM access_story_revisions WHERE story_id=?',
                                              (self.note['id'],)).fetchone()[0], 0)
            self.assertEqual(restored.execute(f'SELECT count(*) FROM {IDENTITIES} WHERE note_id=?',
                                              (self.note['id'],)).fetchone()[0], 1)
            self.assertEqual(restored.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_replay_accepts_older_mutable_revision_with_same_identity_and_scope(self):
        backup = self.root / 'before-edit.sqlite'
        _snapshot(self.f.path, backup)
        self._edit_note(revision=1)
        self._live_erase(expected_revision=2)
        _, restored = self._restore(backup)
        with closing(restored):
            self.assertEqual(self.journal.replay(restored)[3], 1)
            self.assertEqual(restored.execute('SELECT count(*) FROM access_stories WHERE id=?',
                                              (self.note['id'],)).fetchone()[0], 0)
            self.assertEqual(restored.execute(f'SELECT count(*) FROM {IDENTITIES} WHERE note_id=?',
                                              (self.note['id'],)).fetchone()[0], 1)

    def test_replay_accepts_pre_move_equal_revision_scope_prefix(self):
        backup = self.root / 'before-move.sqlite'
        _snapshot(self.f.path, backup)
        self._move_note()
        self._live_erase()
        _, restored = self._restore(backup)
        with closing(restored):
            self.assertEqual(self.journal.replay(restored)[3], 1)
            self.assertEqual(restored.execute('SELECT count(*) FROM access_stories WHERE id=?',
                                              (self.note['id'],)).fetchone()[0], 0)
            self.assertEqual(restored.execute(f'SELECT count(*) FROM {SCOPES} WHERE identity_id='
                f'(SELECT identity_id FROM {IDENTITIES} WHERE note_id=?)',
                (self.note['id'],)).fetchone()[0], 1)

    def test_replay_refuses_identity_drift_schema_drift_and_newer_revision_atomically(self):
        backup = self.root / 'refusal-base.sqlite'
        _snapshot(self.f.path, backup)
        self._live_erase()

        def altered_copy(name, mutate):
            path = self.root / name
            shutil.copyfile(backup, path)
            db = sqlite3.connect(path)
            db.execute('PRAGMA foreign_keys=OFF')
            mutate(db)
            db.commit()
            db.execute('PRAGMA foreign_keys=ON')
            return db

        from app.access.family_note_identity_schema import sqlite_family_note_identity_contract
        update_guard = next(sql for kind, name, sql in sqlite_family_note_identity_contract()
                            if name == f'trg_{IDENTITIES}_update')
        identity_db = altered_copy('identity-drift.sqlite', lambda db: (
            db.execute(f'DROP TRIGGER trg_{IDENTITIES}_update'),
            db.execute(f'UPDATE {IDENTITIES} SET author_id=\'changed-owner\' WHERE note_id=?',
                       (self.note['id'],)), db.execute(update_guard)))
        with closing(identity_db):
            before = self._marker(identity_db)
            with self.assertRaises(OriginalDeletionError):
                self.journal.replay(identity_db)
            self.assertEqual(self._marker(identity_db), before)
            self.assertEqual(identity_db.execute('SELECT count(*) FROM access_stories WHERE id=?',
                                                  (self.note['id'],)).fetchone()[0], 1)

        schema_db = altered_copy('schema-drift.sqlite', lambda db: db.execute(
            'DROP TRIGGER trg_family_note_no_reuse'))
        with closing(schema_db):
            before = self._marker(schema_db)
            with self.assertRaises(OriginalDeletionError):
                self.journal.replay(schema_db)
            self.assertEqual(self._marker(schema_db), before)

        newer_db = altered_copy('newer-revision.sqlite', lambda db: (
            db.execute('UPDATE access_stories SET revision=revision+1,text=\'newer private text\' WHERE id=?',
                       (self.note['id'],))))
        with closing(newer_db):
            before = self._marker(newer_db)
            with self.assertRaises(OriginalDeletionError):
                self.journal.replay(newer_db)
            self.assertEqual(self._marker(newer_db), before)
            self.assertEqual(newer_db.execute('SELECT text FROM access_stories WHERE id=?',
                                              (self.note['id'],)).fetchone()[0],
                             'newer private text')

    def test_exact_pending_append_retry_after_primary_rollback(self):
        self._upgrade_journal()
        with self.f.connection() as db:
            db.execute('PRAGMA secure_delete=ON')
            db.execute('BEGIN IMMEDIATE')
            row = {'id': self.note['id'], 'revision': 1}
            first_candidate = prepare_family_tombstone(db, self.note['id'], 1, self.f.now)
            first = self.journal.append(db, 'family_note', row, self.f.now)
            db.rollback()
        with self.f.connection() as db:
            self.assertEqual(db.execute('SELECT applied_seq FROM access_original_deletion_state').fetchone()[0], 0)
            db.execute('PRAGMA secure_delete=ON')
            db.execute('BEGIN IMMEDIATE')
            retry_candidate = prepare_family_tombstone(db, self.note['id'], 1, self.f.now + 10)
            retry = self.journal.append(db, 'family_note', row, self.f.now + 10)
            erase_family_note_original(db, retry_candidate)
            db.commit()
        self.assertEqual(first['seq'], retry['seq'])
        self.assertEqual(first_candidate['family_binding_json'], retry_candidate['family_binding_json'])
        self.assertEqual(self.journal.head()[1], 1)

    def test_v1_upgrade_keeps_legacy_genesis_record_digest_and_marker(self):
        from app.access import original_deletions as journal_module

        record = {'seq': 1, 'collection': 'upload', 'library_id': 'family-a',
            'object_id': _uuid(), 'original_kind': 'text', 'original_sha256': 'a' * 64,
            'batch': 'b' * 32, 'asset_id': None, 'story_id': None, 'occurred_at': self.f.now,
            'prev_digest': journal_module._genesis(self.namespace)}
        record['digest'] = journal_module._record_digest(record['prev_digest'], record)
        ledger = self.journal._connect()
        try:
            ledger.execute('BEGIN IMMEDIATE')
            ledger.execute('''INSERT INTO deletions (seq,collection,library_id,object_id,original_kind,
                original_sha256,batch,asset_id,story_id,occurred_at,prev_digest,digest)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''', tuple(record[key] for key in (
                'seq','collection','library_id','object_id','original_kind','original_sha256',
                'batch','asset_id','story_id','occurred_at','prev_digest','digest')))
            ledger.execute('UPDATE journal_meta SET head_seq=1,head_digest=? WHERE id=1',
                           (record['digest'],))
            ledger.commit()
        finally:
            ledger.close()
        with self.f.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('UPDATE access_original_deletion_state SET applied_seq=1,applied_digest=? WHERE id=1',
                       (record['digest'],))
            before_head = self.journal.head()
            self.journal.upgrade_family_format(db, expected_head=before_head)
            db.commit()
        self.assertEqual(self.journal.head(), before_head)
        upgraded = self.journal._connect()
        try:
            rows = upgraded.execute('SELECT * FROM deletions ORDER BY seq').fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['digest'], record['digest'])
            self.assertEqual(rows[0]['prev_digest'], record['prev_digest'])
            self.assertIsNone(rows[0]['family_binding_json'])
        finally:
            upgraded.close()

    def test_uncited_and_older_editions_and_ai_replies_are_scrubbed_but_manual_input_stays(self):
        proposal, _raw, receipt, _job_id = self.seed._saved()
        self.assertNotIn('family-' + self.note['id'], {
            source_id for chapter in proposal['manuscript']['chapters']
            for source_id in chapter['source_ids']})
        self.seed.base.base.save(self.seed.owner, self.seed.base.base.body(
            [self.seed.child_one, self.seed.child_two], title='Revised memoir', revision='1'),
            self.seed.book_id)
        _proposal2, _raw2, receipt2, _job_id2 = self.seed._saved()

        with self.f.connection() as db:
            # Add one book conversation turn. Its prompt/output/reply are copies
            # that must be scrubbed; the user's own message remains authored input.
            jobs = MemoryJobs(AccessService(db, clock=lambda: self.f.now))
            conversation = jobs.start(self.seed.owner, 'family-a', 'book', self.seed.book_id, _uuid())
            queued = jobs.send(self.seed.owner, 'family-a', conversation['id'], str(self.seed._book_revision()), _uuid(),
                               'manual question stays')
            db.execute("UPDATE access_memory_jobs SET state='ready',input_json=?,output_json=? WHERE id=?",
                       ('{"instructions":"private note prompt"}', '{"reply":"private note answer"}', queued['id']))
            db.execute('UPDATE access_memory_turns SET reply_text=?,reply_kind=? WHERE job_id=?',
                       ('private note answer', 'answer', queued['id']))
            db.commit()

        self._live_erase()
        with self.f.connection() as db:
            editions = db.execute('''SELECT id,state,manuscript_json FROM access_memory_book_editions
                WHERE id IN (?,?) ORDER BY id''', (receipt['id'], receipt2['id'])).fetchall()
            self.assertEqual(len(editions), 2)
            self.assertTrue(all(row[1] == 'source_invalidated' and row[2] is None for row in editions))
            self.assertEqual(db.execute(f'SELECT count(*) FROM {EDITION_NOTES} WHERE identity_id=(SELECT identity_id FROM {IDENTITIES} WHERE note_id=?)',
                (self.note['id'],)).fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM access_memory_jobs WHERE input_json!='{}' OR output_json IS NOT NULL OR lease_id IS NOT NULL OR lease_until IS NOT NULL").fetchone()[0], 0)
            self.assertEqual(db.execute('''SELECT count(*) FROM access_memory_turns
                WHERE input_text='manual question stays' AND reply_text IS NULL AND reply_kind IS NULL''').fetchone()[0], 1)

    def test_replay_repairs_orphaned_note_revision_when_parent_is_missing(self):
        backup = self.root / 'orphan-parent.sqlite'
        _snapshot(self.f.path, backup)
        self._live_erase()
        _, restored = self._restore(backup)
        with closing(restored):
            restored.execute('PRAGMA foreign_keys=OFF')
            restored.execute('DELETE FROM access_stories WHERE id=?', (self.note['id'],))
            restored.commit()
            restored.execute('PRAGMA foreign_keys=ON')
            review = self.journal.review(restored)
            self.assertEqual(review['pending_count'], 1)
            self.assertEqual(self.journal.replay(restored)[3], 1)
            self.assertEqual(restored.execute('SELECT count(*) FROM access_story_revisions WHERE story_id=?',
                                              (self.note['id'],)).fetchone()[0], 0)
            self.assertEqual(restored.execute(f'SELECT count(*) FROM {IDENTITIES} WHERE note_id=?',
                                              (self.note['id'],)).fetchone()[0], 1)
            self.assertEqual(restored.execute('PRAGMA foreign_key_check').fetchall(), [])


if __name__ == '__main__':
    unittest.main()
