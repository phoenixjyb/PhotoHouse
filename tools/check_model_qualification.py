#!/usr/bin/env python3
"""Review private model qualification evidence; hash only explicitly selected files."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'server' / 'backend'))
sys.path.insert(0, str(ROOT / 'tools'))
from app.access.model_deployment import DeploymentError, load_private_deployment
from app.access.model_qualification import (QualificationError, _canonical, load_private_audio_plan, load_private_qualification,
                                           selection_identity, validate_case_plan, verify_identity_files)
import model_catalog


class _Parser(argparse.ArgumentParser):
    def error(self, _message):
        raise QualificationError('invalid_arguments')


def main(argv=None):
    parser = _Parser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--evidence', type=Path)
    parser.add_argument('--audio-inputs', type=Path)
    parser.add_argument('--selection', choices=('current', 'rollback'), help='Plan branch, or expected evidence branch')
    parser.add_argument('--verify-files', action='store_true')
    parser.add_argument('--hash-timeout-seconds', type=float, default=120)
    try:
        args = parser.parse_args(argv)
        if args.evidence is None and args.verify_files:
            raise QualificationError('evidence_required')
        if not args.verify_files and args.hash_timeout_seconds != 120:
            raise QualificationError('file_verification_required')
        model_catalog.verify(ROOT)
        catalog = model_catalog._load(ROOT, 'models/catalog.json')
        plan = model_catalog._load(ROOT, 'models/quality-cases.json')
        suites = validate_case_plan(plan)
        deployment = load_private_deployment(args.manifest, catalog, source_root=ROOT)
        if args.evidence is None:
            audio = load_private_audio_plan(args.audio_inputs, plan, source_root=ROOT) if args.audio_inputs is not None else None
            selection = args.selection or 'current'
            roles = [role for role in sorted(suites) if deployment.resolve(role, rollback=selection == 'rollback') is not None]
            report = {'status': 'qualification_plan', 'selection_sha256': deployment.selection_sha256,
                      'selection': selection, 'case_plan_sha256': hashlib.sha256(_canonical(plan)).hexdigest(),
                      'audio_plan_sha256': hashlib.sha256(_canonical(audio)).hexdigest() if audio is not None else None,
                      'selection_identities': {role: selection_identity(deployment, role, selection=selection) for role in roles},
                      'cases': {role: [case['id'] for case in suites[role].values()] for role in roles},
                      'observations_collected': False, 'activation_performed': False}
        else:
            evidence = load_private_qualification(args.evidence, deployment, plan, source_root=ROOT,
                                                  now=datetime.now(timezone.utc), audio_plan_path=args.audio_inputs)
            if args.selection is not None and args.selection != evidence.report()['selection']:
                raise QualificationError('evidence_selection_mismatch')
            report = verify_identity_files(evidence, deployment, source_root=ROOT,
                                           timeout_seconds=args.hash_timeout_seconds) if args.verify_files else evidence.report()
    except (QualificationError, DeploymentError, model_catalog.CatalogError) as error:
        print(json.dumps({'status': 'refused', 'reason': str(error)}, sort_keys=True))
        return 1
    except (OSError, ValueError, TypeError, RecursionError):
        print(json.dumps({'status': 'refused', 'reason': 'qualification_unavailable'}, sort_keys=True))
        return 1
    print(json.dumps(report, sort_keys=True))
    # A syntactically valid record with failed/missing/stale observations is not
    # success. Even code 0 is evidence consistency, never activation authority.
    return 2 if report['status'] == 'scoped_evidence_incomplete' else 0


if __name__ == '__main__':
    raise SystemExit(main())
