"""Immutable caption closure, portable source layout and no-overwrite packaging."""
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_released_caption_package as package


class ReleasedCaptionPackageTests(unittest.TestCase):
    def files(self):
        return {name: ('synthetic ' + name).encode() for name in package.FILES}

    def test_exact_deterministic_source_only_closure_and_hashes(self):
        files = self.files()
        data = package.package_bytes('a' * 40, files)
        self.assertEqual(data, package.package_bytes('a' * 40, dict(reversed(list(files.items())))))
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            manifest = json.loads(archive.read('manifest.json'))
            self.assertEqual(set(archive.namelist()), set(package.FILES) | {'manifest.json'})
            self.assertEqual(manifest['artifact_kind'], 'released_caption_worker_source_only')
            self.assertEqual(manifest['source_commit'], 'a' * 40)
            self.assertEqual(manifest['schema_revision'], 'a0c9d2e4f817')
            for field in ('activated', 'dependencies_included', 'private_configuration_included',
                          'model_weights_included', 'media_included'):
                self.assertIs(manifest[field], False)
            for name, value in files.items():
                self.assertEqual(manifest['files'][name], hashlib.sha256(value).hexdigest())
            for required in ('config/detailed-caption-prompt.txt', 'scripts/qualify_memory_groups.py',
                             'scripts/bounded_windows_job.py', 'backend/app/access/private_storage.py',
                             'scripts/qualify_released_caption_worker.py', 'scripts/run_released_caption_worker.py'):
                self.assertIn(required, archive.namelist())
            self.assertFalse(any(name.endswith(('.env', '.sqlite', '.safetensors', '.gguf', '.apk'))
                                 for name in archive.namelist()))

    def test_extra_missing_floating_or_unknown_schema_refused(self):
        files = self.files()
        for selected in ({**files, '.env': b'excluded'},
                         {k: v for k, v in files.items() if k != 'config/detailed-caption-prompt.txt'}):
            with self.assertRaises(ValueError):
                package.package_bytes('a' * 40, selected)
        with self.assertRaises(ValueError):
            package.source_files('HEAD')
        with self.assertRaises(ValueError):
            package.package_bytes('a' * 40, files, schema_revision='unknown')

    def test_cli_creates_once_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary).resolve() / 'source.zip'
            args = ['--commit', 'a' * 40, '--out', str(output)]
            with patch.object(package, 'source_files', return_value=self.files()), redirect_stdout(io.StringIO()):
                self.assertEqual(package.main(args), 0)
                original = output.read_bytes()
                self.assertEqual(output.stat().st_mode & 0o777, 0o600)
                self.assertEqual(package.main(args), 2)
            self.assertEqual(output.read_bytes(), original)

    def test_git_uses_pinned_committed_source_in_both_layouts(self):
        for prefix in ('', 'server/'):
            with self.subTest(prefix=prefix), tempfile.TemporaryDirectory() as temporary:
                repo = Path(temporary).resolve()
                def git(*args):
                    return subprocess.check_output(['git', '-c', 'commit.gpgsign=false',
                        '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', *args],
                        cwd=repo, stderr=subprocess.DEVNULL)
                git('init', '-q')
                files = self.files()
                for name, value in files.items():
                    path = repo / (prefix + name)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(value)
                git('add', '.'); git('commit', '-qm', 'Synthetic source')
                commit = git('rev-parse', 'HEAD').decode().strip()
                dirty = repo / (prefix + 'config/detailed-caption-prompt.txt')
                dirty.write_bytes(b'uncommitted prompt remains untouched')
                untracked = repo / (prefix + '.env')
                untracked.write_bytes(b'excluded fixture')
                with patch.object(package, 'ROOT', repo / prefix):
                    self.assertEqual(package.source_files(commit), files)
                self.assertEqual(dirty.read_bytes(), b'uncommitted prompt remains untouched')
                self.assertTrue(untracked.exists())

    def test_missing_prompt_and_symlink_cannot_enter_source(self):
        rows = b'\0'.join(('100644 blob abc\tserver/' + name).encode()
                           for name in package.FILES if name != 'config/detailed-caption-prompt.txt')
        with patch.object(package, 'git', side_effect=[b'commit', b'server/', rows]):
            with self.assertRaisesRegex(ValueError, 'missing'):
                package.source_files('a' * 40)
        with patch.object(package, 'git', side_effect=[b'commit', b'server/',
                b'120000 blob abc\tserver/config/detailed-caption-prompt.txt\0']):
            with self.assertRaisesRegex(ValueError, 'Regular'):
                package.source_files('a' * 40)

    def test_total_source_budget_refused_before_blob_reads(self):
        rows = b'\0'.join(('100644 blob abc\t' + name).encode() for name in package.FILES)
        with patch.object(package, 'git', side_effect=[b'commit', b'', rows,
                *([b'999999'] * len(package.FILES))]):
            with self.assertRaisesRegex(ValueError, 'budget'):
                package.source_files('a' * 40)


if __name__ == '__main__':
    unittest.main()
