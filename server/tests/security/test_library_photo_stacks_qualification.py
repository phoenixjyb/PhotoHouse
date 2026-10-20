"""Generated rehearsal and admission controls; no production data or services."""
from contextlib import closing, redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path, PureWindowsPath
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import bounded_windows_job as controller
import qualify_library_photo_stacks as q


class LibraryPhotoStacksQualificationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='stack-rehearsal-')
        self.addCleanup(temp.cleanup)
        self.parent = Path(temp.name).resolve()
        if os.name != 'nt':
            self.parent.chmod(0o700)
        self.target = self.parent/'generated'

    def test_complete_flow_ignores_live_settings_and_opens_no_network_or_child(self):
        with patch.dict(os.environ, {'DATABASE_URL':'sqlite:////must-not-open.sqlite'}), \
                patch('socket.socket.connect', side_effect=AssertionError('external connection')), \
                patch('socket.socket.bind', side_effect=AssertionError('listener')), \
                patch('subprocess.Popen', side_effect=AssertionError('child')):
            report = q.run(self.target)
        self.assertEqual(report, q._report(os.name == 'nt'))
        self.assertEqual(json.loads((self.target/'qualification-report.json').read_bytes()), report)
        self.assertEqual(set(p.name for p in self.target.iterdir()), set(q.FILE_NAMES)-{'qualification-failure.json'})
        self.assertEqual(q.fixture._revision(self.target/'a0-restored.sqlite'), [(q.FROM,)])
        self.assertEqual(q.fixture._revision(self.target/'f2-restored.sqlite'), [(q.REVISION,)])
        for name, count in (('v1-restored.sqlite',1), ('v2-restored.sqlite',1), ('journal.sqlite',2)):
            with closing(q.fixture._db(self.target/name)) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM deletions').fetchone(), (count,))
        # An original audio BLOB and legacy prose survived migration/indexing;
        # only the explicitly selected synthetic text original was later erased.
        with closing(q.fixture._db(self.target/'primary.sqlite')) as db:
            self.assertEqual(db.execute('SELECT text,byline FROM access_stories').fetchall(),
                             [('我们一起看夕阳。', 'Synthetic narrator')])
            rows = db.execute('SELECT kind,original_audio,sha256 FROM access_upload_annotations').fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][0], 'audio')
            self.assertEqual(hashlib.sha256(rows[0][1]).hexdigest(), rows[0][2])
        with closing(q.fixture._db(self.target/'a0-backup.sqlite')) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM access_upload_annotations').fetchone(), (2,))
        with closing(q.fixture._db(self.target/'f2-restored.sqlite')) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM access_upload_annotations').fetchone(), (2,))
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_existing_output_relative_and_symlink_parent_refused(self):
        self.target.mkdir(mode=0o700)
        sentinel = self.target/'keep'; sentinel.write_bytes(b'owned data')
        for target in (self.target, Path('relative'), self.parent/'missing'/'..'/'child'):
            with self.subTest(target=target), self.assertRaises((ValueError, FileNotFoundError)):
                q.run(target)
        self.assertEqual(sentinel.read_bytes(), b'owned data')
        if os.name != 'nt':
            alias = self.parent/'alias'; alias.symlink_to(self.target, target_is_directory=True)
            with self.assertRaises(ValueError):
                q.run(alias/'child')
            self.assertFalse((self.target/'child').exists())

    def test_unprivate_parent_refused_before_seed(self):
        if os.name == 'nt':
            self.skipTest('POSIX permissions only; Windows uses native private ACL checks')
        self.parent.chmod(0o755)
        with patch.object(q.fixture, '_seed') as seed, self.assertRaises(ValueError):
            q.run(self.target)
        seed.assert_not_called()

    def test_failure_receipt_is_sanitized_and_never_claims_pass(self):
        with patch.object(q, '_gallery_lifecycle', side_effect=OSError('private filename and endpoint')):
            with self.assertRaises(OSError):
                q.run(self.target)
        failure = json.loads((self.target/'qualification-failure.json').read_bytes())
        self.assertEqual(failure, {'status':'failed','synthetic_only':True,'phase':'gallery','exception_class':'OSError'})
        self.assertFalse((self.target/'qualification-report.json').exists())
        self.assertNotIn('private filename', json.dumps(failure))

    def test_interruption_must_reach_f2_and_successful_migration_cannot_be_reported_as_rollback(self):
        original = q._migrate
        with patch.object(q, '_migrate', side_effect=lambda p,r,**k: original(p,r)):
            with self.assertRaisesRegex(RuntimeError, 'synthetic_interruption_not_reached'):
                q.run(self.target)
        self.assertEqual(json.loads((self.target/'qualification-failure.json').read_bytes())['phase'], 'migration')

    def test_windows_path_budget_checks_sidecars_and_utf16(self):
        q._check_windows_paths(PureWindowsPath('C:/short/generated'), windows=True)
        with self.assertRaisesRegex(ValueError, 'windows_fixture_path_too_long'):
            q._check_windows_paths(PureWindowsPath('C:/'+'\U0001f3e0'*120), windows=True)
        with patch.object(q, '_check_windows_paths', side_effect=ValueError('windows_fixture_path_too_long')), \
                patch.object(q.fixture, '_seed') as seed, patch.object(controller, 'run_bounded') as launch:
            for entry in (q.run, q._bounded_report):
                with self.assertRaises(ValueError):
                    entry(self.target)
            seed.assert_not_called(); launch.assert_not_called()

    def _child(self, report):
        self.target.mkdir(mode=0o700)
        q.fixture._write_json(self.target/'qualification-report.json', report)
        return 0

    def test_windows_supervisor_pins_limits_and_clean_environment(self):
        with patch.dict(os.environ, {'SystemRoot':'synthetic-system', 'DATABASE_URL':'live', 'OLLAMA_HOST':'live'}), \
                patch.object(controller, 'WindowsAPI', return_value=object()), \
                patch.object(controller, 'run_bounded', side_effect=lambda *a,**k:self._child(q._report(True))) as launch:
            self.assertEqual(q._bounded_report(self.target), q._report(True))
        args, kwargs = launch.call_args
        self.assertEqual(kwargs, {'timeout_seconds':240,'memory_limit':2*1024**3,
                                 'process_limit':8,'minimum_free_ram':8*1024**3})
        self.assertEqual(args[2][1:4], ['-I','-B','-c'])
        self.assertIn('runpy.run_path', args[2][4])
        self.assertNotIn('DATABASE_URL', args[3]); self.assertNotIn('OLLAMA_HOST', args[3])
        self.assertNotIn('--bounded-child', args[2])

    def test_supervisor_rejects_failed_child_without_accepting_receipt(self):
        with patch.dict(os.environ, {'SystemRoot':'synthetic-system'}), \
                patch.object(controller, 'WindowsAPI', return_value=object()), \
                patch.object(controller, 'run_bounded', return_value=2):
            with self.assertRaisesRegex(controller.CheckRefused, 'qualification_child_failed'):
                q._bounded_report(self.target)
        self.assertFalse(self.target.exists())

    def test_supervisor_rejects_inexact_or_boolean_lookalike_report(self):
        for changes in ({'native_windows':1}, {'models_loaded':0}, {'deletion_records_before_upgrade':True}, {'cases':[]}, {'extra':True}):
            with self.subTest(changes=changes), tempfile.TemporaryDirectory(dir=self.parent) as name:
                target = Path(name)/'generated'
                def child(*a, **k):
                    target.mkdir(mode=0o700)
                    q.fixture._write_json(target/'qualification-report.json', {**q._report(True), **changes})
                    return 0
                with patch.dict(os.environ, {'SystemRoot':'synthetic-system'}), \
                        patch.object(controller, 'WindowsAPI', return_value=object()), \
                        patch.object(controller, 'run_bounded', side_effect=child):
                    with self.assertRaisesRegex(controller.CheckRefused, 'qualification_report_unavailable'):
                        q._bounded_report(target)

    def test_cli_has_no_runtime_target_or_child_bypass(self):
        for extra in (['--database','live.sqlite'], ['--bounded-child'], ['--library','live']):
            with self.subTest(extra=extra), redirect_stdout(io.StringIO()), \
                    patch('sys.stderr', new_callable=io.StringIO), patch.object(q, 'run') as run:
                with self.assertRaises(SystemExit):
                    q.main(['--out',str(self.target),*extra])
                run.assert_not_called()
        self.assertFalse(self.target.exists())


if __name__ == '__main__':
    unittest.main()
