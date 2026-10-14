"""Generated output/privacy and native-child contract tests for the source runner."""
import json
import io
import os
from pathlib import Path
from contextlib import redirect_stderr, redirect_stdout
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

SERVER = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SERVER / 'scripts'))
sys.path.insert(0, str(SERVER / 'backend'))
import qualify_oral_history as runner


class QualifyOralHistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='oral-qualification-')
        self.addCleanup(self.tmp.cleanup)
        self.parent = Path(self.tmp.name).resolve()
        os.chmod(self.parent, 0o700)

    def test_generated_run_exercises_all_content_free_case_groups(self):
        output = self.parent / 'generated'
        result = runner.run(output)
        self.assertEqual(set(result['cases']), set(runner.CASES))
        self.assertTrue(all(result['cases'].values()))
        self.assertEqual(result['groups'], {
            'journal_upgrade_and_recovery': 3, 'private_durable_intake': 3,
            'identity_scope_withdrawal': 3, 'source_integrity': 1})
        self.assertTrue(result['experimental_fixture_schema'])
        self.assertFalse(result['production_admission_available'])
        self.assertFalse(result['production_transport_available'])
        self.assertFalse(result['production_erasure_available'])
        for field in ('production_database_opened', 'family_media_opened',
                      'provider_or_model_used', 'socket_listener_started', 'network_accessed',
                      'workers_executed', 'services_changed', 'tasks_changed', 'published'):
            self.assertFalse(result[field])
        self.assertFalse(result['source_audio_exported'])
        self.assertEqual(result['accepted_counts_before_restore'], {
            'sessions': 1, 'sections': 2, 'mutations': 3, 'journal_recordings': 1})
        self.assertEqual(result['final_fixture_counts'], {
            'sessions': 1, 'sections': 1, 'mutations': 2, 'journal_recordings': 1})
        self.assertEqual(json.loads((output / runner.REPORT).read_text()), result)
        report = (output / runner.REPORT).read_text()
        for forbidden in ('Synthetic interview', 'Generated subject', 'Generated speaker', 'RIFF'):
            self.assertNotIn(forbidden, report)
        self.assertTrue((output / 'main.sqlite').is_file())
        self.assertTrue((output / 'oral-journal.sqlite').is_file())
        self.assertEqual({path.name for path in output.iterdir()},
                         {'main.sqlite', 'oral-journal.sqlite', runner.REPORT})
        self.assertEqual((output / runner.REPORT).stat().st_mode & 0o777, 0o600)
        if os.name != 'nt':
            for name in ('main.sqlite', 'oral-journal.sqlite'):
                self.assertEqual((output / name).stat().st_mode & 0o777, 0o600)
        with sqlite3.connect(output / 'main.sqlite') as db:
            self.assertEqual(tuple(db.execute('SELECT state,section_count FROM '
                'access_oral_history_sessions').fetchone()), ('withdrawn', 1))
            self.assertEqual(db.execute('SELECT count(*) FROM access_oral_history_sections').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT count(*) FROM access_oral_history_mutations').fetchone()[0], 2)

    def test_rejects_existing_relative_symlink_and_nonprivate_output_parent(self):
        with self.assertRaises(ValueError):
            runner._validate_output(Path('relative'))
        existing = self.parent / 'existing'
        existing.mkdir()
        with self.assertRaises(ValueError):
            runner._validate_output(existing)
        alias = self.parent / 'alias'
        alias.symlink_to(existing, target_is_directory=True)
        with self.assertRaises(ValueError):
            runner._validate_output(alias / 'new')

    def test_cli_rejects_database_or_provider_options(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        secret_path = '/private/Family Name/original.sqlite'
        with redirect_stdout(stdout), redirect_stderr(stderr), self.assertRaises(ValueError):
            runner.main(['--out', str(self.parent / 'new'), '--database', secret_path])
        self.assertNotIn(secret_path, stdout.getvalue() + stderr.getvalue())
        self.assertEqual(stdout.getvalue() + stderr.getvalue(), '')

    def test_rejects_parent_that_is_not_private_on_posix(self):
        if os.name == 'nt':
            self.skipTest('POSIX mode check')
        os.chmod(self.parent, 0o755)
        with self.assertRaises(ValueError):
            runner._validate_output(self.parent / 'new')

    def test_refuses_broken_upgrade_without_report_of_success(self):
        from app.access.original_deletions import OriginalDeletionJournal, OriginalDeletionError
        with patch.object(OriginalDeletionJournal, 'upgrade_oral_format',
                          side_effect=OriginalDeletionError('synthetic upgrade refusal')):
            with self.assertRaises(OriginalDeletionError):
                runner.run(self.parent / 'broken')
        failure = json.loads((self.parent / 'broken' / runner.FAILURE).read_text())
        self.assertEqual(failure, {'status': 'failed', 'synthetic_only': True,
                                   'phase': 'v3_upgrade', 'exception_class': 'Exception'})
        self.assertFalse((self.parent / 'broken' / runner.REPORT).exists())
        with sqlite3.connect(self.parent / 'broken' / 'oral-journal.sqlite') as ledger:
            self.assertEqual(ledger.execute('SELECT format FROM journal_meta').fetchone()[0],
                             'photohouse-original-deletion-journal-v3')

    def test_windows_path_guard_counts_outputs_and_interpreter(self):
        target = self.parent / ('x' * 270)
        with self.assertRaises(ValueError):
            runner._validate_output(target, windows=True)

    def test_bounded_child_forwards_all_native_limits_and_clean_environment(self):
        target = self.parent / 'child'
        target.mkdir(mode=0o700)
        report = runner._report(True)
        runner._write_json(target / runner.REPORT, report)
        calls = []
        class API: pass
        def fake(api, executable, argv, environment, cwd, **limits):
            calls.append((api, executable, argv, environment, cwd, limits))
            return 0
        with patch.dict(os.environ, {'SystemRoot': str(self.parent)}, clear=True), \
             patch('bounded_windows_job.WindowsAPI', API), \
             patch('bounded_windows_job.run_bounded', fake):
            self.assertEqual(runner._bounded_run(target), report)
        api, executable, argv, environment, cwd, limits = calls[0]
        self.assertIsInstance(api, API)
        self.assertEqual(limits, {'timeout_seconds': 300, 'memory_limit': 2 * 1024**3,
                                  'process_limit': 8, 'minimum_free_ram': 8 * 1024**3})
        self.assertEqual(argv[1:3], ['-I', '-B'])
        self.assertEqual(cwd, str(self.parent))
        self.assertEqual(environment['PHOTOHOUSE_NO_DOTENV'], '1')
        self.assertEqual(environment['PYTHONNOUSERSITE'], '1')
        self.assertEqual(environment['PYTHONDONTWRITEBYTECODE'], '1')
        self.assertNotIn('PYTHONPATH', environment)
        self.assertEqual(set(environment), {'PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP',
                                            'PHOTOHOUSE_NO_DOTENV', 'PYTHONNOUSERSITE',
                                            'PYTHONDONTWRITEBYTECODE'})

    def test_bounded_child_refuses_malformed_or_unexpected_report(self):
        target = self.parent / 'child'
        target.mkdir(mode=0o700)
        runner._write_json(target / runner.REPORT, {'status': 'passed'})
        class API: pass
        with patch.dict(os.environ, {'SystemRoot': str(self.parent)}, clear=True), \
             patch('bounded_windows_job.WindowsAPI', API), \
             patch('bounded_windows_job.run_bounded', return_value=0):
            with self.assertRaises(Exception):
                runner._bounded_run(target)

    def test_report_validation_does_not_treat_boolean_counts_as_integers(self):
        expected = runner._report(True)
        altered = {**expected, 'final_fixture_counts': {
            **expected['final_fixture_counts'], 'sections': True}}
        self.assertFalse(runner._validate_report(altered, expected))

    def test_wrong_transport_status_does_not_satisfy_refusal_case(self):
        from app.access.transport import TransportError
        def forbidden_status():
            raise TransportError(403, 'wrong refusal')
        with self.assertRaises(RuntimeError):
            runner._expect_status(409, forbidden_status, 'status_mismatch')


if __name__ == '__main__':
    unittest.main()
