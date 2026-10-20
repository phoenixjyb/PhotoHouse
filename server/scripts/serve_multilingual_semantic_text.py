#!/usr/bin/env python3
"""Explicit, pinned SigLIP2 loopback provider; plan-only without an operation.

Serving requires a private bearer credential and the exact image/text binding.
This provider does not enable or configure PhotoHouse semantic search.
"""
import argparse
import json
import logging
from pathlib import Path
import re
import sys

from semantic_siglip import SiglipModel
import qualify_multilingual_scenes as qualification
from qualify_semantic_pair import quiet_dependencies
from app.access.model_deployment import _load_private_document
from app.access.semantic_encoder import JointSpaceBinding
from app.access.visual_candidates import VectorSpaceIdentity


class ProviderRefused(ValueError):
    def __init__(self):
        super().__init__('multilingual_provider_unavailable')


def configuration(path, *, serving=False):
    value = _load_private_document(path, source_root=qualification.ROOT.parent)
    if (type(value) is not dict or set(value) != {'schema', 'model_directory', 'artifacts',
            'package_versions', 'binding', 'credential_file', 'port'}
            or value['schema'] != 'photohouse.multilingual_text_provider.v1'
            or type(value['model_directory']) is not str
            or value['artifacts'] != qualification.OFFICIAL_ARTIFACTS
            or value['package_versions'] != qualification.EXPECTED_PACKAGES
            or type(value['port']) is not int or not 1024 <= value['port'] <= 65535):
        raise ProviderRefused()
    binding = None
    if value['binding'] is not None:
        b = value['binding']
        if type(b) is not dict or set(b) != {'image_identity', 'text_identity', 'qualification_sha256'}:
            raise ProviderRefused()
        binding = JointSpaceBinding(VectorSpaceIdentity(**b['image_identity']),
            VectorSpaceIdentity(**b['text_identity']), b['qualification_sha256'])
        if binding.image_identity.dimension != qualification.DIMENSION:
            raise ProviderRefused()
    credential = value['credential_file']
    if credential is not None and (type(credential) is not str or not Path(credential).is_absolute()
            or '..' in Path(credential).parts or Path(credential).is_relative_to(qualification.ROOT.parent)):
        raise ProviderRefused()
    token = None
    if serving:
        if binding is None or credential is None:
            raise ProviderRefused()
        secret = _load_private_document(credential, source_root=qualification.ROOT.parent)
        if (type(secret) is not dict or set(secret) != {'token'} or type(secret['token']) is not str
                or re.fullmatch(r'[A-Za-z0-9_-]{32,128}', secret['token'], flags=re.ASCII) is None):
            raise ProviderRefused()
        token = secret['token']
    return value, binding, token


def run(argv=None):
    class Parser(argparse.ArgumentParser):
        def error(self, _message):
            raise ProviderRefused()
    try:
        parser = Parser(description=__doc__)
        parser.add_argument('operation', choices=('probe', 'serve'), nargs='?')
        parser.add_argument('--configuration', type=Path)
        args = parser.parse_args(argv)
        if args.operation is None:
            if args.configuration is not None:
                raise ProviderRefused()
            print(json.dumps({'status': 'multilingual_provider_plan', 'models_loaded': False,
                'private_files_read': False, 'listener_started': False, 'activation_performed': False}))
            return 0
        if args.configuration is None:
            raise ProviderRefused()
        previous = logging.root.manager.disable
        logging.disable(logging.CRITICAL)
        try:
            with quiet_dependencies():
                config, binding, token = configuration(args.configuration, serving=args.operation == 'serve')
                model = SiglipModel.load(model_directory=config['model_directory'],
                    artifacts=config['artifacts'], package_versions=config['package_versions'])
                if binding is not None:
                    model.bind(binding)
            if args.operation == 'probe':
                print(json.dumps({'model': model.receipt(), 'models_loaded': True,
                    'listener_started': False, 'activation_performed': False}, sort_keys=True))
                return 0
            from app.access.semantic_provider_transport import create_provider_app
            import uvicorn
            application = create_provider_app(model, bearer_token=token, port=config['port'])
            uvicorn.run(application, host='127.0.0.1', port=config['port'], workers=1,
                access_log=False, log_config=None, proxy_headers=False, forwarded_allow_ips='',
                timeout_keep_alive=1, limit_concurrency=8, backlog=8, h11_max_incomplete_event_size=8192)
            return 0
        finally:
            logging.disable(previous)
    except Exception:
        print('{"error":"multilingual_provider_unavailable"}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(run())
