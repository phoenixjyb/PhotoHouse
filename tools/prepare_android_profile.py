#!/usr/bin/env python3
"""Attest explicit private Android release inputs; do not build, sign or publish."""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'server/backend'))
from app.access.private_storage import require_private_file, stable_stat_identity

DIGEST = re.compile(r'[0-9a-f]{64}\Z')
COMMIT = re.compile(r'[0-9a-f]{40}\Z')
PHONE_STRINGS = {'photohouseOrigin', 'photohousePhoneHomeOrigin', 'photohousePhoneHomeLanAddress'}
TV_STRINGS = {'photohouseTvOrigin', 'photohouseTvLanAddress', 'photohouseTvUpdateOrigin', 'photohouseTvUpdateLanAddress'}
PRIVATE_NETWORKS = tuple(map(ipaddress.ip_network, ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')))
MAX_GRADLE_BYTES = 128 * 1024
PHONE_BOOLEANS = {
    'photohouseProtectedNativeV2Enabled', 'photohousePhoneUploadEnabled',
    'photohousePhoneDiscoveryEnabled', 'photohousePhoneFamilyTagsEnabled',
    'photohousePhonePhotoDeliveryEnabled', 'photohousePhonePreparedVideoEnabled',
    'photohousePhoneMediaFilterEnabled', 'photohousePhonePreparedBrowseEnabled',
    'photohousePhoneHomeDiscoveryEnabled', 'photohouseHomeTagLookupEnabled',
    'photohouseAssistantEnabled', 'photohouseMemoryCommunityEnabled',
    'photohouseMemoryGroupsEnabled', 'photohouseHomeCalendarEnabled',
    'photohouseStoryFixtureEnabled', 'photohousePhoneUiQa',
}
TV_BOOLEANS = {'photohouseTvDiscoveryEnabled', 'photohouseTvBrowseEnabled',
    'photohouseHomeTagLookupEnabled', 'photohouseHomeCalendarEnabled', 'photohouseStoryFixtureEnabled'}


class Refused(ValueError):
    """Fixed public-safe reason; never include profile values in errors."""


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def parse_properties(raw):
    if type(raw) is not bytes or not 1 <= len(raw) <= 16_384:
        raise Refused('profile_size_invalid')
    try:
        text = raw.decode('utf-8')
    except UnicodeError:
        raise Refused('profile_encoding_invalid') from None
    result = {}
    for line in text.splitlines():
        if not line or line.startswith('#'):
            continue
        if '=' not in line:
            raise Refused('profile_line_invalid')
        key, value = line.split('=', 1)
        if (not re.fullmatch(r'photohouse[A-Za-z0-9]+', key) or key in result
                or any(ord(c) < 32 or c in '\\"' for c in value)
                or len(value.encode('utf-8')) > 512):
            raise Refused('profile_property_invalid')
        result[key] = value
    return result


def _origin(value):
    if not value:
        return
    try:
        parsed = urlsplit(value)
        if (parsed.scheme != 'https'
                or not parsed.hostname or parsed.username is not None or parsed.password is not None
                or parsed.path not in ('', '/') or parsed.query or parsed.fragment
                or '?' in value or '#' in value or any(c.isspace() for c in value) or parsed.port == 0):
            raise ValueError()
        # HomeOrigin is consumed by Home mode and both OTA clients. Its exact
        # canonical DNS origin also works with the phone's TrustedOrigin.
        host = parsed.hostname.encode('idna').decode('ascii')
        if (len(host) > 253 or len(host.split('.')) < 2 or re.fullmatch(r'[0-9.]+', host)
                or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in host.split('.'))
                or value != 'https://'+host+('' if parsed.port in (None,443) else ':'+str(parsed.port))):
            raise ValueError()
    except ValueError:
        raise Refused('profile_origin_invalid') from None


def validate_profile(module, raw, gradle_text):
    if module not in {'phone', 'tv'}:
        raise Refused('module_invalid')
    values = parse_properties(raw)
    strings = PHONE_STRINGS if module == 'phone' else TV_STRINGS
    booleans = PHONE_BOOLEANS if module == 'phone' else TV_BOOLEANS
    expected = strings | booleans | ({'photohouseTvCatalogVersion'} if module == 'tv' else set())
    declared = re.findall(r'providers\.gradleProperty\("([^"]+)"\)', gradle_text)
    local_keys = set(re.findall(r'localConfig\.getProperty\("([^"]+)"', gradle_text))
    if len(declared) != len(set(declared)) or set(declared) != expected or not local_keys <= expected or set(values) != expected:
        raise Refused('profile_source_keys_mismatch')
    if any(values[key] not in {'true', 'false'} for key in booleans):
        raise Refused('profile_boolean_invalid')
    if values['photohouseStoryFixtureEnabled'] != 'false' or (module == 'phone' and values['photohousePhoneUiQa'] != 'false'):
        raise Refused('profile_release_mode_invalid')
    if values['photohouseHomeCalendarEnabled'] == 'true' and values['photohouseHomeTagLookupEnabled'] != 'true':
        raise Refused('profile_feature_dependency_invalid')
    main_origin = 'photohouseOrigin' if module == 'phone' else 'photohouseTvOrigin'
    if not values[main_origin]:
        raise Refused('profile_main_origin_missing')
    if module == 'phone':
        protected = {'photohousePhoneUploadEnabled', 'photohousePhoneFamilyTagsEnabled',
            'photohousePhonePreparedVideoEnabled', 'photohousePhoneMediaFilterEnabled',
            'photohouseMemoryCommunityEnabled', 'photohouseMemoryGroupsEnabled'}
        if any(values[k] == 'true' for k in protected) and values['photohouseProtectedNativeV2Enabled'] != 'true':
            raise Refused('profile_feature_dependency_invalid')
        if values['photohousePhonePreparedBrowseEnabled'] == 'true' and any(values[k] != 'true' for k in
                ('photohousePhoneMediaFilterEnabled', 'photohousePhonePreparedVideoEnabled')):
            raise Refused('profile_feature_dependency_invalid')
        _origin(values['photohouseOrigin']); _origin(values['photohousePhoneHomeOrigin'])
        if values['photohousePhoneHomeDiscoveryEnabled'] == 'true' and not values['photohousePhoneHomeOrigin']:
            raise Refused('profile_home_origin_missing')
        pairs = [('photohousePhoneHomeLanAddress', 'photohousePhoneHomeOrigin')]
    else:
        version = values['photohouseTvCatalogVersion']
        if (version not in {'1','2','3'} or
                values['photohouseTvDiscoveryEnabled'] == 'true' and version == '1' or
                values['photohouseTvBrowseEnabled'] == 'true' and version != '3'):
            raise Refused('profile_catalog_dependency_invalid')
        _origin(values['photohouseTvOrigin']); _origin(values['photohouseTvUpdateOrigin'])
        pairs = [('photohouseTvLanAddress','photohouseTvOrigin'), ('photohouseTvUpdateLanAddress','photohouseTvUpdateOrigin')]
    for address_key, origin_key in pairs:
        if values[address_key]:
            try:
                address = ipaddress.ip_address(values[address_key])
                if not values[origin_key] or address.version != 4 or not any(address in net for net in PRIVATE_NETWORKS):
                    raise ValueError()
            except ValueError:
                raise Refused('profile_lan_address_invalid') from None
    code = re.findall(r'\bversionCode\s*=\s*(\d+)', gradle_text)
    name = re.findall(r'\bversionName\s*=\s*"([a-zA-Z0-9.-]{1,96})"', gradle_text)
    if len(code) != 1 or len(name) != 1 or not 1 <= int(code[0]) <= 2_100_000_000:
        raise Refused('source_version_invalid')
    canonical = json.dumps(values, sort_keys=True, separators=(',',':'), ensure_ascii=False).encode()
    return {'module': module, 'version_code': int(code[0]), 'version_name': name[0],
        'profile_sha256': sha(raw), 'canonical_profile_sha256': sha(canonical),
        'property_keys': sorted(values), 'boolean_choices': {k:values[k] == 'true' for k in sorted(booleans)},
        'routing_value_sha256': {k:sha(values[k].encode()) for k in sorted(strings)}}


def _git(root, args):
    try:
        result = subprocess.run(['git', *args], cwd=root, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, timeout=15, check=True)
        return result.stdout
    except (OSError, subprocess.SubprocessError):
        raise Refused('source_git_unavailable') from None


def _read_source(source):
    before = stable_stat_identity(source.stat())
    if not 1 <= before[2] <= MAX_GRADLE_BYTES:
        raise Refused('source_size_invalid')
    fd = os.open(source, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0))
    with os.fdopen(fd, 'rb') as stream:
        if stable_stat_identity(os.fstat(stream.fileno())) != before:
            raise Refused('source_bytes_changed')
        raw = stream.read(MAX_GRADLE_BYTES+1)
        if stable_stat_identity(os.fstat(stream.fileno())) != before:
            raise Refused('source_bytes_changed')
    if len(raw) > MAX_GRADLE_BYTES or stable_stat_identity(source.stat()) != before:
        raise Refused('source_bytes_changed')
    return raw


