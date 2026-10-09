"""Closed source-only access UI overlay builder and router binding tests."""
import hashlib
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from access_ui_overlay import (ASSETS, MANIFEST_NAME, OverlayVerificationError,
                               bind_access_ui_overlay)
import build_access_ui_overlay as builder

SYNTHETIC_FILES = {
    'backend/app/ui/access/app.js': b'window.syntheticOverlay = true;\n',
    'backend/app/ui/access/index.html': b'<!doctype html><title>synthetic overlay</title>\n',
    'backend/app/ui/access/memory-community.js': b'window.syntheticCommunity = true;\n',
    'backend/app/ui/access/story-workspace.js': b'window.syntheticStoryWorkspace = true;\n',
    'backend/app/ui/access/styles.css': b'body { color: rgb(1, 2, 3); }\n',
}


def synthetic_git_repository(root, prefix=""):
    root.mkdir()
    env = dict(os.environ, GIT_AUTHOR_NAME='Overlay Test',
               GIT_AUTHOR_EMAIL='overlay-test@example.invalid',
               GIT_COMMITTER_NAME='Overlay Test',
               GIT_COMMITTER_EMAIL='overlay-test@example.invalid',
               GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)
    def git(*args):
        subprocess.run(['git', *args], cwd=root, env=env, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    git('init', '--quiet')
    for name, data in SYNTHETIC_FILES.items():
        path = root / prefix / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    git('add', '--', *(prefix + name for name in SYNTHETIC_FILES))
    git('commit', '--quiet', '-m', 'synthetic overlay fixture')
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root,
                                     env=env, stderr=subprocess.DEVNULL).decode().strip()
    return commit


def materialize(directory, commit):
    files = builder.source_files(commit)
    manifest = builder.manifest_bytes(commit, files)
    for name, data in files.items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (directory / MANIFEST_NAME).write_bytes(manifest)
    return files, manifest


class OverlayBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.git_temp = tempfile.TemporaryDirectory()
        cls.git_root = Path(cls.git_temp.name).resolve() / 'source'
        cls.source = synthetic_git_repository(cls.git_root)
        cls.original_builder_root = builder.ROOT
        builder.ROOT = cls.git_root

    @classmethod
    def tearDownClass(cls):
        builder.ROOT = cls.original_builder_root
        cls.git_temp.cleanup()

    def test_reads_exact_pinned_blobs_and_builds_deterministic_closed_zip(self):
        self.assertEqual(builder.ASSETS, ASSETS)
        self.assertEqual(builder.MANIFEST_NAME, MANIFEST_NAME)
        files = builder.source_files(self.source)
        self.assertEqual(tuple(files), ASSETS)
        self.assertEqual(set(files), set(ASSETS))
        self.assertEqual(files, SYNTHETIC_FILES)
        artifact = builder.package_bytes(self.source, files)
        self.assertEqual(artifact, builder.package_bytes(self.source, files))
        with zipfile.ZipFile(__import__('io').BytesIO(artifact)) as archive:
            self.assertEqual(set(archive.namelist()), set(ASSETS) | {MANIFEST_NAME})
            self.assertEqual(len(archive.namelist()), len(ASSETS) + 1)
            for item in archive.infolist():
                self.assertEqual(item.date_time, (1980, 1, 1, 0, 0, 0))
                self.assertEqual(item.external_attr >> 16, 0o100644)
            manifest = json.loads(archive.read(MANIFEST_NAME))
            self.assertEqual(manifest['source_commit'], self.source)
            self.assertEqual(set(manifest['files']), set(ASSETS))
            for name in ASSETS:
                self.assertEqual(archive.read(name), files[name])
                self.assertEqual(manifest['files'][name], hashlib.sha256(files[name]).hexdigest())

    def test_builder_rejects_incomplete_or_extra_source_maps(self):
        files = builder.source_files(self.source)
        with self.assertRaises(ValueError):
            builder.package_bytes(self.source, {key: val for key, val in files.items() if key != ASSETS[0]})
        with self.assertRaises(ValueError):
            builder.package_bytes(self.source, {**files, '../private': b'x'})
        with self.assertRaises(ValueError):
            builder.source_files('not-a-full-commit')

    def test_unified_server_subdirectory_reads_exact_assets(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary).resolve() / 'unified'
            commit = synthetic_git_repository(repo, prefix='server/')
            previous = builder.ROOT
            try:
                builder.ROOT = repo / 'server'
                files = builder.source_files(commit)
                self.assertEqual(files, SYNTHETIC_FILES)
                self.assertEqual(set(json.loads(builder.manifest_bytes(commit, files))['files']), set(ASSETS))
            finally:
                builder.ROOT = previous

    def test_output_creation_is_exclusive_and_does_not_overwrite(self):
        files = builder.source_files(self.source)
        payload = builder.package_bytes(self.source, files)
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp).resolve() / 'overlay.zip'
            builder.write_exclusive(target, payload)
            before = target.read_bytes()
            with self.assertRaises(FileExistsError):
                builder.write_exclusive(target, b'overwrite')
            self.assertEqual(target.read_bytes(), before)


class OverlayBindTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.git_temp = tempfile.TemporaryDirectory()
        cls.git_root = Path(cls.git_temp.name).resolve() / 'source'
        cls.source = synthetic_git_repository(cls.git_root)
        cls.original_builder_root = builder.ROOT
        builder.ROOT = cls.git_root

    @classmethod
    def tearDownClass(cls):
        builder.ROOT = cls.original_builder_root
        cls.git_temp.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve() / 'overlay'
        self.root.mkdir()
        self.files, self.manifest = materialize(self.root, self.source)
        self.manifest_sha = hashlib.sha256(self.manifest).hexdigest()
        sys.path.insert(0, str(ROOT / 'backend'))
        from app.routers import ui
        self.ui = ui
        self.before = {name: getattr(ui, name) for name in
                       ('UI_DIR', 'INDEX_FILE', 'APP_FILE', 'STYLE_FILE', 'ICON_FILE')}

    def tearDown(self):
        for name, value in self.before.items():
            setattr(self.ui, name, value)
        self.temp.cleanup()
        try:
            sys.path.remove(str(ROOT / 'backend'))
        except ValueError:
            pass

    def bind(self, **kwargs):
        return bind_access_ui_overlay(
            self.ui, self.root,
            expected_source_commit=kwargs.get('commit', self.source),
            expected_manifest_sha256=kwargs.get('digest', self.manifest_sha),
        )

    def assert_globals_unchanged(self):
        for name, value in self.before.items():
            self.assertEqual(getattr(self.ui, name), value)

    def test_validates_then_binds_only_static_globals_and_preserves_icon_route(self):
        verified = self.bind()
        self.assertEqual(verified.source_commit, self.source)
        self.assertEqual(verified.manifest_sha256, self.manifest_sha)
        self.assertEqual(self.ui.UI_DIR, self.root / 'backend/app/ui/access')
        self.assertEqual(self.ui.INDEX_FILE.read_bytes(), self.files['backend/app/ui/access/index.html'])
        self.assertEqual(self.ui.APP_FILE.read_bytes(), self.files['backend/app/ui/access/app.js'])
        self.assertEqual(self.ui.STYLE_FILE.read_bytes(), self.files['backend/app/ui/access/styles.css'])
        self.assertEqual(self.ui.ICON_FILE, self.before['ICON_FILE'])

        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        app = FastAPI()
        app.include_router(self.ui.router)
        with TestClient(app, base_url='https://photohouse.test') as client:
            routes = {
                '/ui': ('backend/app/ui/access/index.html', 'text/html'),
                '/ui/app.js': ('backend/app/ui/access/app.js', 'application/javascript'),
                '/ui/story-workspace.js': ('backend/app/ui/access/story-workspace.js', 'application/javascript'),
                '/ui/memory-community.js': ('backend/app/ui/access/memory-community.js', 'application/javascript'),
                '/ui/styles.css': ('backend/app/ui/access/styles.css', 'text/css'),
            }
            for route, (asset, media_type) in routes.items():
                response = client.get(route)
                self.assertEqual(response.status_code, 200, route)
                self.assertEqual(response.content, self.files[asset], route)
                self.assertTrue(response.headers['content-type'].startswith(media_type), route)
                self.assertEqual(response.headers['cache-control'],
                                 'no-store, no-cache, must-revalidate, max-age=0')
                self.assertIn("default-src 'none'", response.headers['content-security-policy'])
                self.assertEqual(response.headers['x-frame-options'], 'DENY')
                self.assertEqual(response.headers['cross-origin-resource-policy'], 'same-origin')
            self.assertIn(self.before['ICON_FILE'].name, {'photohouse-icon.png', 'photohouse-icon.svg'})
            icon = client.get('/ui/' + self.before['ICON_FILE'].name)
            self.assertEqual(icon.status_code, 200)
            self.assertEqual(icon.content, self.before['ICON_FILE'].read_bytes())
            icon_types = {'.png': 'image/png', '.svg': 'image/svg+xml'}
            self.assertIn(self.before['ICON_FILE'].suffix.lower(), icon_types)
            self.assertEqual(icon.headers['content-type'], icon_types[self.before['ICON_FILE'].suffix.lower()])

    def test_expected_source_and_manifest_identity_are_both_required(self):
        with self.assertRaises(OverlayVerificationError):
            self.bind(commit='0' * 40)
        self.assert_globals_unchanged()
        with self.assertRaises(OverlayVerificationError):
            self.bind(digest='0' * 64)
        self.assert_globals_unchanged()
        with self.assertRaises(OverlayVerificationError):
            bind_access_ui_overlay(self.ui, self.root, expected_source_commit=self.source,
                                    expected_manifest_sha256=None)
        self.assert_globals_unchanged()

    def test_tampered_asset_and_manifest_leave_router_unchanged(self):
        asset = self.root / ASSETS[0]
        asset.write_bytes(asset.read_bytes() + b'changed')
        with self.assertRaises(OverlayVerificationError):
            self.bind()
        self.assert_globals_unchanged()

    def test_missing_extra_and_empty_unexpected_directory_are_refused(self):
        victim = self.root / ASSETS[-1]
        backup = victim.read_bytes()
        victim.unlink()
        with self.assertRaises(OverlayVerificationError):
            self.bind()
        self.assert_globals_unchanged()
        victim.write_bytes(backup)
        (self.root / 'unlisted').write_bytes(b'x')
        with self.assertRaises(OverlayVerificationError):
            self.bind()
        (self.root / 'unlisted').unlink()
        (self.root / 'empty-extra').mkdir()
        with self.assertRaises(OverlayVerificationError):
            self.bind()
        self.assert_globals_unchanged()

    def test_symlinks_and_unsafe_or_duplicate_manifest_keys_are_refused(self):
        asset = self.root / ASSETS[0]
        moved = asset.with_suffix('.saved')
        asset.rename(moved)
        try:
            asset.symlink_to(moved.name)
            with self.assertRaises(OverlayVerificationError):
                self.bind()
            self.assert_globals_unchanged()
        finally:
            asset.unlink(missing_ok=True)
            moved.rename(asset)
        raw = self.manifest.replace(b'"files":', b'"../files":', 1)
        (self.root / MANIFEST_NAME).write_bytes(raw)
        with self.assertRaises(OverlayVerificationError):
            self.bind(digest=hashlib.sha256(raw).hexdigest())
        self.assert_globals_unchanged()
        duplicate = self.manifest[:-2] + b',"source_commit":"' + self.source.encode() + b'"}\n'
        (self.root / MANIFEST_NAME).write_bytes(duplicate)
        with self.assertRaises(OverlayVerificationError):
            self.bind(digest=hashlib.sha256(duplicate).hexdigest())
        self.assert_globals_unchanged()


if __name__ == '__main__':
    unittest.main()
