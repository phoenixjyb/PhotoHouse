"""Portable safety and behavior checks for the listener-free qualification."""
import json
import os
from pathlib import Path, PureWindowsPath
import subprocess
import sys
import stat
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))

import qualify_private_assistant as qualification


class QualifyPrivateAssistantTests(unittest.TestCase):
    def setUp(self):
        self.parent_context = tempfile.TemporaryDirectory(prefix='private-assistant-qualification-')
        self.addCleanup(self.parent_context.cleanup)
        self.parent = Path(self.parent_context.name).resolve()
        if os.name != 'nt':
            self.parent.chmod(0o700)

    def test_import_keeps_runtime_dependencies_unloaded_until_run(self):
        script = Path(qualification.__file__).resolve()
        code = (
            'import importlib.util,sys; '
            f'spec=importlib.util.spec_from_file_location("qualifier_probe",{str(script)!r}); '
            'module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); '
            'names=("alembic", "sqlalchemy", "fastapi", "app.access.runtime", '
            '"app.access.assistant_speech"); '
            'loaded=[name for name in sys.modules if any(name == item or name.startswith(item + ".") '
            'for item in names)]; '
            'assert not loaded, sorted(loaded)'
        )
        probe = subprocess.run([sys.executable, '-I', '-B', '-c', code],
                               capture_output=True, text=True, check=False)
        self.assertEqual(probe.returncode, 0, probe.stdout + probe.stderr)
        self.assertEqual(probe.stdout, '')

    def test_generated_runtime_qualifies_turn_recovery_labels_history_scope_and_retention(self):
        output = self.parent / 'fresh-output'
        result = qualification.run(output)
        self.assertEqual(result, qualification._report(os.name == 'nt'))
        self.assertEqual(len(result['cases_passed']), 12)
        self.assertIn('negotiated_saved_story_memoir_and_strict_legacy_recovery',
                      result['cases_passed'])
        self.assertIn('saved_memory_reply_speech_revalidates_sources_after_synthesis',
                      result['cases_passed'])
        if os.name != 'nt':
            self.assertIs(result['native_windows'], False)
        self.assertEqual({path.name for path in output.iterdir()}, {
            'main.sqlite', 'assistant-workspace.sqlite', 'assistant-journal.sqlite', 'discovery-index.json',
            'qualification-report.json', 'synthetic-originals', 'synthetic-derived'})
        report = (output / 'qualification-report.json').read_text(encoding='ascii')
        self.assertNotIn(qualification.TOKEN, report)
        self.assertNotIn(qualification.OTHER_TOKEN, report)
        self.assertNotIn('find photos', report)
        self.assertTrue((output / 'main.sqlite').is_file())
        self.assertTrue((output / 'assistant-workspace.sqlite').is_file())
        self.assertTrue((output / 'discovery-index.json').is_file())

    def test_generated_runtime_fails_if_contextual_action_parser_stops_dispatching(self):
        sys.path.insert(0, str(ROOT / 'backend'))
        from app.access import assistant_workspace_transport as transport

        output = self.parent / 'action-parser-failure'
        with patch.object(transport, 'parse_saved_memory_action', return_value=None):
            with self.assertRaisesRegex(
                    RuntimeError, 'synthetic_memory_read_action_cohort_or_order_invalid'):
                qualification.run(output)
        failure = json.loads((output / 'qualification-failure.json').read_text(encoding='ascii'))
        self.assertEqual(failure, {'status': 'failed', 'synthetic_only': True,
            'phase': 'saved_memory_contextual_actions', 'exception_class': 'RuntimeError',
            'winerror': None})

    def test_generated_runtime_refuses_broken_segment_metadata(self):
        sys.path.insert(0, str(ROOT / 'backend'))
        from app.access import assistant_workspace_transport as transport

        output = self.parent / 'segment-contract-failure'
        with patch.object(transport, 'saved_reading_segments', side_effect=lambda text: (text,)):
            with self.assertRaisesRegex(RuntimeError, 'synthetic_segment_speech_or_metadata_failed'):
                qualification.run(output)
        failure = json.loads((output / 'qualification-failure.json').read_text(encoding='ascii'))
        self.assertEqual(failure['phase'], 'saved_memory_segment_reading')
        self.assertEqual(failure['status'], 'failed')
        self.assertTrue(failure['synthetic_only'])

    def test_output_must_be_new_absolute_direct_private_local_path(self):
        with self.assertRaises(ValueError):
            qualification._validate_output(Path('relative-output'))
        existing = self.parent / 'existing'
        existing.mkdir(mode=0o700)
        with self.assertRaises(ValueError):
            qualification._validate_output(existing)
        with self.assertRaises(ValueError):
            qualification._windows_path_check(PureWindowsPath(r'\\server\share\out'), windows=False)
        alias = self.parent / 'alias'
        try:
            alias.symlink_to(self.parent, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest('symlinks unavailable for this account')
        with self.assertRaises(ValueError):
            qualification._validate_output(alias / 'new-output')

    def test_output_rejects_uri_query_and_fragment_markers_without_creating_siblings(self):
        query_component = self.parent / 'foo?mode=ro' / 'out'
        fragment_component = self.parent / 'foo' / 'out#fragment'
        for target in (query_component, fragment_component):
            with self.subTest(target=target.name):
                with self.assertRaises(ValueError):
                    qualification._validate_output(target)
                self.assertFalse(target.exists())
                self.assertFalse(target.parent.exists())

    def test_windows_reparse_attribute_is_rejected_by_parent_walk(self):
        fake_info = type('Info', (), {'st_file_attributes': 0x400,
                                      'st_mode': stat.S_IFDIR | 0o700})()
        with patch.object(qualification.Path, 'lstat', return_value=fake_info):
            with self.assertRaises(ValueError):
                qualification._require_direct_directory(self.parent)

    def test_failure_report_contains_only_phase_and_exception_class(self):
        output = self.parent / 'failed-output'
        with patch.object(qualification, '_seed_main',
                          side_effect=RuntimeError('synthetic transcript and credential must not escape')):
            with self.assertRaisesRegex(RuntimeError, 'synthetic transcript'):
                qualification.run(output)
        failure = json.loads((output / 'qualification-failure.json').read_text(encoding='ascii'))
        self.assertEqual(failure, {'status': 'failed', 'synthetic_only': True,
            'phase': 'migration', 'exception_class': 'RuntimeError', 'winerror': None})
        rendered = json.dumps(failure)
        self.assertNotIn('transcript', rendered)
        self.assertNotIn('credential', rendered)


if __name__ == '__main__':
    unittest.main()
