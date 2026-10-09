"""Additional failure-boundary tests for family-note deletion replay."""
from contextlib import closing
import hashlib
import shutil
import sqlite3
import unittest
import uuid

import test_family_note_deletions as fixture
from app.access.family_note_deletions import prepare_family_tombstone
from app.access.family_note_identity_schema import IDENTITIES, SCOPES
from app.access.original_deletions import OriginalDeletionError


def _uuid():
    return str(uuid.uuid4())


def _sha(value):
    return hashlib.sha256(value).hexdigest()


class FamilyNoteDeletionBoundaryTests(unittest.TestCase):
    """Compose the shared fixture without inheriting/rerunning its test methods."""

    @classmethod
    def setUpClass(cls):
        fixture.FamilyNoteDeletionTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        fixture.FamilyNoteDeletionTests.tearDownClass()

    def setUp(self):
        self.base = fixture.FamilyNoteDeletionTests()
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.f = self.base.f

    def _pending_family_delete(self):
        self.base._upgrade_journal()
        with self.f.connection() as db:
            db.execute('PRAGMA secure_delete=ON')
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT revision FROM access_stories WHERE id=?',
                              (self.base.note['id'],)).fetchone()
            candidate = prepare_family_tombstone(db, self.base.note['id'], row[0], self.f.now)
            self.base.journal.append(db, 'family_note',
                {'id': self.base.note['id'], 'revision': row[0]}, self.f.now)
            db.rollback()
        ledger = self.base.journal._connect()
        try:
            record = dict(ledger.execute("SELECT * FROM deletions WHERE collection='family_note' "
                                         'AND object_id=?', (self.base.note['id'],)).fetchone())
        finally:
            ledger.close()
        return candidate, record

    def _remove_book_without_foreign_keys(self, path):
        db = sqlite3.connect(path)
        db.execute('PRAGMA foreign_keys=OFF')
        db.execute('DELETE FROM access_memory_books WHERE id=?', (self.base.seed.book_id,))
        db.commit()
        db.execute('PRAGMA foreign_keys=ON')
        return db

    def test_equal_revision_changed_content_in_pre_move_backup_refuses_atomically(self):
        backup = self.base.root / 'same-revision-before-move.sqlite'
        fixture._snapshot(self.f.path, backup)
        self.base._move_note()
        self.base._live_erase()
        _, restored = self.base._restore(backup)
        with closing(restored):
            restored.execute("UPDATE access_stories SET text='tampered at same revision' WHERE id=?",
                             (self.base.note['id'],))
            restored.commit()
            before = self.base._marker(restored)
            with self.assertRaises(OriginalDeletionError):
                self.base.journal.replay(restored)
            self.assertEqual(self.base._marker(restored), before)
            self.assertEqual(restored.execute('SELECT revision,text FROM access_stories WHERE id=?',
                (self.base.note['id'],)).fetchone(), (1, 'tampered at same revision'))

    def test_unbound_normalized_family_closure_refuses_before_append(self):
        _proposal, _raw, receipt, _job = self.base.seed._saved()
        with self.f.connection() as db:
            db.execute('''DELETE FROM access_memory_book_edition_family_notes
                WHERE edition_id=?''', (receipt['id'],))
            db.commit()
        self.base._upgrade_journal()
        before = self.base.journal.head()
        with self.f.connection() as db:
            db.execute('PRAGMA secure_delete=ON')
            db.execute('BEGIN IMMEDIATE')
            revision = db.execute('SELECT revision FROM access_stories WHERE id=?',
                                  (self.base.note['id'],)).fetchone()[0]
            with self.assertRaises(OriginalDeletionError):
                self.base.journal.append(db, 'family_note',
                    {'id': self.base.note['id'], 'revision': revision}, self.f.now)
            db.rollback()
        self.assertEqual(self.base.journal.head(), before)
        with self.f.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM access_stories WHERE id=?',
                                        (self.base.note['id'],)).fetchone()[0], 1)

    def test_orphaned_historical_edition_helper_scrubs_but_replay_refuses_other_fk_damage(self):
        _proposal, _raw, receipt, _job = self.base.seed._saved()
        backup = self.base.root / 'edition-parent-backup.sqlite'
        fixture._snapshot(self.f.path, backup)
        _candidate, record = self._pending_family_delete()

        helper_path = self.base.root / 'edition-orphan-helper.sqlite'
        shutil.copyfile(backup, helper_path)
        helper_db = self._remove_book_without_foreign_keys(helper_path)
        with closing(helper_db):
            helper_db.execute('PRAGMA secure_delete=ON')
            helper_db.execute('BEGIN IMMEDIATE')
            from app.access.family_note_deletions import erase_family_note_original
            erase_family_note_original(helper_db, record)
            helper_db.commit()
            edition = helper_db.execute('SELECT state,manuscript_json FROM access_memory_book_editions WHERE id=?',
                                        (receipt['id'],)).fetchone()
            self.assertEqual(edition, ('source_invalidated', None))

        replay_path = self.base.root / 'edition-orphan-replay.sqlite'
        shutil.copyfile(backup, replay_path)
        replay_db = self._remove_book_without_foreign_keys(replay_path)
        with closing(replay_db):
            before = self.base._marker(replay_db)
            with self.assertRaises(OriginalDeletionError):
                self.base.journal.replay(replay_db)
            self.assertEqual(self.base._marker(replay_db), before)
            self.assertEqual(replay_db.execute('SELECT count(*) FROM access_stories WHERE id=?',
                                               (self.base.note['id'],)).fetchone()[0], 1)
            edition = replay_db.execute('SELECT state,manuscript_json FROM access_memory_book_editions WHERE id=?',
                                        (receipt['id'],)).fetchone()
            self.assertEqual(edition[0], 'current')
            self.assertIsNotNone(edition[1])

    def test_mixed_v1_upload_and_v2_family_chain_replays_from_v1_marker(self):
        upload_id, batch = _uuid(), 'c' * 32
        raw = 'synthetic V1 upload original'
        with self.f.connection() as db:
            author = db.execute('SELECT author_id FROM access_stories WHERE id=?',
                                (self.base.note['id'],)).fetchone()[0]
            db.execute('''INSERT INTO access_upload_annotations
                (id,author_id,library_id,batch,asset_id,kind,original_text,original_audio,
                 mime,duration_ms,sha256,language,consent,mutation_id,request_digest,created_at)
                VALUES (?,?, 'family-a',?,101,'text',?,NULL,NULL,NULL,?,'en',1,?,?,?)''',
                (upload_id, author, batch, raw, _sha(raw.encode()), _uuid(), _sha(b'upload'), self.f.now))
            db.commit()
        earlier_backup = self.base.root / 'mixed-chain-before-v1.sqlite'
        fixture._snapshot(self.f.path, earlier_backup)
        with self.f.connection() as db:
            db.execute('PRAGMA secure_delete=ON')
            db.execute('BEGIN IMMEDIATE')
            cursor = db.execute('SELECT * FROM access_upload_annotations WHERE id=?', (upload_id,))
            row = dict(zip((column[0] for column in cursor.description), cursor.fetchone()))
            first = self.base.journal.append(db, 'upload', row, self.f.now)
            db.execute('DELETE FROM access_upload_annotations WHERE id=?', (upload_id,))
            db.commit()
        v1_digest = first['digest']
        backup = self.base.root / 'mixed-chain-after-v1.sqlite'
        fixture._snapshot(self.f.path, backup)

        self.base._live_erase()
        self.assertEqual(self.base.journal.history_digest(1), v1_digest)
        _, restored = self.base._restore(backup)
        with closing(restored):
            self.assertEqual(self.base.journal.replay(restored)[3], 1)
            self.assertEqual(restored.execute('SELECT count(*) FROM access_stories WHERE id=?',
                                              (self.base.note['id'],)).fetchone()[0], 0)
            self.assertEqual(self.base._marker(restored)[0], 2)
        _, earlier = self.base._restore(earlier_backup)
        with closing(earlier):
            self.assertEqual(self.base.journal.replay(earlier)[3], 2)
            self.assertEqual(earlier.execute('SELECT count(*) FROM access_upload_annotations').fetchone()[0], 0)
            self.assertEqual(earlier.execute('SELECT count(*) FROM access_stories').fetchone()[0], 0)
            self.assertEqual(self.base._marker(earlier)[0], 2)

    def test_pending_retry_with_changed_revision_and_content_refuses_without_advancing_marker(self):
        self._pending_family_delete()
        original_head = self.base.journal.head()
        self.base._edit_note(revision=1, text='changed while deletion was pending')
        with self.f.connection() as db:
            db.execute('PRAGMA secure_delete=ON')
            db.execute('BEGIN IMMEDIATE')
            with self.assertRaises(OriginalDeletionError):
                self.base.journal.append(db, 'family_note',
                    {'id': self.base.note['id'], 'revision': 2}, self.f.now + 1)
            db.rollback()
            current = db.execute('SELECT revision,text FROM access_stories WHERE id=?',
                                 (self.base.note['id'],)).fetchone()
            self.assertEqual(current, (2, 'changed while deletion was pending'))
            self.assertEqual(self.base._marker(db)[0], 0)
        self.assertEqual(self.base.journal.head(), original_head)

    def test_missing_identity_with_absent_note_and_revisions_refuses_replay(self):
        backup = self.base.root / 'missing-identity-base.sqlite'
        fixture._snapshot(self.f.path, backup)
        self._pending_family_delete()
        missing_path = self.base.root / 'missing-identity.sqlite'
        shutil.copyfile(backup, missing_path)
        db = sqlite3.connect(missing_path)
        with closing(db):
            db.execute('PRAGMA foreign_keys=OFF')
            identity = db.execute(f'SELECT identity_id FROM {IDENTITIES} WHERE note_id=?',
                                  (self.base.note['id'],)).fetchone()[0]
            from app.access.family_note_identity_schema import sqlite_family_note_identity_contract
            delete_guards = {}
            for kind, name, ddl in sqlite_family_note_identity_contract():
                if kind == 'trigger' and name in {
                        f'trg_{SCOPES}_delete', f'trg_{IDENTITIES}_delete'}:
                    delete_guards[name] = ddl
                    db.execute('DROP TRIGGER ' + name)
            db.execute('DELETE FROM access_story_revisions WHERE story_id=?', (self.base.note['id'],))
            db.execute('DELETE FROM access_stories WHERE id=?', (self.base.note['id'],))
            db.execute(f'DELETE FROM {SCOPES} WHERE identity_id=?', (identity,))
            db.execute(f'DELETE FROM {IDENTITIES} WHERE identity_id=?', (identity,))
            for ddl in delete_guards.values():
                db.execute(ddl)
            db.commit()
            db.execute('PRAGMA foreign_keys=ON')
            before = self.base._marker(db)
            with self.assertRaises(OriginalDeletionError):
                self.base.journal.replay(db)
            self.assertEqual(self.base._marker(db), before)
            self.assertEqual(db.execute('SELECT count(*) FROM access_stories WHERE id=?',
                                        (self.base.note['id'],)).fetchone()[0], 0)
            self.assertEqual(db.execute(f'SELECT count(*) FROM {IDENTITIES} WHERE note_id=?',
                                        (self.base.note['id'],)).fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
