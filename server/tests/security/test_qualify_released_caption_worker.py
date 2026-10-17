"""Generated-only end-to-end qualification for the released-caption worker."""
import importlib.util
import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'scripts'))

SPEC = importlib.util.spec_from_file_location(
    'qualify_released_caption_worker', ROOT / 'scripts' / 'qualify_released_caption_worker.py',
)
qualifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(qualifier)


class ReleasedCaptionQualificationTests(unittest.TestCase):
    def test_generated_only_queue_and_provider_journey(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory(prefix='released-caption-qual-') as temporary:
            parent = Path(temporary).resolve()
            output = parent / 'qualification'
            report = qualifier.run(output)
            self.assertEqual(report['status'], 'passed')
            self.assertTrue(report['synthetic_only'])
            self.assertFalse(report['native_windows'])
            self.assertEqual(report['cases_passed'], list(qualifier.CASES))
            self.assertEqual(report['case_count'], len(qualifier.CASES))
            self.assertEqual(report['released_caption_task_count'], 6)
            self.assertEqual(report['generated_original_count'], 6)
            self.assertEqual(report['foreign_failed_task_count'], 1)
            self.assertFalse(report['production_database_opened'])
            self.assertFalse(report['family_media_opened'])
            self.assertFalse(report['models_loaded'])
            self.assertFalse(report['network_requests'])
            self.assertFalse(report['services_changed'])
            self.assertTrue(report['original_bytes_preserved'])
            self.assertTrue(report['configured_journal_unchanged_during_processing'])
            self.assertEqual(report['mock_http_requests_by_path']['/health'], 6)
            self.assertGreaterEqual(report['mock_http_requests_by_path']['/caption'], 8)
            self.assertEqual(report['mock_http_requests_by_path']['/translate'], 0)
            self.assertEqual((output.stat().st_mode & 0o777), 0o700)
            self.assertEqual((output / qualifier.REPORT_NAME).stat().st_mode & 0o777, 0o600)

    def test_run_refuses_existing_output_without_modifying_it(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory(prefix='released-caption-existing-') as temporary:
            output = Path(temporary) / 'already-there'
            output.mkdir(mode=0o700)
            marker = output / 'keep.txt'
            marker.write_text('synthetic marker')
            with self.assertRaises(qualifier.QualificationRefused) as caught:
                qualifier.run(output)
            self.assertEqual(caught.exception.code, 'invalid_output')
            self.assertEqual(marker.read_text(), 'synthetic marker')

    def test_cli_accepts_only_the_new_output_directory(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory(prefix='released-caption-cli-') as temporary:
            output = Path(temporary).resolve() / 'qualification'
            stdout = StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(qualifier.main(['--out', str(output)]), 0)
            cli_report = json.loads(stdout.getvalue())
            self.assertEqual(cli_report['status'], 'passed')
            self.assertEqual(cli_report['cases_passed'], list(qualifier.CASES))

    def test_direct_child_mode_cannot_create_output_without_a_windows_budget(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory(prefix='released-caption-unbounded-') as temporary:
            output = Path(temporary).resolve() / 'must-not-exist'
            with patch.object(qualifier.runner.sys, 'platform', 'darwin'):
                with self.assertRaisesRegex(qualifier.runner.WorkerRefused, 'windows_required'):
                    qualifier.main(['--out', str(output), '--bounded-child'])
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
