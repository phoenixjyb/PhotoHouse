"""Private, offline provider selection records; never an inference controller.

Validation checks declared metadata and graph consistency. It does not establish
installed artifacts, runtime compatibility, available resources or model quality.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from urllib.parse import urlsplit

from .private_storage import require_private_directory, require_private_file

MAX_BYTES = 128 * 1024
ID = re.compile(r'[a-z0-9][a-z0-9._-]{0,63}\Z', re.ASCII)
DIGEST = re.compile(r'[0-9a-f]{64}\Z', re.ASCII)
REVISION = re.compile(r'(?:[0-9a-f]{40}|[0-9a-f]{64})\Z', re.ASCII)
ENV = re.compile(r'[A-Z][A-Z0-9_]{0,127}\Z', re.ASCII)
VECTOR_ROLES = {'face_embedding', 'image_embedding', 'video_embedding', 'text_embedding'}
TEXT_ROLES = {'annotation_polish', 'narrative', 'title_suggestions'}
# The inventory also names implementations behind adapters. These are not
# interchangeable with the reviewed HTTP request adapters for these roles.
INVENTORY_ONLY_ADAPTERS = {'CaptionSubprocessProvider', 'WindowsSystemSpeech'}
WSL_HTTP_ROLES = {'assistant_asr', 'memory_asr', 'assistant_tts', *TEXT_ROLES}
_VALIDATION_SEAL = object()


class DeploymentError(ValueError):
    """A fixed reason with no paths, model names, endpoint values or credentials."""


def _fail(reason):
    raise DeploymentError(reason)


def _object(value, keys, reason):
    if type(value) is not dict or set(value) != keys:
        _fail(reason)
    return value


def _text(value, limit, reason):
    if (type(value) is not str or not value or value != value.strip()
            or len(value.encode('utf-8', errors='replace')) > limit
            or any(ord(c) < 32 or 0x7f <= ord(c) < 0xa0 or 0xd800 <= ord(c) <= 0xdfff for c in value)):
        _fail(reason)
    return value


def _match(value, pattern, reason):
    if type(value) is not str or pattern.fullmatch(value) is None:
        _fail(reason)
    return value


def _integer(value, low, high, reason):
    if type(value) is not int or not low <= value <= high:
        _fail(reason)


def _choice(value, choices, reason):
    if type(value) is not str or value not in choices:
        _fail(reason)


def _reference_url(value):
    _text(value, 1024, 'invalid_reference_url')
    try:
        parts = urlsplit(value)
        if (parts.scheme != 'https' or not parts.hostname or parts.username is not None
                or parts.password is not None or parts.query or parts.fragment
                or any(c.isspace() for c in value)):
            _fail('invalid_reference_url')
        parts.port
    except ValueError:
        _fail('invalid_reference_url')


def _endpoint(value, role):
    _text(value, 1024, 'invalid_local_endpoint')
    try:
        parts = urlsplit(value)
        if (parts.scheme != 'http' or parts.hostname not in {'127.0.0.1', 'localhost'}
                or not parts.port or parts.username is not None or parts.password is not None
                or parts.query or parts.fragment or any(c.isspace() for c in value)):
            _fail('invalid_local_endpoint')
        if role in TEXT_ROLES and parts.path.rstrip('/') not in {'', '/api/generate'}:
            _fail('invalid_local_endpoint')
        if role in {'assistant_asr', 'memory_asr', 'assistant_tts'} and not parts.path.startswith('/'):
            _fail('invalid_local_endpoint')
    except ValueError:
        _fail('invalid_local_endpoint')


def _records(value, maximum, reason):
    if type(value) is not list or not 1 <= len(value) <= maximum:
        _fail(reason)
    records = {}
    for record in value:
        if type(record) is not dict:
            _fail(reason)
        ident = _match(record.get('id'), ID, reason)
        if ident in records:
            _fail(reason)
        records[ident] = record
    return records


def _runtime(record, schema):
    keys = {'id', 'execution_mode', 'platform', 'environment_id', 'runtime_version',
            'dependency_lock_sha256', 'implementation', 'device', 'resources'}
    _object(record, keys | ({'placement'} if schema == 2 else set()), 'runtime_fields')
    _choice(record['execution_mode'], {'http_service', 'loopback_http', 'bounded_child', 'in_process'}, 'runtime_mode')
    _choice(record['platform'], {'windows', 'linux', 'macos'}, 'runtime_platform')
    if schema == 2:
        placement = _object(record['placement'], {'kind', 'host_platform', 'instance'}, 'placement_fields')
        _choice(placement['host_platform'], {'windows', 'linux', 'macos'}, 'placement_host_platform')
        _choice(placement['kind'], {'native', 'wsl2'}, 'placement_kind')
        if placement['kind'] == 'native':
            if placement['host_platform'] != record['platform'] or placement['instance'] is not None:
                _fail('native_placement_identity')
        else:
            if (placement['host_platform'] != 'windows' or record['platform'] != 'linux'
                    or record['execution_mode'] != 'loopback_http'):
                _fail('wsl_placement_contract')
            _text(placement['instance'], 120, 'wsl_instance_identity')
    _match(record['environment_id'], ID, 'runtime_environment')
    _text(record['runtime_version'], 120, 'runtime_version')
    _match(record['dependency_lock_sha256'], DIGEST, 'runtime_lock_identity')
    implementation = _object(record['implementation'], {'repository', 'revision'}, 'implementation_fields')
    _reference_url(implementation['repository'])
    _match(implementation['revision'], REVISION, 'implementation_revision')
    device = _object(record['device'], {'kind', 'index', 'hardware_id'}, 'device_fields')
    if device['kind'] == 'cpu':
        if device['index'] is not None or device['hardware_id'] is not None:
            _fail('cpu_device_identity')
    elif device['kind'] == 'cuda':
        _integer(device['index'], 0, 15, 'cuda_device_index')
        if type(device['hardware_id']) is not str or re.fullmatch(r'GPU-[0-9a-fA-F-]{8,64}', device['hardware_id']) is None:
            _fail('cuda_device_identity')
    else:
        _fail('device_kind')
    budget = _object(record['resources'], {'max_concurrency', 'ram_limit_mib', 'minimum_free_ram_mib',
                                         'vram_floor_mib', 'timeout_seconds'}, 'resource_fields')
    _integer(budget['max_concurrency'], 1, 32, 'resource_concurrency')
    for name in ('ram_limit_mib', 'minimum_free_ram_mib'):
        _integer(budget[name], 1, 1024 * 1024, 'resource_memory')
    _integer(budget['timeout_seconds'], 1, 21600, 'resource_timeout')
    _integer(budget['vram_floor_mib'], 0, 1024 * 1024, 'resource_vram')
    if (device['kind'] == 'cpu' and budget['vram_floor_mib'] != 0
            or device['kind'] == 'cuda' and budget['vram_floor_mib'] == 0):
        _fail('resource_device_mismatch')


def _artifact(record):
    _object(record, {'id', 'kind', 'model_name', 'model_version', 'identity_sha256',
                     'license_source', 'preprocessing_sha256', 'vector_space'}, 'artifact_fields')
    _choice(record['kind'], {'checkpoint', 'service_manifest', 'system_voice'}, 'artifact_kind')
    _text(record['model_name'], 120, 'artifact_model_name')
    _match(record['model_version'], ID, 'artifact_model_version')
    _match(record['identity_sha256'], DIGEST, 'artifact_identity')
    _match(record['preprocessing_sha256'], DIGEST, 'artifact_preprocessing')
    _reference_url(record['license_source'])
    space = record['vector_space']
    if space is not None:
        _object(space, {'id', 'dimension', 'normalization'}, 'vector_space_fields')
        _match(space['id'], ID, 'vector_space_identity')
        _integer(space['dimension'], 8, 8192, 'vector_space_dimension')
        _choice(space['normalization'], {'unit_l2', 'none'}, 'vector_space_normalization')


def _bindings(value, providers, roles, *, allow_empty=False):
    if type(value) is not list or not (0 if allow_empty else 1) <= len(value) <= len(roles):
        _fail('binding_inventory')
    result = {}
    for binding in value:
        _object(binding, {'role', 'provider', 'enabled'}, 'binding_fields')
        role = binding['role']
        if type(role) is not str or role not in roles or role in result:
            _fail('binding_role')
        if type(binding['provider']) is not str or binding['provider'] not in providers:
            _fail('binding_provider')
        if providers[binding['provider']]['role'] != role or type(binding['enabled']) is not bool:
            _fail('binding_contract')
        result[role] = binding
    return result


@dataclass(frozen=True, init=False)
class ValidatedDeployment:
    """An immutable private snapshot; repr/report cannot reveal its selections."""
    selection_sha256: str
    _payload: bytes = field(repr=False)
    _seal: object = field(repr=False, compare=False)

    def __init__(self, *args, **kwargs):
        raise TypeError('Use validate_deployment to create a validated snapshot')

    def report(self):
        if not _validated_snapshot(self):
            _fail('validated_deployment_required')
        doc = json.loads(self._payload)
        return {'status': 'configuration_valid', 'selection_sha256': self.selection_sha256,
                'selected_roles': sorted(binding['role'] for binding in doc['bindings']),
                'requested_enabled_roles': sorted(binding['role'] for binding in doc['bindings'] if binding['enabled']),
                'rollback_declared_roles': sorted(binding['role'] for binding in doc['rollback_bindings']),
                'runtimes_declared': len(doc['runtimes']), 'artifacts_declared': len(doc['artifacts']),
                'runtime_probed': False, 'artifacts_verified': False,
                'quality_evaluated': False, 'activation_performed': False}

    def resolve(self, role, *, rollback=False):
        """Return a private metadata copy for an explicit caller, without applying it."""
        if not _validated_snapshot(self):
            _fail('validated_deployment_required')
        doc = json.loads(self._payload)
        key = 'rollback_bindings' if rollback else 'bindings'
        binding = next((item for item in doc[key] if item['role'] == role), None)
        if binding is None:
            return None
        provider = next(item for item in doc['providers'] if item['id'] == binding['provider'])
        return {'binding': binding, 'provider': provider,
                'runtime': next(item for item in doc['runtimes'] if item['id'] == provider['runtime']),
                'artifact': next(item for item in doc['artifacts'] if item['id'] == provider['artifact'])}


def _validated_snapshot(value):
    """Factory/integrity invariant, not a sandbox against code in this process."""
    return (type(value) is ValidatedDeployment
            and getattr(value, '_seal', None) is _VALIDATION_SEAL
            and type(getattr(value, '_payload', None)) is bytes
            and type(getattr(value, 'selection_sha256', None)) is str
            and hashlib.sha256(value._payload).hexdigest() == value.selection_sha256)


def runtime_host_platform(runtime):
    """Effective application-facing host from an already validated runtime copy.

    Schema 1 remains native, while schema 2 preserves a separate execution OS.
    This helper does not establish actual host/distro placement or forwarding.
    """
    return runtime['placement']['host_platform'] if 'placement' in runtime else runtime['platform']


def validate_deployment(document, catalog) -> ValidatedDeployment:
    """Validate selections against the reviewed source catalog, with no I/O."""
    _object(document, {'schema', 'kind', 'id', 'runtimes', 'artifacts', 'providers',
                       'bindings', 'rollback_bindings'}, 'manifest_fields')
    if type(document['schema']) is not int or document['schema'] not in {1, 2} or document['kind'] != 'photohouse-model-deployment':
        _fail('manifest_version')
    _match(document['id'], ID, 'manifest_identity')
    # The catalog is source-maintained metadata, not supplied by the private record.
    if type(catalog) is not dict or type(catalog.get('capabilities')) is not list:
        _fail('source_catalog')
    roles = {}
    for spec in catalog['capabilities']:
        if (type(spec) is not dict or type(spec.get('id')) is not str
                or spec['id'] in roles or type(spec.get('contract')) is not str
                or type(spec.get('adapters')) is not list
                or any(type(adapter) is not dict or type(adapter.get('symbol')) is not str
                       for adapter in spec['adapters'])
                or type(spec.get('execution_modes')) is not list):
            _fail('source_catalog')
        roles[spec['id']] = spec
    runtimes = _records(document['runtimes'], 32, 'runtime_inventory')
    artifacts = _records(document['artifacts'], 64, 'artifact_inventory')
    providers = _records(document['providers'], 64, 'provider_inventory')
    environments = {}
    for runtime in runtimes.values():
        _runtime(runtime, document['schema'])
        identity = (runtime['platform'], runtime['dependency_lock_sha256'],
                    json.dumps(runtime.get('placement'), sort_keys=True))
        if runtime['environment_id'] in environments and environments[runtime['environment_id']] != identity:
            _fail('environment_identity_conflict')
        environments[runtime['environment_id']] = identity
    spaces = {}
    model_versions = {}
    for artifact in artifacts.values():
        _artifact(artifact)
        identity = (artifact['kind'], artifact['identity_sha256'], artifact['preprocessing_sha256'],
                    json.dumps(artifact['vector_space'], sort_keys=True))
        key = (artifact['model_name'], artifact['model_version'])
        if key in model_versions and model_versions[key] != identity:
            _fail('model_version_reused')
        model_versions[key] = identity
        space = artifact['vector_space']
        if space is not None:
            fingerprint = (artifact['model_name'], artifact['model_version'], *identity)
            if space['id'] in spaces and spaces[space['id']] != fingerprint:
                _fail('vector_space_reused')
            spaces[space['id']] = fingerprint
    for provider in providers.values():
        _object(provider, {'id', 'role', 'adapter', 'contract', 'runtime', 'artifact',
                           'endpoint', 'credential_env'}, 'provider_fields')
        role = provider['role']
        if type(role) is not str or role not in roles:
            _fail('provider_role')
        spec = roles[role]
        if (type(provider['adapter']) is not str or provider['contract'] != spec['contract']
                or provider['adapter'] not in {adapter['symbol'] for adapter in spec['adapters']}):
            _fail('provider_contract')
        if provider['adapter'] in INVENTORY_ONLY_ADAPTERS:
            _fail('adapter_not_selectable')
        if (type(provider['runtime']) is not str or provider['runtime'] not in runtimes
                or type(provider['artifact']) is not str or provider['artifact'] not in artifacts):
            _fail('provider_reference')
        runtime, artifact = runtimes[provider['runtime']], artifacts[provider['artifact']]
        if runtime['execution_mode'] not in spec['execution_modes']:
            _fail('provider_execution_mode')
        if runtime.get('placement', {}).get('kind') == 'wsl2' and role not in WSL_HTTP_ROLES:
            _fail('wsl_role_not_supported')
        http = runtime['execution_mode'] in {'loopback_http', 'http_service'}
        if http:
            _endpoint(provider['endpoint'], role)
            limit = 60 if role in {'assistant_asr', 'assistant_tts'} else 120
            if runtime['resources']['timeout_seconds'] > limit:
                _fail('provider_timeout')
        elif provider['endpoint'] is not None or provider['credential_env'] is not None:
            _fail('non_http_provider_endpoint')
        if provider['credential_env'] is not None:
            _match(provider['credential_env'], ENV, 'credential_reference')
        if (role in VECTOR_ROLES) != (artifact['vector_space'] is not None):
            _fail('provider_vector_contract')
        if role == 'face_embedding' and artifact['vector_space']['dimension'] != 512:
            _fail('approved_face_dimension')
        if role in {'image_embedding', 'video_embedding'} and not artifact['model_name'].startswith('clip-'):
            _fail('approved_image_model')
        if role in {'image_embedding', 'video_embedding'} and len(artifact['model_name']) > 64:
            _fail('approved_image_model')
        if role in {'image_embedding', 'video_embedding'} and artifact['vector_space']['normalization'] != 'unit_l2':
            _fail('approved_image_normalization')
        if artifact['kind'] == 'system_voice' and (role != 'assistant_tts' or runtime['platform'] != 'windows'):
            _fail('system_voice_runtime')
    bindings = _bindings(document['bindings'], providers, roles)
    rollback = _bindings(document['rollback_bindings'], providers, roles, allow_empty=True)
    for role, previous in rollback.items():
        if role not in bindings or not previous['enabled']:
            _fail('rollback_binding')
        current = providers[bindings[role]['provider']]
        old = providers[previous['provider']]
        if current == old or {k: v for k, v in current.items() if k != 'id'} == {k: v for k, v in old.items() if k != 'id'}:
            _fail('rollback_not_distinct')
    if any(binding['enabled'] and role not in rollback for role, binding in bindings.items()):
        _fail('enabled_without_rollback')
    for selected in (bindings, rollback):
        if all(role in selected and selected[role]['enabled'] for role in ('image_embedding', 'video_embedding')):
            identities = [artifacts[providers[selected[role]['provider']]['artifact']]['vector_space']['id']
                          for role in ('image_embedding', 'video_embedding')]
            if identities[0] != identities[1]:
                _fail('image_video_space_mismatch')
    try:
        payload = json.dumps(document, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                             allow_nan=False).encode('ascii')
    except (ValueError, UnicodeError, TypeError, RecursionError):
        _fail('manifest_encoding')
    if len(payload) > MAX_BYTES:
        _fail('manifest_too_large')
    result = object.__new__(ValidatedDeployment)
    object.__setattr__(result, 'selection_sha256', hashlib.sha256(payload).hexdigest())
    object.__setattr__(result, '_payload', payload)
    object.__setattr__(result, '_seal', _VALIDATION_SEAL)
    return result


def _strict_json(payload):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                _fail('duplicate_json_key')
            result[key] = value
        return result

    def constant(_value):
        _fail('nonfinite_json')

    try:
        document = json.loads(payload.decode('utf-8', errors='strict'), object_pairs_hook=pairs,
                              parse_constant=constant)
        pending = [(document, 0)]
        while pending:
            value, depth = pending.pop()
            if depth > 16:
                _fail('manifest_json')
            if type(value) is dict:
                pending.extend((child, depth + 1) for child in value.values())
            elif type(value) is list:
                pending.extend((child, depth + 1) for child in value)
        return document
    except DeploymentError:
        raise
    except (UnicodeError, ValueError, RecursionError):
        _fail('manifest_json')


def _load_private_document(path, *, source_root):
    """Read bounded private JSON; shared by offline selection/evidence readers."""
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts or path.is_relative_to(Path(source_root).resolve()):
        _fail('manifest_location')
    try:
        for parent in (*reversed(path.parents), path):
            info = parent.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                _fail('manifest_link')
        require_private_directory(path.parent)
        require_private_file(path)
        before = path.stat()
        if not 1 <= before.st_size <= MAX_BYTES:
            _fail('manifest_too_large')
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0))
        with os.fdopen(fd, 'rb') as stream:
            opened = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode):
                _fail('manifest_changed')
            payload = stream.read(MAX_BYTES + 1)
            after = os.fstat(stream.fileno())
        require_private_file(path)
        for parent in path.parents:
            info = parent.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                _fail('manifest_link')
        final = path.stat()
        identity = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
        if identity(before) != identity(opened) or identity(opened) != identity(after) or identity(after) != identity(final):
            _fail('manifest_changed')
        if len(payload) > MAX_BYTES:
            _fail('manifest_too_large')
    except (OSError, ValueError) as error:
        if isinstance(error, DeploymentError):
            raise
        _fail('private_manifest_unavailable')
    return _strict_json(payload)


def load_private_deployment(path, catalog, *, source_root) -> ValidatedDeployment:
    """Read one owner-private metadata file outside the source checkout, stably."""
    return validate_deployment(_load_private_document(path, source_root=source_root), catalog)
