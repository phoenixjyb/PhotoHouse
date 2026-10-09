#!/usr/bin/env python3
"""Validate one private model selection offline; never apply it or probe a model."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'server' / 'backend'))
sys.path.insert(0, str(ROOT / 'tools'))

from app.access.model_deployment import DeploymentError, load_private_deployment
from app.access.model_binding import ModelBindingError, TARGET_ROLES, project_configuration
import model_catalog


class _Parser(argparse.ArgumentParser):
    def error(self, _message):
        # argparse's ordinary unknown-argument output can echo a private value.
        raise DeploymentError('invalid_arguments')


def main(argv=None):
    parser = _Parser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--project', choices=sorted(TARGET_ROLES))
    parser.add_argument('--platform', choices=('windows', 'linux', 'macos'))
    parser.add_argument('--feature-enabled', action='store_true')
    try:
        args = parser.parse_args(argv)
        if args.project is None and (args.platform is not None or args.feature_enabled):
            raise DeploymentError('projection_target_required')
        model_catalog.verify(ROOT)
        catalog = model_catalog._load(ROOT, 'models/catalog.json')
        deployment = load_private_deployment(args.manifest, catalog, source_root=ROOT)
        result = deployment.report() if args.project is None else project_configuration(
            deployment, target=args.project, platform=args.platform,
            feature_enabled=args.feature_enabled).report()
    except (DeploymentError, ModelBindingError, model_catalog.CatalogError) as error:
        print(json.dumps({'status': 'refused', 'reason': str(error)}, sort_keys=True))
        return 1
    except (OSError, ValueError, TypeError):
        print(json.dumps({'status': 'refused', 'reason': 'configuration_unavailable'}, sort_keys=True))
        return 1
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        noun = 'projection' if args.project else 'configuration'
        print(f'Private model {noun} valid; artifacts, runtime and quality not verified. No activation performed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
