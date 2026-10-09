"""Build a successor offline rehearsal archive from pinned Git blobs.

The reviewed prior archive defines the source allowlist. Fixture imports are
expanded from Git, so collection cannot accidentally rely on the full checkout.
No source module is executed, and no existing output is overwritten.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import zipfile

BASELINE_SHA256 = 'c3d04af1fa60ff1e8aacf5aab71e4c73814676d6a70656a6feda9b9a47fade51'
ADDITIONS = (
    'backend/requirements-editorial-test.in',
    'backend/requirements-editorial-test.lock',
    'scripts/bounded_windows_job.py',
    'scripts/run_editorial_rehearsal_group.py',
    'scripts/build_editorial_rehearsal_package.py',
    'tests/security/test_bounded_windows_job.py',
    'tests/security/test_fixture_network_guard.py',
    'scripts/apply_memory_editorial_schema.py',
    'scripts/apply_memory_sources_schema.py',
    'tests/security/test_apply_memory_editorial_schema.py',
    'docs/security/MEMOIR_EDITORIAL_SCHEMA_APPLICATION.md',
    'scripts/approved_face_queue.py',
    'scripts/run_approved_face_pipeline.py',
    'scripts/approved_face_inference_child.py',
    'tests/security/test_approved_face_queue.py',
    'tests/security/test_approved_face_pipeline.py',
    'tests/security/test_editorial_rehearsal_database_guard.py',
)
MAX_TOTAL_BYTES = 16 * 1024**2
MAX_MEMBER_BYTES = 2 * 1024**2


def relative_path(name: str) -> str:
    if (not isinstance(name, str) or not name or '\\' in name or ':' in name
            or any(ord(c) < 32 for c in name) or any(p in ('', '.', '..') for p in name.split('/'))
            or PurePosixPath(name).is_absolute()):
        raise ValueError('unsafe_member')
    return name


def git_blob(repo: Path, commit: str, path: str) -> bytes:
    relative_path(path)
    data = subprocess.check_output(['git', 'show', commit + ':' + path], cwd=repo,
                                   stderr=subprocess.DEVNULL)
    if len(data) > MAX_MEMBER_BYTES:
        raise ValueError('source_size_limit')
    return data


def source_files(repo: Path, commit: str, baseline: Path) -> dict[str, bytes]:
    if not re.fullmatch('[0-9a-f]{40}', commit):
        raise ValueError('full_commit_required')
    raw = baseline.read_bytes()
    if hashlib.sha256(raw).hexdigest() != BASELINE_SHA256:
        raise ValueError('baseline_hash_mismatch')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        manifest = json.loads(z.read('manifest.json'))
        files = manifest['files']
        if len(files) != 213 or set(z.namelist()) != set(files) | {'manifest.json'}:
            raise ValueError('baseline_shape_mismatch')
        for name, digest in files.items():
            relative_path(name)
            if hashlib.sha256(z.read(name)).hexdigest() != digest:
                raise ValueError('baseline_member_mismatch')
    names = set(files) | set(ADDITIONS)
    sources = {name: git_blob(repo, commit, name) for name in sorted(names)}
    pending = [name for name in names if name.startswith('tests/') and name.endswith('.py')]
    visited = set(pending)
    while pending:
        tree = ast.parse(sources[pending.pop()])
        for node in ast.walk(tree):
            modules = ([item.name for item in node.names] if isinstance(node, ast.Import)
                       else [node.module] if isinstance(node, ast.ImportFrom) else [])
            for module in modules:
                if module and module.startswith('test_'):
                    name = 'tests/security/' + module.split('.')[0] + '.py'
                    if name not in sources:
                        sources[name] = git_blob(repo, commit, name)
                    if name not in visited:
                        visited.add(name)
                        pending.append(name)
    if sum(len(data) for data in sources.values()) > MAX_TOTAL_BYTES:
        raise ValueError('source_size_limit')
    return sources


def build(repo: Path, commit: str, baseline: Path, output: Path) -> dict:
    if not output.is_absolute() or output.exists() or not output.parent.is_dir():
        raise ValueError('new_absolute_output_required')
    files = source_files(repo, commit, baseline)
    manifest = {'format_version': 1, 'artifact_kind': 'offline_synthetic_rehearsal_source_only',
                'source_commit': commit, 'baseline_archive_sha256': BASELINE_SHA256,
                'target_revision': 'b1d7e4a9c230', 'source_revision_for_migration_fixture': 'a0c9d2e4f817',
                'runtime_enabled': False, 'live_database_access': False,
                'task_or_service_control': False, 'client_publication': False,
                'private_configuration_included': False, 'original_media_included': False,
                'files': {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}}
    with output.open('xb') as stream, zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_STORED) as z:
        values = dict(files, **{'manifest.json': (json.dumps(manifest, sort_keys=True, indent=2) + '\n').encode()})
        for name, data in sorted(values.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            z.writestr(info, data)
    return {'source_commit': commit, 'members': len(files), 'bytes': output.stat().st_size,
            'sha256': hashlib.sha256(output.read_bytes()).hexdigest(), 'execution_enabled': False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(build(args.repo, args.commit, args.baseline, args.output), sort_keys=True))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError, zipfile.BadZipFile):
        print(json.dumps({'status': 'refused', 'existing_output_overwritten': False}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
