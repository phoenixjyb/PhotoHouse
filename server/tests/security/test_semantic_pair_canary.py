"""Canary admission is private and explicit; generated inputs need no model."""
from contextlib import redirect_stderr, redirect_stdout, nullcontext
import io
import json
import logging
import os
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'backend'), str(ROOT/'scripts')]
import qualify_semantic_pair as subject
from semantic_openclip import PACKAGES


class PairCanaryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='pair-canary-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.root.chmod(0o700)
        self.provider = self.root/'provider.json'
        self.pair = self.root/'pair.json'
        provider = {'schema': 'photohouse.semantic_text_provider.v1',
            'architecture': 'ViT-B-32', 'device': 'cpu',
            'checkpoint': {'path': str(self.root/'weights.pt'), 'sha256': 'a'*64},
            'bpe': {'path': str(self.root/'vocabulary.gz'), 'sha256': 'b'*64},
            'package_versions': {name: '1.2.3' for name in PACKAGES},
            'binding': None, 'port': 8912, 'credential_file': None}
        self.provider.write_text(json.dumps(provider)); self.provider.chmod(0o600)
        self.document = {'schema': 'photohouse.semantic_pair_canary.v1',
            'provider_configuration': str(self.provider),
            'image_package_versions': {name: '1.2.3' for name in subject.IMAGE_PACKAGES}}
        self.write()

    def write(self):
        self.pair.write_text(json.dumps(self.document)); self.pair.chmod(0o600)

    def test_plan_only_does_not_read_configuration_or_load_optional_packages(self):
        output = io.StringIO()
        with patch.object(subject, 'configuration', side_effect=AssertionError), patch.object(
                subject, 'load_model', side_effect=AssertionError), redirect_stdout(output):
            self.assertEqual(subject.run([]), 0)
        value = json.loads(output.getvalue())
        self.assertEqual(value['queries'], 8)
        self.assertFalse(value['models_loaded'])

    def test_exact_private_configuration_and_versions_are_required(self):
        self.assertEqual(subject.configuration(self.pair)[0], self.document)
        for update in ({'unknown': True}, {'schema': 1}, {'image_package_versions': {}},
                       {'provider_configuration': 'relative.json'}):
            with self.subTest(update=update):
                before = dict(self.document); self.document.update(update); self.write()
                with self.assertRaises(ValueError): subject.configuration(self.pair)
                self.document = before
        self.write(); self.pair.write_text('{"schema":1,"schema":2}')
        with self.assertRaises(ValueError): subject.configuration(self.pair)

    def test_existing_output_and_source_location_refuse_before_model_load(self):
        target = self.root/'exists'; target.mkdir(mode=0o700)
        factory = Mock(side_effect=AssertionError)
        for selected in (target, ROOT/'new-pair-output', Path('relative-output')):
            with self.subTest(path=selected), patch.object(subject, 'version', return_value='1.2.3'):
                with self.assertRaises(ValueError): subject.execute(self.pair, selected, model_factory=factory)
        factory.assert_not_called()

    def test_version_drift_precedes_output_creation(self):
        output = self.root/'output'
        with patch.object(subject, 'version', return_value='9.9.9'):
            with self.assertRaises(ValueError): subject.execute(self.pair, output)
        self.assertFalse(output.exists())

    def test_symlink_configuration_and_parent_are_refused(self):
        alias = self.root/'alias'; alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError): subject.configuration(alias/'pair.json')
        with self.assertRaises(ValueError): subject.output_target(alias/'output')

    def test_generated_images_are_deterministic_bounded_and_visually_distinct(self):
        hashes = set(); plan = subject.case_plan()
        for item in plan['images']:
            first, digest = subject.render_case(item, plan['rendering'])
            second, repeated = subject.render_case(item, plan['rendering'])
            try:
                self.assertEqual((first.mode, first.size), ('RGB', (256, 256)))
                self.assertEqual(digest, repeated)
                self.assertEqual(first.tobytes(), second.tobytes())
                self.assertGreater(first.getpixel((0, 0))[0], 250)
                self.assertNotEqual(first.getpixel((128, 128)), first.getpixel((0, 0)))
                hashes.add(digest)
            finally:
                first.close(); second.close()
        self.assertEqual(len(hashes), 4)

    def test_execution_reserves_once_writes_measurement_and_does_not_bind(self):
        model = Mock(); measure = Mock(return_value={'metrics': {'synthetic_only': True}})
        factory = Mock(return_value=model); output = self.root/'run'
        with patch.object(subject, 'version', return_value='1.2.3'):
            result = subject.execute(self.pair, output, model_factory=factory, measure_fn=measure)
            self.assertEqual(result['status'], 'synthetic_pair_measured')
            self.assertFalse(result['pair_binding_created'])
            self.assertEqual(json.loads((output/'measurement.json').read_text())['metrics'], {'synthetic_only': True})
            with self.assertRaises(ValueError): subject.execute(self.pair, output, model_factory=factory)
        self.assertEqual(factory.call_count, 1)
        model.bind.assert_not_called()

    def test_cli_failure_redacts_provider_details_and_restores_logging(self):
        output, error = io.StringIO(), io.StringIO(); before = logging.root.manager.disable
        with patch.object(subject, 'execute', side_effect=RuntimeError('PRIVATE MODEL PATH')), redirect_stdout(output), redirect_stderr(error):
            self.assertEqual(subject.run(['--run', '--configuration', str(self.pair), '--output-directory', str(self.root/'out')]), 1)
        self.assertEqual(output.getvalue(), '')
        self.assertEqual(json.loads(error.getvalue()), {'error': 'semantic_pair_canary_unavailable'})
        self.assertEqual(logging.root.manager.disable, before)

    def test_execution_failure_leaves_started_evidence_and_never_overwrites(self):
        output = self.root/'failed'
        with patch.object(subject, 'version', return_value='1.2.3'):
            with self.assertRaises(RuntimeError):
                subject.execute(self.pair, output, model_factory=Mock(side_effect=RuntimeError))
        self.assertTrue((output/'started.json').exists())
        self.assertFalse((output/'measurement.json').exists())

    def test_python_and_native_dependency_diagnostics_do_not_reach_cli(self):
        def fail(*args):
            print('PRIVATE PYTHON PATH')
            os.write(1, b'PRIVATE NATIVE PATH')
            os.write(2, b'PRIVATE NATIVE ERROR')
            raise RuntimeError('PRIVATE DETAILS')
        output, error = io.StringIO(), io.StringIO()
        with patch.object(subject, 'execute', side_effect=fail), redirect_stdout(output), redirect_stderr(error):
            self.assertEqual(subject.run(['--run', '--configuration', str(self.pair), '--output-directory', str(self.root/'out')]), 1)
        self.assertEqual(output.getvalue(), '')
        self.assertEqual(json.loads(error.getvalue()), {'error': 'semantic_pair_canary_unavailable'})

    def test_measure_uses_one_model_all_cases_eval_preprocessing_and_normalized_vectors(self):
        plan = subject.case_plan()
        def vector(index, scale=1.0):
            result = [0.0]*512; result[index] = scale; return result
        class Tensor:
            shape = (1, 3, 224, 224)
            def unsqueeze(self, dimension): return self
            def to(self, **kwargs): return self
        class Output:
            shape = (1, 512)
            def __init__(self, values): self.values = values
            def detach(self): return self
            def to(self, **kwargs): return self
            def __getitem__(self, index): return self
            def tolist(self): return self.values
        encode = Mock(side_effect=[Output(vector(i, 2.0)) for i in range(4)])
        lookup = {q['text']:vector(next(i for i,image in enumerate(plan['images']) if image['id']==q['expected_image'])) for q in plan['queries']}
        model = SimpleNamespace(_device='cpu', _pins=(), _recipe={'package_versions': {}},
            _model=SimpleNamespace(visual=SimpleNamespace(preprocess_cfg={'size':224}), encode_image=encode),
            _torch=SimpleNamespace(float32='float32', inference_mode=nullcontext),
            _vector=Mock(side_effect=lambda words,check:lookup[words]),
            probe=Mock(return_value={'dimension':512,'relevance_measured':False}))
        transform = SimpleNamespace(__file__=__file__, PreprocessCfg=lambda **kwargs:kwargs,
            image_transform_v2=Mock(return_value=lambda image:Tensor()))
        original = subject.importlib.import_module
        def module(name):
            if name=='open_clip.transform': return transform
            if name.startswith(('torchvision.','PIL.')): return SimpleNamespace(__file__=__file__)
            return original(name)
        with patch.object(subject, 'version', return_value='1.2.3'), patch.object(
                subject.importlib, 'import_module', side_effect=module), patch.object(
                subject, '_source_pin', return_value=SimpleNamespace(sha256='c'*64)), patch.object(
                subject, '_current'), patch.object(subject, 'verify_checkpoint'), patch.object(
                subject, 'observe_preprocessing', return_value={'schema':'synthetic-recipe'}), patch.object(
                subject, 'render_case', side_effect=lambda *args:(SimpleNamespace(close=Mock()),'d'*64)):
            result = subject.measure(model, {name:'1.2.3' for name in subject.IMAGE_PACKAGES})
        self.assertEqual(encode.call_count, 4)
        self.assertEqual(model._vector.call_count, 8)
        transform.image_transform_v2.assert_called_once_with({'size':224}, is_train=False)
        self.assertEqual(result['metrics']['languages']['en']['top1'], 4)
        self.assertEqual(result['metrics']['languages']['zh']['top1'], 4)
        self.assertFalse(result['pair_binding_created'])
        self.assertEqual(len(result['images']), 4)


if __name__ == '__main__':
    unittest.main()
