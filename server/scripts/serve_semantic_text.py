#!/usr/bin/env python3
"""Explicit private configuration, offline probe, or loopback provider serving.

No listener, optional ML import, model load or file read occurs at import time.
"""
import argparse
from dataclasses import fields
import json
import logging
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from app.access.model_deployment import _load_private_document
from app.access.semantic_encoder import JointSpaceBinding, SemanticUnavailable
from app.access.visual_candidates import VectorSpaceIdentity
from semantic_openclip import OpenClipTextModel, PACKAGES, ARCHITECTURE


class ConfigurationError(ValueError):
    def __init__(self):
        super().__init__('invalid_semantic_provider_configuration')


def load_configuration(path, *, source_root=ROOT.parent, serving=False):
    try:
        value = _load_private_document(path, source_root=source_root)
        if (type(value) is not dict or set(value) != {'schema', 'architecture', 'checkpoint', 'bpe',
                'device', 'package_versions', 'binding', 'port', 'credential_file'}
                or value['schema'] != 'photohouse.semantic_text_provider.v1'
                or value['architecture'] != ARCHITECTURE or value['device'] not in ('cpu', 'cuda:0')
                or type(value['port']) is not int or not 1024 <= value['port'] <= 65535
                or type(value['package_versions']) is not dict or set(value['package_versions']) != PACKAGES
                or any(type(v) is not str or re.fullmatch(r'[A-Za-z0-9._+!-]{1,120}', v) is None
                       for v in value['package_versions'].values())):
            raise ConfigurationError()
        for key in ('checkpoint', 'bpe'):
            record = value[key]
            if (type(record) is not dict or set(record) != {'path', 'sha256'}
                    or type(record['path']) is not str or not Path(record['path']).is_absolute()
                    or '..' in Path(record['path']).parts
                    or Path(record['path']).is_relative_to(Path(source_root).resolve())
                    or type(record['sha256']) is not str
                    or re.fullmatch('[0-9a-f]{64}', record['sha256']) is None):
                raise ConfigurationError()
        binding = value['binding']
        if binding is not None:
            if type(binding) is not dict or set(binding) != {'image_identity', 'text_identity', 'qualification_sha256'}:
                raise ConfigurationError()
            identities = {}
            for key in ('image_identity', 'text_identity'):
                item = binding[key]
                if type(item) is not dict or set(item) != {field.name for field in fields(VectorSpaceIdentity)}:
                    raise ConfigurationError()
                identities[key] = VectorSpaceIdentity(**item)
            binding = JointSpaceBinding(**identities, qualification_sha256=binding['qualification_sha256'])
            if (binding.image_identity.artifact_sha256 != value['checkpoint']['sha256'] or
                    binding.text_identity.artifact_sha256 != value['checkpoint']['sha256'] or
                    binding.text_identity.dimension != 512):
                raise ConfigurationError()
        credential_file = value['credential_file']
        if credential_file is not None and (type(credential_file) is not str or
                not Path(credential_file).is_absolute() or '..' in Path(credential_file).parts or
                Path(credential_file).is_relative_to(Path(source_root).resolve())):
            raise ConfigurationError()
        if serving and (binding is None or type(value['credential_file']) is not str):
            raise ConfigurationError()
        value = dict(value, binding=binding)
        if serving:
            credential = _load_private_document(value['credential_file'], source_root=source_root)
            if (type(credential) is not dict or set(credential) != {'token'} or
                    type(credential['token']) is not str or
                    re.fullmatch(r'[A-Za-z0-9_-]{32,128}', credential['token'], flags=re.ASCII) is None):
                raise ConfigurationError()
            value['bearer_token'] = credential['token']
        return value
    except ConfigurationError:
        raise
    except Exception:
        raise ConfigurationError() from None


def load_model(configuration):
    model = OpenClipTextModel.load(
        checkpoint=configuration['checkpoint']['path'],
        checkpoint_sha256=configuration['checkpoint']['sha256'],
        bpe=configuration['bpe']['path'], bpe_sha256=configuration['bpe']['sha256'],
        architecture=configuration['architecture'], device=configuration['device'],
        package_versions=configuration['package_versions'])
    return model


def run(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('probe', 'serve'))
    parser.add_argument('--configuration', type=Path, required=True)
    values = parser.parse_args(argv)
    # Provider/library diagnostics can include local filenames. This dedicated
    # process emits only the fixed probe or error below, never request logs.
    previous_disable = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        configuration = load_configuration(values.configuration, serving=values.operation == 'serve')
        model = load_model(configuration)
        probe = model.probe()
        if values.operation == 'probe':
            print(json.dumps(probe, sort_keys=True, separators=(',', ':'), allow_nan=False))
            return 0
        model.bind(configuration['binding'])
        from app.access.semantic_provider_transport import create_provider_app
        import uvicorn
        application = create_provider_app(model, bearer_token=configuration['bearer_token'],
                                          port=configuration['port'])
        uvicorn.run(application, host='127.0.0.1', port=configuration['port'], workers=1,
                    access_log=False, log_config=None, proxy_headers=False,
                    forwarded_allow_ips='', timeout_keep_alive=1,
                    limit_concurrency=8, backlog=8, h11_max_incomplete_event_size=8192)
        return 0
    except Exception:
        print('{"error":"semantic_provider_unavailable"}', file=sys.stderr)
        return 1
    finally:
        logging.disable(previous_disable)


if __name__ == '__main__':
    raise SystemExit(run())
