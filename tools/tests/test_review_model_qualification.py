"""Portable private worksheets only mutate pinned human-review fields."""
import builtins
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def _module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReviewQualificationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.private = Path(temp.name).resolve()
        self.private.chmod(0o700)
        helper = _module('review_qualification_fixture', ROOT / 'server/tests/security/test_model_qualification.py')
        self.catalog, self.manifest, self.deployment, self.plan, self.inputs, self.evidence = helper.synthetic_fixture(self.private)
        for record in self.evidence['records']:
            for quality in record['quality']:
                quality['criteria'] = {key: 'unreviewed' for key in quality['criteria']}
                quality['reviewed_by'] = None
                quality['reviewed_at'] = None
        now = datetime.now(timezone.utc).replace(microsecond=0)
        self.evidence['started_at'] = (now - timedelta(minutes=4)).strftime('%Y-%m-%dT%H:%M:%SZ')
        self.evidence['ended_at'] = (now - timedelta(minutes=3)).strftime('%Y-%m-%dT%H:%M:%SZ')
        for name, value in (('manifest', self.manifest), ('evidence', self.evidence), ('inputs', self.inputs)):
            path = self.private / f'{name}.json'
            self.write_json(path, value)
            self.paths = getattr(self, 'paths', {})
            self.paths[name] = path
        self.module = _module('review_model_qualification', ROOT / 'tools/review_model_qualification.py')

    def write_json(self, path, value):
        path.write_text(json.dumps(value), encoding='utf-8')
        path.chmod(0o600)

    def call(self, *arguments):
        output = io.StringIO()
        with redirect_stdout(output):
            code = self.module.main(list(arguments))
        return code, json.loads(output.getvalue())

    def args(self, command, output, *, evidence=None, audio=True):
        values = [command, '--manifest', str(self.paths['manifest']), '--evidence',
                  str(evidence or self.paths['evidence'])]
        if audio:
            values += ['--audio-inputs', str(self.paths['inputs'])]
        values += ['--output', str(output)]
        return values

    def export(self, name='worksheet.json'):
        path = self.private / name
        code, report = self.call(*self.args('export', path))
        self.assertEqual(code, 0, report)
        return path, report

    def test_export_is_private_pinned_and_all_unreviewed(self):
        output, report = self.export()
        worksheet = json.loads(output.read_text())
        self.assertEqual(worksheet['kind'], 'photohouse-model-review-worksheet')
        self.assertEqual(len(worksheet['records']), 12)
        self.assertTrue(all(item['reviewed_by'] is None and item['reviewed_at'] is None
                            for item in worksheet['records']))
        self.assertTrue(all(criterion['verdict'] == 'unreviewed'
                            for item in worksheet['records'] for criterion in item['criteria']))
        self.assertTrue(all({'input_sha256', 'output_sha256'} <= set(item)
                            for item in worksheet['records']))
        self.assertIn('selection_identities', worksheet)
        for private_value in (str(self.private), 'private-reviewer', 'synthetic-case.wav', 'example.invalid'):
            self.assertNotIn(private_value, json.dumps(report))
        self.assertEqual(report['status'], 'review_worksheet_exported')
        self.assertFalse(report['activation_performed'])
        if os.name != 'nt':
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)

    def test_title_review_rows_are_title_specific_and_remain_separate_from_narrative(self):
        output, _ = self.export('title-review.json')
        worksheet = json.loads(output.read_text())
        title_rows = [row for row in worksheet['records'] if row['role'] == 'title_suggestions']
        narrative_rows = [row for row in worksheet['records'] if row['role'] == 'narrative']
        self.assertEqual({row['case_id'] for row in title_rows},
                         {'synthetic-title-family', 'synthetic-title-uncertainty',
                          'synthetic-title-abstention'})
        self.assertEqual(3, len(narrative_rows))
        self.assertEqual({'title_grounded', 'exact_title_citations', 'title_language_fit',
                          'title_review_required'},
                         {criterion['id'] for row in title_rows
                          if row['case_id'] == 'synthetic-title-family'
                          for criterion in row['criteria']})
        abstention = next(row for row in title_rows if row['case_id'] == 'synthetic-title-abstention')
        self.assertIn('title_abstains_without_sources',
                      {criterion['id'] for criterion in abstention['criteria']})
        narrative_criteria = {'grounded_facts', 'exact_citations', 'attribution_uncertainty',
                              'coherent_chapters', 'no_withheld_sources'}
        self.assertTrue(all(criterion['id'] not in narrative_criteria
                            for row in title_rows for criterion in row['criteria']))

    def test_import_changes_only_review_fields_and_keeps_failed_incomplete(self):
        worksheet_path, _ = self.export()
        original = deepcopy(self.evidence)
        original['records'][0]['resources'] = None  # structurally valid but incomplete evidence
        source = self.private / 'incomplete-evidence.json'
        self.write_json(source, original)
        # This worksheet binds to the evidence digest, so re-export from that
        # exact source before importing the judgments.
        worksheet_path.unlink()
        worksheet_path, _ = self.export_from(source, 'incomplete-review.json')
        worksheet = json.loads(worksheet_path.read_text())
        worksheet['records'][0]['criteria'][0]['verdict'] = 'failed'
        worksheet['records'][0]['reviewed_by'] = 'reviewer-private'
        worksheet['records'][0]['reviewed_at'] = datetime.now(timezone.utc).replace(microsecond=0).strftime('%Y-%m-%dT%H:%M:%SZ')
        worksheet['records'][1]['criteria'][0]['verdict'] = 'passed'
        worksheet['records'][1]['reviewed_by'] = 'reviewer-private'
        worksheet['records'][1]['reviewed_at'] = worksheet['records'][0]['reviewed_at']
        self.write_json(worksheet_path, worksheet)
        source_bytes = source.read_bytes()
        result_path = self.private / 'reviewed-evidence.json'
        code, report = self.call(*self.args('import', result_path, evidence=source) + ['--worksheet', str(worksheet_path)])
        self.assertEqual(code, 0, report)
        self.assertEqual(source.read_bytes(), source_bytes)
        result = json.loads(result_path.read_text())
        self.assertIsNone(result['records'][0]['resources'])
        self.assertEqual(result['records'][0]['observed_identity'], original['records'][0]['observed_identity'])
        first = result['records'][0]['quality'][0]
        self.assertIn('failed', first['criteria'].values())
        second = result['records'][0]['quality'][1]
        self.assertIn('passed', second['criteria'].values())
        self.assertIn('unreviewed', second['criteria'].values())
        self.assertEqual(report['status'], 'qualification_evidence_written')
        for private_value in (str(self.private), 'reviewer-private', 'example.invalid'):
            self.assertNotIn(private_value, json.dumps(report))

    def export_from(self, evidence, name):
        output = self.private / name
        code, report = self.call(*self.args('export', output, evidence=evidence))
        self.assertEqual(code, 0, report)
        return output, report

    def test_import_refuses_modified_inventory_hash_definitions_and_fields(self):
        base, _ = self.export()
        cases = []
        value = json.loads(base.read_text())
        value['records'][0]['output_sha256'] = '0' * 64
        cases.append(('hash', value))
        value = json.loads(base.read_text())
        value['records'].append(deepcopy(value['records'][0]))
        cases.append(('duplicate', value))
        value = json.loads(base.read_text())
        value['records'][0]['unexpected'] = True
        cases.append(('extra', value))
        value = json.loads(base.read_text())
        value['records'][0]['criteria'].pop()
        cases.append(('missing-criterion', value))
        value = json.loads(base.read_text())
        value['records'][0]['criteria'][0]['definition'] = 'changed private rubric'
        cases.append(('rubric', value))
        value = json.loads(base.read_text())
        value['schema'] = True
        cases.append(('boolean-schema', value))
        value = json.loads(base.read_text())
        value['schema'] = 1.0
        cases.append(('float-schema', value))
        for name, worksheet in cases:
            with self.subTest(name=name):
                path = self.private / f'{name}.json'
                self.write_json(path, worksheet)
                output = self.private / f'{name}-out.json'
                code, report = self.call(*self.args('import', output) + ['--worksheet', str(path)])
                self.assertEqual(code, 1)
                self.assertEqual(report['status'], 'refused')
                self.assertFalse(output.exists())

    def test_import_requires_explicit_review_boundary_and_current_source(self):
        worksheet_path, _ = self.export()
        for mutate, reason in (
            (lambda item: item.update(extra=True), 'worksheet_record_fields'),
            (lambda item: (item['criteria'][0].update(verdict='passed')), 'worksheet_reviewer_required'),
            (lambda item: (item.update(reviewed_by='reviewer'),), 'worksheet_reviewer_required'),
            (lambda item: (item.update(reviewed_by='reviewer', reviewed_at='2099-01-01T00:00:00Z'),
                           item['criteria'][0].update(verdict='passed')), 'qualification_input_invalid'),
        ):
            with self.subTest(reason=reason):
                worksheet = json.loads(worksheet_path.read_text())
                mutate(worksheet['records'][0])
                path = self.private / f'mutation-{len(list(self.private.glob("mutation-*")))}.json'
                self.write_json(path, worksheet)
                output = self.private / f'{path.stem}-out.json'
                code, report = self.call(*self.args('import', output) + ['--worksheet', str(path)])
                self.assertEqual(code, 1)
                self.assertEqual(report['reason'], reason)
                self.assertFalse(output.exists())
        changed = deepcopy(self.evidence)
        changed['records'][0]['quality'][0]['output_sha256'] = 'd' * 64
        changed_path = self.private / 'changed-source.json'
        self.write_json(changed_path, changed)
        output = self.private / 'stale-out.json'
        code, report = self.call(*self.args('import', output, evidence=changed_path) + ['--worksheet', str(worksheet_path)])
        self.assertEqual(code, 1)
        self.assertEqual(report['reason'], 'worksheet_source_mismatch')
        self.assertFalse(output.exists())

    def test_export_refuses_missing_asr_inventory_existing_review_and_output(self):
        output = self.private / 'no-audio.json'
        code, report = self.call(*self.args('export', output, audio=False))
        self.assertEqual(code, 1)
        self.assertEqual(report['reason'], 'audio_inputs_required')
        self.assertFalse(output.exists())
        reviewed = deepcopy(self.evidence)
        reviewed['records'][0]['quality'][0]['criteria']['mandarin_fidelity'] = 'failed'
        reviewed['records'][0]['quality'][0]['reviewed_by'] = 'reviewer-private'
        reviewed['records'][0]['quality'][0]['reviewed_at'] = datetime.now(timezone.utc).replace(microsecond=0).strftime('%Y-%m-%dT%H:%M:%SZ')
        reviewed_path = self.private / 'already-reviewed.json'
        self.write_json(reviewed_path, reviewed)
        code, report = self.call(*self.args('export', self.private / 'should-not-exist.json', evidence=reviewed_path))
        self.assertEqual(code, 1)
        self.assertEqual(report['reason'], 'source_review_already_present')
        existing = self.private / 'existing.json'
        existing.write_text('preserve', encoding='utf-8')
        code, report = self.call(*self.args('export', existing))
        self.assertEqual(code, 1)
        self.assertEqual(existing.read_text(), 'preserve')

    def test_malformed_source_json_types_refuse_without_traceback_or_output(self):
        for index, value in enumerate(([], None, 'scalar', 3)):
            with self.subTest(value=value):
                path = self.private / f'malformed-{index}.json'
                self.write_json(path, value)
                output = self.private / f'malformed-{index}-out.json'
                code, report = self.call(*self.args('export', output, evidence=path))
                self.assertEqual(code, 1)
                self.assertEqual(report, {'status': 'refused', 'reason': 'qualification_input_invalid'})
                self.assertFalse(output.exists())

    def test_privacy_is_checked_before_payload_write_and_refusal_leaves_no_output(self):
        output = self.private / 'privacy-order.json'
        original = self.module.require_private_file
        observed = []

        def inspect_empty_file(path):
            observed.append((Path(path).exists(), Path(path).stat().st_size))
            return original(path)

        with patch.object(self.module, 'require_private_file', side_effect=inspect_empty_file):
            code, report = self.call(*self.args('export', output))
        self.assertEqual(code, 0, report)
        self.assertEqual(observed, [(True, 0)])

        refused = self.private / 'privacy-refused.json'

        def reject_empty_file(path):
            self.assertEqual(Path(path).stat().st_size, 0)
            raise ValueError('private ACL rejected')

        with patch.object(self.module, 'require_private_file', side_effect=reject_empty_file):
            code, report = self.call(*self.args('export', refused))
        self.assertEqual(code, 1)
        self.assertEqual(report['reason'], 'output_private_storage')
        self.assertFalse(refused.exists())

    def test_symlink_target_parent_and_nonprivate_parent_preserve_neighbors(self):
        protected = self.private / 'protected.json'
        protected.write_text('keep target', encoding='utf-8')
        protected.chmod(0o600)
        target_link = self.private / 'target-link.json'
        target_link.symlink_to(protected)
        code, report = self.call(*self.args('export', target_link))
        self.assertEqual(code, 1)
        self.assertEqual(protected.read_text(), 'keep target')
        self.assertTrue(target_link.is_symlink())

        parent = self.private / 'real-parent'
        parent.mkdir(mode=0o700)
        sentinel = parent / 'sentinel.txt'
        sentinel.write_text('keep neighbor', encoding='utf-8')
        sentinel.chmod(0o600)
        parent_link = self.private / 'linked-parent'
        parent_link.symlink_to(parent, target_is_directory=True)
        output = parent_link / 'should-not-exist.json'
        code, report = self.call(*self.args('export', output))
        self.assertEqual(code, 1)
        self.assertEqual(sentinel.read_text(), 'keep neighbor')
        self.assertFalse((parent / output.name).exists())

        public_parent = self.private / 'nonprivate-parent'
        public_parent.mkdir(mode=0o755)
        public_parent.chmod(0o755)
        public_sentinel = public_parent / 'sentinel.txt'
        public_sentinel.write_text('keep public sibling', encoding='utf-8')
        public_sentinel.chmod(0o600)
        output = public_parent / 'should-not-exist.json'
        code, report = self.call(*self.args('export', output))
        self.assertEqual(code, 1)
        self.assertEqual(report['reason'], 'output_private_storage')
        self.assertEqual(public_sentinel.read_text(), 'keep public sibling')
        self.assertFalse(output.exists())

    def test_output_location_redaction_and_forbidden_imports(self):
        for path in (ROOT / 'inside-checkout.json', self.private / 'missing-parent' / 'out.json'):
            code, report = self.call(*self.args('export', path))
            self.assertEqual(code, 1)
            self.assertEqual(report['status'], 'refused')
        original = builtins.__import__
        blocked = {'torch', 'transformers', 'onnxruntime', 'requests', 'httpx', 'socket', 'subprocess'}

        def guarded(name, *args, **kwargs):
            if name.split('.')[0] in blocked or name in {'app.main', 'app.config'}:
                raise AssertionError(f'Forbidden runtime import: {name}')
            return original(name, *args, **kwargs)

        with patch.object(builtins, '__import__', side_effect=guarded):
            module = _module('isolated_review_model_qualification', ROOT / 'tools/review_model_qualification.py')
            output = self.private / 'isolated.json'
            with redirect_stdout(io.StringIO()):
                self.assertEqual(module.main(self.args('export', output)), 0)


if __name__ == '__main__':
    unittest.main()
