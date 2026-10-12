"""Synthetic security checks for the private assistant workspace store."""
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))

from app.access.assistant_workspace_store import (  # noqa: E402
    RETENTION_SECONDS,
    AssistantWorkspaceStore,
    WorkspaceStoreConflict,
    WorkspaceStoreMissing,
    WorkspaceStoreUnavailable,
    initialize,
)
from app.access import assistant_workspace_store as workspace_store_module  # noqa: E402


def new_id():
    return str(uuid.uuid4())


def card_ref():
    return dict(type='media', id='103', revision='a' * 64, fingerprint='b' * 64)


class AssistantWorkspaceStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        # macOS may expose its temporary directory through a /var symlink;
        # the store intentionally rejects symlinked parent paths.
        self.path = Path(self.temp.name).resolve() / 'private-assistant.sqlite'
        self.now = [1_800_000_000]
        self.store = initialize(self.path, clock=lambda: self.now[0])

    def append(self, account, library, thread, request, revision, **changes):
        args = dict(input_text='Find the park photos', reply='I found two photos.',
                    cards=[card_ref()], receipts=[])
        args.update(changes)
        return self.store.append_exchange(account, library, thread, request,
                                          revision, **args)

    def test_exclusive_initialization_private_sqlite_and_absent_open(self):
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute('PRAGMA application_id').fetchone()[0], 1346914882)
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 2)
            self.assertEqual(db.execute('PRAGMA journal_mode').fetchone()[0], 'delete')
        with self.store.connection() as db:
            self.assertEqual(db.execute('PRAGMA secure_delete').fetchone()[0], 1)
        with self.assertRaises(WorkspaceStoreUnavailable):
            initialize(self.path, clock=lambda: self.now[0])
        absent = Path(self.temp.name) / 'not-created.sqlite'
        with self.assertRaises(WorkspaceStoreUnavailable):
            AssistantWorkspaceStore(absent)
        self.assertFalse(absent.exists())

    def test_threads_are_private_to_exact_account_and_library(self):
        thread = self.store.create_thread('member-a', 'family-a')['thread_id']
        self.append('member-a', 'family-a', thread, new_id(), 0)

        self.assertEqual(len(self.store.list_threads('member-a', 'family-a')), 1)
        self.assertEqual(self.store.list_threads('member-b', 'family-a'), [])
        self.assertEqual(self.store.list_threads('member-a', 'family-b'), [])
        for account, library in (('member-b', 'family-a'), ('member-a', 'family-b')):
            with self.assertRaises(WorkspaceStoreMissing):
                self.store.get_thread(account, library, thread)
            with self.assertRaises(WorkspaceStoreMissing):
                self.store.delete_thread(account, library, thread, 1)
        detail = self.store.get_thread('member-a', 'family-a', thread)
        self.assertEqual(detail['exchanges'][0]['input_text'], 'Find the park photos')
        with self.assertRaises(WorkspaceStoreConflict):
            self.store.delete_thread('member-a', 'family-a', thread, 0)
        self.assertTrue(self.store.delete_thread('member-a', 'family-a', thread, 1)['deleted'])
        with self.assertRaises(WorkspaceStoreMissing):
            self.store.get_thread('member-a', 'family-a', thread)

    def test_revision_conflict_and_exact_idempotent_retry(self):
        thread = self.store.create_thread('member-a', 'family-a')['thread_id']
        request = new_id()
        first = self.append('member-a', 'family-a', thread, request, 0)
        retry = self.append('member-a', 'family-a', thread, request, 0)
        self.assertFalse(first['replayed'])
        self.assertTrue(retry['replayed'])
        self.assertEqual(first['exchange'], retry['exchange'])
        self.assertEqual(first['revision'], 1)

        with self.assertRaises(WorkspaceStoreConflict):
            self.append('member-a', 'family-a', thread, request, 0,
                        reply='Changed payload')
        with self.assertRaises(WorkspaceStoreConflict):
            self.append('member-a', 'family-a', thread, request, 1)
        with self.assertRaises(WorkspaceStoreConflict):
            self.append('member-a', 'family-a', thread, new_id(), 0)
        self.assertEqual(len(self.store.get_thread('member-a', 'family-a', thread)['exchanges']), 1)

    def test_expected_revisions_reject_bool_negative_and_sqlite_overflow(self):
        thread = self.store.create_thread('member-a', 'family-a')['thread_id']
        invalid = (True, -1, 1 << 63, 1 << 100)
        for revision in invalid:
            with self.subTest(operation='append', revision=revision):
                with self.assertRaises(ValueError):
                    self.append('member-a', 'family-a', thread, new_id(), revision)
            with self.subTest(operation='delete', revision=revision):
                with self.assertRaises(ValueError):
                    self.store.delete_thread('member-a', 'family-a', thread, revision)
            with self.subTest(operation='preference update', revision=revision):
                with self.assertRaises(ValueError):
                    self.store.update_preferences('member-a', revision, {'locale': 'en'})
            with self.subTest(operation='preference reset', revision=revision):
                with self.assertRaises(ValueError):
                    self.store.reset_preferences('member-a', revision)

    def test_payload_accepts_only_bounded_text_typed_refs_and_receipt_ids(self):
        thread = self.store.create_thread('member-a', 'family-a')['thread_id']
        opaque_ids = ('103', new_id(), 'chapter_02-v1.3')
        accepted = self.append('member-a', 'family-a', thread, new_id(), 0,
                               cards=[dict(card_ref(), id=ident) for ident in opaque_ids])
        self.assertEqual([item['id'] for item in accepted['exchange']['cards']],
                         list(opaque_ids))
        invalid_cards = [
            [dict(card_ref(), audio='data:audio/wav;base64,secret')],
            [dict(card_ref(), url='https://example.invalid/private')],
            [dict(type='provider_object', id='1', revision='a' * 64, fingerprint='b' * 64)],
        ]
        for cards in invalid_cards:
            with self.assertRaises(ValueError):
                self.append('member-a', 'family-a', thread, new_id(), 1, cards=cards)
        unsafe_ids = (
            'https://user:pass@example.invalid/media/103?token=secret',
            '/private/media/103',
            'media?id=103',
            'user:pass@example.invalid',
            '.', '..', '相册-103', 'x' * 129,
        )
        for ident in unsafe_ids:
            with self.subTest(card_id=ident):
                with self.assertRaises(ValueError):
                    self.append('member-a', 'family-a', thread, new_id(), 1,
                                cards=[dict(card_ref(), id=ident)])
        with self.assertRaises(TypeError):
            self.store.append_exchange('member-a', 'family-a', thread, new_id(), 1,
                                       input_text='x', reply='y', cards=[], receipts=[],
                                       audio=b'raw audio')
        with self.assertRaises(ValueError):
            self.append('member-a', 'family-a', thread, new_id(), 1,
                        input_text='汉' * 342)
        with self.assertRaises(ValueError):
            self.append('member-a', 'family-a', thread, 'not-a-v4-id', 1)
        with self.assertRaises(ValueError):
            self.append('member-a', 'family-a', thread, new_id(), 1,
                        receipts=['not-a-v4-id'])

    def test_turn_expiry_is_fixed_per_exchange_and_preferences_remain(self):
        prefs = self.store.update_preferences('member-a', 0,
                                              {'locale': 'zh', 'voice_pace': 'slow'})
        self.assertEqual(prefs['revision'], 1)
        thread = self.store.create_thread('member-a', 'family-a')['thread_id']
        first_request = new_id()
        first = self.append('member-a', 'family-a', thread, first_request, 0)
        with sqlite3.connect(self.path) as db:
            first_created, first_expires = db.execute(
                'SELECT created_at,expires_at FROM exchanges WHERE request_id=?',
                (first_request,)).fetchone()
        self.assertEqual(first_expires, first_created + RETENTION_SECONDS)
        self.now[0] += 29 * 86400
        second = self.append('member-a', 'family-a', thread, new_id(), 1,
                             input_text='Only videos', reply='One video.')
        self.now[0] += 2 * 86400
        history = self.store.get_thread('member-a', 'family-a', thread)
        self.assertEqual([item['revision'] for item in history['exchanges']], [2])
        self.assertEqual(self.store.get_preferences('member-a'), prefs)
        second_created = datetime.fromisoformat(
            second['exchange']['created_at'].replace('Z', '+00:00'))
        second_expiry = (second_created + timedelta(seconds=RETENTION_SECONDS)).isoformat()
        self.assertEqual(second['exchange']['expires_at'],
                         second_expiry.replace('+00:00', 'Z'))
        self.assertEqual(self.store.prune(), dict(exchanges=1, threads=0))

    def test_preferences_are_strict_account_owned_revisioned_and_resettable(self):
        self.assertEqual(self.store.get_preferences('member-a'),
                         dict(locale=None, reply_length=None, voice_pace=None, revision=0))
        updated = self.store.update_preferences('member-a', 0,
                                                {'locale': 'en', 'reply_length': 'brief'})
        self.assertEqual(updated, dict(locale='en', reply_length='brief',
                                       voice_pace=None, revision=1))
        self.assertEqual(self.store.get_preferences('member-b')['revision'], 0)
        with self.assertRaises(WorkspaceStoreConflict):
            self.store.update_preferences('member-a', 0, {'locale': 'zh'})
        for bad in ({'voice': 'warm'}, {'locale': 'fr'}, {'reply_length': 'long'},
                    {'voice_pace': 'fast'}, {'locale': True}, {'remembered_fact': 'x'}):
            with self.assertRaises(ValueError):
                self.store.update_preferences('member-a', 1, bad)
        cleared = self.store.reset_preferences('member-a', 1)
        self.assertEqual(cleared, dict(locale=None, reply_length=None,
                                      voice_pace=None, revision=2))
        with self.assertRaises(WorkspaceStoreConflict):
            self.store.reset_preferences('member-a', 1)
        self.assertEqual(self.store.get_preferences('member-a'), cleared)

    def test_open_refuses_an_existing_schema_mismatch(self):
        with sqlite3.connect(self.path) as db:
            db.execute('ALTER TABLE threads ADD COLUMN unexpected TEXT')
        with self.assertRaises(WorkspaceStoreUnavailable):
            AssistantWorkspaceStore(self.path)

    def test_fixed_thread_expiry_and_explicit_prune(self):
        thread = self.store.create_thread('member-a', 'family-a')['thread_id']
        self.append('member-a', 'family-a', thread, new_id(), 0)
        self.now[0] += RETENTION_SECONDS + 1
        self.assertEqual(self.store.list_threads('member-a', 'family-a'), [])
        self.assertEqual(self.store.prune(), dict(exchanges=1, threads=1))

    def test_get_thread_reads_parent_and_exchanges_from_one_snapshot(self):
        thread = self.store.create_thread('member-a', 'family-a')['thread_id']
        self.append('member-a', 'family-a', thread, new_id(), 0)
        parent_read = threading.Event()
        release_reader = threading.Event()
        writer_ready = threading.Event()
        writer_committed = threading.Event()
        reader_result = []
        worker_errors = []
        original_connect = sqlite3.connect

        class PausingCursor(sqlite3.Cursor):
            def execute(self, sql, parameters=()):
                self.statement = sql
                return super().execute(sql, parameters)

            def fetchone(self):
                row = super().fetchone()
                if (row is not None and 'FROM threads WHERE thread_id=?' in self.statement
                        and not parent_read.is_set()):
                    parent_read.set()
                    if not release_reader.wait(3):
                        raise RuntimeError('test reader timed out')
                return row

        class PausingConnection(sqlite3.Connection):
            def cursor(self, factory=None):
                return super().cursor(factory or PausingCursor)

            def execute(self, sql, parameters=()):
                return self.cursor().execute(sql, parameters)

        def intercepted_connect(database, *args, **kwargs):
            if type(database) is str and '?mode=rw' in database:
                kwargs['factory'] = PausingConnection
            return original_connect(database, *args, **kwargs)

        def read_thread():
            try:
                reader_result.append(self.store.get_thread('member-a', 'family-a', thread))
            except BaseException as error:  # surfaced in the main test thread
                worker_errors.append(error)

        def append_concurrently():
            try:
                with original_connect(self.path, timeout=3, isolation_level=None) as db:
                    db.execute('PRAGMA foreign_keys=ON')
                    db.execute('BEGIN IMMEDIATE')
                    now = self.now[0] + 1
                    db.execute('''INSERT INTO exchanges(exchange_id,thread_id,account_id,library_id,
                        request_id,revision,created_at,expires_at,input_text,reply,card_refs,receipt_ids,
                        payload_fingerprint) VALUES (?,?,?,?,?,2,?,?,?,?,'[]','[]',?)''',
                               (new_id(), thread, 'member-a', 'family-a', new_id(), now,
                                now + RETENTION_SECONDS, 'New turn', 'New reply', 'c' * 64))
                    db.execute('UPDATE threads SET revision=2,updated_at=?,expires_at=? WHERE thread_id=?',
                               (now, now + RETENTION_SECONDS, thread))
                    writer_ready.set()
                    db.commit()
                    writer_committed.set()
            except BaseException as error:  # surfaced in the main test thread
                worker_errors.append(error)

        reader = threading.Thread(target=read_thread)
        writer = threading.Thread(target=append_concurrently)
        try:
            with patch.object(workspace_store_module.sqlite3, 'connect', intercepted_connect):
                reader.start()
                self.assertTrue(parent_read.wait(3), 'reader did not capture the thread row')
                writer.start()
                self.assertTrue(writer_ready.wait(3), 'writer did not stage its update')
                # In DELETE journal mode the active read transaction keeps the
                # writer commit pending until both reads finish.
                self.assertFalse(writer_committed.wait(.1))
                release_reader.set()
                reader.join(3)
                self.assertFalse(reader.is_alive())
                self.assertTrue(writer_committed.wait(3), 'writer did not commit after reader closed')
                writer.join(3)
            self.assertEqual(worker_errors, [])
            snapshot = reader_result[0]
            self.assertEqual(snapshot['thread']['revision'], 1)
            self.assertEqual([item['revision'] for item in snapshot['exchanges']], [1])
        finally:
            release_reader.set()
            reader.join(3)
            writer.join(3)
        current = self.store.get_thread('member-a', 'family-a', thread)
        self.assertEqual(current['thread']['revision'], 2)
        self.assertEqual([item['revision'] for item in current['exchanges']], [1, 2])


if __name__ == '__main__':
    unittest.main()
