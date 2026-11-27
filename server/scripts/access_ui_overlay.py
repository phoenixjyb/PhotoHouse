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
from threading import Lock
from types import MappingProxyType
import types


ASSETS = tuple(sorted((
    'backend/app/ui/access/index.html',
    'backend/app/ui/access/app.js',
    'backend/app/ui/access/assistant-private-workspace.js',
    'backend/app/ui/access/voice-session-control.js',
    'backend/app/ui/access/voice-turn-timing.js',
    'backend/app/ui/access/story-workspace.js',
    'backend/app/ui/access/story-draft-store.js',
    'backend/app/ui/access/memory-community.js',
    'backend/app/ui/access/memory-groups.js',
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


def _direct_stat(path):
    info = path.stat(follow_symlinks=False)
    attributes = getattr(info, 'st_file_attributes', 0)
    if stat.S_ISLNK(info.st_mode) or attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        _fail()
    return info


def _bounded_file(path, limit):
    info = _direct_stat(path)
    if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
        _fail()
    with path.open('rb') as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        _fail()
    return data


def verify_overlay(overlay_dir, *, expected_source_commit, expected_manifest_sha256):
    """Read and fully verify a materialized package tree without changing state."""
    if not _valid_identity(expected_source_commit, expected_manifest_sha256):
        _fail()
    root = Path(overlay_dir)
    try:
        if not stat.S_ISDIR(_direct_stat(root).st_mode) or root.resolve(strict=True) != root:
            _fail()
        manifest_path = root / MANIFEST_NAME
        expected_dirs = (root, root / 'backend', root / 'backend/app',
                         root / 'backend/app/ui', root / 'backend/app/ui/access')
        expected_paths = {root / name for name in ASSETS} | {manifest_path, *expected_dirs[1:]}
        for directory in expected_dirs:
            if not stat.S_ISDIR(_direct_stat(directory).st_mode):
                _fail()
            expected = {path for path in expected_paths if path.parent == directory}
            for entry in directory.iterdir():
                if entry not in expected:
                    _fail()
                expected.remove(entry)
            if expected:
                _fail()
        manifest_raw = _bounded_file(manifest_path, 16_384)
        manifest_sha = hashlib.sha256(manifest_raw).hexdigest()
        if manifest_sha != expected_manifest_sha256:
            _fail()
        manifest = json.loads(manifest_raw.decode('utf-8'), object_pairs_hook=_pairs_no_duplicates)
        if (type(manifest) is not dict
                or set(manifest) != {'artifact_kind', 'format_version', 'source_commit', 'files'}
                or manifest['artifact_kind'] != 'photohouse_access_ui_overlay_source_only'
                or type(manifest['format_version']) is not int or manifest['format_version'] != 2
                or manifest['source_commit'] != expected_source_commit
                or type(manifest['files']) is not dict or set(manifest['files']) != set(ASSETS)):
            _fail()

        file_hashes = []
        total = 0
        for name in ASSETS:
            path = root / name
            data = _bounded_file(path, MAX_ASSET_BYTES)
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

SELECTION_NAME = 'current.json'


def read_selection(release_root, expected_api_commit):
    """Read the exact, operator-owned release selector. It contains no paths."""
    try:
        marker = _bounded_file(release_root / SELECTION_NAME, 1024)
        selection = json.loads(marker, object_pairs_hook=_pairs_no_duplicates)
        if (type(selection) is not dict
                or set(selection) != {'api_commit', 'source_commit', 'manifest_sha256'}
                or selection['api_commit'] != expected_api_commit
                or not _valid_identity(selection['source_commit'], selection['manifest_sha256'])):
            _fail()
        return selection
    except (OSError, ValueError, RecursionError):
        _fail()


class LiveAccessUIOverlays:
    """Serve complete verified byte snapshots of the active and preceding UI."""

    def __init__(self, release_root, expected_api_commit):
        self.root = Path(release_root)
        if (not _valid_identity(expected_api_commit, '0' * 64)
                or self.root.resolve(strict=True) != self.root
                or not stat.S_ISDIR(_direct_stat(self.root).st_mode)):
            _fail()
        self.api_commit = expected_api_commit
        self.lock = Lock()
        self.marker_identity = None
        self.snapshots = ()
        self.manifest_sha256 = None
        if not self():
            _fail()

    def __call__(self):
        # Serialize pointer reads and snapshot swaps across concurrent requests.
        # An in-flight HTTP handler keeps its own reference to one complete set.
        with self.lock:
            try:
                info = _direct_stat(self.root / SELECTION_NAME)
                identity = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
                if identity != self.marker_identity:
                    # Latch each published selector once. To correct a refused
                    # release, publish a new selector after staging its bytes.
                    self.marker_identity = identity
                    selection = read_selection(self.root, self.api_commit)
                    manifest_sha256 = selection['manifest_sha256']
                    if manifest_sha256 == self.manifest_sha256:
                        return self.snapshots
                    overlay = verify_overlay(
                        self.root / manifest_sha256,
                        expected_source_commit=selection['source_commit'],
                        expected_manifest_sha256=selection['manifest_sha256'],
                    )
                    assets = {}
                    total = 0
                    for relative, digest in overlay.file_sha256:
                        name = Path(relative).name
                        data = _bounded_file(overlay.ui_dir / name, MAX_ASSET_BYTES)
                        total += len(data)
                        if total > MAX_TOTAL_BYTES or hashlib.sha256(data).hexdigest() != digest:
                            _fail()
                        assets[name] = (data, digest)
                    self.snapshots = (MappingProxyType(assets), *self.snapshots[:1])
                    self.manifest_sha256 = manifest_sha256
            except (OSError, OverlayVerificationError):
                # A missing, unverified or momentarily unreadable update cannot
                # displace the last verified bytes. A verified rollback selects
                # the old release through the same mechanism.
                pass
            return self.snapshots


def bind_live_access_ui_overlays(ui_module, release_root, *, expected_api_commit):
    """Called once by a trusted launcher before the API starts accepting traffic."""
    if not isinstance(ui_module, types.ModuleType) or 'LIVE_UI_RELEASES' not in vars(ui_module):
        _fail()
    ui_module.LIVE_UI_RELEASES = LiveAccessUIOverlays(release_root, expected_api_commit)
