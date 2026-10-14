"""Generated local files only: durable sections/retries, ownership and refusal boundaries."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
import hashlib
import io
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch
import uuid
import wave

import test_access_foundation as foundation
from app.access.service import AccessService, AccessDenied
from app.access.oral_history_intake import OralHistoryIntake
from app.access.oral_history_schema import (
    SESSION, SECTION, MUTATION, STATEMENTS, MAX_SESSIONS_PER_AUTHOR,
    MAX_SECTION_BYTES, install_fixture_schema, assert_schema)
from app.access.transport import TransportError
from test_network_guard import install_no_external_sockets


def wav(frames=1600, *, rate=16000, channels=1, width=2):
    out = io.BytesIO()
    with wave.open(out, 'wb') as sound:
        sound.setnchannels(channels); sound.setsampwidth(width); sound.setframerate(rate)
        sound.writeframes(b'\x01\x00' * frames * channels if width == 2 else b'\x00' * frames * channels * width)
    return out.getvalue()


class CommitFailure(sqlite3.Connection):
    fail_commit = False
    def commit(self):
        if self.fail_commit:
            raise sqlite3.OperationalError('synthetic commit failure')
        return super().commit()


class OralHistoryIntakeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = foundation.database()
        from app.access.bootstrap import bootstrap_owner
        bootstrap_owner(cls.template, phone=foundation.OWNER, password=foundation.PASSWORD, library_id='family-a')
        other = bootstrap_owner(cls.template, phone=foundation.OTHER_OWNER, password=foundation.PASSWORD, library_id='family-b')
        access = AccessService(cls.template, clock=lambda: foundation.NOW)
        cls.owner = access.login(foundation.OWNER, foundation.PASSWORD)
        cls.other = access.login(foundation.OTHER_OWNER, foundation.PASSWORD)
        cls.member = access.register(foundation.MEMBER, foundation.PASSWORD,
                                    access.invite(cls.owner, 'family-a', foundation.MEMBER), 'Narrator')
        cls.actor = access.profile(cls.member)['account_id']
        cls.template.execute('INSERT INTO access_memberships(account_id,library_id,status,role,revision,approved_by) VALUES (?,?,\'approved\',\'viewer\',1,?)',
                             (cls.actor, 'family-b', other))
        cls.template.commit()

    @classmethod
    def tearDownClass(cls):
        cls.template.close()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='photohouse-oral-history-')
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'generated.sqlite'
        self.db = self.connect()
        self.template.backup(self.db)
        self.db.execute('BEGIN IMMEDIATE')
        install_fixture_schema(self.db)
        self.db.commit()
        self.access = AccessService(self.db, clock=lambda: foundation.NOW)
        self.intake = OralHistoryIntake(self.access, enabled=True)
        install_no_external_sockets(self)
        for target in ('subprocess.Popen', 'os.system'):
            guard = patch(target, side_effect=AssertionError('No external process'))
            guard.start(); self.addCleanup(guard.stop)
        self.addCleanup(lambda: self.db.close())

    def connect(self, factory=sqlite3.Connection):
        db = sqlite3.connect(self.path, timeout=10, factory=factory)
        db.execute('PRAGMA foreign_keys=ON')
        return db

    def body(self, **changes):
        return {'request_id': str(uuid.uuid4()), 'title': '外婆说起那年春天',
                'subject_label': '外婆', 'narrator_label': '家人的讲述',
                'language': 'zh', 'processing_consent': True, **changes}

    def create(self, body=None):
        return self.intake.create(self.member, 'family-a', body or self.body())

    def append_args(self, record, **changes):
        return {'request_id': str(uuid.uuid4()), 'expected_revision': record['revision'],
                'ordinal': record['next_ordinal'], 'audio': wav(), **changes}

    def append(self, record, args=None):
        return self.intake.append(self.member, 'family-a', record['session_id'],
                                  **(args or self.append_args(record)))

    def refusal(self, status, action):
        with self.assertRaises(TransportError) as caught:
            action()
        self.assertEqual(caught.exception.status, status)

    def counts(self):
        return tuple(self.db.execute(f'SELECT count(*) FROM {t}').fetchone()[0]
                     for t in (SESSION, SECTION, MUTATION))

    def test_saved_sections_and_original_receipts_survive_reopen_and_completion(self):
        body = self.body(); created = self.create(body); args = self.append_args(created)
        first = self.append(created, args)
        second = self.append(first, self.append_args(first, audio=wav(320000)))
        self.db.close(); self.db = self.connect()
        self.intake = OralHistoryIntake(AccessService(self.db, clock=lambda: foundation.NOW), enabled=True)
        self.assertEqual(self.create(body), created)
        self.assertEqual(self.append(created, args), first)
        status = self.intake.status(self.member, 'family-a', created['session_id'])
        self.assertEqual(status['next_ordinal'], 2)
        self.assertEqual(status['total_frames'], 321600)
        self.assertEqual(self.intake.audio(self.member, 'family-a', created['session_id'], 0), args['audio'])
        self.assertNotIn('audio', status)
        close = {'request_id': str(uuid.uuid4()), 'expected_revision': second['revision']}
        ended = self.intake.close(self.member, 'family-a', created['session_id'], **close)
        self.assertEqual(ended['state'], 'completed')
        self.assertEqual(self.intake.close(self.member, 'family-a', created['session_id'], **close), ended)
        # An accepted request retry stays valid after closure, without reopening the session.
        self.assertEqual(self.append(created, args), first)
        self.refusal(409, lambda: self.append(ended))
        self.assertEqual(self.counts(), (1, 2, 4))

    def test_changed_retry_and_cross_scope_reuse_conflict_without_new_source(self):
        body = self.body(); record = self.create(body)
        for update in ({'title':'不同标题'}, {'processing_consent':False}, {'narrator_label':'别人'}):
            self.refusal(409, lambda update=update: self.create({**body, **update}))
        self.refusal(409, lambda: self.intake.create(self.member, 'family-b', body))
        args = self.append_args(record); self.append(record, args)
        self.refusal(409, lambda: self.append(record, {**args, 'audio':wav(1700)}))
        self.refusal(409, lambda: self.append(record, {**args, 'ordinal':1}))
        other = self.create()
        self.refusal(409, lambda: self.append(other, args))
        self.assertEqual(self.counts(), (2, 1, 3))

    def test_owner_and_other_library_cannot_read_or_mutate_private_recording(self):
        record = self.create(); args = self.append_args(record); self.append(record, args)
        for action in (
            lambda: self.intake.status(self.owner, 'family-a', record['session_id']),
            lambda: self.intake.audio(self.owner, 'family-a', record['session_id'], 0),
            lambda: self.intake.append(self.owner, 'family-a', record['session_id'], **args),
            lambda: self.intake.close(self.owner, 'family-a', record['session_id'], request_id=str(uuid.uuid4()), expected_revision=2),
            lambda: self.intake.status(self.member, 'family-b', record['session_id']),
            lambda: self.intake.status(self.other, 'family-a', record['session_id'])):
            with self.assertRaises(AccessDenied): action()
        self.assertEqual(self.counts(), (1, 1, 2))

    def test_revocation_disable_expiry_and_library_closure_fence_all_retries(self):
        for mutation in (
            "UPDATE access_memberships SET status='revoked' WHERE account_id=? AND library_id='family-a'",
            "UPDATE access_accounts SET state='disabled' WHERE id=?",
            f"UPDATE access_memberships SET expires_at={foundation.NOW} WHERE account_id=? AND library_id='family-a'",
            "UPDATE access_libraries SET state='closed' WHERE id='family-a'",
            "UPDATE access_sessions SET revoked=1 WHERE account_id=?",
            f"UPDATE access_sessions SET expires_at={foundation.NOW} WHERE account_id=?"):
            with self.subTest(mutation=mutation):
                body = self.body(); record = self.create(body); args = self.append_args(record); self.append(record, args)
                self.db.execute('SAVEPOINT revoke')
                self.db.execute(mutation, (self.actor,) if '?' in mutation else ())
                # Commit the policy change; preserve a generated backup for the next scenario.
                self.db.execute('RELEASE revoke'); self.db.commit()
                for action in (lambda:self.create(body),lambda:self.append(record,args),
                               lambda:self.intake.status(self.member,'family-a',record['session_id']),
                               lambda:self.intake.audio(self.member,'family-a',record['session_id'],0)):
                    with self.assertRaises(AccessDenied):action()
                self.db.execute("UPDATE access_memberships SET status='approved',expires_at=NULL WHERE account_id=?",(self.actor,))
                self.db.execute("UPDATE access_accounts SET state='active' WHERE id=?",(self.actor,))
                self.db.execute("UPDATE access_libraries SET state='active' WHERE id='family-a'")
                self.db.execute('UPDATE access_sessions SET revoked=0,expires_at=? WHERE account_id=?',(foundation.NOW+1000,self.actor));self.db.commit()

    def test_sequence_conflicts_and_short_final_section_preserve_exact_originals(self):
        record = self.create(); before = self.counts()
        for changes in ({'ordinal':1},{'expected_revision':2},{'ordinal':True},{'expected_revision':True}):
            self.refusal(400 if any(type(v) is bool for v in changes.values()) else 409,
                         lambda changes=changes:self.append(record,self.append_args(record,**changes)))
        self.assertEqual(self.counts(), before)
        first = self.append(record, self.append_args(record, audio=wav(320000)))
        short = wav(1); final = self.append(first, self.append_args(first, audio=short))
        self.assertEqual(final['total_frames'],320001)
        self.assertEqual(self.intake.audio(self.member,'family-a',record['session_id'],1), short)
        self.assertEqual(final['section_sha256'],hashlib.sha256(short).hexdigest())

    def test_invalid_audio_shapes_never_save_a_partial_section(self):
        record=self.create();before=self.counts()
        for audio in (b'', wav(320001), wav(rate=8000), wav(channels=2), wav(width=1),
                      wav()[:-1], wav()+b'private-extra', bytearray(wav()), b'\x00'*(MAX_SECTION_BYTES+1)):
            with self.subTest(length=len(audio)):
                self.refusal(422,lambda:self.append(record,self.append_args(record,audio=audio)))
                self.assertEqual(self.counts(),before)

    def test_consent_is_explicit_immutable_and_never_queues_asr(self):
        record=self.create(self.body(processing_consent=False));self.append(record)
        self.assertFalse(self.intake.status(self.member,'family-a',record['session_id'])['processing_consent'])
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(f'UPDATE {SESSION} SET processing_consent=1 WHERE id=?',(record['session_id'],))
        self.db.rollback()
        names={r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertNotIn('access_annotation_derivations',names)
        self.refusal(422,lambda:self.create(self.body(processing_consent=1)))

    def test_receipt_or_commit_failure_rolls_back_audio_counters_and_audit(self):
        record=self.create();args=self.append_args(record);before=self.counts()
        audits=self.db.execute('SELECT count(*) FROM access_audit').fetchone()[0]
        self.db.execute(f'''CREATE TRIGGER generated_receipt_failure BEFORE INSERT ON {MUTATION}
            BEGIN SELECT RAISE(ABORT,'synthetic failure'); END''');self.db.commit()
        # Exact schema verification catches an unexpected trigger before writing.
        self.refusal(503,lambda:self.append(record,args));self.assertEqual(self.counts(),before)
        self.db.execute('DROP TRIGGER generated_receipt_failure');self.db.commit()
        with patch.object(self.intake,'_record',side_effect=sqlite3.OperationalError('synthetic receipt failure')):
            with self.assertRaises(sqlite3.OperationalError):self.append(record,args)
        self.assertEqual(self.counts(),before)
        self.assertEqual(self.db.execute('SELECT count(*) FROM access_audit').fetchone()[0],audits)
        self.db.close();self.db=self.connect(CommitFailure)
        self.intake=OralHistoryIntake(AccessService(self.db,clock=lambda:foundation.NOW),enabled=True)
        self.db.fail_commit=True
        with self.assertRaises(sqlite3.OperationalError):self.append(record,args)
        self.db.fail_commit=False
        self.assertEqual(self.counts(),before)
        accepted=self.append(record,args);self.assertEqual(accepted['section_count'],1)

    def test_exact_concurrent_retry_commits_one_source_and_one_receipt(self):
        record=self.create();args=self.append_args(record);barrier=threading.Barrier(2)
        def send():
            with closing(self.connect()) as db:
                intake=OralHistoryIntake(AccessService(db,clock=lambda:foundation.NOW),enabled=True)
                barrier.wait(timeout=5)
                return intake.append(self.member,'family-a',record['session_id'],**args)
        with ThreadPoolExecutor(max_workers=2) as executor:
            calls=[executor.submit(send) for _ in range(2)];results=[x.result(timeout=15) for x in calls]
        self.assertEqual(results[0],results[1]);self.assertEqual(self.counts(),(1,1,2))

    def test_cancel_closes_capture_without_erasing_accepted_source(self):
        record=self.append(self.create());request=str(uuid.uuid4())
        ended=self.intake.close(self.member,'family-a',record['session_id'],request_id=request,
                               expected_revision=record['revision'],cancel=True)
        self.assertEqual(ended['state'],'cancelled')
        self.assertEqual(self.intake.audio(self.member,'family-a',record['session_id'],0),wav())
        self.refusal(409,lambda:self.append(ended))
        with self.assertRaises(sqlite3.IntegrityError):self.db.execute(f'DELETE FROM {SESSION} WHERE id=?',(record['session_id'],))
        self.db.rollback()
        empty=self.create();self.refusal(409,lambda:self.intake.close(self.member,'family-a',empty['session_id'],request_id=str(uuid.uuid4()),expected_revision=1))

    def test_schema_drift_default_off_and_unsafe_durability_fail_closed(self):
        record=self.create();names=list(self.db.execute('SELECT name,sql FROM sqlite_master'))
        self.refusal(503,lambda:OralHistoryIntake(self.access).status(self.member,'family-a',record['session_id']))
        self.assertEqual(list(self.db.execute('SELECT name,sql FROM sqlite_master')),names)
        self.db.execute('DROP TRIGGER oral_history_section_update');self.db.commit()
        self.refusal(503,lambda:self.intake.status(self.member,'family-a',record['session_id']))
        self.db.execute(next(s for s in STATEMENTS if 'CREATE TRIGGER oral_history_section_update ' in s));self.db.commit()
        self.db.execute('PRAGMA synchronous=OFF')
        self.refusal(503,lambda:self.append(record))
        self.db.execute('PRAGMA synchronous=FULL');self.db.execute('PRAGMA journal_mode=MEMORY')
        self.refusal(503,lambda:self.append(record))

    def test_manifests_and_raw_audio_have_separate_tamper_guards(self):
        record=self.append(self.create())
        transition=next(s for s in STATEMENTS if 'CREATE TRIGGER oral_history_session_transition ' in s)
        self.db.execute('DROP TRIGGER oral_history_session_transition')
        self.db.execute(f'UPDATE {SESSION} SET total_frames=total_frames+1 WHERE id=?',(record['session_id'],));self.db.execute(transition);self.db.commit()
        self.refusal(503,lambda:self.intake.status(self.member,'family-a',record['session_id']))
        self.db.execute('DROP TRIGGER oral_history_session_transition')
        self.db.execute(f'UPDATE {SESSION} SET total_frames=total_frames-1 WHERE id=?',(record['session_id'],));self.db.execute(transition);self.db.commit()
        # Simulate offline corruption outside the API, then restore the exact trigger definition.
        trigger=next(s for s in STATEMENTS if 'CREATE TRIGGER oral_history_section_update ' in s)
        self.db.execute('DROP TRIGGER oral_history_section_update')
        altered=wav().replace(b'\x01\x00',b'\x02\x00')
        self.db.execute(f'UPDATE {SECTION} SET audio=? WHERE session_id=?',(altered,record['session_id']))
        self.db.execute(trigger);self.db.commit()
        self.refusal(503,lambda:self.intake.audio(self.member,'family-a',record['session_id'],0))

    def test_quota_and_stale_journal_do_not_accept_more_source(self):
        for _ in range(MAX_SESSIONS_PER_AUTHOR):self.create()
        self.refusal(409,lambda:self.create())
        self.assertEqual(self.counts(),(MAX_SESSIONS_PER_AUTHOR,0,MAX_SESSIONS_PER_AUTHOR))
        class StaleJournal:
            def assert_current(self,db):raise RuntimeError('synthetic stale marker')
        self.access.original_deletions=StaleJournal()
        self.refusal(503,lambda:self.create())
        self.assertEqual(self.counts(),(MAX_SESSIONS_PER_AUTHOR,0,MAX_SESSIONS_PER_AUTHOR))

    def test_explicit_schema_install_requires_a_transaction_and_refuses_partial_state(self):
        with self.assertRaises(ValueError):install_fixture_schema(self.db)
        self.db.execute('BEGIN IMMEDIATE');install_fixture_schema(self.db);self.db.rollback()
        self.db.execute(f'DROP TABLE {MUTATION}');self.db.commit();self.db.execute('BEGIN IMMEDIATE')
        with self.assertRaises(ValueError):install_fixture_schema(self.db)
        self.db.rollback()
        with self.assertRaises(ValueError):assert_schema(self.db)

    def test_malformed_receipts_fail_closed_and_terminal_sessions_cannot_reopen(self):
        body=self.body();record=self.create(body)
        trigger=next(s for s in STATEMENTS if 'CREATE TRIGGER oral_history_mutation_update ' in s)
        original=self.db.execute(f'SELECT receipt_json,receipt_sha256 FROM {MUTATION} WHERE request_id=?',(body['request_id'],)).fetchone()
        for raw in ('[]', original[0].replace(record['session_id'],str(uuid.uuid4())), '{broken'):
            self.db.execute('DROP TRIGGER oral_history_mutation_update')
            self.db.execute(f'UPDATE {MUTATION} SET receipt_json=?,receipt_sha256=? WHERE request_id=?',
                            (raw,hashlib.sha256(raw.encode()).hexdigest(),body['request_id']))
            self.db.execute(trigger);self.db.commit()
            self.refusal(503,lambda:self.create(body))
        self.db.execute('DROP TRIGGER oral_history_mutation_update')
        self.db.execute(f'UPDATE {MUTATION} SET receipt_json=?,receipt_sha256=? WHERE request_id=?',(*original,body['request_id']))
        self.db.execute(trigger);self.db.commit()
        ended=self.intake.close(self.member,'family-a',record['session_id'],request_id=str(uuid.uuid4()),expected_revision=1,cancel=True)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(f"UPDATE {SESSION} SET state='open',revision=revision+1 WHERE id=?",(ended['session_id'],))
        self.db.rollback()

    def test_parent_keys_and_missing_tables_are_not_adopted(self):
        with closing(sqlite3.connect(':memory:')) as db:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('CREATE TABLE access_accounts(id TEXT)')
            db.execute('CREATE TABLE access_libraries(id TEXT PRIMARY KEY)')
            db.execute('BEGIN')
            with self.assertRaises(ValueError):install_fixture_schema(db)
            self.assertFalse(db.execute("SELECT 1 FROM sqlite_master WHERE name=?",(SESSION,)).fetchone())
        self.db.execute('PRAGMA ignore_check_constraints=ON')
        self.refusal(503,lambda:self.create())

    def test_competing_new_requests_do_not_both_claim_the_same_ordinal(self):
        record=self.create();args=self.append_args(record);barrier=threading.Barrier(2)
        def send(request):
            with closing(self.connect()) as db:
                intake=OralHistoryIntake(AccessService(db,clock=lambda:foundation.NOW),enabled=True)
                barrier.wait(timeout=5)
                try:
                    return intake.append(self.member,'family-a',record['session_id'],**{**args,'request_id':request})['section_count']
                except TransportError as error:
                    return error.status
        with ThreadPoolExecutor(max_workers=2) as executor:
            calls=[executor.submit(send,str(uuid.uuid4())) for _ in range(2)]
            results=sorted(x.result(timeout=15) for x in calls)
        self.assertEqual(results,[1,409]);self.assertEqual(self.counts(),(1,1,2))

    def test_section_count_bound_and_closed_app_do_not_offer_new_routes(self):
        record=self.create()
        for _ in range(180):record=self.append(record,self.append_args(record,audio=wav(1)))
        self.assertEqual(record['next_ordinal'],180)
        self.refusal(400,lambda:self.append(record))
        self.assertEqual(self.counts(),(1,180,181))
        from app.main import create_app
        self.assertFalse(any('oral' in getattr(route,'path','') for route in create_app().routes))
