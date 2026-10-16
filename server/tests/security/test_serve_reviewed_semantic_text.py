"""Private reviewed-provider configuration and explicit CLI lifecycle, without ML."""
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import asdict, replace
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
import serve_reviewed_semantic_text as subject
from semantic_reviewed_projection import ReviewedProjection, composition_recipe, reviewed_document_sha256
from app.access.semantic_encoder import JointSpaceBinding
from app.access.visual_candidates import VectorSpaceIdentity


class ModelStandIn:
    def __init__(self):
        self.binding = None
        self.bind_calls = []
    def bind(self, value):
        self.binding = value
        self.bind_calls.append(value)
    def probe(self):
        return {'schema': 'synthetic-inner-probe', 'relevance_measured': False}
    def encode(self, query, **kwargs):
        raise AssertionError('No query encode belongs in CLI lifecycle checks')


class ServeReviewedSemanticTextTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='reviewed-provider-configuration-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve(); self.root.chmod(0o700)
        self.config = self.root/'provider.private.json'
        self.encoder_file = self.root/'encoder.private.json'
        self.projection_file = self.root/'projection.private.json'
        self.credential_file = self.root/'credential.private.json'
        ident = VectorSpaceIdentity('a'*64, 'b'*64, 'synthetic-reviewed-space', 'text-v1', 512, 'unit_l2')
        self.inner_binding = JointSpaceBinding(replace(ident, preprocessing_sha256='d'*64), ident, 'c'*64)
        self.encoder = {'schema': 'photohouse.semantic_text_provider.v1',
            'architecture': 'ViT-B-32', 'device': 'cpu',
            'checkpoint': {'path': str(self.root/'weights.pt'), 'sha256': 'a'*64},
            'bpe': {'path': str(self.root/'bpe.gz'), 'sha256': 'e'*64},
            'package_versions': {name: '1.2.3' for name in subject.direct.PACKAGES},
            'binding': asdict(self.inner_binding), 'port': 8912, 'credential_file': None}
        self.projection = {'schema': 'photohouse.reviewed_scene_projection.v1',
            'policy': 'exact_reviewed_only',
            'review': {'status': 'operator_reviewed', 'reference_sha256': '5'*64},
            'entries': [{'original': '请找轻松场景', 'model_input': 'people relaxing together'}]}
        projection = ReviewedProjection(self.projection, expected_sha256=reviewed_document_sha256(self.projection))
        digest, _ = subject.implementation_receipt()
        recipe = composition_recipe(self.inner_binding, projection, digest)
        self.outer_binding = JointSpaceBinding(self.inner_binding.image_identity,
            replace(ident, preprocessing_sha256=recipe['recipe_sha256']), 'f'*64)
        self.document = {'schema': 'photohouse.reviewed_semantic_text_provider.v1',
            'encoder_configuration': {'path': str(self.encoder_file),
                'document_sha256': subject.document_sha256(self.encoder)},
            'projection': {'path': str(self.projection_file),
                'document_sha256': reviewed_document_sha256(self.projection)},
            'binding': asdict(self.outer_binding), 'port': 8915,
            'credential_file': str(self.credential_file)}
        self.write(self.encoder_file, self.encoder)
        self.write(self.projection_file, self.projection)
        self.write(self.credential_file, {'token': 'synthetic_reviewed_token_'+'t'*32})
        self.write_config()

    def write(self, path, value):
        path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
        path.chmod(0o600)
    def write_config(self):
        self.write(self.config, self.document)
    def invoke(self, operation):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            result = subject.run([operation, '--configuration', str(self.config)])
        return result, out.getvalue(), err.getvalue()

    def test_plan_has_no_private_reads_model_or_listener_work(self):
        output = io.StringIO()
        with patch.object(subject, '_load_private_document', side_effect=AssertionError), patch.object(
                subject.direct, 'load_model', side_effect=AssertionError), redirect_stdout(output):
            self.assertEqual(subject.run([]), 0)
        result = json.loads(output.getvalue())
        self.assertFalse(result['execution_performed'])
        self.assertFalse(result['activation_performed'])
        self.assertEqual(result['policy'], 'exact_reviewed_only')

    def test_configuration_uses_one_verified_snapshot_of_each_reference(self):
        original = subject._load_private_document
        with patch.object(subject, '_load_private_document', wraps=original) as reader:
            value = subject.load_configuration(self.config)
        self.assertEqual([str(x.args[0]) for x in reader.call_args_list],
                         [str(self.config), str(self.encoder_file), str(self.projection_file)])
        self.assertEqual(value['encoder']['binding'], self.inner_binding)
        self.assertNotIn('bearer_token', value)
        snapshot = subject.direct.configuration_document(self.encoder)
        self.encoder['checkpoint']['path'] = '/changed'
        self.encoder['package_versions']['torch'] = 'changed'
        self.assertNotEqual(snapshot['checkpoint']['path'], '/changed')
        self.assertNotEqual(snapshot['package_versions']['torch'], 'changed')

    def test_modified_references_and_automatic_review_status_refuse_before_model_loading(self):
        baseline = json.loads(json.dumps(self.document))
        mutations = [lambda: self.document['projection'].update(document_sha256='9'*64),
            lambda: self.document['encoder_configuration'].update(document_sha256='9'*64),
            lambda: self.document.update(extra='private text'),
            lambda: self.document.update(port=True)]
        for mutation in mutations:
            self.document = json.loads(json.dumps(baseline)); mutation(); self.write_config()
            with self.subTest(document=self.document), patch.object(subject.direct, 'load_model') as model:
                code, out, err = self.invoke('serve')
                self.assertEqual(code, 1); self.assertEqual(out, '')
                self.assertEqual(err, '{"error":"reviewed_semantic_provider_unavailable"}\n')
                model.assert_not_called()
        self.document = baseline
        self.projection['review']['status'] = 'model_approved'
        self.write(self.projection_file, self.projection)
        self.document['projection']['document_sha256'] = subject.document_sha256(self.projection)
        self.write_config()
        with self.assertRaises(subject.ReviewedConfigurationError): subject.load_configuration(self.config)

    def test_private_reference_links_duplicate_json_and_source_paths_are_refused(self):
        self.config.write_text('{"schema":1,"schema":2}')
        with self.assertRaises(subject.ReviewedConfigurationError): subject.load_configuration(self.config)
        self.write_config()
        link = self.root/'alias.json'; link.symlink_to(self.projection_file)
        self.document['projection']['path'] = str(link); self.write_config()
        with self.assertRaises(subject.ReviewedConfigurationError): subject.load_configuration(self.config)
        self.document['projection']['path'] = str(self.projection_file); self.write_config()
        with self.assertRaises(subject.ReviewedConfigurationError):
            subject.load_configuration(self.config, source_root=self.root)
        if sys.platform != 'win32':
            self.projection_file.chmod(0o644)
            with self.assertRaises(subject.ReviewedConfigurationError): subject.load_configuration(self.config)

    def test_probe_needs_no_outer_binding_or_credential_and_exposes_no_reviewed_text(self):
        self.document['binding'] = None; self.write_config(); self.credential_file.unlink()
        model = ModelStandIn()
        before = logging.root.manager.disable
        with patch.object(subject.direct, 'load_model', return_value=model):
            code, out, err = self.invoke('probe')
        self.assertEqual(code, 0); self.assertEqual(err, '')
        self.assertEqual(model.bind_calls, [self.inner_binding])
        self.assertEqual(logging.root.manager.disable, before)
        probe = json.loads(out)
        self.assertFalse(probe['binding_present'])
        self.assertFalse(probe['activation_approved'])
        self.assertFalse(probe['semantic_faithfulness_automatically_verified'])
        for private in ('请找轻松场景', 'people relaxing together', str(self.root), 'synthetic_reviewed_token_'):
            self.assertNotIn(private, out)
        with patch.object(subject.direct, 'load_model') as loader:
            self.assertEqual(self.invoke('serve')[0], 1)
            loader.assert_not_called()

    def test_wrong_composite_identity_or_reused_qualification_refuses_before_model(self):
        for binding in (self.inner_binding, replace(self.outer_binding,
                qualification_sha256=self.inner_binding.qualification_sha256),
                replace(self.outer_binding, image_identity=replace(self.outer_binding.image_identity,
                                                                  preprocessing_sha256='8'*64))):
            with self.subTest(binding=binding):
                self.document['binding'] = asdict(binding); self.write_config()
                with patch.object(subject.direct, 'load_model') as loader:
                    code, out, err = self.invoke('serve')
                    self.assertEqual(code, 1); self.assertEqual(out, '')
                    self.assertEqual(err, '{"error":"reviewed_semantic_provider_unavailable"}\n')
                    loader.assert_not_called()

    def test_adapter_source_change_invalidates_binding_before_model_load(self):
        with patch.object(subject, 'implementation_receipt', return_value=('0'*64, ())), patch.object(
                subject.direct, 'load_model') as loader:
            code, out, err = self.invoke('serve')
        self.assertEqual(code, 1); self.assertEqual(out, '')
        self.assertEqual(err, '{"error":"reviewed_semantic_provider_unavailable"}\n')
        loader.assert_not_called()

    def test_serve_uses_existing_authenticated_transport_and_loopback_limits(self):
        model = ModelStandIn(); uvicorn = SimpleNamespace(run=Mock())
        with patch.object(subject.direct, 'load_model', return_value=model), patch.dict(
                sys.modules, {'uvicorn': uvicorn}), patch(
                'app.access.semantic_provider_transport.create_provider_app', return_value='synthetic-app') as app:
            code, out, err = self.invoke('serve')
        self.assertEqual((code, out, err), (0, '', ''))
        self.assertEqual(model.bind_calls, [self.inner_binding])
        provider = app.call_args.args[0]
        self.assertEqual(provider.binding, self.outer_binding)
        self.assertEqual(app.call_args.kwargs['bearer_token'], 'synthetic_reviewed_token_'+'t'*32)
        args = uvicorn.run.call_args.kwargs
        self.assertEqual(args['host'], '127.0.0.1'); self.assertEqual(args['workers'], 1)
        self.assertFalse(args['proxy_headers']); self.assertFalse(args['access_log'])
        self.assertEqual(args['limit_concurrency'], 8)

    def test_model_diagnostics_and_failures_do_not_escape_cli(self):
        def fail(_config):
            print('private model diagnostic', file=sys.stderr)
            raise RuntimeError('private path and token')
        with patch.object(subject.direct, 'load_model', side_effect=fail):
            code, out, err = self.invoke('probe')
        self.assertEqual(code, 1); self.assertEqual(out, '')
        self.assertEqual(err, '{"error":"reviewed_semantic_provider_unavailable"}\n')


if __name__ == '__main__': unittest.main()
