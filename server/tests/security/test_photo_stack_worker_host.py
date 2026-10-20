"""Generated-only refresh host, cancellation, locking and bounded launch checks."""
from contextlib import closing, redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import bounded_windows_job as controller
import qualify_library_photo_stacks as fixture
import run_photo_stack_worker as host
from app.access.library_photo_stacks import LibraryPhotoStacks, rebuild_photo_stack_index
from app.access.photo_stack_index import PhotoStackCancelled, build_library_photo_stacks
from app.access.service import AccessService


class PhotoStackWorkerHostTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='stack-host-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        if os.name != 'nt':
            self.root.chmod(0o700)
        self.database, self.journal_path = self.root/'primary.sqlite', self.root/'journal.sqlite'
        fixture.fixture._seed(self.database, revision=fixture.FROM)
        import uuid
        self.namespace = str(uuid.uuid4())
        self.history = fixture.OriginalDeletionJournal.initialize(self.journal_path, self.namespace)
        fixture._seed_originals(self.database, self.history)
        fixture._migrate(self.database, fixture.REVISION)
        with fixture._connection(self.database, self.history) as db:
            db.execute('BEGIN IMMEDIATE')
            self.history.upgrade_family_format(db, expected_head=self.history.head())
            db.commit()
        fixture._seed_gallery(self.database)
        self.stop = self.root/'refresh.stop'
        self.arguments = {'database':self.database, 'journal':self.journal_path, 'namespace':self.namespace,
                          'libraries':(fixture.fixture.LIBRARY,), 'stop_file':self.stop}

    def rows(self, table):
        with closing(fixture.fixture._db(self.database)) as db:
            return db.execute('SELECT * FROM '+table+' ORDER BY rowid').fetchall()

    def original_rows(self):
        return {name:self.rows(name) for name in ('assets','tasks','captions','access_stories','access_upload_annotations')}

    def test_preflight_opens_no_socket_child_or_writer_and_preserves_raw_bytes(self):
        before = [self.database.read_bytes(), self.journal_path.read_bytes()]
        with patch('socket.socket.connect', side_effect=AssertionError('network')), \
                patch('subprocess.Popen', side_effect=AssertionError('child')):
            report = host.preflight(**self.arguments)
        self.assertEqual(report['status'], 'ready')
        self.assertEqual(report['libraries'][0]['active_assets'], 16)
        self.assertFalse(report['worker_executed'])
        self.assertEqual(before, [self.database.read_bytes(), self.journal_path.read_bytes()])
        self.assertFalse(Path(str(self.database)+'.photo-stack-refresh.lock').exists())

    def test_one_sweep_updates_then_noops_without_modifying_originals_or_tasks(self):
        before, journal_hash = self.original_rows(), hashlib.sha256(self.journal_path.read_bytes()).hexdigest()
        with patch('subprocess.Popen', side_effect=AssertionError('child')), \
                patch('socket.socket.connect', side_effect=AssertionError('network')):
            first = host.execute_once(**self.arguments)
            second = host.execute_once(**self.arguments)
        self.assertEqual(first['results'][0]['status'], 'updated')
        self.assertEqual(second['results'][0]['status'], 'unchanged')
        self.assertEqual(first['results'][0]['index_revision'], second['results'][0]['index_revision'])
        self.assertEqual(before, self.original_rows())
        self.assertEqual(journal_hash, hashlib.sha256(self.journal_path.read_bytes()).hexdigest())

    def test_runnable_hash_waits_and_failures_are_retained(self):
        with closing(fixture.fixture._db(self.database)) as db:
            ident = db.execute("INSERT INTO tasks(type,state,payload_json) VALUES('phash','pending','{\"asset_id\":101}')").lastrowid
            db.commit()
        self.assertEqual(host.execute_once(**self.arguments)['results'][0]['status'], 'waiting')
        with closing(fixture.fixture._db(self.database)) as db:
            db.execute("UPDATE tasks SET state='failed',retry_count=3,last_error='retained generated failure' WHERE id=?", (ident,)); db.commit()
        tasks = self.rows('tasks')
        self.assertEqual(host.execute_once(**self.arguments)['results'][0]['status'], 'updated')
        self.assertEqual(tasks, self.rows('tasks'))

    def test_stop_control_or_signal_before_start_never_creates_lock_or_index(self):
        fixture.fixture._create_file(self.stop)
        for entry in (host.preflight, host.execute_once):
            self.assertEqual(entry(**self.arguments)['status'], 'stopped')
        self.assertEqual(self.rows('access_photo_stack_indexes'), [])
        self.assertFalse(Path(str(self.database)+'.photo-stack-refresh.lock').exists())
        self.stop.unlink()
        event = threading.Event(); event.set()
        self.assertEqual(host.execute_once(**self.arguments,event=event)['reason'], 'signal')

    def test_exclusive_lock_refuses_second_writer_and_leaves_index_untouched(self):
        with host._lock(self.database):
            with self.assertRaisesRegex(host.Refused,'photo_stack_worker_already_running'):
                host.execute_once(**self.arguments)
        self.assertEqual(self.rows('access_photo_stack_indexes'), [])

    def test_stop_inside_publication_rolls_back_to_previous_complete_index(self):
        host.execute_once(**self.arguments)
        with closing(fixture.fixture._db(self.database)) as db:
            db.execute('UPDATE assets SET width=88 WHERE id=101'); db.commit()
        before = {name:self.rows(name) for name in fixture.TABLES}
        event = threading.Event()
        original = host._factory
        def factory(*args, **kwargs):
            actual = original(*args, **kwargs)
            from contextlib import contextmanager
            @contextmanager
            def connect():
                with actual() as db:
                    db.set_trace_callback(lambda sql:event.set() if sql.startswith('DELETE FROM access_photo_stack_groups') else None)
                    yield db
            return connect
        with patch.object(host, '_factory', side_effect=factory):
            result = host.execute_once(**self.arguments, event=event)
        self.assertEqual(result['status'], 'stopped')
        self.assertEqual(before, {name:self.rows(name) for name in fixture.TABLES})
        with closing(fixture.fixture._db(self.database)) as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchall(), [('ok',)])

    def test_pure_cpu_cancellation_does_not_return_partial_groups(self):
        rows = [(i,'image/jpeg','generated',1,1,'2026-01-01 10:00:00','0'*16,None,None) for i in range(1,101)]
        calls = 0
        def stop():
            nonlocal calls
            calls += 1
            return calls > 120
        with self.assertRaises(PhotoStackCancelled):
            build_library_photo_stacks(rows,stopped=stop)

    def test_schema_scope_and_history_inputs_are_not_inferred_or_repaired(self):
        with self.assertRaises((ValueError, RuntimeError)):
            host.preflight(**{**self.arguments,'libraries':('missing-library',)})
        for libraries in ((), ['not-a-tuple'], (fixture.fixture.LIBRARY,)*2):
            with self.subTest(libraries=libraries), self.assertRaises(ValueError):
                host.preflight(**{**self.arguments,'libraries':libraries})
        with self.assertRaises(ValueError):
            host.preflight(**{**self.arguments,'database':self.root/'missing.sqlite'})
        self.assertFalse((self.root/'missing.sqlite').exists())
        with self.assertRaises((ValueError,RuntimeError)):
            host.preflight(**{**self.arguments,'namespace':'invalid'})

    def test_unrelated_journal_does_not_replace_current_history(self):
        path = self.root/'v1.sqlite'
        journal = fixture.OriginalDeletionJournal.initialize(path,self.namespace)
        raw = path.read_bytes()
        with self.assertRaises((ValueError,RuntimeError)):
            host.preflight(**{**self.arguments,'journal':path})
        self.assertEqual(raw,path.read_bytes())

    def test_f2_refresh_preserves_a_valid_v1_journal_without_capability_upgrade(self):
        primary, journal_path = self.root/'v1-primary.sqlite', self.root/'valid-v1.sqlite'
        fixture.fixture._seed(primary,revision=fixture.FROM)
        journal = fixture.OriginalDeletionJournal.initialize(journal_path,self.namespace)
        fixture._seed_originals(primary,journal)
        fixture._migrate(primary,fixture.REVISION)
        fixture._seed_gallery(primary)
        raw = journal_path.read_bytes()
        arguments = {**self.arguments,'database':primary,'journal':journal_path}
        self.assertEqual(host.preflight(**arguments)['status'],'ready')
        self.assertEqual(host.execute_once(**arguments)['results'][0]['status'],'updated')
        self.assertEqual(raw,journal_path.read_bytes())

    def test_selected_primary_and_journal_identity_cannot_change_mid_sweep(self):
        _, _, history, _ = host._configuration(**self.arguments)
        with closing(fixture.fixture._db(self.database)) as db:
            factory = host._factory(self.database,history,lambda:False,readonly=True)
        replacement = self.root/'replacement.sqlite'
        fixture._backup(self.database,replacement)
        os.replace(replacement,self.database)
        with self.assertRaisesRegex(host.Refused,'database_replaced'):
            with factory():
                self.fail('replaced database opened')
        with self.assertRaisesRegex(host.Refused,'database_replaced'):
            history.head()
        history = host._PinnedJournal(self.journal_path,self.namespace,database=self.database)
        replacement = self.root/'replacement-journal.sqlite'
        fixture._backup(self.journal_path,replacement); os.replace(replacement,self.journal_path)
        with self.assertRaisesRegex(host.Refused,'journal_replaced'):
            history.head()

    def test_stop_reason_is_bounded_and_sticky(self):
        now = [100.0]
        stop = host.StopSignal(self.stop,seconds=2,monotonic=lambda:now[0])
        self.assertFalse(stop())
        now[0] = 103
        self.assertTrue(stop()); self.assertEqual(stop.reason,'time_budget')
        now[0] = 100
        self.assertTrue(stop())

    def test_journal_guard_uses_a_strictly_read_only_sqlite_handle(self):
        raw = self.journal_path.read_bytes()
        guard = host._PinnedJournal(self.journal_path,self.namespace)
        with closing(guard._connect()) as db:
            self.assertEqual(db.execute('PRAGMA query_only').fetchone()[0],1)
            with self.assertRaises(sqlite3.OperationalError):
                db.execute("UPDATE journal_meta SET head_seq=9")
        self.assertEqual(raw,self.journal_path.read_bytes())

    def test_windows_execution_has_no_cli_child_bypass_and_fixed_job_limits(self):
        arguments = {k:str(v) if isinstance(v,Path) else v for k,v in self.arguments.items()}
        with patch.dict(os.environ,{'SystemRoot':'synthetic-system','DATABASE_URL':'must-not-forward','OLLAMA_HOST':'must-not-forward'}), \
                patch.object(controller,'WindowsAPI',return_value=object()), \
                patch.object(controller,'run_bounded',return_value=0) as launch:
            self.assertEqual(host._bounded_execute(arguments),0)
        args, kwargs = launch.call_args
        self.assertEqual(kwargs,{'timeout_seconds':240,'memory_limit':2*1024**3,'process_limit':8,'minimum_free_ram':8*1024**3})
        self.assertNotIn('DATABASE_URL',args[3]); self.assertNotIn('OLLAMA_HOST',args[3])
        self.assertEqual(args[2][1:4],['-I','-B','-c'])
        with patch('sys.stderr',new_callable=io.StringIO), self.assertRaises(host.Refused):
            host.main(['--bounded-child'])


if __name__ == '__main__':
    unittest.main()
