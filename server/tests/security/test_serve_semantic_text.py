"""Explicit private configuration and CLI dispatch; no listener or ML import."""
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import asdict
import io
import json
import logging
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'backend'), str(ROOT/'scripts')]
import serve_semantic_text as subject
from app.access.semantic_encoder import JointSpaceBinding
from app.access.visual_candidates import VectorSpaceIdentity


class ServeSemanticTextTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='semantic-text-configuration-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.root.chmod(0o700)
        self.config = self.root/'configuration.private.json'
        self.credential = self.root/'credential.private.json'
        self.credential.write_text(json.dumps({'token': 'synthetic_token_'+'t'*32}))
        self.credential.chmod(0o600)
        ident = VectorSpaceIdentity('a'*64, 'b'*64, 'synthetic-space', 'v1', 512, 'unit_l2')
        self.binding = JointSpaceBinding(ident, ident, 'c'*64)
        self.document = {'schema': 'photohouse.semantic_text_provider.v1',
            'architecture': 'ViT-B-32', 'device': 'cpu',
            'checkpoint': {'path': str(self.root/'weights.pt'), 'sha256': 'a'*64},
            'bpe': {'path': str(self.root/'bpe.gz'), 'sha256': 'd'*64},
            'package_versions': {name: '1.2.3' for name in subject.PACKAGES},
            'binding': asdict(self.binding), 'port': 8912, 'credential_file': str(self.credential)}
        self.write()

    def write(self):
        self.config.write_text(json.dumps(self.document))
        self.config.chmod(0o600)

    def test_probe_does_not_read_credential_and_serving_requires_private_credential(self):
        probe = subject.load_configuration(self.config)
        self.assertNotIn('bearer_token', probe)
        served = subject.load_configuration(self.config, serving=True)
        self.assertEqual(served['bearer_token'], 'synthetic_token_'+'t'*32)
        self.credential.unlink()
        self.assertIsNotNone(subject.load_configuration(self.config))
        with self.assertRaises(subject.ConfigurationError): subject.load_configuration(self.config, serving=True)

    def test_missing_binding_unknown_fields_and_mismatched_checkpoint_refuse_serve(self):
        for update in ({'binding': None}, {'unexpected': True}, {'port': True},
                       {'architecture': 'hf-hub:example'}, {'device': 'auto'}):
            with self.subTest(update=update):
                original = dict(self.document)
                self.document.update(update); self.write()
                with self.assertRaises(subject.ConfigurationError): subject.load_configuration(self.config, serving=True)
                self.document = original
        self.document['binding']['text_identity']['artifact_sha256'] = 'f'*64
        self.write()
        with self.assertRaises(subject.ConfigurationError): subject.load_configuration(self.config, serving=True)

    def test_private_json_duplicates_and_links_are_refused(self):
        self.config.write_text('{"schema":1,"schema":2}')
        with self.assertRaises(subject.ConfigurationError): subject.load_configuration(self.config)
        self.write()
        alias = self.root/'alias.json'; alias.symlink_to(self.config)
        with self.assertRaises(subject.ConfigurationError): subject.load_configuration(alias)
        self.config.chmod(0o644)
        if sys.platform != 'win32':
            with self.assertRaises(subject.ConfigurationError): subject.load_configuration(self.config)

    def test_model_files_inside_source_checkout_are_refused_without_opening_them(self):
        self.document['checkpoint']['path'] = str(ROOT/'weights.pt'); self.write()
        with self.assertRaises(subject.ConfigurationError): subject.load_configuration(self.config)

    def test_probe_cli_prints_only_receipt_and_never_binds_or_serves(self):
        fake = SimpleNamespace(probe=Mock(return_value={'relevance_measured': False}), bind=Mock())
        output, error = io.StringIO(), io.StringIO()
        before = logging.root.manager.disable
        with patch.object(subject, 'load_model', return_value=fake), redirect_stdout(output), redirect_stderr(error):
            result = subject.run(['probe', '--configuration', str(self.config)])
        self.assertEqual(result, 0)
        self.assertEqual(json.loads(output.getvalue()), {'relevance_measured': False})
        self.assertEqual(error.getvalue(), '')
        self.assertEqual(logging.root.manager.disable, before)
        fake.bind.assert_not_called()

    def test_serve_cli_only_binds_loopback_and_disables_proxy_and_access_logging(self):
        fake = SimpleNamespace(probe=Mock(return_value={}), bind=Mock())
        uvicorn = SimpleNamespace(run=Mock())
        with patch.object(subject, 'load_model', return_value=fake), patch.dict(sys.modules, {'uvicorn': uvicorn}), patch(
                'app.access.semantic_provider_transport.create_provider_app', return_value='synthetic-app'):
            result = subject.run(['serve', '--configuration', str(self.config)])
        self.assertEqual(result, 0)
        self.assertEqual(fake.bind.call_args.args, (self.binding,))
        arguments = uvicorn.run.call_args.kwargs
        self.assertEqual(arguments['host'], '127.0.0.1')
        self.assertFalse(arguments['proxy_headers'])
        self.assertFalse(arguments['access_log'])
        self.assertEqual(arguments['workers'], 1)

    def test_cli_failure_does_not_echo_path_or_credentials(self):
        error = io.StringIO()
        with patch.object(subject, 'load_model', side_effect=RuntimeError('private path and token')), redirect_stderr(error):
            result = subject.run(['probe', '--configuration', str(self.config)])
        self.assertEqual(result, 1)
        self.assertEqual(error.getvalue(), '{"error":"semantic_provider_unavailable"}\n')


if __name__ == '__main__': unittest.main()
