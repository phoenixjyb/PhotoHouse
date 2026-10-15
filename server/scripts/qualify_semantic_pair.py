#!/usr/bin/env python3
"""Measure one pinned local image/text model on fixed generated inputs.

Plan-only unless --run is explicit. No library, database, network client,
listener, vector publication or activation is used by this command.
"""
import argparse
from contextlib import contextmanager, redirect_stdout, redirect_stderr
from datetime import datetime, timezone
import hashlib
import importlib
from importlib.metadata import version
import io
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
from app.access.visual_candidates import canonical_vector_checksum
from image_embedding_receipts import recipe_sha256, verify_checkpoint
from image_preprocessing_receipts import observe_preprocessing
from semantic_openclip import _source_pin, _current
from serve_semantic_text import load_configuration, load_model
from semantic_pair_cases import case_plan, plan_sha256, evaluate

IMAGE_PACKAGES = frozenset(('torchvision', 'Pillow', 'numpy'))


class PairRefused(ValueError):
    def __init__(self):
        super().__init__('semantic_pair_canary_unavailable')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False).encode('ascii')


def configuration(path):
    value = _load_private_document(path, source_root=ROOT.parent)
    if (type(value) is not dict or set(value) != {'schema', 'provider_configuration', 'image_package_versions'}
            or value['schema'] != 'photohouse.semantic_pair_canary.v1'
            or type(value['provider_configuration']) is not str
            or type(value['image_package_versions']) is not dict
            or set(value['image_package_versions']) != IMAGE_PACKAGES
            or any(type(v) is not str or re.fullmatch(r'[A-Za-z0-9._+!-]{1,120}', v) is None
                   for v in value['image_package_versions'].values())):
        raise PairRefused()
    provider = load_configuration(Path(value['provider_configuration']))
    if provider['binding'] is not None:
        raise PairRefused()
    return value, provider


def output_target(path):
    path = Path(path)
    if (not path.is_absolute() or '..' in path.parts
            or path.resolve(strict=False).is_relative_to(ROOT.parent.resolve())):
        raise PairRefused()
    for parent in reversed(path.parents):
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise PairRefused()
    require_private_directory(path.parent)
    if os.path.lexists(path):
        raise PairRefused()
    return path


