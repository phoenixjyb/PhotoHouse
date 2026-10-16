#!/usr/bin/env python3
"""Measure an explicitly selected private scene set with one pinned local model.

No-argument planning reads no private files or optional model packages. Execution
does not open a library, publish vectors, start a service or approve activation.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib
from importlib.metadata import version
import io
import json
import logging
import math
from pathlib import Path
import re
import stat
import sys
import time
import warnings

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.access.model_deployment import _load_private_document
from app.access.private_storage import require_private_directory, require_private_file
from app.access.visual_candidates import canonical_vector_checksum
from image_embedding_receipts import (inspect_checkpoint, verify_checkpoint,
    recipe_sha256, _open_pinned)
from image_preprocessing_receipts import observe_preprocessing
from semantic_openclip import _source_pin, _current
from serve_semantic_text import load_configuration, load_model
from qualify_semantic_pair import (IMAGE_PACKAGES, canonical, output_target,
    write_record, quiet_dependencies)
from semantic_scene_cases import validate_dataset, dataset_sha256, evaluate

MAX_IMAGE_BYTES = 32 * 1024**2
MAX_TOTAL_BYTES = 256 * 1024**2
MAX_PIXELS = 16 * 1024**2


class SceneRefused(ValueError):
    def __init__(self):
        super().__init__('semantic_scene_measurement_unavailable')


def configuration(path):
    value = _load_private_document(path, source_root=ROOT.parent)
    if (type(value) is not dict or set(value) != {'schema', 'provider_configuration',
            'dataset', 'image_package_versions', 'max_elapsed_seconds'}
            or value['schema'] != 'photohouse.semantic_scene_run.v1'
            or type(value['provider_configuration']) is not str
            or type(value['dataset']) is not str
            or type(value['max_elapsed_seconds']) is not int
            or not 30 <= value['max_elapsed_seconds'] <= 1800
            or type(value['image_package_versions']) is not dict
            or set(value['image_package_versions']) != IMAGE_PACKAGES
            or any(type(v) is not str or re.fullmatch(r'[A-Za-z0-9._+!-]{1,120}', v) is None
                   for v in value['image_package_versions'].values())):
        raise SceneRefused()
    provider = load_configuration(Path(value['provider_configuration']))
    if provider['binding'] is not None:
        raise SceneRefused()
    dataset = validate_dataset(_load_private_document(value['dataset'], source_root=ROOT.parent))
    if not all(dataset['review'].values()):
        raise SceneRefused()
    return value, provider, dataset


def inspect_images(dataset):
    """Admit only the explicitly named private files, with byte and identity pins."""
    pins, total = {}, 0
    for image in dataset['images']:
        path = Path(image['path'])
        if (not path.is_absolute() or '..' in path.parts
                or path.drive.startswith('\\\\')
                or path.resolve(strict=False).is_relative_to(ROOT.parent.resolve())):
            raise SceneRefused()
        for parent in reversed(path.parents):
            info = parent.lstat()
            if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                raise SceneRefused()
        require_private_directory(path.parent)
        require_private_file(path)
        size = path.lstat().st_size
        total += size
        if not 0 < size <= MAX_IMAGE_BYTES or total > MAX_TOTAL_BYTES:
            raise SceneRefused()
        pin = inspect_checkpoint(path, image['sha256'])
        if pin.stat_identity[3] != size:
            raise SceneRefused()
        pins[image['id']] = pin
    return pins


def decode_image(pin):
    """Decode bounded JPEG/PNG bytes, normalize orientation, discard metadata."""
    Image = importlib.import_module('PIL.Image')
    ImageOps = importlib.import_module('PIL.ImageOps')
    require_private_file(pin.path)
    with _open_pinned(Path(pin.path), pin.stat_identity) as stream:
        raw = stream.read(MAX_IMAGE_BYTES + 1)
    if (len(raw) != pin.stat_identity[3] or len(raw) > MAX_IMAGE_BYTES
            or hashlib.sha256(raw).hexdigest() != pin.sha256):
        raise SceneRefused()
    with warnings.catch_warnings():
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(raw)) as opened:
            if (opened.format not in ('JPEG', 'PNG') or getattr(opened, 'n_frames', 1) != 1
                    or not 0 < opened.width <= 8192 or not 0 < opened.height <= 8192
                    or opened.width * opened.height > MAX_PIXELS):
                raise SceneRefused()
            opened.verify()
        with Image.open(io.BytesIO(raw)) as opened:
            oriented = ImageOps.exif_transpose(opened)
            try:
                decoded = oriented.convert('RGB')
                decoded.info.clear()
            finally:
                oriented.close()
    _current(pin)
    return decoded


def measure(model, dataset, image_pins, image_package_versions, deadline):
    if {name: version(name) for name in IMAGE_PACKAGES} != image_package_versions:
        raise SceneRefused()
    modules = {name: importlib.import_module(module) for name, module in {
        'openclip_transform': 'open_clip.transform',
        'torchvision_transforms': 'torchvision.transforms.transforms',
        'torchvision_functional': 'torchvision.transforms.functional',
        'pillow_image': 'PIL.Image', 'pillow_ops': 'PIL.ImageOps',
        'pillow_jpeg': 'PIL.JpegImagePlugin', 'pillow_png': 'PIL.PngImagePlugin',
        'scene_cases': 'semantic_scene_cases', 'shared_canary_helpers': 'qualify_semantic_pair',
        'image_preprocessing_receipts': 'image_preprocessing_receipts',
    }.items()}
    pins = {name: _source_pin(module.__file__) for name, module in modules.items()}
    pins['runner'] = _source_pin(Path(__file__).resolve())
    transform = modules['openclip_transform']
    preprocess = transform.image_transform_v2(
        transform.PreprocessCfg(**model._model.visual.preprocess_cfg), is_train=False)
    digests = {name: pin.sha256 for name, pin in pins.items()}
    digests.update(decoder=pins['runner'].sha256, worker=pins['runner'].sha256,
                   embedding_service=pins['runner'].sha256)
    recipe = observe_preprocessing(preprocess,
        package_versions={**model._recipe['package_versions'], **image_package_versions}, source_digests=digests)
    recipe['input_profile'] = 'private_single_frame_jpeg_png_exif_rgb_v1'
    recipe['dataset_sha256'] = dataset_sha256(dataset)
    all_pins = (*model._pins, *pins.values(), *image_pins.values())

    def check():
        if time.monotonic() >= deadline:
            raise SceneRefused()
        for pin in all_pins:
            _current(pin)

    images, texts, image_records = {}, {}, []
    timings = {'images': [], 'text': []}
    for image in dataset['images']:
        check()
        started = time.monotonic()
        decoded = decode_image(image_pins[image['id']])
        try:
            tensor = preprocess(decoded).unsqueeze(0).to(device=model._device, dtype=model._torch.float32)
            if tuple(tensor.shape) != (1, 3, 224, 224):
                raise SceneRefused()
            with model._torch.inference_mode():
                output = model._model.encode_image(tensor)
                if tuple(output.shape) != (1, 512):
                    raise SceneRefused()
                values = output.detach().to(device='cpu', dtype=model._torch.float32)[0].tolist()
            if len(values) != 512 or any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
                raise SceneRefused()
            norm = math.sqrt(math.fsum(v*v for v in values))
            if not math.isfinite(norm) or norm <= 0:
                raise SceneRefused()
            vector = tuple(v/norm for v in values)
            images[image['id']] = vector
            image_records.append({'id': image['id'], 'input_sha256': image['sha256'],
                                  'vector_checksum': canonical_vector_checksum(vector)})
        finally:
            decoded.close()
        check()
        timings['images'].append(time.monotonic() - started)
    for case in dataset['cases']:
        for language in ('en', 'zh', 'zh-en'):
            check()
            started = time.monotonic()
            texts[case['id'] + ':' + language] = model._vector(case['queries'][language], check)
            check()
            timings['text'].append(time.monotonic() - started)
    metrics = evaluate(dataset, images, texts)
    probe = model.probe()
    for pin in all_pins:
        verify_checkpoint(pin)
    check()
    return {'schema': 'photohouse.semantic_scene_measurement.v1',
        'dataset_sha256': dataset_sha256(dataset), 'text_probe': probe,
        'image_preprocessing_recipe': recipe, 'image_preprocessing_sha256': recipe_sha256(recipe),
        'images': image_records, 'metrics': metrics, 'timings_seconds': timings,
        'device': model._device, 'review_declarations': dataset['review'],
        'content_authenticity_verified': False, 'library_database_opened': False,
        'pair_binding_created': False, 'legacy_vectors_qualified': False,
        'activation_performed': False, 'resource_limits_enforced_by_cli': False,
        'family_relevance_accepted': False, 'dialect_relevance_measured': False}


def execute(path, output, *, model_factory=load_model, measure_fn=measure):
    config, provider, dataset = configuration(path)
    target = output_target(output)
    if {name: version(name) for name in IMAGE_PACKAGES} != config['image_package_versions']:
        raise SceneRefused()
    image_pins = inspect_images(dataset)
    target.mkdir(mode=0o700)
    require_private_directory(target)
    write_record(target, 'started.json', {'dataset_sha256': dataset_sha256(dataset),
        'configuration_sha256': recipe_sha256(config), 'review_declarations': dataset['review'],
        'image_count': len(dataset['images']), 'query_count': 3 * len(dataset['cases']),
        'activation_performed': False})
    started = time.monotonic()
    deadline = started + config['max_elapsed_seconds']
    model = model_factory(provider)
    loading_seconds = time.monotonic() - started
    if time.monotonic() >= deadline:
        raise SceneRefused()
    record = measure_fn(model, dataset, image_pins, config['image_package_versions'], deadline)
    if time.monotonic() >= deadline:
        raise SceneRefused()
    record['model_loading_seconds'] = loading_seconds
    record['observed_utc'] = datetime.now(timezone.utc).isoformat()
    write_record(target, 'measurement.json', record)
    return {'status': 'scene_pair_measured', 'dataset_sha256': dataset_sha256(dataset),
        'measurement_sha256': hashlib.sha256(canonical(record)+b'\n').hexdigest(),
        'overall': record['metrics']['overall'], 'languages': record['metrics']['languages'],
        'activation_performed': False, 'family_relevance_accepted': False,
        'dialect_relevance_measured': False, 'pair_binding_created': False}


def run(argv=None):
    class Parser(argparse.ArgumentParser):
        def error(self, message):
            raise SceneRefused()
    previous = logging.root.manager.disable
    try:
        parser = Parser(description=__doc__)
        parser.add_argument('--run', action='store_true')
        parser.add_argument('--configuration', type=Path)
        parser.add_argument('--output-directory', type=Path)
        args = parser.parse_args(argv)
        if not args.run:
            if args.configuration is not None or args.output_directory is not None:
                raise SceneRefused()
            print(json.dumps({'status': 'scene_pair_plan', 'images': {'min': 4, 'max': 64},
                'matched_cases': {'min': 2, 'max': 32}, 'languages': ['en', 'zh', 'zh-en'],
                'models_loaded': False, 'private_files_read': False, 'activation_performed': False}, sort_keys=True))
            return 0
        if args.configuration is None or args.output_directory is None:
            raise SceneRefused()
        logging.disable(logging.CRITICAL)
        with quiet_dependencies():
            result = execute(args.configuration, args.output_directory)
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0
    except Exception:
        print('{"error":"semantic_scene_measurement_unavailable"}', file=sys.stderr)
        return 1
    finally:
        logging.disable(previous)


if __name__ == '__main__':
    raise SystemExit(run())
