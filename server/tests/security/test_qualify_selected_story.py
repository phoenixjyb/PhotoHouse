"""Portable refusal and report-shape checks for the native rehearsal CLI.

These tests deliberately do not emulate Windows Job membership. Native process
acceptance belongs to the explicit Windows canary run.
"""
import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[2] / 'scripts'
SERVER = SCRIPTS.parent
sys.path.insert(0, str(SERVER / 'backend'))
sys.path.insert(0, str(SCRIPTS))

import qualify_selected_story as qualifier


class SelectedStoryQualificationTests(unittest.TestCase):
    def test_import_is_inert_and_does_not_load_windows_job_adapter(self):
        code = (f"import sys; sys.path.insert(0,{str(SERVER / 'backend')!r}); "
                f"sys.path.insert(0,{str(SCRIPTS)!r}); import qualify_selected_story; "
                "assert 'bounded_windows_job' not in sys.modules; "
                "assert not hasattr(qualify_selected_story,'WindowsAPI')")
        result = subprocess.run([sys.executable, '-I', '-c', code], capture_output=True,
                                text=True, timeout=5)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(qualifier.FEATURE_BASE_COMMIT,
                         '31083f72b0d20e7c0c55f2faea5e4181eea1ff2e')

    def test_source_identity_requires_matching_full_commit_and_self_hash(self):
        with tempfile.TemporaryDirectory() as root:
            package = Path(root)
            script = package / 'scripts' / 'qualify_selected_story.py'
            script.parent.mkdir()
            script.write_bytes(b'synthetic runner source')
            commit = 'b' * 40
            manifest = {'source_commit': commit,
                        'files': {'scripts/qualify_selected_story.py':
                                  hashlib.sha256(script.read_bytes()).hexdigest()}}
            (package / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
            self.assertEqual(commit, qualifier._source_identity(
                commit, package_root=package, script_path=script))
            with self.assertRaises(ValueError):
                qualifier._source_identity('c' * 40, package_root=package, script_path=script)
            script.write_bytes(b'changed runner source')
            with self.assertRaises(ValueError):
                qualifier._source_identity(commit, package_root=package, script_path=script)

    def test_cli_requires_explicit_execute_and_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / 'new-run'
            result = subprocess.run([sys.executable, str(SCRIPTS / 'qualify_selected_story.py'),
                '--commit', 'a' * 40, '--out', str(output)], capture_output=True,
                text=True, timeout=5)
            self.assertEqual(2, result.returncode)
            self.assertFalse(output.exists())
            self.assertEqual('{"status":"failed","synthetic_only":true}',
                             result.stderr.strip())

    def test_existing_output_directory_is_refused(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError):
                qualifier._validate_output(Path(root))

    def test_relative_and_parent_traversal_paths_are_refused(self):
        with self.assertRaises(ValueError):
            qualifier._validate_output('relative-output')
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError):
                qualifier._validate_output(Path(root) / '..' / 'escape')

    def test_report_writer_emits_private_ascii_json_without_contents(self):
        from app.access.private_storage import require_private_file
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root) / 'private'
            directory.mkdir(mode=0o700)
            os.chmod(directory, 0o700)
            path = directory / qualifier.REPORT_NAME
            report = {'status': 'passed', 'synthetic_only': True,
                      'source_commit': 'b' * 40,
                      'feature_base_commit': qualifier.FEATURE_BASE_COMMIT,
                      'interpreter_sha256': 'a' * 64,
                      'cases_passed': list(qualifier.CASES)}
            qualifier._write_report(path, report)
            require_private_file(path)
            self.assertEqual(report, json.loads(path.read_text('ascii')))
            with self.assertRaises(FileExistsError):
                qualifier._write_report(path, report)

    def test_non_windows_execution_refuses_before_creating_output(self):
        if os.name == 'nt':
            self.skipTest('native Windows execution requires the outer proof wrapper')
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / 'new-run'
            with self.assertRaises(ValueError):
                qualifier.main(['--execute', '--commit', 'b' * 40, '--out', str(output)])
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
