#!/usr/bin/env python3
"""Build a deterministic static UI overlay from an explicit Git commit.

This creates a source-only ZIP. It does not touch the API package, configuration,
runtime files, Windows, or any service.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import zipfile


ROOT = Path(__file__).resolve().parents[1]
ASSETS = tuple(sorted((
    'backend/app/ui/access/index.html',
    'backend/app/ui/access/app.js',
    'backend/app/ui/access/story-workspace.js',
    'backend/app/ui/access/memory-community.js',
    'backend/app/ui/access/styles.css',
)))
MANIFEST_NAME = 'manifest.json'
MAX_ASSET_BYTES = 1_000_000
MAX_TOTAL_BYTES = 2_000_000


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT,
                                   stderr=subprocess.DEVNULL)


def _commit_id(commit):
    if type(commit) is not str or re.fullmatch(r'[0-9a-f]{40}', commit) is None:
        raise ValueError('Full source commit required')
    if git('cat-file', '-t', commit).strip() != b'commit':
        raise ValueError('Full source commit required')
    return commit


def source_files(commit):
    """Read exactly the five selected regular blobs from the immutable commit."""
    commit = _commit_id(commit)
    prefix = git('rev-parse', '--show-prefix').decode('utf-8').strip()
    records = git('ls-tree', '-r', '-z', '--full-tree', commit,
                  '--', *(prefix + name for name in ASSETS)).split(b'\0')
    objects = {}
    for record in filter(None, records):
        identity, name = record.split(b'\t', 1)
        mode, kind, oid = identity.decode('ascii').split()
        name = name.decode('utf-8')
        if not name.startswith(prefix):
            raise ValueError('UI source is outside the application root')
        name = name[len(prefix):]
        if name not in ASSETS or mode not in ('100644', '100755') or kind != 'blob':
            raise ValueError('Only allowlisted regular UI source is allowed')
        if name in objects:
            raise ValueError('Duplicate source path')
        objects[name] = oid
    if set(objects) != set(ASSETS):
        raise ValueError('Pinned commit lacks a required UI file')
    sizes = {name: int(git('cat-file', '-s', oid)) for name, oid in objects.items()}
    if any(size > MAX_ASSET_BYTES for size in sizes.values()) or sum(sizes.values()) > MAX_TOTAL_BYTES:
        raise ValueError('UI overlay size limit exceeded')
    return {name: git('cat-file', 'blob', objects[name]) for name in ASSETS}


def manifest_bytes(commit, files):
    _commit_id(commit)
    if type(files) is not dict or set(files) != set(ASSETS):
        raise ValueError('Exact UI allowlist required')
    if any(type(data) is not bytes or len(data) > MAX_ASSET_BYTES for data in files.values()):
        raise ValueError('UI asset is not bounded bytes')
    if sum(map(len, files.values())) > MAX_TOTAL_BYTES:
        raise ValueError('UI overlay size limit exceeded')
    manifest = {
        'artifact_kind': 'photohouse_access_ui_overlay_source_only',
        'format_version': 1,
        'source_commit': commit,
        'files': {name: hashlib.sha256(files[name]).hexdigest() for name in ASSETS},
    }
    return (json.dumps(manifest, ensure_ascii=True, sort_keys=True,
                       separators=(',', ':')) + '\n').encode('ascii')


def package_bytes(commit, files):
    commit = _commit_id(commit)
    if type(files) is not dict or set(files) != set(ASSETS):
        raise ValueError('Exact UI allowlist required')
    manifest = manifest_bytes(commit, files)
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_STORED) as archive:
        for name, data in [*((name, files[name]) for name in ASSETS),
                           (MANIFEST_NAME, manifest)]:
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    return output.getvalue()


def write_exclusive(path, payload):
    path = Path(path)
    if (not path.is_absolute() or '..' in path.parts or path.name in ('', '.', '..')
            or path.parent.resolve(strict=True) != path.parent):
        raise ValueError('Explicit direct output required')
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0)
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, 'wb', closefd=False) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(fd)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit', required=True,
                        help='full immutable source commit SHA-1')
    parser.add_argument('--out', required=True, type=Path,
                        help='new absolute output ZIP path')
    args = parser.parse_args(argv)
    try:
        files = source_files(args.commit)
        artifact = package_bytes(args.commit, files)
        write_exclusive(args.out, artifact)
        manifest = manifest_bytes(args.commit, files)
        print(json.dumps({
            'source_commit': args.commit,
            'asset_count': len(ASSETS),
            'asset_manifest_sha256': hashlib.sha256(manifest).hexdigest(),
            'archive_sha256': hashlib.sha256(artifact).hexdigest(),
            'archive_bytes': len(artifact),
            'deployed': False,
        }, sort_keys=True))
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError):
        print('UI overlay build refused; existing files were not overwritten.')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
