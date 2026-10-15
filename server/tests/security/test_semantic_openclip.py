"""Optional model wiring with generated files and stand-ins, never real ML."""
from dataclasses import replace
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'backend'), str(ROOT/'scripts')]

import semantic_openclip as subject
from app.access.semantic_encoder import JointSpaceBinding, SemanticInvalid, SemanticUnavailable
from app.access.visual_candidates import VectorSpaceIdentity, canonical_vector_checksum


class FakeTensor:
    shape = (1, 512)
    def __init__(self, data): self.data = data
    def detach(self): return self
    def to(self, **kwargs): return self
    def __getitem__(self, key): return SimpleNamespace(tolist=lambda: self.data[key])


class FakeTokenizer:
    context_length = 77
    vocab_size = 49408
    sot_token_id = 49406
    eot_token_id = 49407
    def __init__(self, **kwargs):
        self.arguments = kwargs
        self.cache = {'special': 'baseline'}
        self.tokens = [3, 4]
    def encode(self, query):
        self.cache[query] = 'private bpe'
        return self.tokens


class FakeModel:
    training = True
    context_length = 77
    text_projection = SimpleNamespace(shape=(512, 512))
    def __init__(self):
        self.device, self.dtype = 'cpu', 'float32'
        self.data = [3.0, 4.0]+[0.0]*510
        self.sequences = []
    def eval(self): self.training = False; return self
    def parameters(self): return iter([SimpleNamespace(device=self.device, dtype=self.dtype)])
    def encode_text(self, tensor):
        self.sequences.append(tensor.data[0])
        return FakeTensor([self.data])


class SemanticOpenClipTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='semantic-openclip-fixture-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.checkpoint = self.root/'weights.pt'; self.checkpoint.write_bytes(b'generated-not-weights')
        self.bpe = self.root/'bpe.gz'; self.bpe.write_bytes(gzip.compress(b'generated-not-real-bpe'))
        self.packages = {'open_clip_torch': '3.1.0', 'torch': '2.6.0', 'ftfy': '6.3.0', 'regex': '2025.1.1'}
        self.model = FakeModel()
        self.calls = []
        from contextlib import nullcontext
        self.torch = SimpleNamespace(float32='float32', long='int64',
            cuda=SimpleNamespace(is_available=lambda: False), inference_mode=nullcontext,
            tensor=lambda data, **kwargs: FakeTensor(data), load=lambda path, weights_only=True: None)
        config = {'embed_dim': 512, 'text_cfg': {'context_length': 77}}
        (self.root/'model_configs').mkdir()
        (self.root/'model_configs/ViT-B-32.json').write_text(json.dumps(config))
        self.modules = {'torch': self.torch}
        for name in ('open_clip', 'open_clip.factory', 'open_clip.model', 'open_clip.tokenizer'):
            path = self.root/(name.rsplit('.', 1)[-1]+'.py')
            path.write_text('# generated implementation stand-in\n')
            self.modules[name] = SimpleNamespace(__file__=str(path))
        self.modules['open_clip'].create_model = self.create_model
        self.modules['open_clip'].get_model_config = lambda name: config
        self.modules['open_clip.tokenizer'].SimpleTokenizer = FakeTokenizer
        original = subject.importlib.import_module
        self.addCleanup(patch.stopall)
        patch.object(subject.importlib, 'import_module', side_effect=lambda name: self.modules[name]
                     if name in self.modules else original(name)).start()
        patch.object(subject, 'version', side_effect=lambda name: self.packages[name]).start()

    def create_model(self, *args, **kwargs):
        self.assertEqual(os.environ.get('TORCH_FORCE_WEIGHTS_ONLY_LOAD'), '1')
        self.calls.append((args, kwargs))
        return self.model

    def load(self, **changes):
        arguments = dict(checkpoint=self.checkpoint,
            checkpoint_sha256=hashlib.sha256(self.checkpoint.read_bytes()).hexdigest(),
            bpe=self.bpe, bpe_sha256=hashlib.sha256(self.bpe.read_bytes()).hexdigest(),
            architecture='ViT-B-32', device='cpu', package_versions=dict(self.packages))
        arguments.update(changes)
        return subject.OpenClipTextModel.load(**arguments)

    def binding(self, model):
        identity = VectorSpaceIdentity(model._checkpoint_sha256, model._recipe_sha256,
                                       'synthetic-joint', 'v1', 512, 'unit_l2')
        return JointSpaceBinding(replace(identity, preprocessing_sha256='b'*64), identity, 'c'*64)

    def test_explicit_local_load_and_normalized_text_vector(self):
        model = self.load()
        args, kwargs = self.calls[0]
        self.assertEqual(args, ('ViT-B-32',))
        self.assertEqual(kwargs['pretrained'], str(self.checkpoint))
        self.assertTrue(kwargs['weights_only'])
        self.assertTrue(kwargs['require_pretrained'])
        self.assertFalse(kwargs['pretrained_image'])
        self.assertFalse(kwargs['pretrained_text'])
        self.assertEqual(model._tokenizer.arguments['bpe_path'], str(self.bpe))
        model.bind(self.binding(model))
        result = model.encode('private scene')
        self.assertAlmostEqual(result.vector[0], .6)
        self.assertAlmostEqual(result.vector[1], .8)
        self.assertEqual(result.checksum_sha256, canonical_vector_checksum(result.vector))
        sequence = self.model.sequences[0]
        self.assertEqual(sequence[:4], [49406, 3, 4, 49407])
        self.assertEqual(len(sequence), 77)
        self.assertEqual(model._tokenizer.cache, {'special': 'baseline'})

    def test_probe_has_no_paths_queries_or_vectors_and_does_not_claim_relevance(self):
        model = self.load()
        receipt = model.probe()
        self.assertFalse(receipt['relevance_measured'])
        self.assertEqual(receipt['dimension'], 512)
        self.assertIsNone(model.binding)
        self.assertNotIn(str(self.root), json.dumps(receipt))
        self.assertNotIn('a red circle', json.dumps(receipt))
        with self.assertRaises(SemanticUnavailable): model.encode('scene')

    def test_checkpoint_package_and_tokenizer_failures_precede_model_load(self):
        for changes in ({'checkpoint_sha256': 'f'*64}, {'bpe_sha256': 'f'*64},
                        {'architecture': 'hf-hub:untrusted'}, {'device': 'cuda:0'},
                        {'package_versions': {name: 'different' for name in self.packages}}):
            with self.subTest(changes=changes), self.assertRaises(SemanticUnavailable):
                self.load(**changes)
        self.assertEqual(self.calls, [])

    def test_binding_requires_the_same_pinned_checkpoint_and_observed_text_recipe(self):
        model = self.load(); binding = self.binding(model)
        for bad in (replace(binding, image_identity=replace(binding.image_identity, artifact_sha256='f'*64)),
                    replace(binding, text_identity=replace(binding.text_identity, preprocessing_sha256='f'*64))):
            with self.assertRaises(SemanticUnavailable): model.bind(bad)
        model.bind(binding)
        with self.assertRaises(SemanticUnavailable): model.bind(binding)

    def test_overflow_special_tokens_and_invalid_query_are_refused_without_truncation(self):
        model = self.load(); model.bind(self.binding(model))
        for tokens in ([3]*76, [49407, 3], [True], [-1], []):
            model._tokenizer.tokens = tokens
            with self.subTest(tokens=tokens[:2]), self.assertRaises(SemanticInvalid):
                model.encode('private scene')
            self.assertEqual(model._tokenizer.cache, {'special': 'baseline'})
        self.assertEqual(self.model.sequences, [])
        for query in ('x'*513, 'scene\nextra', 'scene\u0085extra', ''):
            with self.assertRaises(SemanticInvalid): model.encode(query)

    def test_output_shape_nonfinite_zero_or_wrong_device_fail_closed(self):
        model = self.load(); model.bind(self.binding(model))
        for values in ([0.0]*512, [float('nan')]+[0.0]*511, [1.0]*511):
            self.model.data = values
            with self.assertRaises(SemanticUnavailable): model.encode('scene')
        self.model.device = 'cuda:0'
        with self.assertRaises(SemanticUnavailable): self.load()

    def test_file_mutation_during_or_after_loading_refuses_identity(self):
        original = self.modules['open_clip'].create_model
        def mutate(*args, **kwargs):
            self.checkpoint.write_bytes(b'changed-during-load')
            return original(*args, **kwargs)
        self.modules['open_clip'].create_model = mutate
        with self.assertRaises(SemanticUnavailable): self.load()
        self.modules['open_clip'].create_model = original
        model = self.load(); model.bind(self.binding(model))
        self.bpe.write_bytes(b'changed-after-load')
        with self.assertRaises(SemanticUnavailable): model.encode('scene')

    def test_cancellation_and_busy_direct_calls_do_not_run_inference(self):
        model = self.load(); model.bind(self.binding(model))
        def cancelled(): raise RuntimeError('cancelled')
        with self.assertRaisesRegex(RuntimeError, 'cancelled'): model.encode('scene', check=cancelled)
        self.assertEqual(self.model.sequences, [])
        model._lock.acquire()
        try:
            with self.assertRaises(SemanticUnavailable): model.encode('scene')
        finally:
            model._lock.release()

    def test_unsafe_loader_settings_and_unsupported_torch_are_refused(self):
        with patch.dict(os.environ, {'TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD': '1'}):
            with self.assertRaises(SemanticUnavailable): self.load()
        self.packages['torch'] = '2.5.0'
        with self.assertRaises(SemanticUnavailable): self.load()
        self.packages['torch'] = '2.6.0'
        self.torch.load = lambda path: None
        with self.assertRaises(SemanticUnavailable): self.load()
        self.assertEqual(self.calls, [])

    def test_forced_restricted_loading_environment_is_restored_on_failure(self):
        self.modules['open_clip'].create_model = Mock(side_effect=TypeError('loader failed'))
        with patch.dict(os.environ, {'TORCH_FORCE_WEIGHTS_ONLY_LOAD': 'original'}):
            with self.assertRaises(SemanticUnavailable): self.load()
            self.assertEqual(os.environ['TORCH_FORCE_WEIGHTS_ONLY_LOAD'], 'original')


if __name__ == '__main__': unittest.main()
