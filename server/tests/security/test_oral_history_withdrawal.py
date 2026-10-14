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

    def legacy(self,version=3):
        journal=OriginalDeletionJournal.initialize(self.root/f'upgrade-v{version}.sqlite',self.journal.namespace,format_version=version)
        self.journal=journal;self.attach();return journal

    def test_v3_upgrade_preserves_populated_legacy_history_and_primary_marker(self):
        from app.access import original_deletions as journal_module
        journal=self.legacy()
        entry={'seq':1,'collection':'upload','library_id':'family-a','object_id':str(uuid.uuid4()),
            'original_kind':'text','original_sha256':'a'*64,'batch':'b'*32,'asset_id':None,
            'story_id':None,'occurred_at':1,'prev_digest':journal_module._genesis(journal.namespace),
            'family_binding_json':None,'asset_binding_json':None}
        entry['digest']=journal_module._record_digest(entry['prev_digest'],entry)
        with closing(journal._connect()) as ledger:
            ledger.execute('BEGIN IMMEDIATE')
            names=list(journal_module._RECORD_COLUMNS)+['family_binding_json','asset_binding_json']
            ledger.execute('INSERT INTO deletions ('+','.join(names)+') VALUES ('+','.join('?' for _ in names)+')',tuple(entry[n] for n in names))
            ledger.execute('UPDATE journal_meta SET head_seq=1,head_digest=? WHERE id=1',(entry['digest'],));ledger.commit()
        self.db.execute('UPDATE access_original_deletion_state SET applied_seq=1,applied_digest=?',(entry['digest'],));self.db.commit()
        before=journal.head();self.db.execute('BEGIN IMMEDIATE')
        self.assertEqual(journal.upgrade_oral_format(self.db,expected_head=before),before);self.db.commit()
        self.assertEqual(journal.head(),before);journal.require_oral_format()
        with closing(journal._connect()) as ledger:
            stored=dict(ledger.execute('SELECT * FROM deletions WHERE seq=1').fetchone())
            for key,value in entry.items():self.assertEqual(stored[key],value)
            self.assertIsNone(stored['oral_binding_json'])
        # The upgraded ledger is usable for a new retained-source withdrawal.
        record=self.add(self.record());self.withdraw(record);self.denied_source(record)
        self.db.execute('BEGIN IMMEDIATE');head=journal.head()
        self.assertEqual(journal.upgrade_oral_format(self.db,expected_head=head),head);self.db.commit()

    def test_upgrade_requires_owned_transaction_current_head_and_v3(self):
        for version in (1,2,3):
            journal=self.legacy(version);head=journal.head()
            with self.assertRaises(OriginalDeletionError):journal.upgrade_oral_format(self.db,expected_head=head)
            self.db.execute('BEGIN IMMEDIATE')
            with self.assertRaises(OriginalDeletionError):journal.upgrade_oral_format(self.db,expected_head=(head[0],1,'a'*64))
            if version!=3:
                with self.assertRaises(OriginalDeletionError):journal.upgrade_oral_format(self.db,expected_head=head)
            self.db.rollback();self.assertEqual(journal.head(),head)

    def test_upgrade_refuses_existing_recordings_and_preserves_v3_bytes(self):
        journal=self.legacy();self.record();before=journal.path.read_bytes();head=journal.head()
        self.db.execute('BEGIN IMMEDIATE')
        with self.assertRaises(OriginalDeletionError):journal.upgrade_oral_format(self.db,expected_head=head)
        self.db.rollback();self.assertEqual(journal.path.read_bytes(),before)

    def test_upgrade_guard_failure_does_not_change_schema_or_head(self):
        journal=self.legacy();before=journal.path.read_bytes();head=journal.head()
        self.db.execute('BEGIN IMMEDIATE')
        def refuse(db):raise OriginalDeletionError('Synthetic offline guard refusal')
        with self.assertRaises(OriginalDeletionError):journal.upgrade_oral_format(self.db,expected_head=head,precommit_guard=refuse)
        self.db.rollback();self.assertEqual(journal.path.read_bytes(),before)

    def test_upgrade_ddl_failure_rolls_back_the_journal(self):
        from app.access import original_deletions as journal_module
        journal=self.legacy();before=journal.path.read_bytes();head=journal.head()
        self.db.execute('BEGIN IMMEDIATE')
        with patch.object(journal_module,'_deletions_ddl',return_value='INVALID GENERATED SQL'):
            with self.assertRaises(sqlite3.Error):journal.upgrade_oral_format(self.db,expected_head=head)
        self.db.rollback();self.assertEqual(journal.path.read_bytes(),before);self.assertEqual(journal.head(),head)

    def test_deferred_wal_upgrade_serializes_a_concurrent_recording_writer(self):
        journal=self.legacy();self.db.execute('PRAGMA journal_mode=WAL')
        other=self.f.connect();self.addCleanup(other.close);other.execute('PRAGMA busy_timeout=0')
        intake=OralHistoryIntake(AccessService(other,clock=lambda:fixture_module.foundation.NOW),enabled=True)
        blocked=[]
        def probe(db):
            with self.assertRaises(sqlite3.OperationalError):intake.create(self.f.member,'family-a',self.f.body())
            blocked.append(True)
        # A deferred transaction is upgraded to a real write fence before admission reads.
        self.db.execute('BEGIN');head=journal.head()
        self.assertEqual(journal.upgrade_oral_format(self.db,expected_head=head,precommit_guard=probe),head)
        self.assertEqual(blocked,[True]);self.assertEqual(self.db.execute(f'SELECT count(*) FROM {SESSION}').fetchone()[0],0)
        self.db.commit()
        created=intake.create(self.f.member,'family-a',self.f.body());self.assertEqual(created['state'],'open')

    def test_final_guard_mutation_cannot_commit_an_unreviewed_upgrade(self):
        for mutation in ('marker','schema','recording','commit'):
            with self.subTest(mutation=mutation):
                before=self.backup('guard-primary.sqlite')
                journal=OriginalDeletionJournal.initialize(self.root/f'guard-{mutation}.sqlite',self.journal.namespace,format_version=3)
                original=journal.path.read_bytes();head=journal.head()
                def guard(db):
                    if mutation=='marker':db.execute('UPDATE access_original_deletion_state SET applied_seq=1,applied_digest=?',('a'*64,))
                    elif mutation=='schema':db.execute('ALTER TABLE '+SESSION+' ADD COLUMN unexpected TEXT')
                    elif mutation=='recording':db.execute(f'''INSERT INTO {SESSION}
                        (id,library_id,author_id,title,subject_label,narrator_label,language,processing_consent,
                         state,revision,section_count,total_bytes,total_frames,manifest_sha256,created_at)
                        VALUES (?,'family-a',?,'Generated guard row','','','zh',0,'open',1,0,0,0,?,1)''',
                        (str(uuid.uuid4()),self.f.actor,'a'*64))
                    else:db.commit()
                self.db.execute('BEGIN IMMEDIATE')
                with self.assertRaises(OriginalDeletionError):journal.upgrade_oral_format(self.db,expected_head=head,precommit_guard=guard)
                self.db.rollback();self.assertEqual(journal.path.read_bytes(),original)
                self.restore(before)
