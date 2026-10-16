#!/usr/bin/env python3
"""Offline measurements of an explicitly configured reviewed scene provider.

Requires existing inner/composite bindings. Creates no binding, listener,
activation or vector publication. Default planning reads no private inputs.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.access.model_deployment import _load_private_document
from app.access.private_storage import require_private_directory
from image_embedding_receipts import recipe_sha256, verify_checkpoint
from semantic_openclip import _source_pin, _current
from semantic_reviewed_projection import validate_projection_binding, ReviewedSemanticProvider
from semantic_scene_cases import validate_dataset, dataset_sha256
from qualify_semantic_pair import canonical, output_target, write_record, quiet_dependencies, IMAGE_PACKAGES
import qualify_semantic_scenes as scenes
import serve_reviewed_semantic_text as reviewed


class ReviewedSceneRefused(ValueError):
    def __init__(self):
        super().__init__('reviewed_scene_measurement_unavailable')


def configuration(path):
    value = _load_private_document(path, source_root=ROOT.parent)
    if (type(value) is not dict or set(value) != {'schema', 'provider_configuration',
            'dataset', 'image_package_versions', 'max_elapsed_seconds'}
            or value['schema'] != 'photohouse.reviewed_scene_run.v1'
            or type(value['provider_configuration']) is not str
            or type(value['dataset']) is not str
            or type(value['max_elapsed_seconds']) is not int
            or not 30 <= value['max_elapsed_seconds'] <= 1800
            or type(value['image_package_versions']) is not dict
            or set(value['image_package_versions']) != IMAGE_PACKAGES
            or any(type(v) is not str or re.fullmatch(r'[A-Za-z0-9._+!-]{1,120}', v) is None
                   for v in value['image_package_versions'].values())):
        raise ReviewedSceneRefused()
    provider = reviewed.load_configuration(Path(value['provider_configuration']))
    if provider['binding'] is None:
        raise ReviewedSceneRefused()
    source_digest, _pins = reviewed.implementation_receipt()
    validate_projection_binding(provider['encoder']['binding'], provider['projection'],
        provider['binding'], source_digest)
    dataset = validate_dataset(_load_private_document(value['dataset'], source_root=ROOT.parent))
    if not all(dataset['review'].values()):
        raise ReviewedSceneRefused()
    provenance = {case['id'] + ':' + language: provider['projection'].provenance(case['queries'][language])
        for case in dataset['cases'] for language in ('en', 'zh', 'zh-en')}
    return value, provider, dataset, provenance


def prepare(configuration):
    """Load the shared image/text model once, using the serving adapter unchanged."""
    source_digest, pins = reviewed.implementation_receipt()
    validate_projection_binding(configuration['encoder']['binding'], configuration['projection'],
        configuration['binding'], source_digest)

    def check_sources():
        for pin in pins:
            _current(pin)

    check_sources()
    model = reviewed.direct.load_model(configuration['encoder'])
    model.bind(configuration['encoder']['binding'])
    inner_probe = model.probe()
    for pin in pins:
        verify_checkpoint(pin)
    check_sources()
    provider = ReviewedSemanticProvider(model, configuration['projection'], configuration['binding'],
        adapter_source_sha256=source_digest, source_check=check_sources)
    return model, provider, {'schema': 'photohouse.reviewed_scene_preparation.v1',
        'encoder_document_sha256': configuration['encoder_document_sha256'],
        'inner_probe': inner_probe, 'provider': provider.probe(), 'activation_approved': False}


def execute(path, output, *, prepare_fn=None, measure_fn=None):
    config, provider_config, dataset, provenance = configuration(path)
    target = output_target(output)
    if {name: scenes.version(name) for name in IMAGE_PACKAGES} != config['image_package_versions']:
        raise ReviewedSceneRefused()
    image_pins = scenes.inspect_images(dataset)
    pins = (_source_pin(Path(__file__).resolve()), _source_pin(Path(scenes.__file__)))
    target.mkdir(mode=0o700)
    require_private_directory(target)
    write_record(target, 'started.json', {'schema': 'photohouse.reviewed_scene_started.v1',
        'configuration_sha256': recipe_sha256(config), 'dataset_sha256': dataset_sha256(dataset),
        'binding_sha256': provider_config['binding'].binding_sha256,
        'projection': provider_config['projection'].probe(),
        'query_count': len(provenance), 'image_count': len(dataset['images']),
        'complete_query_coverage': True, 'pair_binding_created': False, 'activation_performed': False})
    started = time.monotonic()
    deadline = started + config['max_elapsed_seconds']

    def check():
        if time.monotonic() >= deadline:
            raise ReviewedSceneRefused()
        for pin in pins:
            _current(pin)

    check()
    model, provider, probe = (prepare_fn or prepare)(provider_config)
    loading_seconds = time.monotonic() - started
    check()
    if (provider is None or provider.binding != provider_config['binding']
            or provider.inner_binding is not model.binding):
        raise ReviewedSceneRefused()
    record = (measure_fn or scenes.measure)(model, dataset, image_pins,
        config['image_package_versions'], deadline, reviewed_provider=provider)
    check()
    if (record['schema'] != 'photohouse.reviewed_scene_measurement.v1'
            or record['dataset_sha256'] != dataset_sha256(dataset)
            or set(record['query_receipts']) != set(provenance)):
        raise ReviewedSceneRefused()
    for key, receipt in record['query_receipts'].items():
        if receipt['original_query_sha256'] != provenance[key]['original_query_sha256']:
            raise ReviewedSceneRefused()
        receipt.update(provenance[key])
    record.update(provider_preparation=probe, model_loading_seconds=loading_seconds,
        observed_utc=datetime.now(timezone.utc).isoformat(), complete_query_coverage=True,
        evaluator_sources_sha256=[pin.sha256 for pin in pins])
    for pin in pins:
        verify_checkpoint(pin)
    check()
    write_record(target, 'measurement.json', record)
    return {'status': 'reviewed_scene_pair_measured', 'dataset_sha256': dataset_sha256(dataset),
        'measurement_sha256': hashlib.sha256(canonical(record) + b'\n').hexdigest(),
        'binding_sha256': provider.binding.binding_sha256,
        'overall': record['metrics']['overall'], 'languages': record['metrics']['languages'],
        'pair_binding_created': False, 'activation_performed': False,
        'serving_transport_measured': False, 'family_relevance_accepted': False,
        'dialect_relevance_measured': False, 'semantic_faithfulness_automatically_verified': False}


def run(argv=None):
    class Parser(argparse.ArgumentParser):
        def error(self, _message):
            raise ReviewedSceneRefused()
    previous = logging.root.manager.disable
    try:
        parser = Parser(description=__doc__)
        parser.add_argument('--run', action='store_true')
        parser.add_argument('--configuration', type=Path)
        parser.add_argument('--output-directory', type=Path)
        args = parser.parse_args(argv)
        if not args.run:
            if args.configuration is not None or args.output_directory is not None:
                raise ReviewedSceneRefused()
            print(json.dumps({'status': 'reviewed_scene_pair_plan',
                'requires_existing_bindings': True, 'complete_query_coverage_required': True,
                'languages': ['en', 'zh', 'zh-en'], 'models_loaded': False,
                'private_files_read': False, 'pair_binding_created': False,
                'activation_performed': False}, sort_keys=True))
            return 0
        if args.configuration is None or args.output_directory is None:
            raise ReviewedSceneRefused()
        logging.disable(logging.CRITICAL)
        with quiet_dependencies():
            result = execute(args.configuration, args.output_directory)
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0
    except Exception:
        print('{"error":"reviewed_scene_measurement_unavailable"}', file=sys.stderr)
        return 1
    finally:
        logging.disable(previous)


if __name__ == '__main__':
    raise SystemExit(run())
