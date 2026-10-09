"""Offline original-deletion journal bootstrap CLI against disposable e7 SQLite."""
from contextlib import closing, redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
import unittest
import uuid
from unittest.mock import patch

import test_library_reads as fixture
from app.access.original_deletions import OriginalDeletionJournal
from app.access.memory_book_edition_schema import EDITION_TABLE, SOURCES_TABLE
from scripts import initialize_original_deletions as bootstrap


def snapshot(source, target):
    with closing(sqlite3.connect(source)) as src, closing(sqlite3.connect(target)) as dst:
        src.backup(dst)


class InitializeOriginalDeletionCliTests(unittest.TestCase):
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
        self.tmp = tempfile.TemporaryDirectory(prefix='original-journal-bootstrap-', dir='/private/tmp')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.primary = self.root / 'primary.sqlite'
        self.backup = self.root / 'rollback-copy.sqlite'
        self.journal_dir = self.root / 'external-journal'
        self.journal_dir.mkdir(mode=0o700)
        self.journal = self.journal_dir / 'deletions.sqlite'
        self.namespace = str(uuid.uuid4())
        snapshot(self.f.path, self.primary)
        snapshot(self.primary, self.backup)

    def cli(self, *options):
        out, err = io.StringIO(), io.StringIO()
        args = ['--database', str(self.primary), '--backup', str(self.backup),
                '--journal', str(self.journal), '--namespace', self.namespace,
                '--max-bytes', str(128 * 1024 * 1024), '--timeout-seconds', '300', *options]
        with redirect_stdout(out), redirect_stderr(err):
            code = bootstrap.main(args)
        return code, json.loads(out.getvalue()), err.getvalue()

    def snapshot_bytes(self, path):
        return Path(path).read_bytes()

    def restore_c2_pair(self):
        snapshot(self.f.path, self.primary)
        snapshot(self.primary, self.backup)

    def seed_editorial_edition(self, state):
        book_id = str(uuid.uuid4())
        with closing(sqlite3.connect(self.primary)) as db:
            db.execute('PRAGMA foreign_keys=ON')
            owner = db.execute("SELECT account_id FROM access_memberships "
                                "WHERE library_id='family-a' AND role='owner'").fetchone()[0]
            content = json.dumps({'title': 'Synthetic reviewed memoir', 'language': 'en',
                                  'introduction': '', 'kind': 'memoir', 'story_ids': []},
                                 sort_keys=True, separators=(',', ':'))
            db.execute('''INSERT INTO access_memory_books
                (id,library_id,author_id,revision,content,created_at,updated_at)
                VALUES(?,'family-a',?,1,?,1,1)''', (book_id, owner, content))
            db.execute('''INSERT INTO access_memory_book_revisions
                (book_id,revision,editor_id,mutation_id,request_digest,content,occurred_at)
                VALUES(?,1,?,?,?, ?,1)''',
                (book_id, owner, str(uuid.uuid4()), 'a' * 64, content))
            db.execute('''INSERT INTO access_memory_book_editorial
                (book_id,book_revision,children_json,transitions_json,state)
                VALUES(?,1,'[]','[]','current')''', (book_id,))
            manuscript = None if state == 'source_invalidated' else '{"title":"Reviewed"}'
            db.execute(f'''INSERT INTO {EDITION_TABLE}
                (id,book_id,book_revision,library_id,creator_account_id,originating_job_id,
                 job_result_sha256,source_fingerprint,context_profile,children_json,
                 manuscript_json,mutation_id,request_digest,created_at,state)
                VALUES(?,?,1,'family-a',?,?,?,?,'memoir_editorial_v1','[]',?,?,?,1,?)''',
                (str(uuid.uuid4()), book_id, owner, str(uuid.uuid4()), 'b' * 64,
                 'c' * 64, manuscript, str(uuid.uuid4()), 'd' * 64, state))
            db.commit()
        snapshot(self.primary, self.backup)
        return book_id

    def test_default_review_is_readonly_and_emits_only_counts_and_fingerprint(self):
        primary_before = self.snapshot_bytes(self.primary)
        backup_before = self.snapshot_bytes(self.backup)
        code, report, _ = self.cli()
        self.assertEqual(code, 0)
        self.assertEqual(report['status'], 'reviewed')
        with closing(sqlite3.connect(self.primary)) as db:
            actual_revision = db.execute(
                'SELECT version_num FROM alembic_version').fetchone()[0]
        self.assertEqual(report['schema_revision'], actual_revision)
        self.assertEqual(report['original_rows'], 0)
        self.assertEqual(report['marker_rows'], 0)
        self.assertRegex(report['logical_fingerprint'], r'^[0-9a-f]{64}$')
        self.assertIsNone(report['journal_sequence'])
        self.assertNotIn(str(self.primary), json.dumps(report))
        self.assertNotIn('caption-101', json.dumps(report))
        self.assertEqual(self.snapshot_bytes(self.primary), primary_before)
        self.assertEqual(self.snapshot_bytes(self.backup), backup_before)
        self.assertFalse(self.journal.exists())

    def test_execute_requires_writer_attestation_and_does_not_create_journal(self):
        code, report, _ = self.cli('--execute')
        self.assertEqual(code, 2)
        self.assertEqual(report['status'], 'refused')
        self.assertFalse(self.journal.exists())

    def test_existing_f7_schema_still_binds_and_reports_its_actual_revision(self):
        for path in (self.primary,self.backup):
            with closing(sqlite3.connect(path)) as db:
                db.execute('DROP TABLE access_memory_contribution_refs')
                db.execute("UPDATE alembic_version SET version_num='f7c3a9d2e614'")
                db.commit()
        code, report, _ = self.cli('--execute','--all-writers-stopped')
        self.assertEqual(code,0)
        self.assertEqual(report['schema_revision'],'f7c3a9d2e614')
        self.assertEqual(report['status'],'bound')
        self.assertEqual(report['marker_rows'],1)

    def test_new_reference_schema_constraints_are_checked_before_binding(self):
        for path in (self.primary,self.backup):
            with closing(sqlite3.connect(path)) as db:
                db.execute('DROP TABLE access_memory_contribution_refs')
                db.execute('''CREATE TABLE access_memory_contribution_refs
                    (story_id TEXT,revision INTEGER,chapter_id TEXT,ordinal INTEGER,contribution_id TEXT)''')
                db.commit()
        before=self.snapshot_bytes(self.primary)
        code, report, _ = self.cli('--execute','--all-writers-stopped')
        self.assertEqual(code,2)
        self.assertEqual(report['status'],'refused')
        self.assertFalse(self.journal.exists())
        self.assertEqual(self.snapshot_bytes(self.primary),before)

    def test_c2_bootstrap_rejects_missing_or_drifted_edition_indexes_and_triggers(self):
        cases = (
            ('missing edition index', (
                'DROP INDEX ix_memory_book_edition_book_revision',)),
            ('drifted edition index', (
                'DROP INDEX ix_memory_book_edition_book_revision',
                'CREATE INDEX ix_memory_book_edition_book_revision '
                'ON access_memory_book_editions(library_id)',)),
            ('missing edition trigger', (
                'DROP TRIGGER trg_memory_book_edition_immutable',)),
            ('drifted edition trigger', (
                'DROP TRIGGER trg_memory_book_edition_immutable',
                'CREATE TRIGGER trg_memory_book_edition_immutable '
                'BEFORE UPDATE ON access_memory_book_editions '
                'BEGIN SELECT 1; END',)),
        )
        for label, statements in cases:
            with self.subTest(label=label):
                self.restore_c2_pair()
                for path in (self.primary, self.backup):
                    with closing(sqlite3.connect(path)) as db:
                        for statement in statements:
                            db.execute(statement)
                        db.commit()
                primary_before = self.snapshot_bytes(self.primary)
                backup_before = self.snapshot_bytes(self.backup)
                code, report, _ = self.cli('--execute', '--all-writers-stopped')
                self.assertEqual(code, 2)
                self.assertEqual(report['status'], 'refused')
                self.assertFalse(self.journal.exists())
                self.assertEqual(self.snapshot_bytes(self.primary), primary_before)
                self.assertEqual(self.snapshot_bytes(self.backup), backup_before)

    def test_c2_bootstrap_refuses_current_and_invalidated_editions_without_writes(self):
        for state in ('current', 'source_invalidated'):
            with self.subTest(state=state):
                self.restore_c2_pair()
                self.seed_editorial_edition(state)
                primary_before = self.snapshot_bytes(self.primary)
                backup_before = self.snapshot_bytes(self.backup)
                with closing(sqlite3.connect(self.primary)) as db:
                    self.assertEqual(db.execute(
                        f'SELECT count(*) FROM {EDITION_TABLE}').fetchone()[0], 1)
                    self.assertEqual(db.execute(
                        f'SELECT count(*) FROM {SOURCES_TABLE}').fetchone()[0], 0)
                    self.assertEqual(db.execute(
                        'SELECT count(*) FROM access_memory_book_editorial').fetchone()[0], 1)
                    self.assertEqual(db.execute(
                        'SELECT count(*) FROM access_upload_annotations').fetchone()[0], 0)
                    self.assertEqual(db.execute(
                        'SELECT count(*) FROM access_memory_contributions').fetchone()[0], 0)
                code, report, _ = self.cli('--execute', '--all-writers-stopped')
                self.assertEqual(code, 2)
                self.assertEqual(report['status'], 'refused')
                self.assertFalse(self.journal.exists())
                self.assertEqual(self.snapshot_bytes(self.primary), primary_before)
                self.assertEqual(self.snapshot_bytes(self.backup), backup_before)

    def test_execute_binds_new_private_journal_after_locked_recheck(self):
        code, report, _ = self.cli('--execute', '--all-writers-stopped')
        self.assertEqual(code, 0)
        self.assertEqual(report['status'], 'bound')
        self.assertEqual(report['journal_sequence'], 0)
        self.assertRegex(report['journal_digest'], r'^[0-9a-f]{64}$')
        self.assertEqual(report['marker_rows'], 1)
        self.assertEqual(stat.S_IMODE(self.journal.stat().st_mode), 0o600)
        ledger = OriginalDeletionJournal(self.journal, self.namespace)
        with closing(sqlite3.connect(self.primary)) as db:
            self.assertEqual(ledger.assert_current(db),
                             (self.namespace, report['journal_sequence'], report['journal_digest']))
            marker = db.execute('SELECT namespace,applied_seq,applied_digest '
                                'FROM access_original_deletion_state WHERE id=1').fetchone()
        self.assertEqual(tuple(marker), (self.namespace, 0, report['journal_digest']))

    def test_mismatched_backup_is_refused_before_journal_creation(self):
        with closing(sqlite3.connect(self.backup)) as db:
            db.execute("UPDATE captions SET text='different synthetic value' WHERE id=101")
            db.commit()
        code, report, _ = self.cli('--execute', '--all-writers-stopped')
        self.assertEqual(code, 2)
        self.assertEqual(report['status'], 'refused')
        self.assertFalse(self.journal.exists())

    def test_existing_original_rows_are_refused_before_journal_creation(self):
        with closing(sqlite3.connect(self.primary)) as db:
            owner = db.execute("SELECT account_id FROM access_memberships "
                               "WHERE library_id='family-a' AND role='owner'").fetchone()[0]
            db.execute('''INSERT INTO access_upload_annotations
                (id,author_id,library_id,batch,asset_id,kind,original_text,original_audio,mime,
                 duration_ms,sha256,language,consent,mutation_id,request_digest,created_at)
                VALUES (?,?,'family-a',?,101,'text','Synthetic retained original',NULL,NULL,
                 NULL,?,'en',0,?,?,1)''',
                (str(uuid.uuid4()), owner, uuid.uuid4().hex, '0' * 64,
                 str(uuid.uuid4()), '1' * 64))
            db.commit()
        snapshot(self.primary, self.backup)
        code, report, _ = self.cli('--execute', '--all-writers-stopped')
        self.assertEqual(code, 2)
        self.assertEqual(report['status'], 'refused')
        self.assertFalse(self.journal.exists())

    def test_existing_non_original_memory_rows_do_not_block_binding(self):
        headers = {'Authorization': 'Bearer ' + self.f.owner_token}
        preview = self.f.client.post('/story-workspace/preview?library=family-a', headers=headers,
            json={'asset_ids': '101', 'title': 'Synthetic saved essay',
                  'theme': 'everyday', 'language': 'en'})
        self.assertEqual(preview.status_code, 200, preview.text)
        draft = preview.json()
        story_body = {'title': draft['title'], 'theme': draft['theme'], 'language': 'en',
            'asset_ids': '101', 'chapters': json.dumps(draft['chapters']),
            'selection_revision': draft['selection_revision'], 'revision': '0',
            'mutation_id': str(uuid.uuid4())}
        saved = self.f.client.post('/memory-stories?library=family-a',
                                   headers=headers, json=story_body)
        self.assertEqual(saved.status_code, 200, saved.text)
        book_id = str(uuid.uuid4())
        content = json.dumps({'title': 'Synthetic book', 'language': 'en',
            'introduction': '', 'kind': 'memoir', 'story_ids': [saved.json()['id']]})
        with closing(sqlite3.connect(self.primary)) as db:
            owner = db.execute("SELECT account_id FROM access_memberships "
                               "WHERE library_id='family-a' AND role='owner'").fetchone()[0]
            db.execute('''INSERT INTO access_memory_books
                (id,library_id,author_id,revision,content,created_at,updated_at)
                VALUES (?, 'family-a', ?, 1, ?, 1, 1)''', (book_id, owner, content))
            db.execute('''INSERT INTO access_memory_book_revisions
                (book_id,revision,editor_id,mutation_id,request_digest,content,occurred_at)
                VALUES(?,1,?,?,?, ?,1)''',
                (book_id, owner, str(uuid.uuid4()), 'a' * 64, content))
            db.execute('''INSERT INTO access_memory_book_editorial
                (book_id,book_revision,children_json,transitions_json,state)
                VALUES(?,1,'[]','[]','current')''', (book_id,))
            editorial_before = db.execute(
                'SELECT * FROM access_memory_book_editorial WHERE book_id=?',
                (book_id,)).fetchall()
            db.commit()
        snapshot(self.primary, self.backup)
        code, report, _ = self.cli('--execute', '--all-writers-stopped')
        self.assertEqual(code, 0)
        self.assertEqual(report['status'], 'bound')
        self.assertEqual(report['schema_revision'], 'c2e6b8a1d490')
        self.assertGreater(report['primary_rows'], report['original_rows'])
        with closing(sqlite3.connect(self.primary)) as db:
            self.assertEqual(db.execute(
                'SELECT * FROM access_memory_book_editorial WHERE book_id=?',
                (book_id,)).fetchall(), editorial_before)

    def test_locked_backup_change_preserves_new_empty_unbound_journal(self):
        original_initialize = OriginalDeletionJournal.initialize

        def initialize_then_change_backup(path, namespace):
            journal = original_initialize(path, namespace)
            with closing(sqlite3.connect(self.backup)) as db:
                db.execute("UPDATE captions SET text='changed after plan' WHERE id=101")
                db.commit()
            return journal

        with patch.object(bootstrap.OriginalDeletionJournal, 'initialize',
                          side_effect=initialize_then_change_backup):
            code, report, error = self.cli('--execute', '--all-writers-stopped')
        self.assertEqual(code, 2)
        self.assertEqual(report['status'], 'journal_created_unbound')
        self.assertEqual(report['journal_sequence'], 0)
        self.assertEqual(report['marker_rows'], 0)
        self.assertIn('preserve', error)
        self.assertTrue(self.journal.exists())
        self.assertEqual(OriginalDeletionJournal(self.journal, self.namespace).head()[1], 0)
        with closing(sqlite3.connect(self.primary)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM access_original_deletion_state').fetchone()[0], 0)

    def test_locked_primary_data_change_preserves_new_empty_unbound_journal(self):
        original_initialize = OriginalDeletionJournal.initialize

        def initialize_then_change_primary(path, namespace):
            journal = original_initialize(path, namespace)
            with closing(sqlite3.connect(self.primary)) as db:
                db.execute("UPDATE captions SET text='changed after plan' WHERE id=101")
                db.commit()
            return journal

        with patch.object(bootstrap.OriginalDeletionJournal, 'initialize',
                          side_effect=initialize_then_change_primary):
            code, report, _ = self.cli('--execute', '--all-writers-stopped')
        self.assertEqual(code, 2)
        self.assertEqual(report['status'], 'journal_created_unbound')
        self.assertEqual(report['journal_sequence'], 0)
        self.assertTrue(self.journal.exists())
        with closing(sqlite3.connect(self.primary)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM access_original_deletion_state').fetchone()[0], 0)

    def test_primary_file_replacement_after_review_is_refused(self):
        original_initialize = OriginalDeletionJournal.initialize

        def initialize_then_replace_primary(path, namespace):
            journal = original_initialize(path, namespace)
            replacement = self.root / 'replacement.sqlite'
            snapshot(self.primary, replacement)
            os.replace(replacement, self.primary)
            return journal

        with patch.object(bootstrap.OriginalDeletionJournal, 'initialize',
                          side_effect=initialize_then_replace_primary):
            code, report, _ = self.cli('--execute', '--all-writers-stopped')
        self.assertEqual(code, 2)
        self.assertEqual(report['status'], 'journal_created_unbound')
        self.assertTrue(self.journal.exists())
        self.assertEqual(OriginalDeletionJournal(self.journal, self.namespace).head()[1], 0)
        with closing(sqlite3.connect(self.primary)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM access_original_deletion_state').fetchone()[0], 0)

    def test_bad_namespace_and_existing_journal_target_refuse_without_writes(self):
        code, report, _ = self.cli('--namespace', str(uuid.uuid4()).upper())
        self.assertEqual(code, 2)
        self.assertEqual(report['status'], 'refused')
        self.assertFalse(self.journal.exists())

        OriginalDeletionJournal.initialize(self.journal, self.namespace)
        code, report, _ = self.cli('--execute', '--all-writers-stopped')
        self.assertEqual(code, 2)
        self.assertEqual(report['status'], 'refused')


if __name__ == '__main__':
    unittest.main()
