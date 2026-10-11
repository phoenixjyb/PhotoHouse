"""Generated e7 qualification and bounded launch controls; no live resources."""
from contextlib import closing, redirect_stdout
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
import qualify_memory_groups as qualification


class MemoryGroupsQualificationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='group-qualification-')
        self.addCleanup(temp.cleanup)
        self.parent = Path(temp.name).resolve()
        if os.name != 'nt':
            self.parent.chmod(0o700)
        self.target = self.parent / 'generated'

    def test_generated_migration_restore_groups_and_revocation_without_external_io(self):
        with patch.dict(os.environ, {'DATABASE_URL': 'sqlite:////must-never-open-live.sqlite'}), \
                patch('socket.socket.connect', side_effect=AssertionError('external connect')), \
                patch('socket.socket.bind', side_effect=AssertionError('external listener')), \
                patch('subprocess.Popen', side_effect=AssertionError('external child')):
            report = qualification.run(self.target)
        self.assertEqual(report, qualification._report(os.name == 'nt'))
        self.assertEqual(json.loads((self.target/'qualification-report.json').read_text()), report)
        self.assertEqual(qualification._revision(self.target/'d1-restored.sqlite'), [(qualification.FROM,)])
        for name in ('primary.sqlite','e7-backup.sqlite','e7-restored.sqlite'):
            with closing(qualification._db(self.target/name)) as db:
                self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
                self.assertEqual(db.execute('SELECT revision,excluded_asset_ids_json FROM access_memory_groups').fetchall(),
                                 [(2, '[102,103]')])
                self.assertEqual(db.execute('SELECT revision,text,byline FROM access_stories').fetchall(),
                                 [(2, '我们沿着湖边散步，一起看夕阳。', 'Synthetic narrator')])
        self.assertFalse((self.target/'qualification-failure.json').exists())

    def test_existing_output_and_symlink_parent_refuse_before_mutation(self):
        self.target.mkdir(mode=0o700)
        sentinel=self.target/'keep'; sentinel.write_bytes(b'owned data')
        with self.assertRaisesRegex(ValueError, 'new_absolute_output_required'):
            qualification.run(self.target)
        self.assertEqual(sentinel.read_bytes(), b'owned data')
        if os.name != 'nt':
            alias=self.parent/'alias'; alias.symlink_to(self.target, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'new_absolute_output_required'):
                qualification.run(alias/'child')
            self.assertFalse((self.target/'child').exists())

    def test_relative_dotdot_and_unprivate_parent_refuse(self):
        for path in (Path('relative'), self.parent/'missing'/'..'/'child'):
            with self.assertRaises(ValueError):
                qualification.run(path)
        if os.name != 'nt':
            self.parent.chmod(0o755)
            with self.assertRaises(ValueError):
                qualification.run(self.target)
            self.assertFalse(self.target.exists())

    def test_failure_retains_safe_receipt_and_no_exception_message(self):
        error=OSError('private endpoint and family filename')
        error.winerror=206
        with patch.object(qualification, '_groups', side_effect=error):
            with self.assertRaises(OSError) as raised:
                qualification.run(self.target)
        self.assertIs(raised.exception, error)
        failure=json.loads((self.target/'qualification-failure.json').read_text())
        self.assertEqual(failure, {'status':'failed','synthetic_only':True,'phase':'groups',
                                  'exception_class':'OSError','winerror':206})
        self.assertNotIn('private endpoint', (self.target/'qualification-failure.json').read_text())
        self.assertFalse((self.target/'qualification-report.json').exists())

    def test_windows_path_budget_checks_utf16_and_sidecars_before_creation(self):
        qualification._check_windows_paths(PureWindowsPath('C:/short/generated'), windows=True)
        with self.assertRaisesRegex(ValueError, 'windows_fixture_path_too_long'):
            qualification._check_windows_paths(PureWindowsPath('C:/'+'\U0001f3e0'*120), windows=True)
        with patch.object(qualification, '_check_windows_paths', side_effect=ValueError('windows_fixture_path_too_long')), \
                patch.object(qualification, '_seed') as seed, patch.object(controller, 'run_bounded') as launch:
            for entry in (qualification.run, qualification._bounded_report):
                with self.assertRaisesRegex(ValueError, 'windows_fixture_path_too_long'):
                    entry(self.target)
            seed.assert_not_called(); launch.assert_not_called()
        self.assertFalse(self.target.exists())

    def _child(self, value, code=0):
        self.target.mkdir(mode=0o700)
        qualification._write_json(self.target/'qualification-report.json', value)
        return code

    def test_bounded_supervisor_pins_limits_environment_and_exact_report(self):
        expected=qualification._report(True)
        with patch.dict(os.environ, {'SystemRoot':'synthetic-system','DATABASE_URL':'must-not-pass'}), \
                patch.object(controller, 'WindowsAPI', return_value=object()), \
                patch.object(controller, 'run_bounded', side_effect=lambda *a, **k:self._child(expected)) as launch:
            self.assertEqual(qualification._bounded_report(self.target), expected)
        args, kwargs=launch.call_args
        self.assertEqual(kwargs, {'timeout_seconds':900,'memory_limit':2*1024**3,
                                 'process_limit':4,'minimum_free_ram':8*1024**3})
        self.assertNotIn('DATABASE_URL',args[3])
        self.assertEqual(args[2][1:3], ['-I','-B'])
        self.assertEqual(args[2][3], '-c')
        self.assertIn("runpy.run_path", args[2][4])
        self.assertNotIn('--bounded-child',args[2])

    def test_supervisor_rejects_failure_bool_coercion_and_extra_fields(self):
        for index, (value, code) in enumerate((
                (qualification._report(True),2),
                ({**qualification._report(True),'native_windows':1},0),
                ({**qualification._report(True),'unreviewed':'extra'},0))):
            self.target=self.parent/f'bad-{index}'
            with patch.dict(os.environ, {'SystemRoot':'synthetic-system'}), \
                    patch.object(controller, 'WindowsAPI', return_value=object()), \
                    patch.object(controller, 'run_bounded', side_effect=lambda *a, **k:self._child(value,code)):
                with self.assertRaises(controller.CheckRefused):
                    qualification._bounded_report(self.target)

    def test_cli_cannot_select_database_or_caller_marked_child(self):
        with redirect_stdout(io.StringIO()), patch('sys.stderr',new_callable=io.StringIO):
            with self.assertRaises(SystemExit):
                qualification.main(['--out',str(self.target),'--database','live.sqlite'])
        with patch.dict(os.environ, {'PHOTOHOUSE_GROUP_QUALIFICATION_CHILD':'1'}), \
                patch('sys.stderr',new_callable=io.StringIO), patch.object(qualification, 'run') as run:
            with self.assertRaises(SystemExit):
                qualification.main(['--out',str(self.target),'--bounded-child'])
            run.assert_not_called()
        self.assertFalse(self.target.exists())


if __name__=='__main__':
    unittest.main()
