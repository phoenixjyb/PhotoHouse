"""Disposable restore/replay rehearsal for the external original-deletion ledger."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import tempfile
import unittest
import uuid
import wave
from io import BytesIO

from app.access.original_deletions import (
    OriginalDeletionError, OriginalDeletionJournal, erase_memory_original,
)
from app.access.service import AccessService
from scripts.replay_original_deletions import main as replay_cli


def _uuid():
    return str(uuid.uuid4())


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _snapshot(source, target):
    with closing(sqlite3.connect(source)) as src, closing(sqlite3.connect(target)) as dst:
        src.backup(dst)


def _wav():
    stream=BytesIO()
    with wave.open(stream,'wb') as audio:
        audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(16000)
        audio.writeframes(b'\x00\x00'*16000)
    return stream.getvalue()


class OriginalDeletionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from test_library_reads import LibraryReadTests
        cls.fixture_type = LibraryReadTests
        cls.fixture_type.setUpClass()

    @classmethod
    def tearDownClass(cls):
        cls.fixture_type.tearDownClass()

    def setUp(self):
        self.fixture = self.fixture_type()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.work = tempfile.TemporaryDirectory(prefix='photohouse-deletion-replay-',dir='/private/tmp')
        self.addCleanup(self.work.cleanup)
        self.work_path = Path(self.work.name)
        self.namespace = _uuid()
        self.journal_path = self.work_path / 'external-ledger.sqlite'
        self.journal = OriginalDeletionJournal.initialize(self.journal_path, self.namespace)
        if os.name == 'posix':
            self.assertEqual(stat.S_IMODE(self.journal_path.stat().st_mode),0o600)
        with self.fixture.connection() as db:
            self.journal.bind(db)
        with self.fixture.connection() as db:
            self.author = AccessService(db, clock=lambda: self.fixture.now).profile(
                self.fixture.owner_token)['account_id']

    def _insert_upload(self, *, text='Synthetic note to delete'):
        ident, batch = _uuid(), uuid.uuid4().hex
        raw = text.encode('utf-8')
        with self.fixture.connection() as db:
            db.execute('''INSERT INTO access_upload_annotations
                (id,author_id,library_id,batch,asset_id,kind,original_text,original_audio,
                 mime,duration_ms,sha256,language,consent,mutation_id,request_digest,created_at)
                VALUES (?,?,?, ?,101,'text',?,NULL,NULL,NULL,?,'en',1,?,?,?)''',
                (ident,self.author,'family-a',batch,text,_sha(raw),_uuid(),_sha(b'mutation'),self.fixture.now))
            db.execute('''INSERT INTO access_annotation_derivations
                (annotation_id,revision,state,transcript,polished_text,provider,model,created_at,updated_at)
                VALUES (?,1,'completed','derived transcript','polished copy','local','synthetic',?,?)''',
                (ident,self.fixture.now,self.fixture.now))
            db.execute('''INSERT INTO access_annotation_tag_proposals
                (annotation_id,tag,status,revision) VALUES (?,'Synthetic tag','accepted',1)''',(ident,))
            db.commit()
        return ident, batch

    def _insert_memory(self, *, text='Synthetic family contribution'):
        ident, story_id, book_id = _uuid(), _uuid(), _uuid()
        now = self.fixture.now
        story = {'version':1,'title':'Synthetic saved story','theme':'everyday','language':'zh',
                 'asset_ids':['101'],'chapters':[]}
        story_text = json.dumps(story,separators=(',',':'))
        story_digest = _sha(story_text.encode())
        book_text = json.dumps({'title':'Synthetic book','language':'zh','introduction':'',
                                'story_ids':[story_id]},separators=(',',':'))
        raw = text.encode('utf-8')
        with self.fixture.connection() as db:
            db.execute('''INSERT INTO access_memory_stories
                (id,library_id,author_id,revision,content,created_at,updated_at)
                VALUES (?,'family-a',?,1,?,?,?)''',(story_id,self.author,story_text,now,now))
            db.execute('''INSERT INTO access_memory_revisions
                (story_id,revision,editor_id,mutation_id,request_digest,content,occurred_at)
                VALUES (?,1,?,?,?, ?,?)''',(story_id,self.author,_uuid(),story_digest,story_text,now))
            db.execute('''INSERT INTO access_memory_books
                (id,library_id,author_id,revision,content,created_at,updated_at)
                VALUES (?,'family-a',?,1,?,?,?)''',(book_id,self.author,book_text,now,now))
            db.execute('''INSERT INTO access_memory_contributions
                (id,story_id,library_id,author_id,kind,original_text,original_audio,language,byline,
                 sha256,duration_ms,local_processing_consent,chapter_id,base_story_revision,state,
                 mutation_id,request_digest,created_at,reviewed_by_id,reviewed_at)
                VALUES (?,?,? ,?,'text',?,NULL,'zh','Synthetic relative',?,NULL,1,NULL,1,'accepted',?,?,?,NULL,NULL)''',
                (ident,story_id,'family-a',self.author,text,_sha(raw),_uuid(),_sha(b'memory-mutation'),now))
            db.execute('''INSERT INTO access_memory_contribution_derivations
                (contribution_id,revision,state,transcript,polished_text,tags,provider,model,
                 created_at,updated_at) VALUES (?,1,'ready',?,?, '["derived"]','local','synthetic',?,?)''',
                (ident,text,'polished '+text,now,now))
            conversation_ids=[]
            for parent_column,parent_id in (('story_id',story_id),('book_id',book_id)):
                conversation_id=_uuid();conversation_ids.append(conversation_id)
                db.execute(f'''INSERT INTO access_memory_conversations
                    (id,library_id,actor_id,{parent_column},created_at,expires_at)
                    VALUES (?,'family-a',?,?,?,?)''',
                    (conversation_id,self.author,parent_id,now,now+86400))
                job_id=_uuid()
                db.execute(f'''INSERT INTO access_memory_jobs
                    (id,library_id,actor_id,{parent_column},conversation_id,kind,state,mutation_id,
                     request_digest,base_revision,source_fingerprint,input_json,output_json,created_at,
                     updated_at,expires_at) VALUES (?,'family-a',?,?,?,'narrative','ready',?,?,1,?,?,?, ?,?,?)''',
                    (job_id,self.author,parent_id,conversation_id,_uuid(),_sha(b'job-request'),_sha(b'fp'),
                     '{"instructions":"private prompt copy"}', '{"narration":"derived copy"}',now,now,now+86400))
                db.execute('''INSERT INTO access_memory_turns
                    (id,conversation_id,sequence,mutation_id,request_digest,input_text,reply_text,reply_kind,job_id,created_at)
                    VALUES (?,?,1,?,?,?,'private derived reply','answer',?,?)''',
                    (_uuid(),conversation_id,_uuid(),_sha(b'turn'), 'manual family question',job_id,now))
            db.commit()
        return ident,story_id,book_id,conversation_ids

    def _insert_audio_originals(self):
        now=self.fixture.now;raw=_wav();upload_id,story_id,contribution_id=_uuid(),_uuid(),_uuid()
        batch=uuid.uuid4().hex;story=json.dumps({'version':1,'title':'Audio story','theme':'everyday',
            'language':'zh','asset_ids':['101'],'chapters':[]},separators=(',',':'))
        with self.fixture.connection() as db:
            db.execute('''INSERT INTO access_upload_annotations
                (id,author_id,library_id,batch,asset_id,kind,original_text,original_audio,mime,duration_ms,
                 sha256,language,consent,mutation_id,request_digest,created_at)
                VALUES (?,?,?, ?,101,'audio',NULL,?,'audio/wav',1000,?,'zh',1,?,?,?)''',
                (upload_id,self.author,'family-a',batch,raw,_sha(raw),_uuid(),_sha(b'audio-upload'),now))
            db.execute('''INSERT INTO access_annotation_derivations
                (annotation_id,revision,state,created_at,updated_at) VALUES (?,1,'waiting',?,?)''',
                (upload_id,now,now))
            db.execute('''INSERT INTO access_memory_stories
                (id,library_id,author_id,revision,content,created_at,updated_at)
                VALUES (?,'family-a',?,1,?,?,?)''',(story_id,self.author,story,now,now))
            db.execute('''INSERT INTO access_memory_contributions
                (id,story_id,library_id,author_id,kind,original_text,original_audio,language,byline,
                 sha256,duration_ms,local_processing_consent,chapter_id,base_story_revision,state,
                 mutation_id,request_digest,created_at,reviewed_by_id,reviewed_at)
                VALUES (?,?,?,?,'audio',NULL,?,'zh','Synthetic audio',?,1000,1,NULL,1,'pending',?,?,?,NULL,NULL)''',
                (contribution_id,story_id,'family-a',self.author,raw,_sha(raw),_uuid(),_sha(b'audio-memory'),now))
            db.execute('''INSERT INTO access_memory_contribution_derivations
                (contribution_id,revision,state,created_at,updated_at) VALUES (?,1,'waiting',?,?)''',
                (contribution_id,now,now))
            db.commit()
        return upload_id,story_id,contribution_id,raw

    def _live_delete_upload(self, ident):
        with self.fixture.connection() as db:
            db.execute('PRAGMA secure_delete=ON')
            db.execute('BEGIN IMMEDIATE')
            cur=db.execute('SELECT * FROM access_upload_annotations WHERE id=?',(ident,))
            row=dict(zip((column[0] for column in cur.description),cur.fetchone()))
            self.journal.append(db,'upload',row,self.fixture.now)
            db.execute('DELETE FROM access_annotation_tag_proposals WHERE annotation_id=?',(ident,))
            db.execute('DELETE FROM access_annotation_derivations WHERE annotation_id=?',(ident,))
            db.execute('DELETE FROM access_upload_annotations WHERE id=?',(ident,))
            db.commit()

    def _live_delete_memory(self, ident, story_id):
        with self.fixture.connection() as db:
            db.execute('PRAGMA secure_delete=ON')
            db.execute('BEGIN IMMEDIATE')
            cur=db.execute('SELECT * FROM access_memory_contributions WHERE id=?',(ident,))
            row=dict(zip((column[0] for column in cur.description),cur.fetchone()))
            self.journal.append(db,'memory',row,self.fixture.now)
            erase_memory_original(db,ident,story_id,'family-a',self.fixture.now)
            db.commit()

    def _restore(self, backup):
        restored=self.work_path / ('restore-' + _uuid() + '.sqlite')
        shutil.copyfile(backup,restored)
        db=sqlite3.connect(restored)
        db.execute('PRAGMA foreign_keys=ON')
        return restored,db

    def test_upload_delete_replays_from_predelete_backup_and_is_idempotent(self):
        ident,_ = self._insert_upload()
        backup=self.work_path / 'upload-backup.sqlite'
        _snapshot(self.fixture.path,backup)
        self._live_delete_upload(ident)
        self.assertNotIn(b'Synthetic note to delete',self.journal_path.read_bytes())
        with self.fixture.connection() as db:
            self.journal.assert_current(db)
            self.assertEqual(db.execute('SELECT count(*) FROM access_upload_annotations WHERE id=?',(ident,)).fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM access_annotation_derivations WHERE annotation_id=?',(ident,)).fetchone()[0],0)
        _,restored=self._restore(backup)
        with closing(restored):
            with self.assertRaises(OriginalDeletionError):
                self.journal.assert_current(restored)
            result=self.journal.replay(restored)
            self.assertEqual(result[3],1)
            self.assertEqual(restored.execute('SELECT count(*) FROM access_upload_annotations WHERE id=?',(ident,)).fetchone()[0],0)
            self.assertEqual(restored.execute('SELECT count(*) FROM access_annotation_derivations WHERE annotation_id=?',(ident,)).fetchone()[0],0)
            self.assertEqual(restored.execute('SELECT count(*) FROM access_annotation_tag_proposals WHERE annotation_id=?',(ident,)).fetchone()[0],0)
            self.assertEqual(restored.execute('PRAGMA quick_check').fetchone()[0],'ok')
            self.assertEqual(self.journal.replay(restored)[3],0)

    def test_memory_delete_scrubs_ai_copies_but_preserves_story_book_and_manual_turns(self):
        ident,story_id,book_id,conversation_ids=self._insert_memory()
        backup=self.work_path / 'memory-backup.sqlite'
        _snapshot(self.fixture.path,backup)
        self._live_delete_memory(ident,story_id)
        self.assertNotIn(b'Synthetic family contribution',self.journal_path.read_bytes())
        _,restored=self._restore(backup)
        with closing(restored):
            self.assertEqual(self.journal.replay(restored)[3],1)
            self.assertEqual(restored.execute('SELECT count(*) FROM access_memory_contributions WHERE id=?',(ident,)).fetchone()[0],0)
            self.assertEqual(restored.execute('SELECT count(*) FROM access_memory_contribution_derivations WHERE contribution_id=?',(ident,)).fetchone()[0],0)
            self.assertEqual(restored.execute('SELECT count(*) FROM access_memory_stories WHERE id=?',(story_id,)).fetchone()[0],1)
            self.assertEqual(restored.execute('SELECT count(*) FROM access_memory_revisions WHERE story_id=?',(story_id,)).fetchone()[0],1)
            self.assertEqual(restored.execute('SELECT count(*) FROM access_memory_books WHERE id=?',(book_id,)).fetchone()[0],1)
            self.assertEqual(restored.execute("SELECT count(*) FROM access_memory_jobs WHERE input_json!='{}' OR output_json IS NOT NULL OR lease_id IS NOT NULL OR lease_until IS NOT NULL",).fetchone()[0],0)
            self.assertEqual(restored.execute('SELECT count(*) FROM access_memory_turns WHERE input_text="manual family question" AND reply_text IS NULL AND reply_kind IS NULL').fetchone()[0],2)
            self.assertEqual(restored.execute('SELECT count(*) FROM access_memory_conversations WHERE id IN (?,?)',conversation_ids).fetchone()[0],2)
            self.assertEqual(restored.execute('PRAGMA quick_check').fetchone()[0],'ok')

    def test_replay_scrubs_memory_jobs_even_if_the_original_row_is_already_absent(self):
        ident,story_id,_,_=self._insert_memory()
        backup=self.work_path/'memory-parent-missing.sqlite'
        _snapshot(self.fixture.path,backup)
        self._live_delete_memory(ident,story_id)
        _,restored=self._restore(backup)
        with closing(restored):
            restored.execute('PRAGMA foreign_keys=OFF')
            restored.execute('DELETE FROM access_memory_contributions WHERE id=?',(ident,))
            restored.commit()
            restored.execute('PRAGMA foreign_keys=ON')
            self.assertEqual(self.journal.review(restored)['pending_count'],1)
            self.assertEqual(self.journal.replay(restored)[3],1)
            self.assertEqual(restored.execute('SELECT count(*) FROM access_memory_contribution_derivations WHERE contribution_id=?',(ident,)).fetchone()[0],0)
            self.assertEqual(restored.execute("SELECT count(*) FROM access_memory_jobs WHERE input_json!='{}' OR output_json IS NOT NULL OR lease_id IS NOT NULL OR lease_until IS NOT NULL").fetchone()[0],0)
            self.assertEqual(restored.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_audio_tombstones_replay_exact_hash_without_recording_wave_bytes(self):
        upload_id,story_id,contribution_id,raw=self._insert_audio_originals()
        backup=self.work_path/'audio-backup.sqlite'
        _snapshot(self.fixture.path,backup)
        self._live_delete_upload(upload_id)
        self._live_delete_memory(contribution_id,story_id)
        self.assertNotIn(raw,self.journal_path.read_bytes())
        self.assertFalse(any(os.path.lexists(str(self.journal_path)+suffix)
                             for suffix in ('-journal','-wal','-shm')))
        _,restored=self._restore(backup)
        with closing(restored):
            self.assertEqual(self.journal.replay(restored)[3],2)
            self.assertEqual(restored.execute('SELECT count(*) FROM access_upload_annotations WHERE id=?',(upload_id,)).fetchone()[0],0)
            self.assertEqual(restored.execute('SELECT count(*) FROM access_memory_contributions WHERE id=?',(contribution_id,)).fetchone()[0],0)
            self.assertEqual(restored.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_append_then_primary_rollback_is_replayed_and_exact_retry_is_idempotent(self):
        ident,_=self._insert_upload(text='Synthetic crash gap')
        with self.fixture.connection() as db:
            db.execute('PRAGMA secure_delete=ON')
            db.execute('BEGIN IMMEDIATE')
            cur=db.execute('SELECT * FROM access_upload_annotations WHERE id=?',(ident,))
            row=dict(zip((column[0] for column in cur.description),cur.fetchone()))
            entry=self.journal.append(db,'upload',row,self.fixture.now)
            db.rollback()  # simulate crash before primary marker and delete commit
        with self.fixture.connection() as db:
            with self.assertRaises(OriginalDeletionError):
                self.journal.assert_current(db)
            db.execute('PRAGMA secure_delete=ON')
            db.execute('BEGIN IMMEDIATE')
            cur=db.execute('SELECT * FROM access_upload_annotations WHERE id=?',(ident,))
            row=dict(zip((column[0] for column in cur.description),cur.fetchone()))
            retried=self.journal.append(db,'upload',row,self.fixture.now)
            db.execute('DELETE FROM access_annotation_tag_proposals WHERE annotation_id=?',(ident,))
            db.execute('DELETE FROM access_annotation_derivations WHERE annotation_id=?',(ident,))
            db.execute('DELETE FROM access_upload_annotations WHERE id=?',(ident,))
            db.commit()
            self.assertEqual(entry['seq'],retried['seq'])
            self.assertEqual(self.journal.head()[1],1)
            self.journal.assert_current(db)

    def test_append_rejects_stale_or_mismatched_fetched_row_without_ledger_change(self):
        ident,_=self._insert_upload(text='Synthetic exact-row test')
        with self.fixture.connection() as db:
            db.execute('PRAGMA secure_delete=ON')
            db.execute('BEGIN IMMEDIATE')
            cur=db.execute('SELECT * FROM access_upload_annotations WHERE id=?',(ident,))
            row=dict(zip((column[0] for column in cur.description),cur.fetchone()))
            row['sha256']='0'*64
            with self.assertRaises(OriginalDeletionError):
                self.journal.append(db,'upload',row,self.fixture.now)
            db.rollback()
        self.assertEqual(self.journal.head()[1],0)

    def test_changed_restored_original_or_wrong_namespace_fails_closed_without_partial_replay(self):
        first,_=self._insert_upload(text='First original stays private')
        second,_=self._insert_upload(text='Second original stays private')
        backup=self.work_path / 'mismatch-backup.sqlite'
        _snapshot(self.fixture.path,backup)
        self._live_delete_upload(first)
        self._live_delete_upload(second)
        _,restored=self._restore(backup)
        with closing(restored):
            restored.execute('DROP TRIGGER trg_access_upload_annotations_immutable')
            restored.execute("UPDATE access_upload_annotations SET original_text='changed source' WHERE id=?",(second,))
            restored.commit()
            with self.assertRaises(OriginalDeletionError):
                self.journal.replay(restored)
            self.assertEqual(restored.execute('SELECT count(*) FROM access_upload_annotations WHERE id IN (?,?)',(first,second)).fetchone()[0],2)
            self.assertEqual(restored.execute('SELECT original_text FROM access_upload_annotations WHERE id=?',(second,)).fetchone()[0],'changed source')
            self.assertEqual(restored.execute('SELECT applied_seq FROM access_original_deletion_state WHERE id=1').fetchone()[0],0)
        with self.assertRaises(OriginalDeletionError):
            OriginalDeletionJournal(self.journal_path,_uuid())

    def test_readonly_review_validates_pending_original_and_preserves_both_databases(self):
        ident,_=self._insert_upload(text='Review validates exact pending original')
        backup=self.work_path/'review-backup.sqlite'
        _snapshot(self.fixture.path,backup)
        self._live_delete_upload(ident)
        _,restored=self._restore(backup)
        with closing(restored):
            before=restored.execute('SELECT original_text FROM access_upload_annotations WHERE id=?',(ident,)).fetchone()[0]
            plan=self.journal.review(restored)
            self.assertEqual(plan['pending_count'],1)
            self.assertEqual(restored.execute('SELECT original_text FROM access_upload_annotations WHERE id=?',(ident,)).fetchone()[0],before)
        # Changed source bytes and matching a different backup both refuse without mutation.
        _,changed=self._restore(backup)
        with closing(changed):
            changed.execute('DROP TRIGGER trg_access_upload_annotations_immutable')
            changed.execute("UPDATE access_upload_annotations SET original_text='tampered' WHERE id=?",(ident,))
            changed.commit()
            with self.assertRaises(OriginalDeletionError):
                self.journal.review(changed)
            self.assertEqual(changed.execute('SELECT original_text FROM access_upload_annotations WHERE id=?',(ident,)).fetchone()[0],'tampered')

    def test_replay_pins_reviewed_head_and_guard_failure_rolls_back(self):
        ident,_=self._insert_upload()
        backup=self.work_path/'head-pin.sqlite'
        _snapshot(self.fixture.path,backup)
        self._live_delete_upload(ident)
        _,restored=self._restore(backup)
        with closing(restored):
            head=self.journal.head()
            with self.assertRaises(OriginalDeletionError):
                self.journal.replay(restored,expected_head=(head[0],head[1]-1,'0'*64))
            with self.assertRaises(OriginalDeletionError):
                self.journal.replay(restored,expected_head=head,precommit_guard=lambda _db: (_ for _ in ()).throw(OriginalDeletionError('changed')))
            self.assertEqual(restored.execute('SELECT count(*) FROM access_upload_annotations WHERE id=?',(ident,)).fetchone()[0],1)
            self.assertEqual(restored.execute('SELECT applied_seq FROM access_original_deletion_state WHERE id=1').fetchone()[0],0)

    def test_initialize_refuses_existing_symlink_or_shared_mode_and_bind_needs_empty_primary(self):
        with self.assertRaises(OriginalDeletionError):
            OriginalDeletionJournal.initialize(self.journal_path,self.namespace)
        symlink=self.work_path/'ledger-link.sqlite'
        symlink.symlink_to(self.journal_path)
        with self.assertRaises(OriginalDeletionError):
            OriginalDeletionJournal(symlink,self.namespace)
        other=self.work_path/'other.sqlite'
        with closing(sqlite3.connect(other)) as db:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('CREATE TABLE access_original_deletion_state (id INTEGER PRIMARY KEY,namespace TEXT,applied_seq INTEGER,applied_digest TEXT)')
            db.execute('CREATE TABLE access_upload_annotations (id TEXT PRIMARY KEY)')
            db.execute("INSERT INTO access_upload_annotations VALUES ('existing')")
            db.commit()
            journal=OriginalDeletionJournal.initialize(self.work_path/'other-ledger.sqlite',_uuid())
            with self.assertRaises(OriginalDeletionError):
                journal.bind(db)

    def test_cli_review_is_readonly_and_execution_requires_writer_stop_attestation(self):
        ident,_=self._insert_upload(text='Synthetic CLI replay')
        backup=self.work_path/'cli-backup.sqlite'
        _snapshot(self.fixture.path,backup)
        self._live_delete_upload(ident)
        restored_path,restored=self._restore(backup)
        restored.close()
        namespace,sequence,digest=self.journal.head()
        args=['--database',str(restored_path),'--journal',str(self.journal_path),
              '--backup-path',str(backup),'--namespace',namespace,
              '--expected-sequence',str(sequence),'--expected-digest',digest]
        self.assertEqual(replay_cli(args),0)  # default review does not mutate the restored copy
        with closing(sqlite3.connect(restored_path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM access_upload_annotations WHERE id=?',(ident,)).fetchone()[0],1)
        self.assertEqual(replay_cli(args+['--execute']),2)
        with closing(sqlite3.connect(restored_path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM access_upload_annotations WHERE id=?',(ident,)).fetchone()[0],1)
        self.assertEqual(replay_cli(args+['--execute','--all-writers-stopped']),0)
        with closing(sqlite3.connect(restored_path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM access_upload_annotations WHERE id=?',(ident,)).fetchone()[0],0)

    def test_cli_refuses_nonmatching_backup_before_mutation(self):
        ident,_=self._insert_upload(text='Backup matching check')
        backup=self.work_path/'cli-good.sqlite'
        _snapshot(self.fixture.path,backup)
        self._live_delete_upload(ident)
        restored_path,restored=self._restore(backup)
        restored.close()
        wrong_backup=self.work_path/'cli-wrong.sqlite'
        _snapshot(self.fixture.path,wrong_backup)
        namespace,sequence,digest=self.journal.head()
        args=['--database',str(restored_path),'--journal',str(self.journal_path),
              '--backup-path',str(wrong_backup),'--namespace',namespace,
              '--expected-sequence',str(sequence),'--expected-digest',digest]
        self.assertEqual(replay_cli(args),2)
        with closing(sqlite3.connect(restored_path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM access_upload_annotations WHERE id=?',(ident,)).fetchone()[0],1)

    def test_cli_refuses_matching_but_pre_e7_schema_without_mutation(self):
        ident,_=self._insert_upload(text='Old schema review')
        candidate=self.work_path/'old-head.sqlite'
        backup=self.work_path/'old-head-backup.sqlite'
        _snapshot(self.fixture.path,candidate)
        _snapshot(self.fixture.path,backup)
        for path in (candidate,backup):
            with closing(sqlite3.connect(path)) as db:
                db.execute("UPDATE alembic_version SET version_num='e6b2f8a1c903'")
                db.commit()
        namespace,sequence,digest=self.journal.head()
        args=['--database',str(candidate),'--journal',str(self.journal_path),
              '--backup-path',str(backup),'--namespace',namespace,
              '--expected-sequence',str(sequence),'--expected-digest',digest]
        self.assertEqual(replay_cli(args),2)
        with closing(sqlite3.connect(candidate)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM access_upload_annotations WHERE id=?',(ident,)).fetchone()[0],1)
