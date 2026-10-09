#!/usr/bin/env python3
"""Publish one reviewed, signed phone/TV APK to an explicit update directory.

This is an operator action, not part of the API startup or application build.
It never changes the protected database or media. Invoke only after reviewing
the signing certificate, package ID, version and target directory.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import time
import uuid
from contextlib import contextmanager

PACKAGES = {'phone': 'dev.photohouse.connected', 'tv': 'dev.photohouse.tv'}
MAX_BYTES = 160 * 1024 * 1024
LOCK_NAME = '.android-update-publish.lock'
LOCK_WAIT_SECONDS = 1.0
LOCK_POLL_SECONDS = 0.025
_UNSET = object()


class PublicationBusy(ValueError):
    """The shared update-root lock stayed busy for the bounded wait."""


def _direct_regular(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or path.resolve(strict=True) != path:
        raise ValueError('Expected a direct regular file')
    return info


def inspect_apk(apk: Path, aapt: Path, apksigner: Path):
    if _direct_regular(apk).st_size > MAX_BYTES:
        raise ValueError('APK exceeds update limit')
    badging = subprocess.run([str(aapt), 'dump', 'badging', str(apk)],
                             capture_output=True, text=True, timeout=60, check=True).stdout
    match = re.search(r"^package: name='([^']+)' versionCode='([0-9]+)' versionName='([^']+)'", badging, re.M)
    if (not match or not 1 <= int(match[2]) <= 2147483647
            or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9._+ -]{0,79}', match[3])):
        raise ValueError('APK metadata unavailable')
    signed = subprocess.run([str(apksigner), 'verify', '--print-certs', str(apk)],
                            capture_output=True, text=True, timeout=60, check=True).stdout
    certs = re.findall(r'^Signer #[0-9]+ certificate SHA-256 digest: ([0-9a-fA-F]{64})$', signed, re.M)
    if len(certs) != 1:
        raise ValueError('Exactly one verified signer required')
    return match[1], int(match[2]), match[3], certs[0].lower()


def _same_file_identity(left, right):
    return left.st_dev == right.st_dev and left.st_ino != 0 and left.st_ino == right.st_ino


def _unlink_owned_lock(path: Path, token: bytes, identity, allow_incomplete=False):
    """Remove only the regular lock file created by this invocation."""
    try:
        current = path.lstat()
    except FileNotFoundError:
        return
    if (not stat.S_ISREG(current.st_mode) or stat.S_ISLNK(current.st_mode)
            or not _same_file_identity(current, identity)):
        raise RuntimeError('publication lock ownership changed; manual review required')
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise RuntimeError('publication lock could not be verified for cleanup') from exc
    if content != token and not allow_incomplete:
        raise RuntimeError('publication lock ownership changed; manual review required')
    latest = path.lstat()
    if not _same_file_identity(latest, identity):
        raise RuntimeError('publication lock ownership changed; manual review required')
    path.unlink()


def _validate_lock_path(path: Path):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise ValueError('publication lock path is not a direct regular file')


@contextmanager
def _feed_root_lock(root: Path, wait_seconds: float = LOCK_WAIT_SECONDS):
    """Acquire one shared exclusive lock; stale locks are never auto-removed."""
    path = root / LOCK_NAME
    token = uuid.uuid4().hex.encode('ascii')
    deadline = time.monotonic() + max(0.0, wait_seconds)
    identity = None
    while identity is None:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            _validate_lock_path(path)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise PublicationBusy('update feed root is busy; existing locks require manual review')
            time.sleep(min(LOCK_POLL_SECONDS, remaining))
            continue
        try:
            identity = os.fstat(fd)
            view = memoryview(token)
            while view:
                written = os.write(fd, view)
                if written <= 0:
                    raise OSError('could not write publication lock token')
                view = view[written:]
            os.fsync(fd)
        except BaseException:
            if identity is not None:
                _unlink_owned_lock(path, token, identity, allow_incomplete=True)
            raise
        finally:
            os.close(fd)
    try:
        yield
    finally:
        _unlink_owned_lock(path, token, identity)


def _pointer_bytes(root: Path, channel: str):
    pointer = root / f'{channel}.json'
    try:
        before = pointer.lstat()
    except FileNotFoundError:
        return pointer, None
    if not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode):
        raise ValueError('Channel pointer must be a direct regular file')
    raw = pointer.read_bytes()
    try:
        after = pointer.lstat()
    except FileNotFoundError as exc:
        raise ValueError('Channel pointer changed while being read') from exc
    if not _same_file_identity(before, after) or before.st_size != after.st_size:
        raise ValueError('Channel pointer changed while being read')
    return pointer, raw


def _pointer_digest(raw):
    return None if raw is None else hashlib.sha256(raw).hexdigest()


def _check_expected_pointer(raw, expected, description):
    if expected is _UNSET:
        return
    if expected is not None and (not isinstance(expected, str)
                                 or not re.fullmatch(r'[0-9a-f]{64}', expected)):
        raise ValueError(f'{description} digest must be lowercase SHA-256 or explicit absence')
    if _pointer_digest(raw) != expected:
        raise ValueError(f'{description} changed from the expected snapshot')


def publish(root: Path, apk: Path, channel: str, expected_cert: str, aapt: Path, apksigner: Path,
            *, expected_current_pointer_sha256=_UNSET,
            expected_other_pointer_sha256=_UNSET):
    """Publish a signed APK while serializing this feed root's writers.

    Optional pointer expectations pin an existing pointer by SHA-256 or pin
    absence with explicit ``None``. Omitted expectations retain the legacy
    call shape while still checking for pointer drift during this invocation.
    """
    if channel not in PACKAGES or not re.fullmatch('[0-9a-f]{64}', expected_cert):
        raise ValueError('Explicit channel and certificate SHA-256 required')
    if not root.is_absolute() or root.resolve(strict=True) != root or not root.is_dir():
        raise ValueError('Existing direct update directory required')
    if not apk.is_absolute() or apk.resolve(strict=True) != apk or apk.parent == root:
        raise ValueError('Explicit source APK outside update directory required')
    other_channel = 'tv' if channel == 'phone' else 'phone'
    with _feed_root_lock(root):
        pointer, initial_current = _pointer_bytes(root, channel)
        other_pointer, initial_other = _pointer_bytes(root, other_channel)
        _check_expected_pointer(initial_current, expected_current_pointer_sha256, 'Current channel pointer')
        _check_expected_pointer(initial_other, expected_other_pointer_sha256, 'Other channel pointer')

        package, version, name, cert = inspect_apk(apk, aapt, apksigner)
        if package != PACKAGES[channel] or cert != expected_cert:
            raise ValueError('Package or signing certificate mismatch')
        if initial_current is not None:
            old = json.loads(initial_current.decode('utf-8'))
            if (type(old) is not dict or old.get('channel') != channel
                    or old.get('package_name') != package
                    or old.get('signing_cert_sha256') != cert
                    or type(old.get('version_code')) is not int
                    or version <= old['version_code']):
                raise ValueError('Update must preserve signer and increase version code')
        digest = hashlib.sha256()
        size = 0
        with apk.open('rb') as source:
            for part in iter(lambda: source.read(1024 * 1024), b''):
                digest.update(part)
                size += len(part)
        if not 0 < size <= MAX_BYTES:
            raise ValueError('APK size invalid')
        sha = digest.hexdigest()
        destination = root / f'{sha}.apk'
        if destination.exists():
            if _direct_regular(destination).st_size != size or hashlib.sha256(destination.read_bytes()).hexdigest() != sha:
                raise ValueError('Existing package digest mismatch')
        else:
            with apk.open('rb') as source, destination.open('xb') as target:
                shutil.copyfileobj(source, target, 1024 * 1024)
                target.flush()
                os.fsync(target.fileno())
            if hashlib.sha256(destination.read_bytes()).hexdigest() != sha:
                raise ValueError('Copied package digest mismatch')
        manifest = {'schema_version': 1, 'channel': channel, 'package_name': package,
                    'version_code': version, 'version_name': name, 'bytes': size,
                    'sha256': sha, 'signing_cert_sha256': cert}
        temporary = root / f'.{channel}-{uuid.uuid4().hex}.json'
        try:
            with temporary.open('x', encoding='utf-8') as stream:
                json.dump(manifest, stream, separators=(',', ':'), sort_keys=True)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            # Recheck both pointers at the commit boundary. The shared lock
            # serializes cooperating publishers; this check also catches drift
            # from a writer that changed either pointer during this attempt.
            _, current_before_replace = _pointer_bytes(root, channel)
            _, other_before_replace = _pointer_bytes(root, other_channel)
            if current_before_replace != initial_current or other_before_replace != initial_other:
                raise ValueError('Channel pointer changed during publication')
            _check_expected_pointer(current_before_replace, expected_current_pointer_sha256,
                                   'Current channel pointer')
            _check_expected_pointer(other_before_replace, expected_other_pointer_sha256,
                                   'Other channel pointer')
            os.replace(temporary, pointer)
        finally:
            temporary.unlink(missing_ok=True)
        return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--apk', type=Path, required=True)
    parser.add_argument('--channel', choices=sorted(PACKAGES), required=True)
    parser.add_argument('--expected-cert-sha256', required=True)
    current_group = parser.add_mutually_exclusive_group()
    current_group.add_argument('--expected-current-pointer-sha256')
    current_group.add_argument('--expect-current-pointer-absent', action='store_true')
    other_group = parser.add_mutually_exclusive_group()
    other_group.add_argument('--expected-other-pointer-sha256')
    other_group.add_argument('--expect-other-pointer-absent', action='store_true')
    parser.add_argument('--aapt', type=Path, required=True)
    parser.add_argument('--apksigner', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        expected_current = _UNSET
        if args.expected_current_pointer_sha256 is not None:
            expected_current = args.expected_current_pointer_sha256
        elif args.expect_current_pointer_absent:
            expected_current = None
        expected_other = _UNSET
        if args.expected_other_pointer_sha256 is not None:
            expected_other = args.expected_other_pointer_sha256
        elif args.expect_other_pointer_absent:
            expected_other = None
        result = publish(
            args.root, args.apk, args.channel, args.expected_cert_sha256,
            args.aapt, args.apksigner,
            expected_current_pointer_sha256=expected_current,
            expected_other_pointer_sha256=expected_other,
        )
    except (OSError, ValueError, RuntimeError, KeyError, subprocess.SubprocessError, json.JSONDecodeError):
        parser.exit(2, 'Publication refused or incomplete; inspect feed pointers before retrying.\n')
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
