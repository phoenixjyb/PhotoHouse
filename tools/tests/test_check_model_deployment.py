"""The offline doctor must redact private values and perform no provider work."""
import builtins
from contextlib import redirect_stdout
import copy
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


class DeploymentDoctorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.private = Path(self.temp.name).resolve()
        self.private.chmod(0o700)
        self.path = self.private / 'synthetic-private-selection.json'
        self.doc = json.loads((ROOT / 'models/deployment.synthetic.json').read_text())
        self.doc['id'] = 'private-household-selection'
        self.doc['artifacts'][0]['model_name'] = 'private-asr-name'
        self.doc['providers'][0]['credential_env'] = 'PRIVATE_ASR_CREDENTIAL'
        self.write()
        spec = importlib.util.spec_from_file_location('deployment_doctor', ROOT / 'tools/check_model_deployment.py')
        self.doctor = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.doctor)

    def write(self):
        self.path.write_text(json.dumps(self.doc))
        self.path.chmod(0o600)

    def call(self, argv):
        output = io.StringIO()
        with redirect_stdout(output):
            code = self.doctor.main(argv)
        return code, output.getvalue()

    def test_success_outputs_digest_and_known_roles_only(self):
        with patch.dict(os.environ, {'PRIVATE_ASR_CREDENTIAL': 'private-credential-value'}):
            code, output = self.call(['--manifest', str(self.path), '--json'])
        self.assertEqual(code, 0)
        report = json.loads(output)
        self.assertEqual(report['status'], 'configuration_valid')
        self.assertFalse(report['runtime_probed'])
        self.assertFalse(report['activation_performed'])
        for value in (str(self.path), self.doc['id'], 'private-asr-name',
                      'PRIVATE_ASR_CREDENTIAL', 'private-credential-value', '19001', 'example.invalid'):
            self.assertNotIn(value, output)
        self.assertEqual(list(self.private.iterdir()), [self.path])

    def test_refusal_and_argument_errors_do_not_echo_values(self):
        self.doc['providers'][0]['endpoint'] = 'https://private.invalid/secret-token'
        self.write()
        for argv, reason in ((['--manifest', str(self.path), '--json'], 'invalid_local_endpoint'),
                             (['--manifest', str(self.path), '--token=private-secret'], 'invalid_arguments'),
                             ([], 'invalid_arguments'),
                             (['--manifest', str(self.private / 'private-missing')], 'private_manifest_unavailable')):
            code, output = self.call(argv)
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(output), {'status': 'refused', 'reason': reason})
            for value in ('private-secret', 'private.invalid', str(self.private)):
                self.assertNotIn(value, output)

    def test_verification_must_check_source_catalog_first(self):
        with patch.object(self.doctor.model_catalog, 'verify', side_effect=self.doctor.model_catalog.CatalogError('adapter_symbol_missing')):
            with patch.object(self.doctor, 'load_private_deployment') as reader:
                code, output = self.call(['--manifest', str(self.path), '--json'])
                reader.assert_not_called()
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output)['reason'], 'adapter_symbol_missing')

    def test_import_and_doctor_do_not_import_ml_or_network_or_start_processes(self):
        real_import = builtins.__import__
        blocked = {'torch', 'transformers', 'onnxruntime', 'requests', 'httpx', 'socket', 'subprocess'}
        def guarded_import(name, *args, **kwargs):
            if name.split('.')[0] in blocked or name in {'app.main', 'app.config'}:
                raise AssertionError('Forbidden provider/runtime import')
            return real_import(name, *args, **kwargs)
        with patch.object(builtins, '__import__', side_effect=guarded_import):
            spec = importlib.util.spec_from_file_location('isolated_doctor', ROOT / 'tools/check_model_deployment.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(module.main(['--manifest', str(self.path), '--json']), 0)

    def test_disabled_assistant_projection_is_redacted_and_does_not_enable_a_feature(self):
        code, output = self.call(['--manifest', str(self.path), '--project', 'assistant',
                                  '--platform', 'windows', '--json'])
        report = json.loads(output)
        self.assertEqual(code, 0)
        self.assertEqual(report['status'], 'projection_valid')
        self.assertEqual(report['projected_roles'], [])
        self.assertEqual(report['disabled_roles'], ['assistant_asr'])
        self.assertFalse(report['feature_flags_changed'])
        self.assertFalse(report['activation_performed'])

    def test_projection_flags_required_role_and_platform_are_explicit(self):
        for arguments, reason in ((['--platform', 'windows'], 'projection_target_required'),
                                   (['--feature-enabled'], 'projection_target_required'),
                                   (['--project', 'assistant'], 'target_platform_required'),
                                   (['--project', 'memory-contributions', '--platform', 'windows',
                                     '--feature-enabled'], 'required_binding_not_enabled')):
            code, output = self.call(['--manifest', str(self.path), '--json', *arguments])
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(output)['reason'], reason)

    def test_wsl_projection_uses_windows_host_and_redacts_instance(self):
        self.doc = json.loads((ROOT / 'models/deployment.wsl.synthetic.json').read_text())
        provider = self.doc['providers'][0]
        previous = copy.deepcopy(provider)
        previous['id'] += '-previous'
        previous['endpoint'] = previous['endpoint'].replace(':19001', ':19003')
        self.doc['providers'].append(previous)
        self.doc['bindings'][0]['enabled'] = True
        self.doc['rollback_bindings'].append({'role': 'assistant_asr', 'provider': previous['id'], 'enabled': True})
        self.write()
        args = ['--manifest', str(self.path), '--project', 'assistant', '--feature-enabled', '--json']
        code, output = self.call([*args, '--platform', 'windows'])
        self.assertEqual(code, 0)
        report = json.loads(output)
        self.assertEqual(report['host_platform'], 'windows')
        self.assertEqual(report['execution_platforms'], {'assistant_asr': 'linux'})
        self.assertEqual(report['placement_kinds'], {'assistant_asr': 'wsl2'})
        self.assertNotIn('Synthetic-Ubuntu', output)
        self.assertFalse(report['runtime_probed'])
        code, output = self.call([*args, '--platform', 'linux'])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output)['reason'], 'runtime_platform_mismatch')

    def test_active_projection_checks_opt_in_without_reading_credential_values(self):
        provider = self.doc['providers'][0]
        previous = copy.deepcopy(provider)
        previous['id'] += '-previous'
        previous['endpoint'] = previous['endpoint'].replace(':19001', ':19003')
        self.doc['providers'].append(previous)
        self.doc['bindings'][0]['enabled'] = True
        self.doc['rollback_bindings'].append({'role': 'assistant_asr', 'provider': previous['id'], 'enabled': True})
        self.write()
        args = ['--manifest', str(self.path), '--project', 'assistant', '--platform', 'windows', '--json']
        code, output = self.call(args)
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output)['reason'], 'feature_opt_in_required')
        with patch.dict(os.environ, {'PRIVATE_ASR_CREDENTIAL': 'ambient-private-secret'}):
            with patch.object(self.doctor, 'load_private_deployment', wraps=self.doctor.load_private_deployment):
                code, output = self.call([*args, '--feature-enabled'])
        self.assertEqual(code, 0)
        report = json.loads(output)
        self.assertEqual(report['projected_roles'], ['assistant_asr'])
        self.assertEqual(report['request_timeouts_seconds'], {'assistant_asr': 45})
        self.assertFalse(report['credential_values_included'])
        for value in ('ambient-private-secret', 'PRIVATE_ASR_CREDENTIAL', 'private-asr-name', '19001'):
            self.assertNotIn(value, output)

    def test_title_projection_is_selectable_and_reports_only_its_bounded_role(self):
        binding = next(b for b in self.doc['bindings'] if b['role'] == 'title_suggestions')
        binding['enabled'] = True
        provider = next(p for p in self.doc['providers'] if p['role'] == 'title_suggestions')
        previous = copy.deepcopy(provider)
        previous['id'] += '-previous'
        previous['endpoint'] = previous['endpoint'].replace(':19002', ':19003')
        self.doc['providers'].append(previous)
        self.doc['rollback_bindings'].append({
            'role': 'title_suggestions', 'provider': previous['id'], 'enabled': True})
        self.write()
        common = ['--manifest', str(self.path), '--project', 'story-titles',
                  '--platform', 'windows', '--json']
        code, output = self.call(common)
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output), {'status': 'refused', 'reason': 'feature_opt_in_required'})
        code, output = self.call([*common[:-1], '--feature-enabled', '--json'])
        self.assertEqual(code, 0)
        report = json.loads(output)
        self.assertEqual(report['status'], 'projection_valid')
        self.assertEqual(report['target'], 'story-titles')
        self.assertEqual(report['projected_roles'], ['title_suggestions'])
        self.assertEqual(report['request_timeouts_seconds'], {'title_suggestions': 30})
        self.assertFalse(report['credential_values_included'])
        self.assertFalse(report['activation_performed'])
        for value in (str(self.path), self.doc['id'], 'synthetic-language', '19002'):
            self.assertNotIn(value, output)


if __name__ == '__main__':
    unittest.main()
