"""Security and lifecycle checks for durable private assistant turns."""
from pathlib import Path
import json
import sqlite3
import sys
import tempfile
import threading
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))

from app.access import assistant_workspace_store as module  # noqa: E402
from app.access.assistant_workspace_store import (  # noqa: E402
    AssistantWorkspaceStore,
    RETENTION_SECONDS,
    WorkspaceStoreConflict,
    WorkspaceStoreMissing,
    WorkspaceStoreUnavailable,
    initialize_v2,
    offline_upgrade_v1,
)


def new_id():
    return str(uuid.uuid4())


def context(library='family-a', ids=None, total=2, filters=None):
    return dict(library_id=library, binding='a' * 64, fingerprint='b' * 64,
                filters={'media': ['photo']} if filters is None else filters,
                visible_ids=['103', '104'] if ids is None else ids, total=total)


def summary(library='family-a', *, kind='results', ctx=None, effect=None,
            filters=None, total=2):
    ctx = context(library, total=total, filters=filters) if ctx is None else ctx
    return dict(version=1, kind=kind, reply='Found two photos.', context=ctx,
                filters=ctx['filters'] if ctx else None, total=total,
                has_more=False, effect=effect)


class AssistantWorkspaceTurnStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name).resolve() / 'turns.sqlite'
        self.now = [1_800_000_000]
        self.store = initialize_v2(self.path, clock=lambda: self.now[0])
        self.account, self.library = 'member-a', 'family-a'
        self.thread = self.store.create_thread(self.account, self.library)['thread_id']

    def begin(self, *, request=None, revision=0, text='Find photos'):
        return self.store.begin_turn(self.account, self.library, self.thread,
                                     new_id() if request is None else request,
                                     revision, text)

    def test_pending_replay_context_commit_and_latest_turn(self):
        first = self.begin()
        self.assertEqual(first['status'], 'pending')
        self.assertEqual(first['revision'], 0)
        self.assertFalse(first['replayed'])
        replay = self.begin(request=first['request_id'])
        self.assertTrue(replay['replayed'])
        self.assertEqual(replay['lease_id'], first['lease_id'])
        with self.assertRaises(WorkspaceStoreConflict):
            self.begin(request=first['request_id'], text='Changed input')
        with self.assertRaises(WorkspaceStoreConflict):
            self.begin(request=first['request_id'], revision=1)
        with self.assertRaises(WorkspaceStoreConflict):
            self.store.append_exchange(self.account, self.library, self.thread,
                                       new_id(), 0, 'legacy', 'reply', [], [])

        done = self.store.complete_turn(self.account, self.library, self.thread,
                                        first['request_id'], first['lease_id'],
                                        summary(), cards=[], receipts=[])
        self.assertEqual((done['status'], done['revision']), ('completed', 1))
        self.assertEqual(done['result_summary']['kind'], 'results')
        self.assertEqual(self.store.latest_turn_id(self.account, self.library, self.thread),
                         first['request_id'])
        fetched = self.store.get_turn(self.account, self.library, self.thread,
                                      first['request_id'])
        self.assertTrue(fetched['replayed'])
        self.assertEqual(fetched['result_summary'], done['result_summary'])

        detail = self.store.get_thread(self.account, self.library, self.thread)
        self.assertEqual(detail['exchanges'][0]['input_text'], 'Find photos')
        with self.store.connection() as db:
            row = db.execute('SELECT created_at,expires_at FROM turn_requests').fetchone()
            exchange = db.execute('SELECT created_at,expires_at FROM exchanges').fetchone()
            ctx = db.execute('SELECT created_at,expires_at FROM thread_context').fetchone()
        self.assertEqual(row['expires_at'], row['created_at'] + RETENTION_SECONDS)
        self.assertEqual(exchange['created_at'], row['created_at'])
        self.assertEqual(exchange['expires_at'], row['expires_at'])
        self.assertEqual(ctx['created_at'], row['created_at'])
        self.assertEqual(ctx['expires_at'], row['expires_at'])

    def test_existing_only_lookup_reserves_nothing_and_keeps_request_conflicts(self):
        ident = new_id()
        self.assertIsNone(self.store.begin_turn(self.account, self.library, self.thread,
            ident, 0, 'Find photos', existing_only=True))
        with self.store.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM turn_requests').fetchone()[0], 0)
        pending = self.begin(request=ident)
        replay = self.store.begin_turn(self.account, self.library, self.thread,
            ident, 0, 'Find photos', existing_only=True)
        self.assertTrue(replay['replayed'])
        self.assertEqual(replay['lease_id'], pending['lease_id'])
        with self.assertRaises(WorkspaceStoreConflict):
            self.store.begin_turn(self.account, self.library, self.thread,
                ident, 0, 'Other words', existing_only=True)
        with self.assertRaises(WorkspaceStoreConflict):
            self.store.begin_turn(self.account, self.library, self.thread,
                ident, 1, 'Find photos', existing_only=True)

    def test_one_pending_reservation_across_store_instances(self):
        other = AssistantWorkspaceStore(self.path, clock=lambda: self.now[0])
        results, errors = [], []
        gate = threading.Barrier(3)

        def reserve(store):
            gate.wait()
            try:
                results.append(store.begin_turn(self.account, self.library, self.thread,
                                                new_id(), 0, 'Find photos'))
            except BaseException as error:
                errors.append(error)

        a = threading.Thread(target=reserve, args=(self.store,))
        b = threading.Thread(target=reserve, args=(other,))
        a.start(); b.start(); gate.wait()
        a.join(3); b.join(3)
        self.assertFalse(a.is_alive() or b.is_alive())
        self.assertEqual(len(results), 1)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], WorkspaceStoreConflict)

    def test_open_does_not_interrupt_live_lease_and_expired_lease_is_terminal(self):
        pending = self.begin()
        reopened = AssistantWorkspaceStore(self.path, clock=lambda: self.now[0])
        with self.assertRaises(WorkspaceStoreConflict):
            reopened.begin_turn(self.account, self.library, self.thread, new_id(), 0, 'Again')
        self.now[0] += module.LEASE_SECONDS
        interrupted = reopened.get_turn(self.account, self.library, self.thread,
                                         pending['request_id'])
        self.assertEqual(interrupted['status'], 'interrupted')
        self.assertEqual(interrupted['error_code'], 'turn_interrupted')
        self.assertIsNone(interrupted['lease_id'])
        with self.assertRaises(WorkspaceStoreConflict):
            reopened.complete_turn(self.account, self.library, self.thread,
                                   pending['request_id'], pending['lease_id'], summary())

    def test_cancel_failure_keeps_revision_and_context_unchanged(self):
        pending = self.begin()
        failed = self.store.fail_turn(self.account, self.library, self.thread,
                                      pending['request_id'], pending['lease_id'],
                                      'request_cancelled')
        self.assertEqual(failed['status'], 'failed')
        self.assertEqual(failed['error_code'], 'request_cancelled')
        self.assertEqual(failed['revision'], 0)
        self.assertIsNone(self.store.latest_turn_id(self.account, self.library, self.thread))
        self.assertIsNone(self.store.begin_turn(self.account, self.library, self.thread,
                                                new_id(), 0, 'Find photos')['context'])

    def test_scope_isolation_deletion_and_invalid_saved_summaries(self):
        pending = self.begin()
        for account, library in (('member-b', self.library), (self.account, 'family-b')):
            with self.assertRaises(WorkspaceStoreMissing):
                self.store.get_turn(account, library, self.thread, pending['request_id'])
        bad = [
            dict(summary(), items=[]),
            dict(summary(), context=dict(context(), library_id='family-b')),
            dict(summary(), context=dict(context(), binding='z' * 64)),
            dict(summary(), context=dict(context(), visible_ids=['0103'])),
            dict(summary(), effect={'type': 'open_asset', 'asset_id': '999'}),
            dict(summary(), reply='x' * 8193),
        ]
        for value in bad:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.store.complete_turn(self.account, self.library, self.thread,
                                             pending['request_id'], pending['lease_id'], value)
        self.store.delete_thread(self.account, self.library, self.thread, 0)
        with self.assertRaises(WorkspaceStoreMissing):
            self.store.get_turn(self.account, self.library, self.thread, pending['request_id'])

    def test_open_effect_must_reference_visible_id_and_context_must_match_filters(self):
        pending = self.begin()
        opened = summary(kind='open', effect={'type': 'open_asset', 'asset_id': '104'})
        result = self.store.complete_turn(self.account, self.library, self.thread,
                                          pending['request_id'], pending['lease_id'], opened)
        self.assertEqual(result['result_summary']['effect']['asset_id'], '104')
        pending2 = self.store.begin_turn(self.account, self.library, self.thread,
                                         new_id(), 1, 'Refine')
        mismatched = summary()
        mismatched['filters'] = {'media': ['video']}
        with self.assertRaises(ValueError):
            self.store.complete_turn(self.account, self.library, self.thread,
                                     pending2['request_id'], pending2['lease_id'], mismatched)

    def test_carried_context_keeps_original_thirty_day_expiry(self):
        first = self.begin()
        self.store.complete_turn(self.account, self.library, self.thread,
                                 first['request_id'], first['lease_id'], summary())
        with self.store.connection() as db:
            original = db.execute('SELECT created_at,expires_at,context_json FROM thread_context '
                                  'WHERE thread_id=?', (self.thread,)).fetchone()
        original_context = json.loads(original['context_json'])

        self.now[0] += 29 * 86400
        followup = self.store.begin_turn(self.account, self.library, self.thread,
                                         new_id(), 1, 'What else?')
        self.assertEqual(followup['context'], original_context)
        carried = summary(kind='unsupported', ctx=followup['context'])
        self.store.complete_turn(self.account, self.library, self.thread,
                                 followup['request_id'], followup['lease_id'], carried)
        with self.store.connection() as db:
            retained = db.execute('SELECT created_at,expires_at FROM thread_context '
                                  'WHERE thread_id=?', (self.thread,)).fetchone()
        self.assertEqual(tuple(retained), tuple(original[:2]))

        self.now[0] += 2 * 86400
        next_turn = self.store.begin_turn(self.account, self.library, self.thread,
                                          new_id(), 2, 'Find more')
        self.assertIsNone(next_turn['context'])

    def test_reads_reject_tampered_stored_context_and_summary(self):
        pending = self.begin()
        self.store.complete_turn(self.account, self.library, self.thread,
                                 pending['request_id'], pending['lease_id'], summary())
        with sqlite3.connect(self.path) as db:
            row = db.execute('SELECT result_summary FROM turn_requests').fetchone()
            db.execute('UPDATE turn_requests SET result_summary=?',
                       (row[0][:-1] + ',"unexpected":true}',))
        with self.assertRaises(WorkspaceStoreUnavailable):
            self.store.get_turn(self.account, self.library, self.thread, pending['request_id'])

        # Restore the valid summary, then corrupt the independent context record.
        with sqlite3.connect(self.path) as db:
            db.execute('UPDATE turn_requests SET result_summary=?', (row[0],))
            context_row = db.execute('SELECT context_json FROM thread_context').fetchone()
            db.execute('UPDATE thread_context SET context_json=?',
                       (context_row[0][:-1] + ',"unexpected":true}',))
        with self.assertRaises(WorkspaceStoreUnavailable):
            self.store.begin_turn(self.account, self.library, self.thread, new_id(), 1, 'Again')

    def test_stored_oversize_json_fails_as_generic_unavailable(self):
        pending = self.begin()
        self.store.complete_turn(self.account, self.library, self.thread,
                                 pending['request_id'], pending['lease_id'], summary())
        with sqlite3.connect(self.path) as db:
            db.execute('UPDATE turn_requests SET result_summary=?', (' ' * (32 * 1024 + 1),))
        with self.assertRaises(WorkspaceStoreUnavailable) as caught:
            self.store.get_turn(self.account, self.library, self.thread, pending['request_id'])
        self.assertEqual(str(caught.exception), '')

    def test_constructor_rejects_v1_and_explicit_upgrade_preserves_rows_and_mode(self):
        legacy = self.path.parent / 'v1.sqlite'
        with sqlite3.connect(legacy) as db:
            db.executescript(module._V1_SCHEMA_SQL)
            thread = new_id(); exchange = new_id(); request = new_id()
            created = self.now[0]
            db.execute('INSERT INTO threads VALUES (?,?,?,?,?,?,?)',
                       (thread, 'member-a', 'family-a', created, created,
                        created + RETENTION_SECONDS, 1))
            db.execute('''INSERT INTO exchanges VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                       (exchange, thread, 'member-a', 'family-a', request, 1,
                        created, created + RETENTION_SECONDS, 'Old input', 'Old reply',
                        '[]', '[]', 'a' * 64))
            db.execute('INSERT INTO preferences VALUES (?,?,?,?,?,?)',
                       ('member-a', 'zh', 'brief', 'slow', 4, 150))
        legacy.chmod(0o640)
        with self.assertRaises(WorkspaceStoreUnavailable):
            AssistantWorkspaceStore(legacy)
        upgraded = offline_upgrade_v1(legacy)
        self.assertEqual(legacy.stat().st_mode & 0o777, 0o640)
        self.assertEqual(upgraded.get_thread('member-a', 'family-a', thread)['exchanges'][0]['request_id'],
                         request)
        self.assertEqual(upgraded.get_preferences('member-a')['revision'], 4)
        with upgraded.connection() as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 2)
            self.assertEqual(db.execute('SELECT count(*) FROM turn_requests').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT count(*) FROM threads').fetchone()[0], 1)

    def test_malformed_v1_upgrade_is_refused_without_partial_migration(self):
        legacy = self.path.parent / 'bad-v1.sqlite'
        with sqlite3.connect(legacy) as db:
            db.executescript(module._V1_SCHEMA_SQL)
            db.execute('ALTER TABLE threads ADD COLUMN extra TEXT')
        with self.assertRaises(WorkspaceStoreUnavailable):
            offline_upgrade_v1(legacy)
        with sqlite3.connect(legacy) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 1)
            names = {row[0] for row in db.execute("SELECT name FROM sqlite_master")}
            self.assertNotIn('turn_requests', names)


if __name__ == '__main__':
    unittest.main()
