#!/usr/bin/env python3
"""Atomically select a verified static UI for the same running API."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile

from access_ui_overlay import ASSETS, SELECTION_NAME, read_selection, verify_overlay
from build_access_ui_overlay import _commit_id, git, manifest_bytes, source_files


def _compatible_source(api_commit, source_commit):
    prefix = git('rev-parse', '--show-prefix').decode('utf-8').strip()
    changed = set(git(
        'diff', '--name-only', '--no-renames', '-z', api_commit, source_commit, '--',
        prefix + 'backend', prefix + 'config', prefix + 'scripts',
    ).decode('utf-8').split('\0')) - {''}
    if changed - {prefix + path for path in ASSETS}:
        raise ValueError('UI requires a different API build')


def select_overlay(release_root, *, api_commit, source_commit, manifest_sha256, expected_current):
    root = Path(release_root)
    info = root.stat(follow_symlinks=False)
    if (root.resolve(strict=True) != root or not stat.S_ISDIR(info.st_mode)
            or getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
        raise ValueError('A direct release directory is required')
    api_commit = _commit_id(api_commit)
    source_commit = _commit_id(source_commit)
    if (re.fullmatch(r'[0-9a-f]{64}', manifest_sha256) is None
            or expected_current != 'none' and re.fullmatch(r'[0-9a-f]{64}', expected_current) is None):
        raise ValueError('Exact manifest digest required')
    _compatible_source(api_commit, source_commit)
    expected_manifest = manifest_bytes(source_commit, source_files(source_commit))
    if hashlib.sha256(expected_manifest).hexdigest() != manifest_sha256:
        raise ValueError('Staged overlay differs from reviewed source')
    verify_overlay(root / manifest_sha256, expected_source_commit=source_commit,
                   expected_manifest_sha256=manifest_sha256)

    marker = root / SELECTION_NAME
    lock = root / '.ui-selection.lock'
    lock_fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    temporary = None
    try:
        try:
            marker.lstat()
        except FileNotFoundError:
            previous = 'none'
        else:
            previous = read_selection(root, api_commit)['manifest_sha256']
        if previous != expected_current:
            raise ValueError('UI selection changed before activation')
        selected = dict(api_commit=api_commit, source_commit=source_commit,
                        manifest_sha256=manifest_sha256)
        with tempfile.NamedTemporaryFile(mode='wb', dir=root, prefix='.ui-selection-',
                                         delete=False) as stream:
            temporary = Path(stream.name)
            stream.write((json.dumps(selected, sort_keys=True) + '\n').encode('ascii'))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, marker)
        temporary = None
        return {**selected, 'previous_manifest_sha256': previous}
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        os.close(lock_fd)
        lock.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release-root', type=Path, required=True)
    parser.add_argument('--api-commit', required=True)
    parser.add_argument('--ui-commit', required=True)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--expect-current', required=True,
                        help='active manifest SHA-256, or none for initialization')
    args = parser.parse_args(argv)
    try:
        result = select_overlay(
            args.release_root, api_commit=args.api_commit, source_commit=args.ui_commit,
            manifest_sha256=args.manifest_sha256, expected_current=args.expect_current,
        )
    except (OSError, ValueError, subprocess.CalledProcessError):
        print('UI selection refused. Check the API pin, staged overlay and previous selection.')
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
