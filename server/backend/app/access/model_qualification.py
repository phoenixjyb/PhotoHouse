"""Offline review of recorded observations, not a model runner or activation gate.

Private metadata loading and explicitly requested hashing perform file I/O. A record's observation or
human verdict is not independently established by validating its JSON shape.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import sys
import time

from .model_deployment import (DIGEST, ID, DeploymentError, _integer as _deployment_integer,
                               _match as _deployment_match, _object as _deployment_object,
                               _text as _deployment_text, _validated_snapshot, _load_private_document,
                               runtime_host_platform)

ROLES = {'assistant_asr', 'memory_asr', 'assistant_tts', 'narrative'}
FILE_KINDS = {'artifact', 'dependency_lock', 'preprocessing'}
MAX_FILE_BYTES = 64 * 1024 ** 3
MAX_TOTAL_BYTES = 128 * 1024 ** 3
MAX_HASH_SECONDS = 600
_SEAL = object()


class QualificationError(ValueError):
    """Fixed refusal code, never a private path, identity, output or reviewer."""


def _fail(reason):
    raise QualificationError(reason)


def _checked(check, *args):
    try:
        return check(*args)
    except DeploymentError as error:
        _fail(str(error))


def _object(*args):
    return _checked(_deployment_object, *args)


def _match(*args):
    return _checked(_deployment_match, *args)


def _integer(*args):
    return _checked(_deployment_integer, *args)


def _text(*args):
    return _checked(_deployment_text, *args)


def _canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                          allow_nan=False).encode('ascii')
    except (TypeError, ValueError, RecursionError):
        _fail('evidence_encoding')


def _timestamp(value):
    if type(value) is not str:
        _fail('evidence_timestamp')
    try:
        result = datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
    except ValueError:
        _fail('evidence_timestamp')
    if result.strftime('%Y-%m-%dT%H:%M:%SZ') != value:
        _fail('evidence_timestamp')
    return result


def _number(value, low, high):
    if type(value) not in (int, float) or not low <= value <= high or not math.isfinite(value):
        _fail('evidence_measurement')


def validate_case_plan(plan):
    """Validate source-maintained review recipes, without making synthetic audio."""
    _object(plan, {'schema', 'kind', 'suites', 'criteria'}, 'case_plan_fields')
    if type(plan['schema']) is not int or plan['schema'] != 1 or plan['kind'] != 'photohouse-model-quality-cases':
        _fail('case_plan_version')
    if type(plan['suites']) is not list or not 1 <= len(plan['suites']) <= len(ROLES):
        _fail('case_plan_inventory')
    suites = {}
    if type(plan['criteria']) is not dict or not 1 <= len(plan['criteria']) <= 32:
        _fail('case_rubric')
    for criterion, definition in plan['criteria'].items():
        _match(criterion, ID, 'case_rubric')
        _text(definition, 2048, 'case_rubric')
    for suite in plan['suites']:
        _object(suite, {'role', 'cases'}, 'case_suite_fields')
        role = suite['role']
        if type(role) is not str or role not in ROLES or role in suites:
            _fail('case_suite_role')
        if type(suite['cases']) is not list or not 1 <= len(suite['cases']) <= 8:
            _fail('case_inventory')
        cases = {}
        for case in suite['cases']:
            _object(case, {'id', 'input_kind', 'input_text', 'input_sha256', 'criteria'}, 'case_fields')
            _match(case['id'], ID, 'case_identity')
            if case['id'] in cases:
                _fail('case_identity')
            kind = 'wav' if role in {'assistant_asr', 'memory_asr'} else 'text' if role == 'assistant_tts' else 'bundle'
            if case['input_kind'] != kind:
                _fail('case_input_kind')
            if kind == 'bundle':
                if case['input_text'] is not None:
                    _fail('case_input')
                _match(case['input_sha256'], DIGEST, 'case_input')
            else:
                _text(case['input_text'], 2048, 'case_input')
                if kind == 'wav':
                    if case['input_sha256'] is not None:
                        _fail('case_input')
                elif case['input_sha256'] != hashlib.sha256(case['input_text'].encode('utf-8')).hexdigest():
                    _fail('case_input')
            if type(case['criteria']) is not list or not 1 <= len(case['criteria']) <= 12:
                _fail('case_criteria')
            for criterion in case['criteria']:
                _match(criterion, ID, 'case_criteria')
                if criterion not in plan['criteria']:
                    _fail('case_rubric')
            if len(set(case['criteria'])) != len(case['criteria']):
                _fail('case_criteria')
            cases[case['id']] = case
        suites[role] = cases
    return suites


def _input_plan(plan, suites, plan_digest):
    """Separate private, pre-run audio inventory; never inherit result hashes."""
    if plan is None:
        return {}
    _object(plan, {'schema', 'kind', 'case_plan_sha256', 'inputs'}, 'audio_plan_fields')
    if type(plan['schema']) is not int or plan['schema'] != 1 or plan['kind'] != 'photohouse-model-audio-inputs':
        _fail('audio_plan_version')
    if plan['case_plan_sha256'] != plan_digest:
        _fail('audio_plan_case_mismatch')
    if type(plan['inputs']) is not list or not 1 <= len(plan['inputs']) <= 16:
        _fail('audio_plan_inventory')
    inputs = {}
    for entry in plan['inputs']:
        _object(entry, {'role', 'case_id', 'input_sha256', 'file'}, 'audio_input_fields')
        role, case_id = entry['role'], entry['case_id']
        if type(role) is not str or role not in {'assistant_asr', 'memory_asr'} or role not in suites:
            _fail('audio_input_role')
        if type(case_id) is not str or case_id not in suites[role] or (role, case_id) in inputs:
            _fail('audio_input_case')
        _match(entry['input_sha256'], DIGEST, 'audio_input_identity')
        _text(entry['file'], 2048, 'audio_input_file')
        inputs[role, case_id] = entry
    return inputs


def selection_identity(deployment, role, *, selection='current'):
    """Hash the exact branch/role/provider/runtime/artifact declaration."""
    if not _validated_snapshot(deployment):
        _fail('validated_deployment_required')
    if type(selection) is not str or selection not in {'current', 'rollback'}:
        _fail('evidence_selection')
    if type(role) is not str or role not in ROLES:
        _fail('evidence_role')
    resolved = deployment.resolve(role, rollback=selection == 'rollback')
    if resolved is None:
        _fail('evidence_binding_missing')
    return hashlib.sha256(_canonical({'selection': selection, 'resolved': resolved})).hexdigest()


def _resource_gaps(observation, budget, device, window_seconds, role):
    if observation is None:
        return ['resource_observations_missing']
    _object(observation, {'method', 'capture_sha256', 'sample_count', 'window_seconds',
                          'peak_ram_mib', 'minimum_free_ram_mib', 'minimum_free_vram_mib',
                          'peak_concurrency', 'maximum_request_seconds'}, 'resource_observation_fields')
    if type(observation['method']) is not str or observation['method'] not in {'owned_process_tree', 'identified_service_processes'}:
        _fail('resource_measurement_method')
    _match(observation['capture_sha256'], DIGEST, 'resource_capture_identity')
    _integer(observation['sample_count'], 2, 1000000, 'resource_sample_count')
    _number(observation['window_seconds'], 0.001, window_seconds)
    for key in ('peak_ram_mib', 'minimum_free_ram_mib', 'minimum_free_vram_mib'):
        _number(observation[key], 0, 1024 * 1024)
    _integer(observation['peak_concurrency'], 1, 1024, 'resource_observed_concurrency')
    _number(observation['maximum_request_seconds'], 0.001, observation['window_seconds'])
    if device['kind'] == 'cpu' and observation['minimum_free_vram_mib'] != 0:
        _fail('resource_observed_device')
    cap = 60 if role in {'assistant_asr', 'assistant_tts'} else 30
    tests = (
        ('ram_budget_exceeded', observation['peak_ram_mib'] <= budget['ram_limit_mib']),
        ('ram_headroom_below_floor', observation['minimum_free_ram_mib'] >= budget['minimum_free_ram_mib']),
        ('vram_headroom_below_floor', observation['minimum_free_vram_mib'] >= budget['vram_floor_mib']),
        ('concurrency_budget_exceeded', observation['peak_concurrency'] <= budget['max_concurrency']),
        ('request_budget_exceeded', observation['maximum_request_seconds'] <= min(budget['timeout_seconds'], cap)),
    )
    return [reason for reason, passed in tests if not passed]


def _quality_gaps(results, cases, started, now, role, audio_inputs):
    if type(results) is not list or len(results) > len(cases):
        _fail('quality_inventory')
    seen = set()
    gaps = []
    if role in {'assistant_asr', 'memory_asr'} and any((role, ident) not in audio_inputs for ident in cases):
        gaps.append('quality_audio_input_unpinned')
    for result in results:
        _object(result, {'case_id', 'input_sha256', 'output_sha256', 'criteria',
                         'reviewed_by', 'reviewed_at'}, 'quality_result_fields')
        ident = result['case_id']
        if type(ident) is not str or ident not in cases or ident in seen:
            _fail('quality_case_identity')
        seen.add(ident)
        case = cases[ident]
        for key in ('input_sha256', 'output_sha256'):
            _match(result[key], DIGEST, 'quality_capture_identity')
        pinned = case['input_sha256']
        if case['input_kind'] == 'wav':
            audio = audio_inputs.get((role, ident))
            if audio is None:
                gaps.append('quality_audio_input_unpinned')
            else:
                pinned = audio['input_sha256']
        if pinned is not None and result['input_sha256'] != pinned:
            gaps.append('quality_input_mismatch')
        _object(result['criteria'], set(case['criteria']), 'quality_criteria_fields')
        for verdict in result['criteria'].values():
            if type(verdict) is not str or verdict not in {'passed', 'failed', 'unreviewed'}:
                _fail('quality_verdict')
        if result['reviewed_by'] is None and result['reviewed_at'] is None:
            if any(verdict != 'unreviewed' for verdict in result['criteria'].values()):
                _fail('quality_reviewer_required')
            gaps.append('quality_review_missing')
        else:
            _match(result['reviewed_by'], ID, 'quality_reviewer')
            reviewed = _timestamp(result['reviewed_at'])
            if not started <= reviewed <= now:
                _fail('quality_review_time')
        if 'failed' in result['criteria'].values():
            gaps.append('quality_review_failed')
        if 'unreviewed' in result['criteria'].values():
            gaps.append('quality_review_incomplete')
    if seen != set(cases):
        gaps.append('quality_cases_missing')
    return sorted(set(gaps))


@dataclass(frozen=True, init=False, repr=False)
class QualificationEvidence:
    _payload: bytes = field(repr=False)
    _summary: bytes = field(repr=False)
    _inputs: bytes = field(repr=False)
    _seal: object = field(repr=False)
    _integrity: tuple = field(repr=False)

    def __init__(self, *args, **kwargs):
        raise TypeError('Use validate_qualification to create evidence')

    def report(self):
        if not _valid_evidence(self):
            _fail('validated_evidence_required')
        return json.loads(self._summary)


def _valid_evidence(value):
    return (type(value) is QualificationEvidence and getattr(value, '_seal', None) is _SEAL
            and type(getattr(value, '_payload', None)) is bytes
            and type(getattr(value, '_summary', None)) is bytes
            and type(getattr(value, '_inputs', None)) is bytes
            and getattr(value, '_integrity', None) == (hashlib.sha256(value._payload).digest(),
                                                     hashlib.sha256(value._summary).digest(),
                                                     hashlib.sha256(value._inputs).digest()))


def validate_qualification(document, deployment, case_plan, *, now, audio_plan=None):
    """Compare bounded recorded observations. No observations are collected here."""
    if not _validated_snapshot(deployment):
        _fail('validated_deployment_required')
    if type(now) is not datetime or now.tzinfo is None or now.utcoffset() != timedelta(0):
        _fail('evidence_clock_required')
    suites = validate_case_plan(case_plan)
    _object(document, {'schema', 'kind', 'selection_sha256', 'selection', 'case_plan_sha256',
                       'audio_plan_sha256', 'scope_roles', 'platform', 'started_at', 'ended_at', 'records'}, 'evidence_fields')
    if type(document['schema']) is not int or document['schema'] != 1 or document['kind'] != 'photohouse-model-qualification':
        _fail('evidence_version')
    if document['selection_sha256'] != deployment.selection_sha256:
        _fail('evidence_manifest_mismatch')
    plan_digest = hashlib.sha256(_canonical(case_plan)).hexdigest()
    if document['case_plan_sha256'] != plan_digest:
        _fail('evidence_case_plan_mismatch')
    audio_inputs = _input_plan(audio_plan, suites, plan_digest)
    audio_digest = hashlib.sha256(_canonical(audio_plan)).hexdigest() if audio_plan is not None else None
    if document['audio_plan_sha256'] != audio_digest:
        _fail('evidence_audio_plan_mismatch')
    scope = document['scope_roles']
    if type(scope) is not list or not 1 <= len(scope) <= len(ROLES):
        _fail('evidence_scope')
    if any(type(role) is not str or role not in suites for role in scope) or len(set(scope)) != len(scope):
        _fail('evidence_scope')
    for role in scope:
        selection_identity(deployment, role, selection=document['selection'])
    if type(document['platform']) is not str or document['platform'] not in {'windows', 'linux', 'macos'}:
        _fail('evidence_platform')
    if type(document['selection']) is not str or document['selection'] not in {'current', 'rollback'}:
        _fail('evidence_selection')
    started, ended = _timestamp(document['started_at']), _timestamp(document['ended_at'])
    window = (ended - started).total_seconds()
    if not 0 < window <= 21600 or ended > now:
        _fail('evidence_window')
    stale = now - started > timedelta(days=30)
    records = document['records']
    if type(records) is not list or len(records) > len(scope):
        _fail('evidence_inventory')
    role_reports = {}
    host_platforms = {}
    for record in records:
        _object(record, {'role', 'selection_identity_sha256', 'observed_identity',
                         'runtime_capture_sha256', 'files', 'resources', 'quality'}, 'evidence_record_fields')
        role = record['role']
        if type(role) is not str or role not in scope or role in role_reports:
            _fail('evidence_role')
        if record['selection_identity_sha256'] != selection_identity(deployment, role, selection=document['selection']):
            _fail('evidence_provider_mismatch')
        resolved = deployment.resolve(role, rollback=document['selection'] == 'rollback')
        runtime, artifact = resolved['runtime'], resolved['artifact']
        if document['platform'] != runtime['platform']:
            _fail('evidence_platform_mismatch')
        host_platforms[role] = runtime_host_platform(runtime)
        _match(record['runtime_capture_sha256'], DIGEST, 'runtime_capture_identity')
        expected = {'runtime_version': runtime['runtime_version'], 'implementation': runtime['implementation'],
                    'dependency_lock_sha256': runtime['dependency_lock_sha256'], 'device': runtime['device'],
                    'artifact_sha256': artifact['identity_sha256'], 'preprocessing_sha256': artifact['preprocessing_sha256']}
        if 'placement' in runtime:
            expected['placement'] = runtime['placement']
        # Observed values may be unknown/mismatched. They are private and never
        # become defaults copied from declarations by this validator.
        observed = _object(record['observed_identity'], set(expected), 'observed_identity_fields')
        _object(record['files'], FILE_KINDS, 'evidence_file_fields')
        for value in record['files'].values():
            if value is not None:
                _text(value, 2048, 'evidence_file_path')
        matches = _canonical(observed) == _canonical(expected)
        gaps = ['observed_identity_mismatch'] if not matches else []
        if any(value is None for value in record['files'].values()):
            gaps.append('identity_files_missing')
        resource_gaps = _resource_gaps(record['resources'], runtime['resources'], runtime['device'], window, role)
        gaps.extend(resource_gaps)
        gaps.extend(_quality_gaps(record['quality'], suites[role], started, now, role, audio_inputs))
        if stale:
            gaps.append('evidence_stale')
        role_reports[role] = {'gaps': sorted(set(gaps)), 'recorded_identity_matches': matches,
                              'recorded_resources_within_budget': not resource_gaps,
                              'recorded_quality_review_passed': not any(g.startswith('quality_') for g in gaps)}
    for role in set(scope) - set(role_reports):
        role_reports[role] = {'gaps': ['role_record_missing'], 'recorded_identity_matches': False,
                              'recorded_resources_within_budget': False, 'recorded_quality_review_passed': False}
    declared_roles = deployment.report()['rollback_declared_roles' if document['selection'] == 'rollback' else 'selected_roles']
    summary = {'status': 'scoped_evidence_incomplete' if any(r['gaps'] for r in role_reports.values()) else 'scoped_evidence_consistent',
               'selection_sha256': deployment.selection_sha256, 'selection': document['selection'],
               'case_plan_sha256': plan_digest, 'audio_plan_sha256': audio_digest,
               'scope_roles': sorted(scope), 'other_declared_roles': sorted(set(declared_roles) - set(scope)),
               'execution_platform': document['platform'], 'host_platforms': host_platforms,
               'records': role_reports, 'complete_deployment_qualification': False,
               'files_verified': False, 'provider_probed': False, 'device_verified': False,
               'runtime_environment_verified': False, 'quality_independently_verified': False,
               'resources_enforced': False, 'shared_memory_item_budget_verified': False, 'activation_performed': False}
    evidence = object.__new__(QualificationEvidence)
    payload = _canonical(document)
    if len(payload) > 128 * 1024:
        _fail('evidence_too_large')
    object.__setattr__(evidence, '_payload', payload)
    object.__setattr__(evidence, '_summary', _canonical(summary))
    object.__setattr__(evidence, '_inputs', _canonical(audio_plan))
    object.__setattr__(evidence, '_seal', _SEAL)
    object.__setattr__(evidence, '_integrity', (hashlib.sha256(evidence._payload).digest(),
                                             hashlib.sha256(evidence._summary).digest(),
                                             hashlib.sha256(evidence._inputs).digest()))
    return evidence


def load_private_qualification(path, deployment, case_plan, *, source_root, now, audio_plan_path=None):
    try:
        document = _load_private_document(path, source_root=source_root)
        audio_plan = _load_private_document(audio_plan_path, source_root=source_root) if audio_plan_path is not None else None
        return validate_qualification(document, deployment, case_plan, now=now, audio_plan=audio_plan)
    except DeploymentError:
        _fail('private_evidence_unavailable')


def load_private_audio_plan(path, case_plan, *, source_root):
    """Read a pre-run private audio inventory; no audio file is inspected."""
    try:
        plan = _load_private_document(path, source_root=source_root)
        _input_plan(plan, validate_case_plan(case_plan), hashlib.sha256(_canonical(case_plan)).hexdigest())
        return plan
    except DeploymentError:
        _fail('private_evidence_unavailable')


def _regular_path(path, source_root):
    if not path.is_absolute() or '..' in path.parts or path.is_relative_to(Path(source_root).resolve()):
        _fail('identity_file_location')
    for parent in (*reversed(path.parents), path):
        info = parent.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            _fail('identity_file_link')
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or not 1 <= info.st_size <= MAX_FILE_BYTES:
        _fail('identity_file_size_or_kind')
    return info


def _hash_file(path, *, source_root, deadline):
    """Stream a nonempty regular file stably; no path search, links or copies."""
    before = _regular_path(path, source_root)
    if time.monotonic() >= deadline:
        _fail('identity_hash_deadline')
    digest = hashlib.sha256()
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0))
    with os.fdopen(fd, 'rb') as stream:
        opened = os.fstat(stream.fileno())
        if _stat_identity(opened) != _stat_identity(before) or not stat.S_ISREG(opened.st_mode):
            _fail('identity_file_changed')
        count = 0
        while True:
            if time.monotonic() >= deadline:
                _fail('identity_hash_deadline')
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            count += len(chunk)
            if count > before.st_size:
                _fail('identity_file_changed')
            digest.update(chunk)
        after = os.fstat(stream.fileno())
    final = _regular_path(path, source_root)
    if count != before.st_size or _stat_identity(before) != _stat_identity(after) or _stat_identity(before) != _stat_identity(final):
        _fail('identity_file_changed')
    if time.monotonic() >= deadline:
        _fail('identity_hash_deadline')
    return digest.hexdigest(), _stat_identity(final)


def _stat_identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _verify_identity_files(evidence, deployment, *, source_root, timeout_seconds=120):
    """Explicitly hash up to 28 declared files against the validated selections.

    Does not load weights, probe a process, verify transitive blobs or reproduce
    runtime/GPU/quality measurements. The soft deadline cannot interrupt a blocked
    filesystem read; use an operator-owned process deadline for such hosts.
    """
    if not _valid_evidence(evidence):
        _fail('validated_evidence_required')
    _number(timeout_seconds, 0.001, MAX_HASH_SECONDS)
    report = evidence.report()
    if not _validated_snapshot(deployment) or report['selection_sha256'] != deployment.selection_sha256:
        _fail('evidence_manifest_mismatch')
    document = json.loads(evidence._payload)
    if document['platform'] != {'darwin': 'macos', 'win32': 'windows', 'linux': 'linux'}.get(sys.platform):
        _fail('identity_file_platform_mismatch')
    deadline = time.monotonic() + timeout_seconds
    cache = {}
    total_bytes = 0
    def check(value, digest):
        nonlocal total_bytes
        if value is None:
            _fail('identity_files_missing')
        path = Path(value)
        if path not in cache:
            total_bytes += _regular_path(path, source_root).st_size
            if total_bytes > MAX_TOTAL_BYTES:
                _fail('identity_files_total_size')
            cache[path] = _hash_file(path, source_root=source_root, deadline=deadline)
        if cache[path][0] != digest:
            _fail('identity_file_hash_mismatch')
    if set(report['scope_roles']) != {record['role'] for record in document['records']}:
        _fail('identity_role_record_missing')
    for record in document['records']:
        resolved = deployment.resolve(record['role'], rollback=report['selection'] == 'rollback')
        expected = {'artifact': resolved['artifact']['identity_sha256'],
                    'dependency_lock': resolved['runtime']['dependency_lock_sha256'],
                    'preprocessing': resolved['artifact']['preprocessing_sha256']}
        for kind, value in record['files'].items():
            check(value, expected[kind])
    audio_plan = json.loads(evidence._inputs)
    if audio_plan is not None:
        for entry in audio_plan['inputs']:
            if entry['role'] in report['scope_roles']:
                check(entry['file'], entry['input_sha256'])
    if any('quality_audio_input_unpinned' in record['gaps'] for record in report['records'].values()):
        _fail('audio_input_plan_missing')
    for path, (_, identity) in cache.items():
        if _stat_identity(_regular_path(path, source_root)) != identity:
            _fail('identity_file_changed')
    if time.monotonic() >= deadline:
        _fail('identity_hash_deadline')
    report['files_verified'] = True
    report['unique_files_hashed'] = len(cache)
    return report


def verify_identity_files(evidence, deployment, *, source_root, timeout_seconds=120):
    """Redacted public wrapper for the explicitly requested stable file reads."""
    try:
        return _verify_identity_files(evidence, deployment, source_root=source_root,
                                      timeout_seconds=timeout_seconds)
    except OSError:
        _fail('identity_file_unavailable')
