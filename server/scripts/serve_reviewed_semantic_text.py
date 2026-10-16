#!/usr/bin/env python3
"""Plan, probe or explicitly serve a private reviewed scene-query projection.

No model, listener, private input or optional ML package is opened at import or
no-argument planning. This does not create or approve a real serving binding.
"""
import argparse
from dataclasses import asdict, fields, replace
import hashlib
import json
import logging
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from app.access.model_deployment import _load_private_document
from app.access.semantic_encoder import JointSpaceBinding
from app.access.visual_candidates import VectorSpaceIdentity
from image_embedding_receipts import verify_checkpoint
from semantic_openclip import _source_pin, _current
from qualify_semantic_pair import quiet_dependencies
import qualify_semantic_pair
import semantic_reviewed_projection as projection_module
import serve_semantic_text as direct
from semantic_reviewed_projection import (ReviewedProjection, ReviewedSemanticProvider,
    composition_recipe, validate_projection_binding)

_DIGEST = re.compile(r'[0-9a-f]{64}\Z', re.ASCII)
_TOKEN = re.compile(r'[A-Za-z0-9_-]{32,128}\Z', re.ASCII)


class ReviewedConfigurationError(ValueError):
    def __init__(self):
        super().__init__('invalid_reviewed_semantic_provider_configuration')


def document_sha256(document):
    """Canonical content hash; distinct from the private JSON file's byte hash."""
    return hashlib.sha256(json.dumps(document, sort_keys=True, separators=(',', ':'),
        ensure_ascii=True, allow_nan=False).encode('ascii')).hexdigest()


def _reference(value, source_root):
    if (type(value) is not dict or set(value) != {'path', 'document_sha256'}
            or type(value['path']) is not str
            or type(value['document_sha256']) is not str
            or _DIGEST.fullmatch(value['document_sha256']) is None):
        raise ReviewedConfigurationError()
    document = _load_private_document(value['path'], source_root=source_root)
    if document_sha256(document) != value['document_sha256']:
        raise ReviewedConfigurationError()
    return document


def _binding(value):
    if type(value) is not dict or set(value) != {'image_identity', 'text_identity', 'qualification_sha256'}:
        raise ReviewedConfigurationError()
    identities = {}
    for key in ('image_identity', 'text_identity'):
        if (type(value[key]) is not dict
                or set(value[key]) != {field.name for field in fields(VectorSpaceIdentity)}):
            raise ReviewedConfigurationError()
        identities[key] = VectorSpaceIdentity(**value[key])
    return JointSpaceBinding(**identities, qualification_sha256=value['qualification_sha256'])


def load_configuration(path, *, source_root=ROOT.parent, serving=False):
    try:
        value = _load_private_document(path, source_root=source_root)
        if (type(value) is not dict or set(value) != {'schema', 'encoder_configuration',
                'projection', 'binding', 'port', 'credential_file'}
                or value['schema'] != 'photohouse.reviewed_semantic_text_provider.v1'
                or type(value['port']) is not int or not 1024 <= value['port'] <= 65535):
            raise ReviewedConfigurationError()
        encoder_document = _reference(value['encoder_configuration'], source_root)
        encoder = direct.configuration_document(encoder_document, source_root=source_root)
        if encoder['binding'] is None:
            raise ReviewedConfigurationError()
        projection_document = _reference(value['projection'], source_root)
        projection = ReviewedProjection(projection_document,
            expected_sha256=value['projection']['document_sha256'])
        binding = None if value['binding'] is None else _binding(value['binding'])
        credential_path = value['credential_file']
        if credential_path is not None and (type(credential_path) is not str
                or not Path(credential_path).is_absolute() or '..' in Path(credential_path).parts
                or Path(credential_path).is_relative_to(Path(source_root).resolve())):
            raise ReviewedConfigurationError()
        result = {'encoder': encoder, 'projection': projection, 'binding': binding,
            'port': value['port'], 'encoder_document_sha256': value['encoder_configuration']['document_sha256']}
        if serving:
            if binding is None or type(credential_path) is not str:
                raise ReviewedConfigurationError()
            credential = _load_private_document(credential_path, source_root=source_root)
            if (type(credential) is not dict or set(credential) != {'token'}
                    or type(credential['token']) is not str or _TOKEN.fullmatch(credential['token']) is None):
                raise ReviewedConfigurationError()
            result['bearer_token'] = credential['token']
        return result
    except ReviewedConfigurationError:
        raise
    except Exception:
        raise ReviewedConfigurationError() from None


