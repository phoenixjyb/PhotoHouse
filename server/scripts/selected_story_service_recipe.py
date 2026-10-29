"""Strict, inert recipe loading for the persistent CPU selected-story service.

Recipes describe configuration only. Parsing and construction never activate
maintenance policy, initialize host storage, or start native/model work.
"""
from __future__ import annotations

import json
import math
import ntpath
import os
from pathlib import Path
import re


SCHEMA = 'photohouse.selected_story_service_recipe.v1'
MAX_RECIPE_BYTES = 64 * 1024
_SHA256 = re.compile(r'[0-9a-f]{64}\Z', re.ASCII)
_DRIVE = re.compile(r'[A-Za-z]:\Z', re.ASCII)
_TOP_KEYS = {'schema', 'launch', 'model', 'resource_profile', 'capacity',
             'admission_directory', 'exchange_root', 'timeout_seconds', 'cleanup_seconds'}
_LAUNCH_KEYS = {'executable', 'executable_sha256', 'argv', 'cwd', 'environment',
                'memory_limit', 'process_limit', 'minimum_free_ram'}
_PROFILE_KEYS = {'resource_id', 'launch_sha256', 'minimum_free_ram',
                 'minimum_free_disk', 'minimum_free_vram', 'capacity_sha256'}
_CAPACITY_KEYS = {'directory', 'policy_id', 'identity', 'conflict_images'}
_IDENTITY_KEYS = {'host_id', 'principal_sid', 'volume_id'}


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Invalid selected-story service recipe')
        result[key] = value
    return result


def _constant(_value):
    raise ValueError('Invalid selected-story service recipe')


def _object(value, keys):
    if type(value) is not dict or set(value) != keys:
        raise ValueError('Invalid selected-story service recipe')
    return value


def _path(value):
    if (type(value) is not str or not value or len(value.encode('utf-8')) > 4096
            or any(ord(c) < 32 or 127 <= ord(c) < 160 for c in value)
            or value.startswith(('\\\\', '//'))
            or ntpath.splitdrive(value)[0].startswith('\\\\')):
        raise ValueError('Invalid selected-story service recipe')
    drive, _tail = ntpath.splitdrive(value)
    windows = bool(drive)
    if windows and not _DRIVE.fullmatch(drive):
        raise ValueError('Invalid selected-story service recipe')
    if (windows and not ntpath.isabs(value)) or (not windows and not os.path.isabs(value)):
        raise ValueError('Invalid selected-story service recipe')
    normalized = ntpath.normpath(value) if windows else os.path.normpath(value)
    parts = re.split(r'[\\/]', value)
    if (normalized != value or any(part in {'.', '..'} for part in parts)
            or value in {Path(value).anchor, ntpath.splitdrive(value)[0] + '\\'}):
        raise ValueError('Invalid selected-story service recipe')
    return value


def _number(value, maximum):
    if (type(value) not in (int, float) or not math.isfinite(value)
            or not 0 < value <= maximum):
        raise ValueError('Invalid selected-story service recipe')
    return value


