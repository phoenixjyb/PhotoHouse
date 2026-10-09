#!/usr/bin/env python3
"""Export and import private human-review worksheets for qualification evidence.

This tool records operator-entered verdicts only. It never runs or probes a
model, reads generated media, or hashes identity artifacts.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'server' / 'backend'))
sys.path.insert(0, str(ROOT / 'tools'))

import model_catalog
from app.access.model_deployment import (DeploymentError, _load_private_document,
                                         load_private_deployment)
from app.access.model_qualification import (QualificationError, _canonical,
                                            load_private_audio_plan,
                                            selection_identity, validate_case_plan,
                                            validate_qualification)
from app.access.private_storage import require_private_directory, require_private_file


class ReviewError(ValueError):
    """Fixed refusal code that never exposes private evidence values."""


def _fail(reason: str) -> None:
    raise ReviewError(reason)


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _strict_json(path: Path, source_root: Path):
    try:
        return _load_private_document(path, source_root=source_root)
    except DeploymentError:
        _fail('private_input_unavailable')


def _safe_output_path(path: Path, source_root: Path) -> Path:
    if not path.is_absolute() or '..' in path.parts or path.exists() or path.is_symlink():
        _fail('output_location')
    resolved_root = source_root.resolve()
    if path.is_relative_to(resolved_root):
        _fail('output_location')
    # Reject links/reparse points in every existing parent component. The
    # private storage helper checks owner and ACL/mode on the selected parent.
    for parent in reversed(path.parents):
        try:
            info = parent.lstat()
        except OSError:
            _fail('output_location')
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            _fail('output_location')
    try:
        require_private_directory(path.parent)
    except (ValueError, OSError):
        _fail('output_private_storage')
    return path


def _write_exclusive(path: Path, payload: bytes, source_root: Path) -> None:
    path = _safe_output_path(path, source_root)
    descriptor = None
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0)
        if hasattr(os, 'O_NOFOLLOW'):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags, 0o600)
        # On Windows, inherited ACLs must be inspected before private payload
        # bytes are written. On POSIX this also proves owner-only permissions.
        require_private_file(path)
        with os.fdopen(descriptor, 'wb') as stream:
            descriptor = None
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        _fail('output_exists')
    except (OSError, ValueError):
        _fail('output_private_storage')
    finally:
        if descriptor is not None:
            os.close(descriptor)
            try:
                path.unlink()
            except OSError:
                pass


def _load_context(manifest_path: Path, evidence_path: Path, audio_path: Path | None):
    try:
        model_catalog.verify(ROOT)
        catalog = model_catalog._load(ROOT, 'models/catalog.json')
        case_plan = model_catalog._load(ROOT, 'models/quality-cases.json')
        suites = validate_case_plan(case_plan)
        deployment = load_private_deployment(manifest_path, catalog, source_root=ROOT)
        source = _strict_json(evidence_path, ROOT)
        if type(source) is not dict:
            _fail('qualification_input_invalid')
        # The review worksheet must be tied to the exact pre-run ASR inputs.
        # Never derive their hashes from case text or output observations.
        if audio_path is None and type(source.get('scope_roles')) is list:
            if any(role in {'assistant_asr', 'memory_asr'} for role in source['scope_roles']):
                _fail('audio_inputs_required')
        audio_plan = (load_private_audio_plan(audio_path, case_plan, source_root=ROOT)
                      if audio_path is not None else None)
        now = datetime.now(timezone.utc)
        validate_qualification(source, deployment, case_plan, now=now,
                               audio_plan=audio_plan)
        return source, deployment, case_plan, suites, audio_plan, now
    except ReviewError:
        raise
    except (QualificationError, DeploymentError, model_catalog.CatalogError):
        _fail('qualification_input_invalid')
    except (OSError, KeyError, TypeError, ValueError, RecursionError):
        _fail('qualification_input_unavailable')


def _worksheet(source, deployment, case_plan, suites, audio_plan):
    scope = source['scope_roles']
    records_by_role = {item['role']: item for item in source['records']}
    records = []
    for role in scope:
        source_record = records_by_role.get(role)
        if source_record is None:
            continue
        quality_by_case = {item['case_id']: item for item in source_record['quality']}
        for case_id, case in suites[role].items():
            result = quality_by_case.get(case_id)
            if result is None:
                continue
            if result['reviewed_by'] is not None or result['reviewed_at'] is not None or any(
                    verdict != 'unreviewed' for verdict in result['criteria'].values()):
                _fail('source_review_already_present')
            records.append({
                'role': role,
                'case_id': case_id,
                'input_sha256': result['input_sha256'],
                'output_sha256': result['output_sha256'],
                'criteria': [
                    {'id': criterion, 'definition': case_plan['criteria'][criterion],
                     'verdict': 'unreviewed'}
                    for criterion in case['criteria']
                ],
                'reviewed_by': None,
                'reviewed_at': None,
            })
    role_identities = {role: selection_identity(deployment, role, selection=source['selection'])
                       for role in scope}
    return {
        'schema': 1,
        'kind': 'photohouse-model-review-worksheet',
        'source_evidence_sha256': _digest(source),
        'selection_sha256': source['selection_sha256'],
        'selection': source['selection'],
        'selection_identities': role_identities,
        'case_plan_sha256': _digest(case_plan),
        'audio_plan_sha256': _digest(audio_plan) if audio_plan is not None else None,
        'scope_roles': list(scope),
        'records': records,
    }


def _check_source_unreviewed(source):
    for record in source['records']:
        for result in record['quality']:
            if (result['reviewed_by'] is not None or result['reviewed_at'] is not None
                    or any(value != 'unreviewed' for value in result['criteria'].values())):
                _fail('source_review_already_present')


def _review_mutations(worksheet, expected):
    if type(worksheet) is not dict or set(worksheet) != set(expected):
        _fail('worksheet_fields')
    if any(type(worksheet[key]) is not type(expected[key])
           or _canonical(worksheet[key]) != _canonical(expected[key])
           for key in expected if key != 'records'):
        _fail('worksheet_source_mismatch')
    entries = worksheet['records']
    baseline = expected['records']
    if type(entries) is not list or len(entries) != len(baseline):
        _fail('worksheet_inventory')
    changes = {}
    for entry, original in zip(entries, baseline):
        if type(entry) is not dict or set(entry) != set(original):
            _fail('worksheet_record_fields')
        for key in original:
            if key not in {'criteria', 'reviewed_by', 'reviewed_at'}:
                if (type(entry[key]) is not type(original[key])
                        or _canonical(entry[key]) != _canonical(original[key])):
                    _fail('worksheet_record_mismatch')
        criteria = entry['criteria']
        original_criteria = original['criteria']
        if type(criteria) is not list or len(criteria) != len(original_criteria):
            _fail('worksheet_criteria_inventory')
        verdicts = {}
        for criterion, fixed in zip(criteria, original_criteria):
            if type(criterion) is not dict or set(criterion) != {'id', 'definition', 'verdict'}:
                _fail('worksheet_criterion_fields')
            if (type(criterion['id']) is not type(fixed['id'])
                    or type(criterion['definition']) is not type(fixed['definition'])
                    or _canonical(criterion['id']) != _canonical(fixed['id'])
                    or _canonical(criterion['definition']) != _canonical(fixed['definition'])):
                _fail('worksheet_criterion_mismatch')
            if type(criterion['verdict']) is not str or criterion['verdict'] not in {
                    'unreviewed', 'passed', 'failed'}:
                _fail('worksheet_verdict')
            verdicts[criterion['id']] = criterion['verdict']
        reviewer, reviewed_at = entry['reviewed_by'], entry['reviewed_at']
        any_review = any(value != 'unreviewed' for value in verdicts.values())
        if reviewer is None and reviewed_at is None:
            if any_review:
                _fail('worksheet_reviewer_required')
        else:
            if type(reviewer) is not str or type(reviewed_at) is not str:
                _fail('worksheet_reviewer_required')
            # Final format and time bounds are enforced by the existing
            # qualification validator after merge.
            if not reviewer or not reviewed_at:
                _fail('worksheet_reviewer_required')
        changes[entry['role'], entry['case_id']] = (verdicts, reviewer, reviewed_at)
    return changes


def _merge(source, changes):
    result = deepcopy(source)
    for role_record in result['records']:
        for quality in role_record['quality']:
            update = changes.get((role_record['role'], quality['case_id']))
            if update is not None:
                quality['criteria'], quality['reviewed_by'], quality['reviewed_at'] = update
    return result


class _Parser(argparse.ArgumentParser):
    def error(self, _message):
        raise ReviewError('invalid_arguments')


def main(argv=None):
    parser = _Parser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True, parser_class=_Parser)
    for name in ('export', 'import'):
        command = commands.add_parser(name)
        command.add_argument('--manifest', type=Path, required=True)
        command.add_argument('--evidence', type=Path, required=True)
        command.add_argument('--audio-inputs', type=Path)
        command.add_argument('--output', type=Path, required=True)
        if name == 'import':
            command.add_argument('--worksheet', type=Path, required=True)
    try:
        args = parser.parse_args(argv)
        source, deployment, case_plan, suites, audio_plan, now = _load_context(
            args.manifest, args.evidence, args.audio_inputs)
        expected = _worksheet(source, deployment, case_plan, suites, audio_plan)
        if args.command == 'export':
            _check_source_unreviewed(source)
            payload_value = expected
            status = 'review_worksheet_exported'
        else:
            worksheet = _strict_json(args.worksheet, ROOT)
            changes = _review_mutations(worksheet, expected)
            merged = _merge(source, changes)
            # This preserves all run identity, resource and other unknown-to-
            # this tool values; only the established quality fields changed.
            validate_qualification(merged, deployment, case_plan, now=now, audio_plan=audio_plan)
            payload_value = merged
            status = 'qualification_evidence_written'
        payload = _canonical(payload_value) + b'\n'
        _write_exclusive(args.output, payload, ROOT)
        report = {
            'status': status,
            'scope_role_count': len(source['scope_roles']),
            'review_case_count': len(expected['records']),
            'source_evidence_sha256': expected['source_evidence_sha256'],
            'output_sha256': hashlib.sha256(payload).hexdigest(),
            'quality_independently_verified': False,
            'activation_performed': False,
        }
    except ReviewError as error:
        report = {'status': 'refused', 'reason': str(error)}
        print(json.dumps(report, sort_keys=True))
        return 1
    except (QualificationError, DeploymentError, model_catalog.CatalogError):
        report = {'status': 'refused', 'reason': 'qualification_input_invalid'}
        print(json.dumps(report, sort_keys=True))
        return 1
    except (OSError, TypeError, ValueError, RecursionError):
        report = {'status': 'refused', 'reason': 'review_unavailable'}
        print(json.dumps(report, sort_keys=True))
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
