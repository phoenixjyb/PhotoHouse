from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
from pathlib import Path
import hashlib, importlib.util, json, os, subprocess, tempfile, unittest, zipfile, warnings, sys, shutil
from unittest.mock import patch
from tools import inspect_api_package as tool

class InspectApiPackageTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.root.chmod(448)
        self.git = Path(shutil.which('git')).resolve(strict=True)
        self.git_sha = hashlib.sha256(self.git.read_bytes()).hexdigest()
        original_builder = (tool.ROOT / 'server/scripts/build_staging_package.py').read_text()
        start = original_builder.index('FILES = (')
        end = original_builder.index('\n\n\ndef git', start)
        mini_builder = original_builder[:start] + "FILES = ('a.py', 'b.txt')" + original_builder[end:]
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        (self.repo / 'server/scripts').mkdir(parents=True)
        (self.repo / 'server/scripts/build_staging_package.py').write_text(mini_builder)
        (self.repo / 'server/.env').write_text('SYNTHETIC_NOT_A_SECRET=yes\n')
        (self.repo / 'server/a.py').write_text('SAFE = True\n')
        (self.repo / 'server/b.txt').write_text('source only\n')
        for args in (['init', '-q'], ['add', 'server'], ['-c', 'user.name=Synthetic', '-c', 'user.email=synthetic@example.test', 'commit', '-qm', 'fixture']):
            subprocess.run(['git', *args], cwd=self.repo, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=self.repo, text=True).strip()
        s = importlib.util.spec_from_file_location('test_package_builder', self.repo / 'server/scripts/build_staging_package.py')
        self.builder = importlib.util.module_from_spec(s)
        s.loader.exec_module(self.builder)
        self.builder.ROOT = self.repo / 'server'
        self.archive = self.root / 'source.zip'
        self.raw = self.builder.package_bytes(self.commit, self.builder.source_files(self.commit))
        self.write(self.raw)
        self.mock = patch.object(tool, 'ROOT', self.repo)
        self.mock.start()
        self.addCleanup(self.mock.stop)

    def write(self, raw):
        self.archive.write_bytes(raw)
        self.archive.chmod(384)
        self.digest = hashlib.sha256(raw).hexdigest()

    def inspect(self, commit=None, digest=None, schema_revision='a0c9d2e4f817'):
        return tool.inspect(self.archive, self.commit if commit is None else commit,
                            self.digest if digest is None else digest, self.git, self.git_sha,
                            schema_revision=schema_revision)

    def test_exact_immutable_source_is_read_only(self):
        before = set(self.root.rglob('*'))
        r = self.inspect()
        self.assertEqual(r['source_files'], 2)
        self.assertEqual(r['source_commit'], self.commit)
        self.assertEqual(r['zip_sha256'], self.digest)
        self.assertEqual(set(self.root.rglob('*')), before)
        self.assertEqual(self.archive.read_bytes(), self.raw)
        for key in ('extracted', 'packaged_code_executed', 'database_opened', 'models_called', 'services_changed', 'published', 'private_configuration_included', 'dependencies_included'):
            self.assertIs(r[key], False)

    def test_explicit_schema_target_reconstructs_exact_archive(self):
        for revision in ('e7c1a9d5b304', 'f2a8c5d1e640'):
            with self.subTest(revision=revision):
                raw = self.builder.package_bytes(self.commit,
                    self.builder.source_files(self.commit), schema_revision=revision)
                self.write(raw)
                report = self.inspect(schema_revision=revision)
                self.assertEqual(report['status'], 'verified')
                self.assertEqual(report['target_schema_revision'], revision)

    def test_schema_target_mismatch_and_unknown_target_are_refused(self):
        raw = self.builder.package_bytes(self.commit,
            self.builder.source_files(self.commit), schema_revision='f2a8c5d1e640')
        self.write(raw)
        with self.assertRaisesRegex(tool.Refused, 'archive_source_mismatch'):
            self.inspect()
        with self.assertRaisesRegex(tool.Refused, 'archive_source_mismatch'):
            self.inspect(schema_revision='e7c1a9d5b304')
        with self.assertRaisesRegex(tool.Refused, 'schema_revision_invalid'):
            self.inspect(schema_revision='unsupported')

    def test_dirty_worktree_does_not_replace_committed_source(self):
        (self.repo / 'server/a.py').write_text('UNREVIEWED = True\n')
        self.assertEqual(self.inspect()['status'], 'verified')

    def test_invalid_full_identity_refused(self):
        for commit, digest in [(self.commit[:7], self.digest), (self.commit.upper(), self.digest), (self.commit, 'A' * 64), (self.commit, None)]:
            with self.subTest(commit=commit, digest=digest), self.assertRaises(tool.Refused):
                tool.inspect(self.archive, commit, digest, self.git, self.git_sha)

    def test_digest_mismatch_refused(self):
        with self.assertRaisesRegex(tool.Refused, 'archive_hash_mismatch'):
            self.inspect(digest='0' * 64)

    def test_self_consistent_changed_source_refused(self):
        self.write(self.builder.package_bytes(self.commit, {'a.py': b'SAFE = False\n', 'b.txt': b'source only\n'}))
        with self.assertRaisesRegex(tool.Refused, 'archive_source_mismatch'):
            self.inspect()

    def test_extra_member_and_duplicate_manifest_refused(self):
        for name in ('private-config.json', 'manifest.json', '../escape.txt'):
            with self.subTest(name=name):
                self.write(self.raw)
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore', UserWarning)
                    with zipfile.ZipFile(self.archive, 'a') as z:
                        z.writestr(name, b'{}')
                self.digest = hashlib.sha256(self.archive.read_bytes()).hexdigest()
                with self.assertRaisesRegex(tool.Refused, 'archive_source_mismatch'):
                    self.inspect()

    def test_repacked_equivalent_members_refused(self):
        with zipfile.ZipFile(self.archive) as z:
            items = [(i.filename, z.read(i)) for i in z.infolist()]
        with zipfile.ZipFile(self.archive, 'w', compression=zipfile.ZIP_DEFLATED) as z:
            for name, data in items:
                z.writestr(name, data)
        self.digest = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        with self.assertRaisesRegex(tool.Refused, 'archive_source_mismatch'):
            self.inspect()

    @unittest.skipIf(os.name == 'nt', 'POSIX file mode fixture; Windows ACL is a separate native gate')
    def test_private_file_and_symlink_required(self):
        self.archive.chmod(420)
        with self.assertRaises(ValueError):
            self.inspect()
        self.archive.chmod(384)
        link = self.root / 'linked.zip'
        link.symlink_to(self.archive)
        with self.assertRaisesRegex(tool.Refused, 'archive_path_invalid'):
            tool.inspect(link, self.commit, self.digest, self.git, self.git_sha)

    def test_symlink_parent_refused(self):
        link = self.root / 'directory-link'
        link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(tool.Refused, 'archive_path_invalid'):
            tool.inspect(link / 'source.zip', self.commit, self.digest, self.git, self.git_sha)

    def test_hardlink_refused(self):
        os.link(self.archive, self.root / 'other.zip')
        with self.assertRaises(ValueError):
            self.inspect()

    def test_invalid_and_oversized_file_refused_before_git(self):
        self.write(b'')
        with self.assertRaisesRegex(tool.Refused, 'archive_identity_invalid'):
            self.inspect()
        with self.archive.open('wb') as f:
            f.truncate(tool.MAX_ARCHIVE_BYTES + 1)
        with self.assertRaisesRegex(tool.Refused, 'archive_identity_invalid'):
            self.inspect()

    def mutate_source_traversal(self, callback):
        original = tool._builder

        def builder(commit, git):
            module = original(commit, git)
            read = module.source_files

            def change(commit):
                files = read(commit)
                callback()
                return files
            module.source_files = change
            return module
        return patch.object(tool, '_builder', side_effect=builder)

    def test_replaced_during_git_traversal_refused(self):

        def change():
            old = self.archive.stat()
            self.archive.write_bytes(self.raw[:-1] + b'X')
            os.utime(self.archive, ns=(old.st_atime_ns, old.st_mtime_ns))
        with self.mutate_source_traversal(change), self.assertRaises(tool.Refused):
            self.inspect()

    @unittest.skipIf(os.name == 'nt', 'POSIX mode mutation; Windows ACL is a separate native gate')
    def test_permission_change_during_git_refused(self):
        with self.mutate_source_traversal(lambda: self.archive.chmod(420)), self.assertRaises(ValueError):
            self.inspect()

    def test_dirty_builder_cannot_widen_to_private_config_or_execute(self):
        path = self.repo / 'server/scripts/build_staging_package.py'
        path.write_text(path.read_text() + "\nFILES = FILES + ('.env',)\nraise RuntimeError('dirty builder was executed')\n")
        with self.assertRaisesRegex(tool.Refused, 'builder_not_pinned'):
            self.inspect()

    def test_ambient_fake_git_is_not_selected(self):
        directory = self.root / 'bin'
        directory.mkdir()
        fake = directory / 'git'
        marker = self.root / 'fake-was-executed'
        fake.write_text('#!/bin/sh\n/bin/touch ' + str(marker) + '\necho invented\n')
        fake.chmod(448)
        with patch.dict(os.environ, {'PATH': str(directory) + os.pathsep + os.environ['PATH']}):
            self.assertEqual(self.inspect()['status'], 'verified')
        self.assertFalse(marker.exists())

    def test_git_hash_mismatch_refused_before_execution(self):
        with self.assertRaisesRegex(tool.Refused, 'git_hash_mismatch'):
            tool.inspect(self.archive, self.commit, self.digest, self.git, '0' * 64)

    def test_git_symlink_path_refused(self):
        path = self.root / 'git-link'
        path.symlink_to(self.git)
        with self.assertRaisesRegex(tool.Refused, 'git_path_invalid'):
            tool.inspect(self.archive, self.commit, self.digest, path, self.git_sha)

    def test_bounded_git_output_refused(self):
        from io import BytesIO

        class Process:

            def __init__(self):
                self.stdout = BytesIO(b'X' * 200000)
                self.returncode = 0

            def wait(self, timeout=None):
                return 0

            def poll(self):
                return 0

            def kill(self):
                pass
        with patch.object(tool.subprocess, 'Popen', return_value=Process()), self.assertRaisesRegex(tool.Refused, 'git_output_limit'):
            self.inspect()

    def test_local_git_override_and_replace_ref_cannot_change_source(self):
        env = {'GIT_DIR': '/not-a-repository', 'GIT_WORK_TREE': '/wrong', 'GIT_REPLACE_REF_BASE': 'refs/evil/', 'GIT_CONFIG_COUNT': '1', 'GIT_CONFIG_KEY_0': 'core.fsmonitor', 'GIT_CONFIG_VALUE_0': '/missing'}
        with patch.dict(os.environ, env):
            self.assertEqual(self.inspect()['status'], 'verified')

    def test_real_git_replace_ref_is_ignored(self):
        (self.repo / 'server/a.py').write_text('UNREVIEWED = True\n')
        subprocess.run(['git', 'add', 'server'], cwd=self.repo, check=True)
        subprocess.run(['git', '-c', 'user.name=Synthetic', '-c', 'user.email=synthetic@example.test', 'commit', '-qm', 'changed'], cwd=self.repo, check=True)
        other = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=self.repo, text=True).strip()
        subprocess.run(['git', 'replace', self.commit, other], cwd=self.repo, check=True)
        self.assertEqual(self.inspect()['status'], 'verified')

    def test_missing_promised_blob_cannot_trigger_lazy_fetch(self):
        oid = subprocess.check_output([str(self.git), 'rev-parse', self.commit + ':server/a.py'], cwd=self.repo, text=True).strip()
        objects = self.repo / '.git/objects'
        (objects / oid[:2] / oid[2:]).unlink()
        for key, value in [('extensions.partialClone', 'origin'), ('remote.origin.promisor', 'true'), ('remote.origin.url', str(self.root / 'absent-generated-local-remote'))]:
            subprocess.run([str(self.git), 'config', key, value], cwd=self.repo, check=True)
        commands = []
        original = tool.subprocess.Popen

        def capture(arguments, **kwargs):
            commands.append((arguments, kwargs['env']))
            return original(arguments, **kwargs)
        with patch.object(tool.subprocess, 'Popen', side_effect=capture), self.assertRaisesRegex(tool.Refused, 'local_git_failed'):
            self.inspect()
        self.assertTrue(commands)
        self.assertTrue(all(('--no-lazy-fetch' in args and env.get('GIT_NO_LAZY_FETCH') == '1' for args, env in commands)))

    def test_source_budget_timeout_refused(self):
        with patch.object(tool.time, 'monotonic', side_effect=[0, 31]), self.assertRaisesRegex(tool.Refused, 'source_inspection_timeout'):
            self.inspect()

    def test_cli_safe_refusal_has_no_private_path(self):
        output = StringIO()
        with redirect_stdout(output):
            code = tool.main(['--archive', str(self.archive), '--commit', self.commit, '--sha256', '0' * 64, '--git', str(self.git), '--git-sha256', self.git_sha])
        self.assertEqual(code, 2)
        r = json.loads(output.getvalue())
        self.assertEqual(r, {'kind': 'api_source_package_inspection', 'status': 'refused', 'error_code': 'archive_hash_mismatch'})
        self.assertNotIn(str(self.archive), output.getvalue())

    def test_cli_verified_output_has_no_private_path(self):
        output = StringIO()
        with redirect_stdout(output):
            code = tool.main(['--archive', str(self.archive), '--commit', self.commit, '--sha256', self.digest, '--git', str(self.git), '--git-sha256', self.git_sha])
        self.assertEqual(code, 0)
        report = json.loads(output.getvalue())
        self.assertEqual(report['status'], 'verified')
        self.assertEqual(report['target_schema_revision'], 'a0c9d2e4f817')
        self.assertNotIn(str(self.root), output.getvalue())

    def test_cli_schema_revision_binds_inspection_target(self):
        raw = self.builder.package_bytes(self.commit,
            self.builder.source_files(self.commit), schema_revision='f2a8c5d1e640')
        self.write(raw)
        output = StringIO()
        with redirect_stdout(output):
            code = tool.main(['--archive', str(self.archive), '--commit', self.commit,
                '--sha256', self.digest, '--git', str(self.git), '--git-sha256', self.git_sha,
                '--schema-revision', 'f2a8c5d1e640'])
        self.assertEqual(code, 0)
        report = json.loads(output.getvalue())
        self.assertEqual(report['status'], 'verified')
        self.assertEqual(report['target_schema_revision'], 'f2a8c5d1e640')
        output = StringIO()
        with redirect_stdout(output):
            code = tool.main(['--archive', str(self.archive), '--commit', self.commit,
                '--sha256', self.digest, '--git', str(self.git), '--git-sha256', self.git_sha])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output.getvalue())['error_code'], 'archive_source_mismatch')

    def test_unknown_exception_message_is_never_echoed(self):
        output = StringIO()
        with patch.object(tool, 'inspect', side_effect=ValueError(str(self.archive))), redirect_stdout(output):
            code = tool.main(['--archive', str(self.archive), '--commit', self.commit, '--sha256', self.digest, '--git', str(self.git), '--git-sha256', self.git_sha])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output.getvalue())['error_code'], 'inputs_unavailable')
        self.assertNotIn(str(self.archive), output.getvalue())

    def test_invalid_cli_does_not_echo_private_arguments(self):
        output, error = (StringIO(), StringIO())
        with redirect_stdout(output), redirect_stderr(error):
            code = tool.main(['--unexpected-private-argument', str(self.archive)])
        self.assertEqual(code, 2)
        self.assertEqual(error.getvalue(), '')
        self.assertEqual(json.loads(output.getvalue())['status'], 'refused')
        self.assertNotIn(str(self.archive), output.getvalue())
if __name__ == '__main__':
    unittest.main()
