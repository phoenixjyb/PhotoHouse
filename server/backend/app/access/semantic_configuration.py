"""Explicit private configuration for the disabled-by-default semantic pilot.

The pinned joint-space binding is an operator attestation. Loading it does not
measure model compatibility or establish multilingual retrieval quality.
"""
from __future__ import annotations

from pathlib import Path
import stat

from .model_deployment import DeploymentError, _load_private_document
from .semantic_encoder import JointSpaceBinding, LocalSemanticEncoder
from .semantic_search import SemanticSearchRuntime, _valid_pilot_owner_account_id
from .semantic_streaming import SemanticServingLimits
from .semantic_bulk_vectors import BulkVectorStore
from .visual_candidates import VectorSpaceIdentity

_IDENTITY_KEYS = {'artifact_sha256', 'preprocessing_sha256', 'vector_space_id',
                  'model_version', 'dimension', 'normalization'}
_FIELDS = {'format_version', 'vector_root', 'encoder_url', 'encoder_timeout_seconds',
           'credential_file', 'binding', 'binding_sha256', 'operator_reviewed'}
_OWNER_FIELDS = _FIELDS | {'pilot_owner_account_id'}
_LARGE_FIELDS = _OWNER_FIELDS | {'serving_limits'}
_BULK_FIELDS = _LARGE_FIELDS | {'bulk_vectors'}


class SemanticConfigurationError(ValueError):
    """Fixed safe refusal; private values and exception details are omitted."""

    def __init__(self):
        super().__init__('Invalid semantic runtime configuration')


def _identity(value):
    if type(value) is not dict or set(value) != _IDENTITY_KEYS:
        raise SemanticConfigurationError()
    try:
        return VectorSpaceIdentity(**value)
    except (TypeError, ValueError):
        raise SemanticConfigurationError() from None


def _checked_path(value):
    if type(value) is not str or not value or len(value) > 4096:
        raise SemanticConfigurationError()
    path = Path(value)
    if (not path.is_absolute() or '..' in path.parts or str(path) != value or
            path == Path(path.anchor)):
        raise SemanticConfigurationError()
    return path


def _vector_root(value, *, source_root):
    from .private_storage import require_private_directory
    path = _checked_path(value)
    source = Path(source_root).resolve(strict=True)
    try:
        if path.resolve(strict=True) != path or path.is_relative_to(source) or source.is_relative_to(path):
            raise SemanticConfigurationError()
        for parent in reversed(path.parents):
            info = parent.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                raise SemanticConfigurationError()
        info = path.lstat()
        if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or
                getattr(info, 'st_file_attributes', 0) & 0x400):
            raise SemanticConfigurationError()
        require_private_directory(path)
    except (OSError, ValueError):
        raise SemanticConfigurationError() from None
    return path


def _require_semantic_paths_disjoint(semantic_paths, protected_paths):
    semantic = tuple(semantic_paths)
    protected = tuple(protected_paths)
    for path in semantic:
        if not isinstance(path, Path) or not path.is_absolute() or '..' in path.parts:
            raise SemanticConfigurationError()
    for index, path in enumerate(semantic):
        if any(path.is_relative_to(other) or other.is_relative_to(path)
               for other in semantic[:index]):
            raise SemanticConfigurationError()
        if any(path.is_relative_to(other) or other.is_relative_to(path)
               for other in protected if isinstance(other, Path) and other.is_absolute()):
            raise SemanticConfigurationError()


def load_semantic_runtime(path, *, discovery, source_root, protected_paths=()):
    """Load one bounded private manifest and build a loopback encoder runtime.

    Call only after an explicit semantic opt-in. The separately selected token
    file and vector root are checked only on this enabled path.
    """
    try:
        doc = _load_private_document(path, source_root=source_root)
        if type(doc) is not dict or type(doc.get('format_version')) is not int:
            raise SemanticConfigurationError()
        version = doc['format_version']
        if version == 1:
            if set(doc) != _FIELDS:
                raise SemanticConfigurationError()
            owner_account_id = None
        elif version in (2, 3, 4):
            if (set(doc) != (_OWNER_FIELDS if version == 2 else _LARGE_FIELDS if version == 3 else _BULK_FIELDS) or
                    not _valid_pilot_owner_account_id(doc['pilot_owner_account_id'])):
                raise SemanticConfigurationError()
            owner_account_id = doc['pilot_owner_account_id']
        else:
            raise SemanticConfigurationError()
        limits = None
        if version in (3, 4):
            value = doc['serving_limits']
            if type(value) is not dict or set(value) != {
                    'candidate_limit', 'source_rows', 'source_bytes', 'search_seconds'}:
                raise SemanticConfigurationError()
            limits = SemanticServingLimits(**value)
        if type(doc['operator_reviewed']) is not bool or doc['operator_reviewed'] is not True:
            raise SemanticConfigurationError()
        binding_doc = doc['binding']
        if (type(binding_doc) is not dict or set(binding_doc) !=
                {'image_identity', 'text_identity', 'qualification_sha256'}):
            raise SemanticConfigurationError()
        binding = JointSpaceBinding(_identity(binding_doc['image_identity']),
            _identity(binding_doc['text_identity']), binding_doc['qualification_sha256'])
        if type(doc['binding_sha256']) is not str or doc['binding_sha256'] != binding.binding_sha256:
            raise SemanticConfigurationError()
        manifest_path = _checked_path(str(path))
        credential_path = _checked_path(doc['credential_file'])
        root = _vector_root(doc['vector_root'], source_root=source_root)
        semantic_paths = (manifest_path, credential_path, root)
        bulk = None
        if version == 4:
            value = doc['bulk_vectors']
            if type(value) is not dict or set(value) != {'path', 'file_sha256', 'library_id'}:
                raise SemanticConfigurationError()
            bulk_path = _checked_path(value['path'])
            # A separately pinned serving copy cannot overlap source, secrets,
            # live stores or the original per-file vector tree. Loading a
            # configuration does not load or trust its vector payload.
            _vector_root(str(bulk_path.parent), source_root=source_root)
            bulk = BulkVectorStore(bulk_path, value['file_sha256'],
                value['library_id'], binding.image_identity)
            semantic_paths += (bulk_path,)
        _require_semantic_paths_disjoint(semantic_paths, protected_paths)
        credential = _load_private_document(credential_path, source_root=source_root)
        if (type(credential) is not dict or set(credential) != {'token'} or
                type(credential['token']) is not str):
            raise SemanticConfigurationError()
        token = credential['token']
        timeout = doc['encoder_timeout_seconds']
        if type(timeout) not in (int, float):
            raise SemanticConfigurationError()
        encoder = LocalSemanticEncoder(binding, doc['encoder_url'], timeout=float(timeout),
                                       bearer_token=token)
        return SemanticSearchRuntime(discovery, root, encoder, owner_account_id, limits, bulk)
    except SemanticConfigurationError:
        raise
    except (DeploymentError, OSError, TypeError, ValueError, KeyError, OverflowError):
        raise SemanticConfigurationError() from None