def write_record(directory, name, value):
    descriptor = os.open(directory / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                         getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(descriptor, 'wb') as stream:
        require_private_file(directory / name)
        stream.write(canonical(value) + b'\n')
        stream.flush()
        os.fsync(stream.fileno())


def render_case(image_case, rendering):
    """Only the fixed, source-pinned case definitions reach this renderer."""
    Image = importlib.import_module('PIL.Image')
    Draw = importlib.import_module('PIL.ImageDraw')
    image = Image.new('RGB', tuple(rendering['canvas_px']), tuple(rendering['background_rgb']))
    draw = Draw.Draw(image)
    method = draw.ellipse if image_case['shape'] == 'circle' else draw.rectangle
    method(tuple(rendering['geometry_xyxy_px']), fill=tuple(image_case['color']))
    encoded = io.BytesIO()
    image.save(encoded, format='JPEG', quality=rendering['jpeg_quality'],
               subsampling=rendering['jpeg_subsampling'])
    image.close()
    raw = encoded.getvalue()
    if not 0 < len(raw) <= 65536:
        raise PairRefused()
    with Image.open(io.BytesIO(raw)) as opened:
        if opened.format != 'JPEG' or opened.size != tuple(rendering['canvas_px']):
            raise PairRefused()
        opened.verify()
    with Image.open(io.BytesIO(raw)) as opened:
        decoded = opened.convert('RGB')
    return decoded, hashlib.sha256(raw).hexdigest()


def measure(model, image_package_versions):
    """Reuse the full pinned checkpoint once; never construct a binding."""
    installed = {name: version(name) for name in sorted(IMAGE_PACKAGES)}
    if installed != image_package_versions:
        raise PairRefused()
    transform_module = importlib.import_module('open_clip.transform')
    sources = {name: importlib.import_module(module) for name, module in {
        'openclip_transform': 'open_clip.transform', 'torchvision_transforms': 'torchvision.transforms.transforms',
        'torchvision_functional': 'torchvision.transforms.functional', 'pillow_image': 'PIL.Image',
        'pillow_draw': 'PIL.ImageDraw', 'pillow_jpeg': 'PIL.JpegImagePlugin',
    }.items()}
    pins = {name: _source_pin(module.__file__) for name, module in sources.items()}
    pins['canary'] = _source_pin(Path(__file__).resolve())
    pins['cases'] = _source_pin(importlib.import_module('semantic_pair_cases').__file__)
    pins['image_preprocessing_receipts'] = _source_pin(importlib.import_module('image_preprocessing_receipts').__file__)
    preprocess = transform_module.image_transform_v2(
        transform_module.PreprocessCfg(**model._model.visual.preprocess_cfg), is_train=False)
    all_packages = {**model._recipe['package_versions'], **installed}
    digests = {name: pin.sha256 for name, pin in pins.items()}
    # These roles are implemented by this canary, not by the legacy image worker.
    digests.update(decoder=pins['canary'].sha256, embedding_service=pins['canary'].sha256,
                   worker=pins['canary'].sha256)
    recipe = observe_preprocessing(preprocess, package_versions=all_packages, source_digests=digests)
    recipe['input_profile'] = 'fixed_generated_rgb_jpeg_v1'
    recipe['case_plan_sha256'] = plan_sha256()
    images, texts, image_records, timings = {}, {}, [], {'images': [], 'text': []}
    deadline = time.monotonic() + 120

    def check():
        if time.monotonic() >= deadline:
            raise PairRefused()
        for pin in (*model._pins, *pins.values()):
            _current(pin)

    plan = case_plan()
    for item in plan['images']:
        check()
        started = time.monotonic()
        decoded, digest = render_case(item, plan['rendering'])
        try:
            tensor = preprocess(decoded).unsqueeze(0).to(device=model._device, dtype=model._torch.float32)
            if tuple(tensor.shape) != (1, 3, 224, 224):
                raise PairRefused()
            with model._torch.inference_mode():
                output = model._model.encode_image(tensor)
                if tuple(output.shape) != (1, 512):
                    raise PairRefused()
                values = output.detach().to(device='cpu', dtype=model._torch.float32)[0].tolist()
            if len(values) != 512 or any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
                raise PairRefused()
            norm = math.sqrt(math.fsum(v*v for v in values))
            if not math.isfinite(norm) or norm <= 0:
                raise PairRefused()
            vector = tuple(v/norm for v in values)
            images[item['id']] = vector
            image_records.append({'id': item['id'], 'input_sha256': digest,
                                  'vector_checksum': canonical_vector_checksum(vector)})
        finally:
            decoded.close()
        check()
        timings['images'].append(time.monotonic()-started)
    for item in plan['queries']:
        check()
        started = time.monotonic()
        texts[item['id']] = model._vector(item['text'], check)
        timings['text'].append(time.monotonic()-started)
    metrics = evaluate(images, texts)
    for pin in (*model._pins, *pins.values()):
        verify_checkpoint(pin)
    check()
    return {'schema': 'photohouse.semantic_pair_measurement.v1', 'case_plan_sha256': plan_sha256(),
        'text_probe': model.probe(), 'image_preprocessing_recipe': recipe,
        'image_preprocessing_sha256': recipe_sha256(recipe), 'images': image_records,
        'metrics': metrics, 'timings_seconds': timings, 'device': model._device,
        'pair_binding_created': False, 'legacy_vectors_qualified': False,
        'family_media_read': False, 'activation_performed': False, 'resource_limits_enforced_by_cli': False,
        'dialect_relevance_measured': False}


def execute(path, output, *, model_factory=load_model, measure_fn=measure):
    config, provider = configuration(path)
    target = output_target(output)
    # Check image versions before creating a directory or loading a checkpoint.
    if {name: version(name) for name in IMAGE_PACKAGES} != config['image_package_versions']:
        raise PairRefused()
    target.mkdir(mode=0o700)
    require_private_directory(target)
    write_record(target, 'started.json', {'case_plan_sha256': plan_sha256(),
        'configuration_sha256': recipe_sha256(config), 'synthetic_only': True,
        'activation_performed': False})
    started = time.monotonic()
    model = model_factory(provider)
    loading_seconds = time.monotonic()-started
    record = measure_fn(model, config['image_package_versions'])
    record['model_loading_seconds'] = loading_seconds
    record['observed_utc'] = datetime.now(timezone.utc).isoformat()
    write_record(target, 'measurement.json', record)
    return {'status': 'synthetic_pair_measured', 'case_plan_sha256': plan_sha256(),
        'measurement_sha256': hashlib.sha256(canonical(record)+b'\n').hexdigest(),
        'metrics': record['metrics'], 'activation_performed': False,
        'family_relevance_measured': False, 'dialect_relevance_measured': False,
        'pair_binding_created': False}


@contextmanager
def quiet_dependencies():
    """Dedicated CLI process: discard Python and native dependency diagnostics."""
    saved = []
    try:
        with open(os.devnull, 'w', encoding='utf-8') as sink:
            for descriptor in (1, 2):
                saved.append((descriptor, os.dup(descriptor)))
                os.dup2(sink.fileno(), descriptor)
            with redirect_stdout(sink), redirect_stderr(sink):
                yield
    finally:
        for descriptor, backup in saved:
            try:
                os.dup2(backup, descriptor)
            finally:
                os.close(backup)


def run(argv=None):
    class Parser(argparse.ArgumentParser):
        def error(self, message):
            raise PairRefused()
    previous = logging.root.manager.disable
    try:
        parser = Parser(description=__doc__)
        parser.add_argument('--run', action='store_true')
        parser.add_argument('--configuration', type=Path)
        parser.add_argument('--output-directory', type=Path)
        args = parser.parse_args(argv)
        if not args.run:
            if args.configuration is not None or args.output_directory is not None:
                raise PairRefused()
            plan = case_plan()
            languages = list(dict.fromkeys(query['language'] for query in plan['queries']))
            print(json.dumps({'status': 'synthetic_pair_plan', 'case_plan_sha256': plan_sha256(),
                'images': len(plan['images']), 'queries': len(plan['queries']),
                'languages': languages, 'models_loaded': False,
                'activation_performed': False, 'dialect_relevance_measured': False}, sort_keys=True))
            return 0
        if args.configuration is None or args.output_directory is None:
            raise PairRefused()
        logging.disable(logging.CRITICAL)
        with quiet_dependencies():
            result = execute(args.configuration, args.output_directory)
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0
    except Exception:
        print('{"error":"semantic_pair_canary_unavailable"}', file=sys.stderr)
        return 1
    finally:
        logging.disable(previous)


if __name__ == '__main__':
    raise SystemExit(run())
