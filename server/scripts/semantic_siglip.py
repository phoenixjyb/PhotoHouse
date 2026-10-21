"""Pinned local CPU SigLIP2 image/text adapter; importing performs no ML or IO.

Identities bind the checkpoint, exact preprocessing, packages and source files.
A binding is an operator attestation, never an activation or relevance decision.
"""
from dataclasses import asdict
import copy
import hashlib
import importlib
from pathlib import Path
import threading

import qualify_multilingual_scenes as qualification
from image_embedding_receipts import recipe_sha256, verify_checkpoint
from qualify_semantic_scenes import decode_image
from semantic_openclip import _source_pin, _current
from app.access.semantic_encoder import (JointSpaceBinding, TextVector,
    SemanticInvalid, SemanticUnavailable, SemanticUnsupported, _valid_query)
from app.access.search_exclusions import requires_semantic_clarification
from app.access.visual_candidates import VectorSpaceIdentity, canonical_vector_checksum

DIMENSION = qualification.DIMENSION
SPACE = 'siglip2-base-p16-256-3f9f96c'
MODEL_VERSION = 'siglip2-3f9f96c-v1'


class SiglipModel:
    @classmethod
    def load(cls, *, model_directory, artifacts, package_versions):
        try:
            if (artifacts != qualification.OFFICIAL_ARTIFACTS
                    or package_versions != qualification.EXPECTED_PACKAGES
                    or qualification.installed_versions() != package_versions):
                raise SemanticUnavailable()
            directory = qualification.canonical_private_directory(model_directory)
            pins = qualification.inspect_model_files(directory, artifacts)
            torch = importlib.import_module('torch')
            torch.set_num_threads(2)
            handle = qualification.load_model(directory, pins, package_versions)
            modules = {'adapter': _source_pin(Path(__file__).resolve()),
                'qualification': _source_pin(Path(qualification.__file__).resolve()),
                'decoder': _source_pin(Path(importlib.import_module('qualify_semantic_scenes').__file__).resolve()),
                'receipts': _source_pin(Path(importlib.import_module('image_embedding_receipts').__file__).resolve()),
                'exclusions': _source_pin(Path(importlib.import_module('app.access.search_exclusions').__file__).resolve())}
            sources = {name: pin.sha256 for name, pin in
                       {**modules, **handle['source_pins']}.items()}
            common = {'schema': 'photohouse.siglip2_recipe.v1',
                'model_id': qualification.MODEL_ID, 'revision': qualification.REVISION,
                'artifacts': copy.deepcopy(artifacts), 'package_versions': dict(package_versions),
                'source_digests': sources, 'device': 'cpu', 'dtype': 'float32',
                'dimension': DIMENSION, 'output': 'float32_unit_l2'}
            image_recipe = {**common, 'role': 'image',
                'input_profile': 'private_single_frame_jpeg_png_exif_rgb_v1',
                'preprocessor': copy.deepcopy(handle['preprocessor_config'])}
            text_recipe = {**common, 'role': 'text', 'normalization': 'unicode_lowercase',
                'max_length': qualification.TEXT_MAX_LENGTH, 'padding': 'max_length',
                'truncation': False, 'overflow': 'refuse', 'attention_mask': 'not_supplied',
                'add_bos_token': False, 'add_eos_token': True,
                'original_query_binding': 'sha256_utf8_before_normalization'}
            checkpoint = pins['model.safetensors'].sha256
            result = cls()
            result.image_identity = VectorSpaceIdentity(checkpoint, recipe_sha256(image_recipe),
                SPACE, MODEL_VERSION, DIMENSION, 'unit_l2')
            result.text_identity = VectorSpaceIdentity(checkpoint, recipe_sha256(text_recipe),
                SPACE, MODEL_VERSION, DIMENSION, 'unit_l2')
            result._handle = handle
            result._recipes = {'image': image_recipe, 'text': text_recipe}
            result._pins = (*pins.values(), *modules.values(), *handle['source_pins'].values())
            result._packages = dict(package_versions)
            result._binding = None
            result._lock = threading.Lock()
            result.verify()
            return result
        except SemanticUnavailable:
            raise
        except Exception:
            raise SemanticUnavailable() from None

    @property
    def binding(self):
        return self._binding

    def bind(self, binding):
        if (self._binding is not None or type(binding) is not JointSpaceBinding
                or binding.image_identity != self.image_identity
                or binding.text_identity != self.text_identity):
            raise SemanticUnavailable()
        self._binding = binding
        return self

    def verify(self):
        if qualification.installed_versions() != self._packages:
            raise SemanticUnavailable()
        for pin in self._pins:
            verify_checkpoint(pin)

    def _check(self, check):
        check()
        for pin in self._pins:
            _current(pin)

    def receipt(self):
        return copy.deepcopy({'schema': 'photohouse.siglip2_adapter_receipt.v1',
            'image_identity': asdict(self.image_identity),
            'text_identity': asdict(self.text_identity), 'recipes': self._recipes,
            'cpu_threads': 2, 'relevance_accepted': False, 'activation_approved': False})

    def encode_image(self, pin, *, check=lambda: None):
        if not self._lock.acquire(blocking=False):
            raise SemanticUnavailable()
        decoded = None
        try:
            self._check(check)
            decoded = decode_image(pin)
            h = self._handle
            pixels = h['processor'](images=decoded, return_tensors='pt')['pixel_values']
            if tuple(pixels.shape) != (1, 3, 256, 256):
                raise SemanticUnavailable()
            with h['torch'].inference_mode():
                output = h['model'].get_image_features(
                    pixel_values=pixels.to(device='cpu', dtype=h['torch'].float32))
            vector = qualification._normalise(output, h['torch'])
            self._check(check)
            return vector
        except SemanticUnavailable:
            raise
        except Exception:
            raise SemanticUnavailable() from None
        finally:
            if decoded is not None:
                decoded.close()
            self._lock.release()

    def encode(self, query, *, check=lambda: None):
        if not _valid_query(query) or any(0x7f <= ord(c) < 0xa0 or c in '\u2028\u2029' for c in query):
            raise SemanticInvalid()
        # Keep this check inside the provider as well as in the protected API.
        if requires_semantic_clarification(query):
            raise SemanticUnsupported()
        if self._binding is None or not self._lock.acquire(blocking=False):
            raise SemanticUnavailable()
        try:
            self._check(check)
            h = self._handle
            try:
                model_input, _count = qualification._query_tokens(h['processor'], query)
            except qualification.Refused:
                raise SemanticUnsupported() from None
            inputs = h['processor'](text=[model_input], padding='max_length', max_length=64,
                truncation=False, return_tensors='pt')
            if set(inputs) != {'input_ids'} or tuple(inputs['input_ids'].shape) != (1, 64):
                raise SemanticUnavailable()
            with h['torch'].inference_mode():
                output = h['model'].get_text_features(input_ids=inputs['input_ids'].to('cpu'))
            vector = qualification._normalise(output, h['torch'])
            self._check(check)
            return TextVector(self.binding.binding_sha256, hashlib.sha256(query.encode('utf-8')).hexdigest(),
                vector, canonical_vector_checksum(vector))
        except (SemanticUnavailable, SemanticInvalid):
            raise
        except Exception:
            raise SemanticUnavailable() from None
        finally:
            self._lock.release()
