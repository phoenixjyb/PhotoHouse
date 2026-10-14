"""Generated V4 journal/recording restore cases; no real recordings or live data."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import unittest
from unittest.mock import patch
import uuid

import test_oral_history_intake as fixture_module
from app.access.oral_history_intake import OralHistoryIntake
from app.access.oral_history_schema import SESSION,SECTION,MUTATION,STATEMENTS
from app.access.oral_history_withdrawal import parse_recording_binding
from app.access.original_deletions import OriginalDeletionJournal,OriginalDeletionError
from app.access.service import AccessService,AccessDenied
from app.access.transport import TransportError


class RecordingWithdrawalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixture_module.OralHistoryIntakeTests.setUpClass()
    @classmethod
    def tearDownClass(cls):fixture_module.OralHistoryIntakeTests.tearDownClass()

    def setUp(self):
        self.f=fixture_module.OralHistoryIntakeTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.db=self.f.db;self.path=self.f.path
        self.root=self.path.parent.resolve();self.path.chmod(0o600)
        self.db.executescript('''CREATE TABLE access_upload_annotations(id TEXT PRIMARY KEY);
            CREATE TABLE access_memory_contributions(id TEXT PRIMARY KEY);
            CREATE TABLE access_original_deletion_state(id INTEGER PRIMARY KEY,namespace TEXT NOT NULL,
                applied_seq INTEGER NOT NULL,applied_digest TEXT NOT NULL);''')
        self.journal=OriginalDeletionJournal.initialize(self.root/'deletions.sqlite',str(uuid.uuid4()),format_version=4)
        self.journal.bind(self.db)
        self.attach()

    def attach(self):
        self.f.access=AccessService(self.db,clock=lambda:fixture_module.foundation.NOW)
        self.f.access.original_deletions=self.journal
        self.f.intake=OralHistoryIntake(self.f.access,enabled=True,withdrawal_enabled=True,journal=self.journal)
        self.f.db=self.db

    def record(self):return self.f.create()
    def add(self,record):return self.f.append(record)
    def withdraw_args(self,record):return {'request_id':str(uuid.uuid4()),'expected_revision':record['revision']}
    def withdraw(self,record,args=None,token=None):
        return self.f.intake.withdraw(token or self.f.member,'family-a',record['session_id'],**(args or self.withdraw_args(record)))
    def denied_source(self,record):
        for action in (lambda:self.f.intake.status(self.f.member,'family-a',record['session_id']),
                       lambda:self.f.intake.audio(self.f.member,'family-a',record['session_id'],0),
                       lambda:self.f.append(record)):
            with self.assertRaises(AccessDenied):action()
    def backup(self,name):
        path=self.root/name
        with closing(sqlite3.connect(path)) as db:self.db.backup(db)
        path.chmod(0o600);return path
    def restore(self,backup):
        self.db.close();shutil.copyfile(backup,self.path);self.db=self.f.connect();self.attach()
    def error(self,status,action):self.f.refusal(status,action)

    def test_author_withdrawal_hides_originals_without_erasing_and_retries_exactly(self):
        record=self.add(self.record());audio=self.db.execute(f'SELECT audio FROM {SECTION}').fetchone()[0]
        args=self.withdraw_args(record);receipt=self.withdraw(record,args)
        self.assertEqual(receipt['state'],'withdrawn');self.assertEqual(self.withdraw(record,args),receipt)
        self.assertEqual(self.journal.head()[1],1);self.denied_source(record)
        self.assertEqual(self.db.execute(f'SELECT audio FROM {SECTION}').fetchone()[0],audio)
        self.error(409,lambda:self.withdraw(record))
        with closing(sqlite3.connect(self.journal.path)) as ledger:
            raw=ledger.execute('SELECT oral_binding_json FROM deletions').fetchone()[0]
            for source in ('外婆','家人的讲述','title','narrator_label'):
                self.assertNotIn(source,raw)
            self.assertEqual(parse_recording_binding(raw)['section_heads'],[record['manifest_sha256']])

    def test_owner_and_other_scope_cannot_withdraw_another_authors_recording(self):
        record=self.add(self.record());head=self.journal.head()
        with self.assertRaises(AccessDenied):self.withdraw(record,token=self.f.owner)
        with self.assertRaises(AccessDenied):
            self.f.intake.withdraw(self.f.member,'family-b',record['session_id'],**self.withdraw_args(record))
        self.assertEqual(head,self.journal.head());self.assertEqual(self.f.intake.status(self.f.member,'family-a',record['session_id'])['state'],'open')

    def test_older_verified_source_prefix_is_withdrawn_after_restore(self):
        first=self.add(self.record());backup=self.backup('older.sqlite');last=self.add(first)
        args=self.withdraw_args(last);self.withdraw(last,args);self.restore(backup)
        self.error(503,lambda:self.f.intake.status(self.f.member,'family-a',first['session_id']))
        reviewed=self.journal.review(self.db);self.assertEqual(reviewed['pending_count'],1)
        replay=self.journal.replay(self.db,expected_head=self.journal.head());self.assertEqual(replay[-1],1)
        self.denied_source(first)
        self.assertEqual(self.db.execute(f'SELECT count(*) FROM {SECTION}').fetchone()[0],1)
        # The external request identity remains exact even when replay applies to an older prefix.
        self.assertEqual(self.withdraw(last,args)['state'],'withdrawn')
        self.assertEqual(self.journal.replay(self.db)[-1],0)

    def test_backup_before_any_section_cannot_revive_future_audio_or_source_access(self):
        first=self.record();backup=self.backup('empty-prefix.sqlite');last=self.add(first);self.withdraw(last)
        self.restore(backup);self.journal.replay(self.db);self.denied_source(first)
        self.assertEqual(self.db.execute(f'SELECT count(*) FROM {SECTION}').fetchone()[0],0)

    def test_append_then_primary_rollback_requires_replay_before_other_requests(self):
        record=self.add(self.record());args=self.withdraw_args(record)
        with patch('app.access.oral_history_withdrawal.apply_recording_tombstone',side_effect=sqlite3.OperationalError('synthetic primary failure')):
            with self.assertRaises(sqlite3.OperationalError):self.withdraw(record,args)
        self.assertEqual(self.journal.head()[1],1)
        self.assertEqual(self.db.execute(f'SELECT state FROM {SESSION}').fetchone()[0],'open')
        self.error(503,lambda:self.f.intake.status(self.f.member,'family-a',record['session_id']))
        self.journal.replay(self.db);self.assertEqual(self.withdraw(record,args)['state'],'withdrawn')

    def test_same_marker_with_revived_primary_state_refuses_full_review(self):
        body=self.f.body();record=self.add(self.f.create(body));before=self.backup('before.sqlite');self.withdraw(record)
        marker=self.db.execute('SELECT applied_seq,applied_digest FROM access_original_deletion_state').fetchone()
        self.restore(before);self.db.execute('UPDATE access_original_deletion_state SET applied_seq=?,applied_digest=? WHERE id=1',marker);self.db.commit()
        self.denied_source(record)
        with self.assertRaises(AccessDenied):self.f.create(body)
        with self.assertRaises(OriginalDeletionError):self.journal.review(self.db)
        with self.assertRaises(OriginalDeletionError):self.journal.replay(self.db)

    def test_conflicting_or_corrupt_restored_audio_never_advances_marker(self):
        record=self.add(self.record());before=self.backup('source.sqlite');self.withdraw(record)
        self.restore(before)
        trigger=next(s for s in STATEMENTS if 'CREATE TRIGGER oral_history_section_update ' in s)
        self.db.execute('DROP TRIGGER oral_history_section_update')
        wrong=fixture_module.wav().replace(b'\x01\x00',b'\x03\x00')
        self.db.execute(f'UPDATE {SECTION} SET audio=?',(wrong,));self.db.execute(trigger);self.db.commit()
        with self.assertRaises(OriginalDeletionError):self.journal.replay(self.db)
        self.assertEqual(self.db.execute('SELECT applied_seq FROM access_original_deletion_state').fetchone()[0],0)
        self.assertEqual(self.db.execute(f'SELECT state FROM {SESSION}').fetchone()[0],'open')

    def test_legacy_formats_refuse_new_collection_without_append(self):
        record=self.add(self.record())
        for version in (1,2,3):
            journal=OriginalDeletionJournal.initialize(self.root/f'legacy-{version}.sqlite',str(uuid.uuid4()),format_version=version)
            with self.assertRaises(OriginalDeletionError):journal.require_oral_format()
            # Never bind a second ledger to the existing primary or change its marker.
            self.assertEqual(journal.head()[1],0)
        self.assertEqual(self.journal.head()[1],0)
        self.assertEqual(self.f.intake.status(self.f.member,'family-a',record['session_id'])['state'],'open')

    def test_binding_bounds_duplicate_keys_and_tamper_are_rejected(self):
        record=self.add(self.record());self.withdraw(record)
        with closing(sqlite3.connect(self.journal.path)) as ledger:
            raw=ledger.execute('SELECT oral_binding_json FROM deletions').fetchone()[0]
        binding=json.loads(raw)
        for edited in ({**binding,'section_heads':[]},{**binding,'request_digest':'a'*64},
                       {**binding,'revision':True},{**binding,'unknown':'value'}):
            with self.assertRaises(OriginalDeletionError):
                parse_recording_binding(json.dumps(edited,sort_keys=True,separators=(',',':')))
        for malformed in ('['+'0,'*10000+'0]',raw.replace('"version":1','"version":1,"version":1'),'{broken'):
            with self.assertRaises(OriginalDeletionError):parse_recording_binding(malformed)

    def test_nonempty_recording_history_cannot_be_adopted_by_a_new_ledger(self):
        self.record()
        self.db.execute('DELETE FROM access_original_deletion_state');self.db.commit()
        fresh=OriginalDeletionJournal.initialize(self.root/'fresh.sqlite',str(uuid.uuid4()),format_version=4)
        with self.assertRaises(OriginalDeletionError):fresh.bind(self.db)
        self.assertEqual(fresh.head()[1],0)

    def test_partial_owned_schema_cannot_be_bound(self):
        for present in (SESSION,SECTION,MUTATION):
            with self.subTest(table=present):
                before=self.backup('partial-base.sqlite')
                self.db.execute('DELETE FROM access_original_deletion_state')
                for row in self.db.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'oral_history_%'").fetchall():
                    self.db.execute('DROP TRIGGER '+row[0])
                for table in (MUTATION,SECTION,SESSION):self.db.execute('DROP TABLE '+table)
                self.db.execute('CREATE TABLE '+present+'(id TEXT)');self.db.commit()
                fresh=OriginalDeletionJournal.initialize(self.root/(present+'.sqlite'),str(uuid.uuid4()),format_version=4)
                with self.assertRaises(OriginalDeletionError):fresh.bind(self.db)
                self.assertEqual(fresh.head()[1],0)
                self.assertEqual(self.db.execute('SELECT count(*) FROM access_original_deletion_state').fetchone()[0],0)
                self.restore(before)

    def test_shorter_terminal_prefix_cannot_be_replayed(self):
        for cancel in (False,True):
            with self.subTest(cancel=cancel):
                first=self.add(self.record());before=self.backup('terminal-prefix.sqlite')
                last=self.add(first);self.withdraw(last);self.restore(before)
                # This branch is internally valid but cannot lead to the journal's later sections.
                self.f.access.original_deletions=None
                self.f.intake.close(self.f.member,'family-a',first['session_id'],request_id=str(uuid.uuid4()),expected_revision=first['revision'],cancel=cancel)
                self.f.access.original_deletions=self.journal
                marker=tuple(self.db.execute('SELECT applied_seq,applied_digest FROM access_original_deletion_state').fetchone())
                with self.assertRaises(OriginalDeletionError):self.journal.replay(self.db)
                self.assertEqual(tuple(self.db.execute('SELECT applied_seq,applied_digest FROM access_original_deletion_state').fetchone()),marker)
                # Restore the valid open prefix to finish this generated case before the next one.
                self.restore(before);self.journal.replay(self.db)

    def test_revoked_author_cannot_read_retry_or_create_a_withdrawal(self):
        record=self.add(self.record());args=self.withdraw_args(record);self.withdraw(record,args)
        self.db.execute("UPDATE access_memberships SET status='revoked' WHERE account_id=?",(self.f.actor,));self.db.commit()
        with self.assertRaises(AccessDenied):self.withdraw(record,args)
        self.assertEqual(self.journal.head()[1],1)

    def test_completed_and_cancelled_sessions_can_be_withdrawn_without_reopening(self):
        for cancel in (False,True):
            record=self.add(self.record())
            closed=self.f.intake.close(self.f.member,'family-a',record['session_id'],request_id=str(uuid.uuid4()),expected_revision=record['revision'],cancel=cancel)
            receipt=self.withdraw(closed);self.assertEqual(receipt['state'],'withdrawn');self.denied_source(record)
        self.assertEqual(self.journal.head()[1],2)
