#!/usr/bin/env python3
"""Read-only attestation of one pinned, source-only API ZIP against local Git.

No extraction, import of packaged code, dependency install, network, model,
database, service or task operation. Run the verifier from the corresponding
reviewed source revision: its package builder defines the exact source closure.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
import threading
import types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'server/backend'))
from app.access.private_storage import require_private_file, stable_stat_identity

COMMIT = re.compile(r'[0-9a-f]{40}\Z')
DIGEST = re.compile(r'[0-9a-f]{64}\Z')
MAX_ARCHIVE_BYTES = 32 * 1024**2
REFUSAL_CODES = frozenset(('explicit_identity_invalid', 'archive_path_invalid', 'archive_identity_invalid', 'archive_changed', 'archive_hash_mismatch', 'archive_source_mismatch', 'git_identity_invalid', 'git_path_invalid', 'git_file_invalid', 'git_changed', 'git_hash_mismatch', 'source_inspection_timeout', 'git_output_limit', 'local_git_failed', 'builder_path_invalid', 'builder_size_invalid', 'builder_changed', 'builder_not_pinned', 'builder_root_invalid', 'schema_revision_invalid', 'cli_arguments_invalid'))


class Refused(ValueError):
    """A content-free package inspection refusal."""


class LocalGit:
    """Explicit verified local executable with bounded local-object output."""
    def __init__(self, executable, expected_sha256):
        self.executable = Path(executable)
        if not isinstance(expected_sha256, str) or not DIGEST.fullmatch(expected_sha256):
            raise Refused('git_identity_invalid')
        if (not self.executable.is_absolute() or
                self.executable.resolve(strict=True) != self.executable):
            raise Refused('git_path_invalid')
        for component in (self.executable, *self.executable.parents):
            info = component.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                raise Refused('git_path_invalid')
        self.expected_sha256 = expected_sha256
        self.raw, self.identity = self._read_binary()
        if hashlib.sha256(self.raw).hexdigest() != expected_sha256:
            raise Refused('git_hash_mismatch')
        self.deadline = time.monotonic() + 30
        if __package__:
            from .check_receipt import _git_env
        else:
            from check_receipt import _git_env
        self.environment = _git_env()
        self.environment.update(GIT_NO_REPLACE_OBJECTS='1', GIT_NO_LAZY_FETCH='1')
        self.cwd = ROOT / 'server'

    def _read_binary(self):
        path = self.executable
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or not 1 <= info.st_size <= 64 * 1024**2:
            raise Refused('git_file_invalid')
        before = stable_stat_identity(info)
        with os.fdopen(os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) |
                getattr(os, 'O_BINARY', 0)), 'rb') as stream:
            if stable_stat_identity(os.fstat(stream.fileno())) != before:
                raise Refused('git_changed')
            raw = stream.read(64 * 1024**2 + 1)
            if stable_stat_identity(os.fstat(stream.fileno())) != before:
                raise Refused('git_changed')
        if len(raw) != info.st_size or stable_stat_identity(path.stat()) != before:
            raise Refused('git_changed')
        return raw, before

    def __call__(self, *arguments):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise Refused('source_inspection_timeout')
        if stable_stat_identity(self.executable.stat()) != self.identity:
            raise Refused('git_changed')
        limit = 262144 if arguments[0] == 'ls-tree' else 2_000_000
        if arguments[0] == 'show':
            limit = 131072
        process = subprocess.Popen([str(self.executable), '--no-lazy-fetch', '-c', 'core.fsmonitor=false', *arguments],
            cwd=self.cwd, env=self.environment, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        expired = threading.Event()
        def expire():
            expired.set()
            try:
                process.kill()
            except OSError:
                pass
        timer = threading.Timer(min(10, remaining), expire)
        timer.daemon = True
        timer.start()
        try:
            raw = process.stdout.read(limit + 1)
            if len(raw) > limit:
                raise Refused('git_output_limit')
            process.wait(timeout=1)
            if expired.is_set():
                raise Refused('source_inspection_timeout')
            if process.returncode != 0:
                raise Refused('local_git_failed')
            if stable_stat_identity(self.executable.stat()) != self.identity:
                raise Refused('git_changed')
            return raw
        finally:
            timer.cancel()
            if process.poll() is None:
                process.kill()
                process.wait(timeout=1)
            process.stdout.close()

    def revalidate(self):
        raw, identity = self._read_binary()
        if raw != self.raw or identity != self.identity:
            raise Refused('git_changed')


def _builder(expected_commit, git):
    path = ROOT / 'server/scripts/build_staging_package.py'
    if path.resolve(strict=True) != path or not stat.S_ISREG(path.lstat().st_mode):
        raise Refused('builder_path_invalid')
    before = stable_stat_identity(path.stat())
    if not 1 <= before[2] <= 131072:
        raise Refused('builder_size_invalid')
    with os.fdopen(os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) |
            getattr(os, 'O_BINARY', 0)), 'rb') as stream:
        if stable_stat_identity(os.fstat(stream.fileno())) != before:
            raise Refused('builder_changed')
        raw = stream.read(131073)
        if stable_stat_identity(os.fstat(stream.fileno())) != before:
            raise Refused('builder_changed')
    committed = git('show', expected_commit + ':server/scripts/build_staging_package.py')
    if raw != committed or stable_stat_identity(path.stat()) != before:
        raise Refused('builder_not_pinned')
    # The package builder is local maintenance source, excluded from the ZIP.
    # Execute only bytes verified above, never re-import its mutable pathname or
    # import any application code from the candidate archive.
    module = types.ModuleType('photohouse_api_package_builder')
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    if module.ROOT != ROOT / 'server':
        raise Refused('builder_root_invalid')
    module.git = git
    return module


def _direct_archive(path):
    path = Path(path)
    if (not path.is_absolute() or '..' in path.parts or
            path.resolve(strict=True) != path):
        raise Refused('archive_path_invalid')
    for component in (path, *path.parents):
        info = component.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise Refused('archive_path_invalid')
    require_private_file(path)
    return path


def _read_archive(path, expected_identity=None):
    require_private_file(path)
    before = stable_stat_identity(path.stat())
    if (not 1 <= before[2] <= MAX_ARCHIVE_BYTES or
            expected_identity is not None and before != expected_identity):
        raise Refused('archive_identity_invalid')
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0)
    with os.fdopen(os.open(path, flags), 'rb') as stream:
        if stable_stat_identity(os.fstat(stream.fileno())) != before:
            raise Refused('archive_changed')
        raw = stream.read(MAX_ARCHIVE_BYTES + 1)
        if stable_stat_identity(os.fstat(stream.fileno())) != before:
            raise Refused('archive_changed')
    if len(raw) != before[2] or stable_stat_identity(path.stat()) != before:
        raise Refused('archive_changed')
    require_private_file(path)
    return raw, before


def inspect(archive, expected_commit, expected_sha256, git_executable, git_sha256,
            schema_revision='a0c9d2e4f817'):
    if (not isinstance(expected_commit, str) or not COMMIT.fullmatch(expected_commit) or
            not isinstance(expected_sha256, str) or not DIGEST.fullmatch(expected_sha256)):
        raise Refused('explicit_identity_invalid')
    archive = _direct_archive(archive)
    raw, identity = _read_archive(archive)
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise Refused('archive_hash_mismatch')
    git = LocalGit(git_executable, git_sha256)
    builder = _builder(expected_commit, git)
    if type(schema_revision) is not str or schema_revision not in builder.MIGRATION_REVISIONS:
        raise Refused('schema_revision_invalid')
    # Reconstruct from immutable regular Git blobs, with the reviewed builder's
    # member/expanded-size limits and exact source allowlist. Comparing the whole
    # canonical ZIP refuses every extra or changed member and ZIP metadata.
    files = builder.source_files(expected_commit)
    canonical = builder.package_bytes(expected_commit, files, schema_revision=schema_revision)
    if len(canonical) > MAX_ARCHIVE_BYTES or canonical != raw:
        raise Refused('archive_source_mismatch')
    # Reopen and hash after Git traversal; restored Windows modification time
    # alone must not conceal same-size replacement of the selected input.
    final_raw, final_identity = _read_archive(archive, identity)
    if final_identity != identity or final_raw != raw:
        raise Refused('archive_changed')
    git.revalidate()
    return {
        'schema': 1, 'kind': 'api_source_package_inspection', 'status': 'verified',
        'source_commit': expected_commit, 'source_files': len(files),
        'target_schema_revision': schema_revision,
        'zip_sha256': expected_sha256, 'bytes': len(raw), 'git_sha256': git_sha256,
        'source_only': True, 'private_configuration_included': False,
        'dependencies_included': False, 'extracted': False,
        'packaged_code_executed': False, 'database_opened': False,
        'models_called': False, 'services_changed': False, 'published': False,
    }


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        raise Refused('cli_arguments_invalid')


def main(argv=None):
    parser = SafeParser(description=__doc__)
    parser.add_argument('--archive', required=True, type=Path)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--git', required=True, type=Path, help='Reviewed absolute local Git executable')
    parser.add_argument('--git-sha256', required=True)
    parser.add_argument('--schema-revision', default='a0c9d2e4f817',
                        help='Explicit target schema used to reconstruct the expected package')
    try:
        args = parser.parse_args(argv)
        print(json.dumps(inspect(args.archive, args.commit, args.sha256, args.git, args.git_sha256,
                                 schema_revision=args.schema_revision), sort_keys=True))
        return 0
    except (Refused, ValueError, OSError, UnicodeError, subprocess.SubprocessError) as error:
        code = str(error) if isinstance(error, Refused) and str(error) in REFUSAL_CODES else 'inputs_unavailable'
        print(json.dumps({'kind': 'api_source_package_inspection', 'status': 'refused', 'error_code': code}, sort_keys=True))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