def strict_recipe(raw: bytes) -> dict:
    """Parse a closed v1 recipe into validated native/profile value objects."""
    try:
        if type(raw) is not bytes or not 0 < len(raw) <= MAX_RECIPE_BYTES:
            raise ValueError()
        value = json.loads(raw.decode('utf-8', errors='strict'),
            object_pairs_hook=_pairs, parse_constant=_constant)
        recipe = _object(value, _TOP_KEYS)
        if recipe['schema'] != SCHEMA or type(recipe['schema']) is not str:
            raise ValueError()

        launch_raw = _object(recipe['launch'], _LAUNCH_KEYS)
        profile_raw = _object(recipe['resource_profile'], _PROFILE_KEYS)
        capacity_raw = _object(recipe['capacity'], _CAPACITY_KEYS)
        identity_raw = _object(capacity_raw['identity'], _IDENTITY_KEYS)

        # Validate path spellings before handing them to platform Path handling.
        for path in (launch_raw['executable'], launch_raw['cwd'],
                     capacity_raw['directory'], recipe['admission_directory'],
                     recipe['exchange_root']):
            _path(path)
        if (type(launch_raw['argv']) is not list or
                type(launch_raw['environment']) is not dict or
                type(capacity_raw['conflict_images']) is not list or
                not capacity_raw['conflict_images']):
            raise ValueError()

        from app.access.selected_story_native import NativeStoryLaunch
        from app.access.host_inference_admission import HostResourceProfile
        from app.access.selected_story_local import _MODEL
        from app.access.selected_story_process import process_launch_digest
        from app.access.windows_story_capacity import WindowsProbeIdentity

        launch = NativeStoryLaunch(
            executable=launch_raw['executable'],
            executable_sha256=launch_raw['executable_sha256'],
            argv=tuple(launch_raw['argv']), cwd=launch_raw['cwd'],
            environment=launch_raw['environment'],
            memory_limit=launch_raw['memory_limit'],
            process_limit=launch_raw['process_limit'],
            minimum_free_ram=launch_raw['minimum_free_ram'])
        profile = HostResourceProfile(**profile_raw)
        identity = WindowsProbeIdentity(**identity_raw)
        from app.access.windows_story_service_capacity import (
            windows_service_probe_digest,
        )
        images = tuple(capacity_raw['conflict_images'])
        if profile.resource_id != 'cpu' or profile.capacity_sha256 != windows_service_probe_digest(
                identity, capacity_raw['directory'], capacity_raw['policy_id'], images):
            raise ValueError()

        model = recipe['model']
        launch_digest = process_launch_digest(launch, exchange_root=recipe['exchange_root'])
        if (type(model) is not str or not _MODEL.fullmatch(model) or '://' in model
                or profile.launch_sha256 != launch_digest
                or launch.memory_limit > 2 * 1024**3 or launch.process_limit > 8
                or launch.minimum_free_ram < 8 * 1024**3
                or profile.minimum_free_ram < launch.minimum_free_ram):
            raise ValueError()
        # Match DraftOperations' maximum work window. A caller's shorter scope
        # deadline still wins inside ProcessSelectedStoryProvider.prepare().
        timeout = _number(recipe['timeout_seconds'], 60)
        cleanup = _number(recipe['cleanup_seconds'], 10)
        if type(recipe['timeout_seconds']) not in (int, float) or type(recipe['cleanup_seconds']) not in (int, float):
            raise ValueError()
        return {
            'schema': SCHEMA,
            'launch': launch,
            'model': model,
            'resource_profile': profile,
            'capacity': {
                'directory': capacity_raw['directory'],
                'policy_id': capacity_raw['policy_id'],
                'identity': identity,
                'conflict_images': images,
            },
            'admission_directory': recipe['admission_directory'],
            'exchange_root': recipe['exchange_root'],
            'timeout_seconds': timeout,
            'cleanup_seconds': cleanup,
        }
    except Exception:
        # Raw recipes can contain private paths and should never reach diagnostics.
        raise ValueError('Invalid selected-story service recipe') from None


def build_recipe_provider(raw: bytes, *, expected_model: str,
                          expected_launch_sha256: str,
                          expected_profile_sha256: str,
                          enabled: bool = False):
    """Join a parsed recipe to operator pins, then build an inert provider."""
    if (type(enabled) is not bool or type(expected_model) is not str
            or type(expected_launch_sha256) is not str
            or type(expected_profile_sha256) is not str
            or not _SHA256.fullmatch(expected_launch_sha256)
            or not _SHA256.fullmatch(expected_profile_sha256)):
        raise ValueError('Invalid selected-story service recipe binding')
    recipe = strict_recipe(raw)
    try:
        from app.access.host_inference_admission import resource_profile_digest
        from app.access.selected_story_process import process_launch_digest

        launch = recipe['launch']
        profile = recipe['resource_profile']
        exchange_root = recipe['exchange_root']
        launch_digest = process_launch_digest(launch, exchange_root=exchange_root)
        if (recipe['model'] != expected_model or launch_digest != expected_launch_sha256
                or resource_profile_digest(profile) != expected_profile_sha256
                or profile.launch_sha256 != launch_digest):
            raise ValueError()

        # Keep runtime ownership in the existing explicit Windows factory.
        from selected_story_native_owner import windows_story_service_provider
        capacity = recipe['capacity']
        return windows_story_service_provider(
            launch, recipe['model'], host_directory=recipe['admission_directory'],
            capacity_directory=capacity['directory'], profile=profile,
            policy_id=capacity['policy_id'], identity=capacity['identity'],
            conflict_images=capacity['conflict_images'], exchange_root=exchange_root,
            enabled=enabled, timeout=recipe['timeout_seconds'],
            cleanup_seconds=recipe['cleanup_seconds'])
    except Exception:
        raise ValueError('Invalid selected-story service recipe binding') from None
