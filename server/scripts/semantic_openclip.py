"""Explicit offline OpenCLIP text tower; optional ML imports occur only in load.

No model names, hubs, checkpoint directories or tokenizer defaults are searched.
The probe is an implementation receipt, not a relevance qualification.
"""
import gzip
import hashlib
import importlib
import inspect
import json
from importlib.metadata import version
import math
import os
from pathlib import Path
import threading
import re

from image_embedding_receipts import (inspect_checkpoint, verify_checkpoint,
    recipe_sha256, _checkpoint_path, _stat_identity)
from app.access.semantic_encoder import (JointSpaceBinding, SemanticInvalid,
    SemanticUnavailable, SemanticUnsupported, TextVector, _valid_query)
from app.access.search_policy import requires_semantic_clarification
from app.access.search_policy_binding import (
    QueryPolicyUnavailable,
    capture_current_query_policy_binding,
    verify_query_policy_binding,
)
from app.access.visual_candidates import (VectorRecord, _canonical_components,
                                         canonical_vector_checksum)


PACKAGES = frozenset(('open_clip_torch', 'torch', 'ftfy', 'regex'))
ARCHITECTURE = 'ViT-B-32'
DIMENSION = 512
CONTEXT_LENGTH = 77


def _source_pin(path):
    path = _checkpoint_path(path)
    if not 0 < path.stat().st_size <= 4 * 1024**2:
        raise SemanticUnavailable()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return inspect_checkpoint(path, digest)


def _current(pin):
    path = _checkpoint_path(pin.path)
    if _stat_identity(path.stat()) != pin.stat_identity:
        raise SemanticUnavailable()


