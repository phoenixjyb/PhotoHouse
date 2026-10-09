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
import model_catalog


class _Parser(argparse.ArgumentParser):
    def error(self, _message):
        # argparse's ordinary unknown-argument output can echo a private value.
        raise DeploymentError('invalid_arguments')


def main(argv=None):
    parser = _Parser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--json', action='store_true')
    try:
        args = parser.parse_args(argv)
        model_catalog.verify(ROOT)
        catalog = model_catalog._load(ROOT, 'models/catalog.json')
        result = load_private_deployment(args.manifest, catalog, source_root=ROOT).report()
    except (DeploymentError, model_catalog.CatalogError) as error:
        print(json.dumps({'status': 'refused', 'reason': str(error)}, sort_keys=True))
        return 1
    except (OSError, ValueError, TypeError):
        print(json.dumps({'status': 'refused', 'reason': 'configuration_unavailable'}, sort_keys=True))
        return 1
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print('Private model configuration valid; artifacts, runtime and quality not verified. No activation performed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
