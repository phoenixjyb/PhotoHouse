#!/usr/bin/env python3
"""Offline CPU qualification of direct multilingual scene queries with SigLIP2.

Planning mode imports no optional ML packages and reads no private files. The
run mode accepts one explicitly pinned local model directory, reviewed dataset,
and output directory. It never contacts a model hub or PhotoHouse service.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib
from importlib.metadata import version
import json
import logging
import math
import os
from pathlib import Path
import re
import stat
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.access.model_deployment import _load_private_document
from app.access.private_storage import require_private_directory, require_private_file
from image_embedding_receipts import inspect_checkpoint, verify_checkpoint, _open_pinned
from qualify_semantic_pair import canonical, output_target, write_record, quiet_dependencies
from qualify_semantic_scenes import inspect_images, decode_image
from semantic_scene_cases import validate_dataset, dataset_sha256, evaluate
from semantic_openclip import _source_pin, _current

MODEL_ID = 'google/siglip2-base-patch16-256'
REVISION = '3f9f96cb90da5dbc758b01813f2f6f1aee24c1ab'
DIMENSION = 768
IMAGE_SIZE = 256
TEXT_MAX_LENGTH = 64
MODEL_FILES = frozenset(('config.json', 'model.safetensors', 'preprocessor_config.json',
                         'special_tokens_map.json', 'tokenizer.json', 'tokenizer.model',
                         'tokenizer_config.json'))
PACKAGE_NAMES = frozenset(('torch', 'torchvision', 'transformers', 'huggingface-hub',
    'safetensors', 'tokenizers', 'sentencepiece', 'protobuf', 'Pillow', 'numpy'))
EXPECTED_PACKAGES = {
    'torch': '2.8.0+cu126', 'torchvision': '0.23.0+cu126', 'transformers': '4.55.2',
    'huggingface-hub': '0.34.4', 'safetensors': '0.6.2', 'tokenizers': '0.21.4',
    'sentencepiece': '0.2.1', 'protobuf': '6.33.5', 'Pillow': '11.3.0', 'numpy': '2.2.6',
}
OFFICIAL_ARTIFACTS = {
    'config.json': {'bytes': 276, 'sha256': '7b5aedcb8893e31376e129c1ffd7a5392f1a806dbc793ce53eda220c2ec59edf'},
    'model.safetensors': {'bytes': 1500985224, 'sha256': '6125cacc01fa93bdc98a0c5101cefcd69b2ed1f8ab4f38d86f4ad5984f5dc863'},
    'preprocessor_config.json': {'bytes': 394, 'sha256': 'd14ba2ee3fd816f3de8abaddc31953565128eaf37c73ad4bed32101a98465aff'},
    'special_tokens_map.json': {'bytes': 636, 'sha256': 'baec30ea10906f16adb8c18af7a34023002c1746542612b8b41c9f09e1351351'},
    'tokenizer.json': {'bytes': 34363039, 'sha256': 'cb9140fae3ac5122c972d37adf83e1248471a38147ad76f8215c8872c6fd8322'},
    'tokenizer.model': {'bytes': 4241003, 'sha256': '61a7b147390c64585d6c3543dd6fc636906c9af3865a5548f27f31aee1d4c8e2'},
    'tokenizer_config.json': {'bytes': 47164, 'sha256': '14afe629fe4959b9e0d51e1852b8d9f7ad074f90a1a7125a4fcdd17f06e78fc8'},
}
MAX_IMAGE_BYTES = 32 * 1024**2
MAX_TOTAL_BYTES = 256 * 1024**2
MAX_PIXELS = 16 * 1024**2


class Refused(ValueError):
    def __init__(self):
        super().__init__('multilingual_scene_measurement_unavailable')


def configuration(path):
    value = _load_private_document(path, source_root=ROOT.parent)
    if (type(value) is not dict or set(value) != {'schema', 'model_directory', 'artifacts',
            'package_versions', 'dataset', 'max_elapsed_seconds'}
            or value['schema'] != 'photohouse.multilingual_scene_run.v1'
            or type(value['model_directory']) is not str or type(value['dataset']) is not str
            or type(value['max_elapsed_seconds']) is not int
            or not 30 <= value['max_elapsed_seconds'] <= 1800
            or type(value['package_versions']) is not dict
            or set(value['package_versions']) != PACKAGE_NAMES
            or value['package_versions'] != EXPECTED_PACKAGES
            or type(value['artifacts']) is not dict or set(value['artifacts']) != MODEL_FILES):
        raise Refused()
    for name, pin in value['artifacts'].items():
        if (type(pin) is not dict or set(pin) != {'sha256', 'bytes'}
                or type(pin['sha256']) is not str or re.fullmatch(r'[0-9a-f]{64}', pin['sha256']) is None
                or type(pin['bytes']) is not int or pin['bytes'] <= 0):
            raise Refused()
    if value['artifacts'] != OFFICIAL_ARTIFACTS:
        raise Refused()
    model_dir = canonical_private_directory(value['model_directory'])
    dataset = validate_dataset(_load_private_document(value['dataset'], source_root=ROOT.parent))
    if not all(dataset['review'].values()):
        raise Refused()
    return value, model_dir, dataset


def canonical_private_directory(raw):
    path = Path(raw)
    if (not path.is_absolute() or '..' in path.parts or path == Path(path.anchor)
            or path.drive.startswith('\\\\')):
        raise Refused()
    try:
        if path.resolve(strict=True) != path:
            raise Refused()
        for parent in reversed(path.parents):
            info = parent.lstat()
            if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)
                    or getattr(info, 'st_file_attributes', 0) & 0x400):
                raise Refused()
        info = path.lstat()
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
            raise Refused()
        require_private_directory(path)
    except (OSError, ValueError):
        raise Refused() from None
    if path.resolve().is_relative_to(ROOT.parent.resolve()):
        raise Refused()
    return path


def inspect_model_files(directory, artifacts):
    try:
        actual = {entry.name for entry in directory.iterdir()}
    except OSError:
        raise Refused() from None
    if actual != MODEL_FILES:
        raise Refused()
    pins = {}
    for name in sorted(MODEL_FILES):
        path = directory / name
        try:
            require_private_file(path)
            pin = inspect_checkpoint(path, artifacts[name]['sha256'])
        except Exception:
            raise Refused() from None
        if pin.stat_identity[3] != artifacts[name]['bytes']:
            raise Refused()
        pins[name] = pin
    return pins


def installed_versions():
    try:
        return {name: version(name) for name in PACKAGE_NAMES}
    except Exception:
        raise Refused() from None


def _normalise(output, torch):
    try:
        tensor = output.detach().to(device='cpu', dtype=torch.float32)
        if tuple(tensor.shape) != (1, DIMENSION):
            raise Refused()
        values = tensor[0].tolist()
        if len(values) != DIMENSION or any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
            raise Refused()
        norm = math.sqrt(math.fsum(v * v for v in values))
        if not math.isfinite(norm) or norm <= 0:
            raise Refused()
        result = tuple(v / norm for v in values)
        if not all(math.isfinite(v) for v in result):
            raise Refused()
        return result
    except Refused:
        raise
    except Exception:
        raise Refused() from None


def load_model(directory, pins, packages):
    """Load only the pinned local SigLIP architecture on CPU in float32."""
    if installed_versions() != packages:
        raise Refused()
    for pin in pins.values():
        verify_checkpoint(pin)
    try:
        json_configs = {}
        for name in ('config.json', 'preprocessor_config.json',
                     'special_tokens_map.json', 'tokenizer_config.json'):
            with _open_pinned(directory / name, pins[name].stat_identity) as stream:
                json_configs[name] = json.load(stream)
        config = json_configs['config.json']
        if any('auto_map' in document for document in json_configs.values()):
            raise Refused()
        if (type(config) is not dict or config.get('model_type') != 'siglip'
                or config.get('architectures', ['SiglipModel']) != ['SiglipModel']
                or config.get('vision_config', {}).get('image_size') != IMAGE_SIZE
                or config.get('vision_config', {}).get('hidden_size', 768) != DIMENSION
                or config.get('text_config', {}).get('vocab_size') != 256000
                or config.get('text_config', {}).get('max_position_embeddings', 64) != TEXT_MAX_LENGTH
                or config.get('text_config', {}).get('hidden_size', DIMENSION) != DIMENSION):
            raise Refused()
        preprocessor = json_configs['preprocessor_config.json']
        if (preprocessor.get('image_processor_type') != 'SiglipImageProcessor'
                or preprocessor.get('processor_class') != 'SiglipProcessor'
                or preprocessor.get('size') != {'height': IMAGE_SIZE, 'width': IMAGE_SIZE}
                or preprocessor.get('do_resize') is not True
                or preprocessor.get('resample') != 2
                or preprocessor.get('do_rescale') is not True
                or preprocessor.get('rescale_factor') != 1 / 255
                or preprocessor.get('do_normalize') is not True
                or preprocessor.get('image_mean') != [0.5, 0.5, 0.5]
                or preprocessor.get('image_std') != [0.5, 0.5, 0.5]):
            raise Refused()
        tokenizer_config = json_configs['tokenizer_config.json']
        if (tokenizer_config.get('tokenizer_class') != 'GemmaTokenizer'
                or tokenizer_config.get('do_lower_case') is not True
                or tokenizer_config.get('add_bos_token') is not False
                or tokenizer_config.get('add_eos_token') is not True):
            raise Refused()
        torch = importlib.import_module('torch')
        transformers = importlib.import_module('transformers')
        model_cls = getattr(transformers, 'SiglipModel')
        processor_cls = getattr(transformers, 'SiglipProcessor')
        auto_model = getattr(transformers, 'AutoModel')
        auto_processor = getattr(transformers, 'AutoProcessor')
        model = auto_model.from_pretrained(str(directory), local_files_only=True,
            trust_remote_code=False, use_safetensors=True)
        processor = auto_processor.from_pretrained(str(directory), local_files_only=True,
            trust_remote_code=False, use_fast=False)
        if not isinstance(model, model_cls) or not isinstance(processor, processor_cls):
            raise Refused()
        vision_config, text_config = model.config.vision_config, model.config.text_config
        if (getattr(model.config, 'model_type', None) != 'siglip'
                or getattr(vision_config, 'image_size', None) != IMAGE_SIZE
                or getattr(vision_config, 'hidden_size', None) != DIMENSION
                or getattr(vision_config, 'patch_size', None) != 16
                or getattr(text_config, 'hidden_size', None) != DIMENSION
                or getattr(text_config, 'projection_size', None) != DIMENSION
                or getattr(text_config, 'vocab_size', None) != 256000
                or getattr(text_config, 'max_position_embeddings', None) != TEXT_MAX_LENGTH):
            raise Refused()
        image_processor, tokenizer = processor.image_processor, processor.tokenizer
        if (getattr(image_processor, 'size', None) != {'height': IMAGE_SIZE, 'width': IMAGE_SIZE}
                or getattr(image_processor, 'resample', None) != preprocessor['resample']
                or getattr(image_processor, 'do_resize', None) is not True
                or getattr(image_processor, 'do_rescale', None) is not True
                or getattr(image_processor, 'rescale_factor', None) != preprocessor['rescale_factor']
                or getattr(image_processor, 'do_normalize', None) is not True
                or list(getattr(image_processor, 'image_mean', ())) != preprocessor['image_mean']
                or list(getattr(image_processor, 'image_std', ())) != preprocessor['image_std']
                or not isinstance(getattr(tokenizer, 'init_kwargs', None), dict)
                or tokenizer.init_kwargs.get('do_lower_case') is not True
                or getattr(tokenizer, 'add_bos_token', None) is not False
                or getattr(tokenizer, 'add_eos_token', None) is not True):
            raise Refused()
        model = model.to(device='cpu', dtype=torch.float32)
        model.eval()
        if model.training is not False:
            raise Refused()
        source_names = (
            'transformers.models.siglip.modeling_siglip',
            'transformers.models.siglip.processing_siglip',
            'transformers.models.siglip.image_processing_siglip',
            'transformers.models.gemma.tokenization_gemma',
            'transformers.tokenization_utils', 'transformers.image_transforms',
            'transformers.image_utils', 'torch', 'PIL.Image', 'numpy')
        sources = {name: _source_pin(importlib.import_module(name).__file__)
                   for name in source_names}
        return {'torch': torch, 'model': model, 'processor': processor, 'config': config,
                'preprocessor_config': preprocessor, 'tokenizer_config': tokenizer_config,
                'source_pins': sources}
    except Refused:
        raise
    except Exception:
        raise Refused() from None


def _query_tokens(processor, query):
    if type(query) is not str or not query or query != query.strip():
        raise Refused()
    try:
        encoded_query = query.encode('utf-8', errors='strict')
        if len(encoded_query) > 512 or any(
                ord(c) < 32 or 0x7f <= ord(c) <= 0x9f or c in '\u2028\u2029'
                for c in query):
            raise Refused()
        # GemmaTokenizer accepts do_lower_case in kwargs but does not apply it
        # during tokenization in the pinned Transformers release. Normalize the
        # actual model input explicitly, and use this same text for the length
        # preflight and the processor call below.
        model_input = query.lower()
        if len(model_input.encode('utf-8', errors='strict')) > 512:
            raise Refused()
        encoded = processor.tokenizer(model_input, add_special_tokens=True, truncation=False,
                                      padding=False, return_attention_mask=False)
        ids = encoded['input_ids']
        if ids and type(ids[0]) is list:
            if len(ids) != 1:
                raise Refused()
            ids = ids[0]
        if type(ids) not in (list, tuple) or not 1 <= len(ids) <= TEXT_MAX_LENGTH:
            raise Refused()
        return model_input, len(ids)
    except Refused:
        raise
    except Exception:
        raise Refused() from None


def measure(model_handle, dataset, image_pins, model_pins, package_versions, deadline):
    if installed_versions() != package_versions:
        raise Refused()
    modules = {'runner': _source_pin(Path(__file__).resolve()),
        'scene_runner': _source_pin(Path(__import__('qualify_semantic_scenes').__file__).resolve()),
        'scene_cases': _source_pin(Path(__import__('semantic_scene_cases').__file__).resolve()),
        'image_receipts': _source_pin(Path(__import__('image_embedding_receipts').__file__).resolve()),
        'pair_helpers': _source_pin(Path(__import__('qualify_semantic_pair').__file__).resolve()),
        'semantic_openclip': _source_pin(Path(__import__('semantic_openclip').__file__).resolve()),
        'private_document_reader': _source_pin(Path(__import__('app.access.model_deployment',
            fromlist=['_load_private_document']).__file__).resolve()),
        'private_storage': _source_pin(Path(__import__('app.access.private_storage',
            fromlist=['require_private_directory']).__file__).resolve())}
    def check():
        if time.monotonic() >= deadline or installed_versions() != package_versions:
            raise Refused()
        for pin in (*model_pins.values(), *image_pins.values(), *modules.values(),
                    *model_handle['source_pins'].values()):
            _current(pin)

    torch, model, processor = model_handle['torch'], model_handle['model'], model_handle['processor']
    image_vectors, text_vectors, image_receipts, query_receipts = {}, {}, [], {}
    timings = {'images': [], 'text': []}
    for image in dataset['images']:
        check(); started = time.monotonic()
        decoded = decode_image(image_pins[image['id']])
        try:
            inputs = processor(images=decoded, return_tensors='pt')
            pixels = inputs['pixel_values']
            if tuple(pixels.shape) != (1, 3, IMAGE_SIZE, IMAGE_SIZE):
                raise Refused()
            with torch.inference_mode():
                output = model.get_image_features(pixel_values=pixels.to(device='cpu', dtype=torch.float32))
            vector = _normalise(output, torch)
            image_vectors[image['id']] = vector
            image_receipts.append({'id': image['id'], 'input_sha256': image['sha256'],
                                   'vector_checksum_sha256': hashlib.sha256(canonical(vector)).hexdigest()})
        finally:
            decoded.close()
        check(); timings['images'].append(time.monotonic() - started)
    for case in dataset['cases']:
        for language in ('en', 'zh', 'zh-en'):
            check(); started = time.monotonic()
            key, query = case['id'] + ':' + language, case['queries'][language]
            model_input, token_count = _query_tokens(processor, query)
            inputs = processor(text=[model_input], padding='max_length', max_length=TEXT_MAX_LENGTH,
                               truncation=False, return_tensors='pt')
            ids, mask = inputs['input_ids'], inputs['attention_mask']
            if tuple(ids.shape) != (1, TEXT_MAX_LENGTH) or int(mask.sum().item()) != token_count:
                raise Refused()
            with torch.inference_mode():
                output = model.get_text_features(input_ids=ids.to('cpu'),
                    attention_mask=mask.to('cpu'))
            vector = _normalise(output, torch)
            text_vectors[key] = vector
            query_receipts[key] = {'original_query_sha256': hashlib.sha256(query.encode('utf-8')).hexdigest(),
                                   'model_input_sha256': hashlib.sha256(model_input.encode('utf-8')).hexdigest(),
                                   'model_input_normalization': 'unicode_lowercase',
                                   'token_count_including_special_tokens': token_count,
                                   'vector_checksum_sha256': hashlib.sha256(canonical(vector)).hexdigest()}
            check(); timings['text'].append(time.monotonic() - started)
    metrics = evaluate(dataset, image_vectors, text_vectors, dimension=DIMENSION)
    for pin in (*model_pins.values(), *image_pins.values(), *modules.values(),
                *model_handle['source_pins'].values()):
        verify_checkpoint(pin)
    return {'schema': 'photohouse.multilingual_scene_measurement.v1',
        'model': {'id': MODEL_ID, 'revision': REVISION, 'dimension': DIMENSION,
                  'image_size': IMAGE_SIZE, 'text_max_length': TEXT_MAX_LENGTH,
                  'configuration_sha256': model_pins['config.json'].sha256,
                  'preprocessor_config': model_handle['preprocessor_config'],
                  'tokenizer': {'class': model_handle['tokenizer_config']['tokenizer_class'],
                    'do_lower_case': model_handle['tokenizer_config']['do_lower_case'],
                    'add_bos_token': model_handle['tokenizer_config']['add_bos_token'],
                    'add_eos_token': model_handle['tokenizer_config']['add_eos_token'],
                    'max_sequence_length': TEXT_MAX_LENGTH,
                    'padding': 'max_length', 'truncation': False,
                    'tokenizer_config_sha256': model_pins['tokenizer_config.json'].sha256},
                  'artifact_pins': {name: {'sha256': p.sha256, 'bytes': p.stat_identity[3]}
                                    for name, p in sorted(model_pins.items())}},
        'package_versions': package_versions,
        'source_sha256': {name: pin.sha256 for name, pin in sorted(
            {**modules, **model_handle['source_pins']}.items())},
        'dataset_sha256': dataset_sha256(dataset), 'images': image_receipts,
        'queries': query_receipts, 'metrics': metrics, 'timings_seconds': timings,
        'device': 'cpu', 'dtype': 'float32', 'normalization': 'unit_l2',
        'review_declarations': dataset['review'], 'original_queries_used_without_translation': True,
        'library_database_opened': False, 'vectors_persisted': False,
        'serving_binding_created': False, 'activation_performed': False,
        'network_used': False, 'gpu_used': False, 'cli_resource_limit_enforced': False,
        'family_relevance_accepted': False, 'dialect_relevance_measured': False}


def execute(config_path, output, *, model_loader=load_model, measure_fn=measure):
    config, model_dir, dataset = configuration(config_path)
    target = output_target(output)
    if installed_versions() != config['package_versions']:
        raise Refused()
    model_pins = inspect_model_files(model_dir, config['artifacts'])
    image_pins = inspect_images(dataset)
    target.mkdir(mode=0o700)
    require_private_directory(target)
    write_record(target, 'started.json', {'dataset_sha256': dataset_sha256(dataset),
        'model_revision': REVISION, 'image_count': len(dataset['images']),
        'query_count': len(dataset['cases']) * 3, 'activation_performed': False})
    start = time.monotonic(); deadline = start + config['max_elapsed_seconds']
    model = model_loader(model_dir, model_pins, config['package_versions'])
    loading_seconds = time.monotonic() - start
    record = measure_fn(model, dataset, image_pins, model_pins,
                        config['package_versions'], deadline)
    if time.monotonic() >= deadline:
        raise Refused()
    for pin in (*model_pins.values(), *image_pins.values()):
        verify_checkpoint(pin)
    record['model_loading_seconds'] = loading_seconds
    record['observed_utc'] = datetime.now(timezone.utc).isoformat()
    write_record(target, 'measurement.json', record)
    return {'status': 'multilingual_scene_measured', 'dataset_sha256': record['dataset_sha256'],
        'measurement_sha256': hashlib.sha256(canonical(record) + b'\n').hexdigest(),
        'overall': record['metrics']['overall'], 'languages': record['metrics']['languages'],
        'activation_performed': False, 'serving_binding_created': False}


def run(argv=None):
    class Parser(argparse.ArgumentParser):
        def error(self, message):
            raise Refused()
    try:
        parser = Parser(description=__doc__)
        parser.add_argument('--run', action='store_true')
        parser.add_argument('--configuration', type=Path)
        parser.add_argument('--output-directory', type=Path)
        args = parser.parse_args(argv)
        if not args.run:
            if args.configuration is not None or args.output_directory is not None:
                raise Refused()
            print(json.dumps({'status': 'multilingual_scene_plan', 'model_id': MODEL_ID,
                'revision': REVISION, 'image_size': IMAGE_SIZE, 'dimension': DIMENSION,
                'text_max_length': TEXT_MAX_LENGTH, 'languages': ['en', 'zh', 'zh-en'],
                'models_loaded': False, 'private_files_read': False,
                'activation_performed': False}, sort_keys=True))
            return 0
        if args.configuration is None or args.output_directory is None:
            raise Refused()
        previous = logging.root.manager.disable
        logging.disable(logging.CRITICAL)
        try:
            with quiet_dependencies():
                result = execute(args.configuration, args.output_directory)
        finally:
            logging.disable(previous)
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0
    except Exception:
        print('{"error":"multilingual_scene_measurement_unavailable"}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(run())