def prepare(root, module, profile, expected_commit, expected_profile_sha256):
    if not COMMIT.fullmatch(expected_commit) or not DIGEST.fullmatch(expected_profile_sha256):
        raise Refused('explicit_identity_invalid')
    root = Path(root).resolve(strict=True)
    relative = 'clients/android/android/'+('connected' if module == 'phone' else 'tv')+'/build.gradle.kts'
    if module not in {'phone','tv'}:
        raise Refused('module_invalid')
    if _git(root, ['rev-parse','HEAD']).strip().decode() != expected_commit or _git(root, ['status','--porcelain']).strip():
        raise Refused('source_not_clean_and_pinned')
    profile = Path(profile)
    if not profile.is_absolute() or profile.resolve(strict=True) != profile or profile.is_relative_to(root):
        raise Refused('profile_private_path_invalid')
    require_private_file(profile)
    before = stable_stat_identity(profile.stat())
    if not 1 <= before[2] <= 16_384:
        raise Refused('profile_size_invalid')
    fd = os.open(profile, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0))
    with os.fdopen(fd, 'rb') as stream:
        if stable_stat_identity(os.fstat(stream.fileno())) != before:
            raise Refused('profile_identity_changed')
        raw = stream.read(16_385)
        if stable_stat_identity(os.fstat(stream.fileno())) != before:
            raise Refused('profile_identity_changed')
    if stable_stat_identity(profile.stat()) != before or sha(raw) != expected_profile_sha256:
        raise Refused('profile_identity_changed')
    require_private_file(profile)
    source = root / relative
    if source.is_symlink() or source.resolve(strict=True) != source:
        raise Refused('source_path_invalid')
    if int(_git(root, ['cat-file','-s',expected_commit+':'+relative])) > MAX_GRADLE_BYTES:
        raise Refused('source_size_invalid')
    gradle = _read_source(source)
    if len(gradle) > MAX_GRADLE_BYTES or gradle != _git(root, ['show', expected_commit+':'+relative]):
        raise Refused('source_bytes_changed')
    report = validate_profile(module, raw, gradle.decode('utf-8'))
    # Reopen and hash as well as checking metadata. Windows modification time
    # can be restored after a same-size rewrite; metadata alone is insufficient.
    require_private_file(profile)
    fd = os.open(profile, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0))
    with os.fdopen(fd, 'rb') as stream:
        if stable_stat_identity(os.fstat(stream.fileno())) != before:
            raise Refused('profile_identity_changed')
        final_raw = stream.read(16_385)
        if stable_stat_identity(os.fstat(stream.fileno())) != before or sha(final_raw) != expected_profile_sha256:
            raise Refused('profile_identity_changed')
    if (_git(root, ['rev-parse','HEAD']).strip().decode() != expected_commit
            or _git(root, ['status','--porcelain']).strip()
            or _read_source(source) != gradle
            or stable_stat_identity(profile.stat()) != before):
        raise Refused('preparation_inputs_changed')
    require_private_file(profile)
    report.update(schema=1, kind='android_release_profile_preparation', source_commit=expected_commit,
        gradle_file_sha256=sha(gradle), build_started=False, signed=False, published=False)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module', choices=('phone','tv'), required=True)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--profile-sha256', required=True)
    args = parser.parse_args(argv)
    try:
        report = prepare(ROOT, args.module, args.profile, args.commit, args.profile_sha256)
        # Hashes/choices only; no routing values, paths, process command or secret material.
        print(json.dumps(report, sort_keys=True))
        return 0
    except (Refused, ValueError, OSError, UnicodeError):
        print('{"status":"refused","kind":"android_release_profile_preparation"}')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
