"""Verify and bind a source-only access UI overlay to the existing UI router.

The caller supplies both the source commit and manifest digest through a trusted
deployment decision. Verification completes before any router global is changed.
"""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import stat
import types


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


class OverlayVerificationError(ValueError):
    """A bounded, input-free overlay refusal."""


@dataclass(frozen=True)
class VerifiedOverlay:
    source_commit: str
    manifest_sha256: str
    file_sha256: tuple[tuple[str, str], ...]
    ui_dir: Path


def _fail():
    raise OverlayVerificationError('access UI overlay verification failed') from None


def _valid_identity(source_commit, manifest_sha256):
    return (type(source_commit) is str and re.fullmatch(r'[0-9a-f]{40}', source_commit)
            and type(manifest_sha256) is str
            and re.fullmatch(r'[0-9a-f]{64}', manifest_sha256))


def _pairs_no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail()
        result[key] = value
    return result


def verify_overlay(overlay_dir, *, expected_source_commit, expected_manifest_sha256):
    """Read and fully verify a materialized package tree without changing state."""
    if not _valid_identity(expected_source_commit, expected_manifest_sha256):
        _fail()
    root = Path(overlay_dir)
    try:
        if root.is_symlink() or not root.is_dir() or root.resolve(strict=True) != root:
            _fail()
        manifest_path = root / MANIFEST_NAME
        if manifest_path.is_symlink() or not manifest_path.is_file():
            _fail()
        expected_paths = {root / name for name in ASSETS} | {manifest_path}
        observed = set()
        observed_dirs = set()
        for path in root.rglob('*'):
            if path.is_symlink():
                _fail()
            if path.is_dir():
                observed_dirs.add(path)
                continue
            if not path.is_file() or path.resolve(strict=True) != path:
                _fail()
            observed.add(path)
        if observed != expected_paths:
            _fail()
        expected_dirs = {root / 'backend', root / 'backend/app',
                         root / 'backend/app/ui', root / 'backend/app/ui/access'}
        if observed_dirs != expected_dirs:
            _fail()

        manifest_stat = manifest_path.stat(follow_symlinks=False)
        if not stat.S_ISREG(manifest_stat.st_mode) or manifest_stat.st_size > 16_384:
            _fail()
        manifest_raw = manifest_path.read_bytes()
        manifest_sha = hashlib.sha256(manifest_raw).hexdigest()
        if manifest_sha != expected_manifest_sha256:
            _fail()
        manifest = json.loads(manifest_raw.decode('utf-8'), object_pairs_hook=_pairs_no_duplicates)
        if (type(manifest) is not dict
                or set(manifest) != {'artifact_kind', 'format_version', 'source_commit', 'files'}
                or manifest['artifact_kind'] != 'photohouse_access_ui_overlay_source_only'
                or type(manifest['format_version']) is not int or manifest['format_version'] != 1
                or manifest['source_commit'] != expected_source_commit
                or type(manifest['files']) is not dict or set(manifest['files']) != set(ASSETS)):
            _fail()

        file_hashes = []
        total = 0
        for name in ASSETS:
            path = root / name
            info = path.stat(follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_ASSET_BYTES:
                _fail()
            data = path.read_bytes()
            total += len(data)
            digest = hashlib.sha256(data).hexdigest()
            declared = manifest['files'][name]
            if (type(declared) is not str or re.fullmatch(r'[0-9a-f]{64}', declared) is None
                    or digest != declared):
                _fail()
            file_hashes.append((name, digest))
        if total > MAX_TOTAL_BYTES:
            _fail()
        ui_dir = root / 'backend/app/ui/access'
        return VerifiedOverlay(expected_source_commit, manifest_sha,
                               tuple(file_hashes), ui_dir)
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError, RecursionError):
        _fail()


def bind_access_ui_overlay(ui_module, overlay_dir, *, expected_source_commit,
                           expected_manifest_sha256):
    """Verify an overlay, then atomically update only the four static UI globals."""
    if not isinstance(ui_module, types.ModuleType):
        _fail()
    required = {'UI_DIR', 'INDEX_FILE', 'APP_FILE', 'STYLE_FILE', 'ICON_FILE'}
    namespace = vars(ui_module)
    if not required.issubset(namespace):
        _fail()
    original_icon = namespace['ICON_FILE']
    verified = verify_overlay(
        overlay_dir,
        expected_source_commit=expected_source_commit,
        expected_manifest_sha256=expected_manifest_sha256,
    )
    # One dict update happens only after all input and target validation succeeds.
    namespace.update({
        'UI_DIR': verified.ui_dir,
        'INDEX_FILE': verified.ui_dir / 'index.html',
        'APP_FILE': verified.ui_dir / 'app.js',
        'STYLE_FILE': verified.ui_dir / 'styles.css',
        'ICON_FILE': original_icon,
    })
    return verified
