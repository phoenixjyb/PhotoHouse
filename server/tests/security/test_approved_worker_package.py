import hashlib
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_approved_worker_package as package


class ApprovedWorkerPackageTests(unittest.TestCase):
    def test_fixed_source_only_contents_and_hashes(self):
        files = {name: ('synthetic ' + name).encode() for name in package.FILES}
        data = package.package_bytes('a' * 40, files)
        self.assertEqual(data, package.package_bytes('a' * 40, files))
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            manifest = json.loads(archive.read('manifest.json'))
            self.assertEqual(set(archive.namelist()), set(package.FILES) | {'manifest.json'})
            self.assertFalse(manifest['activated'])
            self.assertEqual(manifest['schema_revision'], 'a0c9d2e4f817')
            self.assertFalse(manifest['model_weights_included'])
            self.assertFalse(manifest['media_included'])
            self.assertIn('scripts/run_approved_cpu_worker.py', archive.namelist())
            self.assertIn('scripts/run_approved_video_worker.py', archive.namelist())
            self.assertNotIn('backend/app/main.py', archive.namelist())
            for name, value in files.items():
                self.assertEqual(manifest['files'][name], hashlib.sha256(value).hexdigest())

    def test_extra_or_missing_source_refused(self):
        files = {name: b'x' for name in package.FILES}
        with self.assertRaises(ValueError):
            package.package_bytes('a' * 40, {**files, '.env': b'secret'})
        files.pop(next(iter(files)))
        with self.assertRaises(ValueError):
            package.package_bytes('a' * 40, files)

    def test_explicit_additive_targets_change_only_manifest_metadata(self):
        files = {name: ('synthetic ' + name).encode() for name in package.FILES}
        legacy = package.package_bytes('a' * 40, files)
        for revision in ('b1d7e4a9c230', 'c2e6b8a1d490', 'd1f6a8c3e920'):
            current = package.package_bytes('a' * 40, files, schema_revision=revision)
            self.assertNotEqual(legacy, current)
            with self.subTest(revision=revision), \
                    zipfile.ZipFile(io.BytesIO(legacy)) as left, \
                    zipfile.ZipFile(io.BytesIO(current)) as right:
                self.assertEqual(left.namelist(), right.namelist())
                old_manifest, new_manifest = (json.loads(archive.read('manifest.json'))
                                              for archive in (left, right))
                self.assertEqual(new_manifest.pop('schema_revision'), revision)
                self.assertEqual(old_manifest.pop('schema_revision'), 'a0c9d2e4f817')
                self.assertEqual(old_manifest, new_manifest)
                for name in package.FILES:
                    self.assertEqual(left.read(name), right.read(name))
            self.assertEqual(current, package.package_bytes(
                'a' * 40, dict(reversed(list(files.items()))), schema_revision=revision))

    def test_unknown_target_refuses_without_creating_archive(self):
        files = {name: b'x' for name in package.FILES}
        for revision in ('unknown', '', None, True):
            with self.subTest(revision=revision), patch.object(package.zipfile, 'ZipFile') as archive:
                with self.assertRaisesRegex(ValueError, 'supported target schema'):
                    package.package_bytes('a' * 40, files, schema_revision=revision)
                archive.assert_not_called()

    def test_cli_binds_selected_schema_to_archive_and_receipt(self):
        files = {name: b'synthetic worker source' for name in package.FILES}
        with tempfile.TemporaryDirectory() as temporary:
            for option, expected in (([], 'a0c9d2e4f817'),
                                     (['--schema-revision', 'b1d7e4a9c230'], 'b1d7e4a9c230'),
                                     (['--schema-revision', 'c2e6b8a1d490'], 'c2e6b8a1d490'),
                                     (['--schema-revision', 'd1f6a8c3e920'], 'd1f6a8c3e920')):
                with self.subTest(expected=expected):
                    target = Path(temporary).resolve() / (expected + '.zip')
                    stdout = io.StringIO()
                    with patch.object(package, 'source_files', return_value=files), redirect_stdout(stdout):
                        self.assertEqual(package.main(['--commit', 'a' * 40, '--out', str(target), *option]), 0)
                    receipt = json.loads(stdout.getvalue())
                    self.assertEqual(receipt['schema_revision'], expected)
                    self.assertEqual(receipt['sha256'], hashlib.sha256(target.read_bytes()).hexdigest())
                    self.assertFalse(receipt['activated'])
                    with zipfile.ZipFile(target) as archive:
                        self.assertEqual(json.loads(archive.read('manifest.json'))['schema_revision'], expected)

    def test_floating_commit_symlink_and_oversize_refused(self):
        with self.assertRaises(ValueError):
            package.source_files('HEAD')
        with patch.object(package, 'git', side_effect=[b'commit', b'', b'120000 blob abc\tbackend/app/config.py\0']):
            with self.assertRaises(ValueError):
                package.source_files('a' * 40)
        rows = b'\0'.join(('100644 blob abc\t' + name).encode() for name in package.FILES)
        with patch.object(package, 'git', side_effect=[b'commit', b'', rows, *([b'999999'] * len(package.FILES))]):
            with self.assertRaises(ValueError):
                package.source_files('a' * 40)

    def test_git_reads_committed_worker_source_from_both_repository_layouts(self):
        for prefix in ('', 'server/'):
            with self.subTest(prefix=prefix), tempfile.TemporaryDirectory() as temporary:
                repo = Path(temporary).resolve()
                def git(*args):
                    return subprocess.check_output(['git', '-c', 'commit.gpgsign=false',
                        '-c', 'user.name=PhotoHouseFixture', '-c', 'user.email=fixture@example.invalid',
                        *args], cwd=repo, stderr=subprocess.DEVNULL)
                git('init', '-q')
                files = {name: ('committed fixture ' + name).encode() for name in package.FILES}
                for name, data in files.items():
                    target = repo / (prefix + name)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
                if prefix:
                    decoy = repo / 'scripts/run_approved_cpu_worker.py'
                    decoy.parent.mkdir(parents=True)
                    decoy.write_bytes(b'wrong root-level source')
                git('add', '.')
                git('commit', '-qm', 'Synthetic worker source')
                commit = git('rev-parse', 'HEAD').decode().strip()
                source_root = repo / prefix
                dirty = source_root / 'scripts/run_approved_cpu_worker.py'
                dirty.write_bytes(b'preserve uncommitted work')
                untracked = source_root / '.env'
                untracked.write_bytes(b'generated excluded fixture')
                with patch.object(package, 'ROOT', source_root):
                    selected = package.source_files(commit)
                self.assertEqual(selected, files)
                self.assertEqual(dirty.read_bytes(), b'preserve uncommitted work')
                self.assertTrue(untracked.exists())
                with zipfile.ZipFile(io.BytesIO(package.package_bytes(commit, selected))) as archive:
                    self.assertEqual(set(archive.namelist()), set(package.FILES) | {'manifest.json'})
                    self.assertEqual(archive.read('scripts/run_approved_cpu_worker.py'),
                                     files['scripts/run_approved_cpu_worker.py'])

    def test_missing_monorepo_source_never_falls_back_to_root_decoy(self):
        prefix = b'server/'
        rows = b'\0'.join(('100644 blob abc\tserver/' + name).encode()
                          for name in package.FILES if name != 'scripts/run_approved_cpu_worker.py')
        with patch.object(package, 'git', side_effect=[b'commit', prefix, rows]):
            with self.assertRaisesRegex(ValueError, 'missing'):
                package.source_files('a' * 40)
