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


if __name__ == '__main__':
    unittest.main()