def implementation_receipt():
    """Pin the adapter, driver and protocol helpers without importing ML packages."""
    paths = {'projection': Path(projection_module.__file__), 'driver': Path(__file__),
        'configuration': Path(direct.__file__), 'diagnostics': Path(qualify_semantic_pair.__file__),
        'private_reader': ROOT/'backend/app/access/model_deployment.py',
        'private_storage': ROOT/'backend/app/access/private_storage.py',
        'vector_validation': ROOT/'backend/app/access/visual_candidates.py',
        'checkpoint_receipts': ROOT/'scripts/image_embedding_receipts.py',
        'provider_transport': ROOT/'backend/app/access/semantic_provider_transport.py',
        'encoder_protocol': ROOT/'backend/app/access/semantic_encoder.py'}
    pins = tuple(_source_pin(path) for path in paths.values())
    identity = {'schema': 'photohouse.reviewed_semantic_implementation.v1',
                'sources': {name: pin.sha256 for name, pin in zip(paths, pins)}}
    return document_sha256(identity), pins


def prepare_provider(configuration):
    """Validate the composite binding before loading an already qualified encoder."""
    source_digest, pins = implementation_receipt()
    inner_binding = configuration['encoder']['binding']
    projection = configuration['projection']
    binding = configuration['binding']
    recipe = composition_recipe(inner_binding, projection, source_digest)
    if binding is not None:
        validate_projection_binding(inner_binding, projection, binding, source_digest)

    def check_sources():
        for pin in pins:
            _current(pin)

    check_sources()
    model = direct.load_model(configuration['encoder'])
    model.bind(inner_binding)
    inner_probe = model.probe()
    for pin in pins:
        verify_checkpoint(pin)
    check_sources()
    provider = None if binding is None else ReviewedSemanticProvider(model, projection,
        binding, adapter_source_sha256=source_digest, source_check=check_sources)
    probe = {'schema': 'photohouse.reviewed_semantic_text_probe.v1',
        'policy': 'exact_reviewed_only', 'recipe': recipe, 'projection': projection.probe(),
        'encoder_document_sha256': configuration['encoder_document_sha256'],
        'expected_text_identity': asdict(replace(inner_binding.text_identity,
            preprocessing_sha256=recipe['recipe_sha256'])),
        'image_identity': asdict(inner_binding.image_identity), 'inner_probe': inner_probe,
        'binding_present': binding is not None, 'activation_approved': False,
        'native_serving_qualified': False, 'semantic_faithfulness_automatically_verified': False}
    return provider, probe


def run(argv=None):
    class Parser(argparse.ArgumentParser):
        def error(self, _message):
            raise ReviewedConfigurationError()
    previous = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        parser = Parser(description=__doc__)
        parser.add_argument('operation', nargs='?', default='plan', choices=('plan', 'probe', 'serve'))
        parser.add_argument('--configuration', type=Path)
        values = parser.parse_args(argv)
        if values.operation == 'plan':
            if values.configuration is not None:
                raise ReviewedConfigurationError()
            print(json.dumps({'schema': 'photohouse.reviewed_semantic_text_plan.v1',
                'policy': 'exact_reviewed_only', 'execution_performed': False,
                'requires_explicit_serve': True, 'original_query_preserved': True,
                'activation_performed': False}, sort_keys=True))
            return 0
        if values.configuration is None:
            raise ReviewedConfigurationError()
        configuration = load_configuration(values.configuration, serving=values.operation == 'serve')
        with quiet_dependencies():
            provider, probe = prepare_provider(configuration)
            if values.operation == 'serve':
                from app.access.semantic_provider_transport import create_provider_app
                import uvicorn
                app = create_provider_app(provider, bearer_token=configuration['bearer_token'],
                                          port=configuration['port'])
                uvicorn.run(app, host='127.0.0.1', port=configuration['port'], workers=1,
                    access_log=False, log_config=None, proxy_headers=False, forwarded_allow_ips='',
                    timeout_keep_alive=1, limit_concurrency=8, backlog=8,
                    h11_max_incomplete_event_size=8192)
        if values.operation == 'probe':
            print(json.dumps(probe, sort_keys=True, separators=(',', ':'), allow_nan=False))
        return 0
    except Exception:
        print('{"error":"reviewed_semantic_provider_unavailable"}', file=sys.stderr)
        return 1
    finally:
        logging.disable(previous)


if __name__ == '__main__':
    raise SystemExit(run())