class OpenClipTextModel:
    def __init__(self):
        self._query_policy_binding = capture_current_query_policy_binding()

    def _verify_query_policy(self, check=lambda: None):
        try:
            return verify_query_policy_binding(self._query_policy_binding, check=check)
        except QueryPolicyUnavailable:
            raise SemanticUnavailable() from None
        except (SemanticInvalid, SemanticUnavailable):
            raise
        except Exception:
            raise SemanticUnavailable() from None

    @property
    def query_policy_binding(self):
        return dict(self._verify_query_policy())

    @classmethod
    def load(cls, *, checkpoint, checkpoint_sha256, bpe, bpe_sha256,
             architecture, device, package_versions):
        """Load one inspected local full checkpoint and explicit BPE file.

        Optional libraries are imported after input/file validation. The fixed
        built-in architecture and full local checkpoint prevent hub/tag loading.
        """
        try:
            if (architecture != ARCHITECTURE or device not in ('cpu', 'cuda:0')
                    or type(package_versions) is not dict or set(package_versions) != PACKAGES
                    or any(type(v) is not str or not 1 <= len(v) <= 120
                           for v in package_versions.values())):
                raise SemanticUnavailable()
            policy_binding = capture_current_query_policy_binding()
            checkpoint_pin = inspect_checkpoint(checkpoint, checkpoint_sha256)
            if Path(checkpoint_pin.path).suffix not in ('.pt', '.pth', '.bin', '.safetensors'):
                raise SemanticUnavailable()
            bpe_pin = inspect_checkpoint(bpe, bpe_sha256)
            if bpe_pin.stat_identity[3] > 4 * 1024**2:
                raise SemanticUnavailable()
            with gzip.open(bpe_pin.path, 'rb') as stream:
                if len(stream.read(16*1024**2+1)) > 16*1024**2:
                    raise SemanticUnavailable()
            verify_checkpoint(bpe_pin)
            installed = {name: version(name) for name in sorted(PACKAGES)}
            if installed != package_versions:
                raise SemanticUnavailable()
            for name, floor in (('open_clip_torch', (3, 1)), ('torch', (2, 6))):
                match = re.match(r'^(\d+)\.(\d+)\.', installed[name])
                if match is None or tuple(map(int, match.groups())) < floor:
                    raise SemanticUnavailable()
            if os.environ.get('TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD', '').lower() in ('1', 'y', 'yes', 'true'):
                raise SemanticUnavailable()
            torch = importlib.import_module('torch')
            if 'weights_only' not in inspect.signature(torch.load).parameters:
                raise SemanticUnavailable()
            clip = importlib.import_module('open_clip')
            tokenizer_module = importlib.import_module('open_clip.tokenizer')
            source_modules = {name: importlib.import_module('open_clip.'+name)
                              for name in ('factory', 'model', 'tokenizer')}
            source_pins = {name: _source_pin(module.__file__) for name, module in source_modules.items()}
            source_pins['initializer'] = _source_pin(clip.__file__)
            config_path = Path(clip.__file__).parent / 'model_configs' / (ARCHITECTURE+'.json')
            source_pins['architecture'] = _source_pin(config_path)
            if json.loads(config_path.read_text(encoding='utf-8')) != clip.get_model_config(ARCHITECTURE):
                raise SemanticUnavailable()
            source_pins['adapter'] = _source_pin(Path(__file__).absolute())
            source_pins['checkpoint_receipts'] = _source_pin(importlib.import_module('image_embedding_receipts').__file__)
            tokenizer = tokenizer_module.SimpleTokenizer(bpe_path=bpe_pin.path,
                context_length=CONTEXT_LENGTH, clean='lower')
            if (type(tokenizer) is not tokenizer_module.SimpleTokenizer or
                    tokenizer.context_length != CONTEXT_LENGTH or tokenizer.vocab_size != 49408
                    or tokenizer.sot_token_id != 49406 or tokenizer.eot_token_id != 49407
                    or type(tokenizer.cache) is not dict):
                raise SemanticUnavailable()
            if device == 'cuda:0' and not torch.cuda.is_available():
                raise SemanticUnavailable()
            # OpenCLIP has supported versions with an internal TypeError
            # fallback to torch.load without an explicit weights_only argument.
            # Force restricted loading even along that path, then restore the
            # caller's environment. This adapter belongs in its own process.
            previous_force = os.environ.get('TORCH_FORCE_WEIGHTS_ONLY_LOAD')
            os.environ['TORCH_FORCE_WEIGHTS_ONLY_LOAD'] = '1'
            try:
                model = clip.create_model(ARCHITECTURE, pretrained=checkpoint_pin.path,
                    precision='fp32', device=device, pretrained_image=False, pretrained_text=False,
                    weights_only=True, require_pretrained=True)
            finally:
                if previous_force is None:
                    os.environ.pop('TORCH_FORCE_WEIGHTS_ONLY_LOAD', None)
                else:
                    os.environ['TORCH_FORCE_WEIGHTS_ONLY_LOAD'] = previous_force
            model.eval()
            if (model.training is not False or model.context_length != CONTEXT_LENGTH
                    or tuple(model.text_projection.shape) != (512, DIMENSION)):
                raise SemanticUnavailable()
            parameters = list(model.parameters())
            if not parameters or any(str(p.device) != device or p.dtype != torch.float32 for p in parameters):
                raise SemanticUnavailable()
            # The loader must not return a model if either input changed during
            # its own file reads. Full hashes are checked at startup, not per query.
            verify_checkpoint(checkpoint_pin)
            verify_checkpoint(bpe_pin)
            for pin in source_pins.values():
                verify_checkpoint(pin)
            recipe = {'schema': 'photohouse.openclip_text_recipe.v1',
                'architecture': ARCHITECTURE, 'context_length': CONTEXT_LENGTH,
                'tokenizer': 'open_clip.tokenizer.SimpleTokenizer', 'clean': 'lower',
                'bpe_sha256': bpe_pin.sha256, 'special_tokens': [49406, 49407],
                'overflow': 'reject', 'token_dtype': 'int64', 'precision': 'fp32',
                'checkpoint_loading': 'forced_weights_only',
                'output': 'float32_unit_l2', 'package_versions': installed,
                'source_digests': {name: pin.sha256 for name, pin in source_pins.items()}}
            result = cls()
            result._query_policy_binding = policy_binding
            result._model, result._torch, result._tokenizer = model, torch, tokenizer
            result._pins = (checkpoint_pin, bpe_pin, *source_pins.values())
            result._checkpoint_sha256 = checkpoint_pin.sha256
            result._recipe, result._recipe_sha256 = recipe, recipe_sha256(recipe)
            result._device, result._binding = device, None
            result._cache_baseline = dict(tokenizer.cache)
            result._lock = threading.Lock()
            result._verify_query_policy()
            return result
        except SemanticUnavailable:
            raise
        except Exception:
            raise SemanticUnavailable() from None

    @property
    def binding(self):
        return self._binding

    def bind(self, binding):
        self._verify_query_policy()
        if (self._binding is not None or type(binding) is not JointSpaceBinding
                or binding.text_identity.artifact_sha256 != self._checkpoint_sha256
                or binding.image_identity.artifact_sha256 != self._checkpoint_sha256
                or binding.text_identity.preprocessing_sha256 != self._recipe_sha256
                or binding.text_identity.dimension != DIMENSION):
            raise SemanticUnavailable()
        self._binding = binding
        return self

    def _vector(self, query, check):
        if not _valid_query(query) or any(0x7f <= ord(c) < 0xa0 for c in query):
            raise SemanticInvalid()
        check()
        try:
            for pin in self._pins:
                _current(pin)
            tokens = self._tokenizer.encode(query)
            if (type(tokens) is not list or not 1 <= len(tokens) <= CONTEXT_LENGTH-2
                    or any(type(value) is not int or not 0 <= value < 49406 for value in tokens)):
                raise SemanticInvalid()
            sequence = [49406, *tokens, 49407]
            sequence += [0] * (CONTEXT_LENGTH - len(sequence))
            tensor = self._torch.tensor([sequence], dtype=self._torch.long, device=self._device)
            with self._torch.inference_mode():
                output = self._model.encode_text(tensor)
                if tuple(output.shape) != (1, DIMENSION):
                    raise SemanticUnavailable()
                values = output.detach().to(device='cpu', dtype=self._torch.float32)[0].tolist()
            if (type(values) is not list or len(values) != DIMENSION
                    or any(type(value) not in (int, float) or not math.isfinite(value) for value in values)):
                raise SemanticUnavailable()
            norm = math.sqrt(math.fsum(value*value for value in values))
            if not math.isfinite(norm) or norm <= 0:
                raise SemanticUnavailable()
            vector = tuple(value/norm for value in values)
            for pin in self._pins:
                _current(pin)
        except (SemanticInvalid, SemanticUnavailable):
            raise
        except Exception:
            raise SemanticUnavailable() from None
        finally:
            # SimpleTokenizer otherwise keeps query words in its BPE cache.
            self._tokenizer.cache.clear()
            self._tokenizer.cache.update(self._cache_baseline)
        check()
        return vector

    def probe(self):
        self._verify_query_policy()
        if not self._lock.acquire(blocking=False):
            raise SemanticUnavailable()
        try:
            vector = self._vector('a red circle', lambda: None)
            self._verify_query_policy()
            return {'schema': 'photohouse.semantic_text_probe.v1',
                'architecture': ARCHITECTURE, 'checkpoint_sha256': self._checkpoint_sha256,
                'text_preprocessing_sha256': self._recipe_sha256, 'recipe': self._recipe,
                'dimension': DIMENSION, 'device': self._device,
                'probe_vector_checksum': canonical_vector_checksum(vector),
                'query_policy_binding': self.query_policy_binding,
                'relevance_measured': False}
        finally:
            self._lock.release()

    def encode(self, query, *, check=lambda: None):
        if not _valid_query(query) or any(0x7f <= ord(c) < 0xa0 for c in query):
            raise SemanticInvalid()
        self._verify_query_policy()
        if requires_semantic_clarification(query):
            raise SemanticUnsupported()
        if self._binding is None or not self._lock.acquire(blocking=False):
            raise SemanticUnavailable()
        try:
            def checked():
                check()
                self._verify_query_policy()

            vector = self._vector(query, checked)
            self._verify_query_policy()
            checksum = canonical_vector_checksum(vector)
            _canonical_components(VectorRecord('1', self.binding.text_identity, vector, checksum),
                                  self.binding.text_identity)
            check()
            return TextVector(self.binding.binding_sha256, hashlib.sha256(query.encode('utf-8')).hexdigest(),
                              vector, checksum)
        finally:
            self._lock.release()
