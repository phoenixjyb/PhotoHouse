"""Synthetic tests for an explicitly private per-provider exchange parent."""

import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.app.access import selected_story_process as process_module
from backend.app.access.host_inference_admission import HostInferenceAdmission, HostResourceProfile
from backend.app.access.selected_story_process import (
    ProcessSelectedStoryError, ProcessSelectedStoryProvider, process_launch_digest,
)
from test_selected_story_local import MODEL, bundle, make_scope, narrative
from test_selected_story_native import launch_spec
from test_selected_story_process import FileKernel, encoded_response


class SelectedStoryExchangeRootTests(unittest.IsolatedAsyncioTestCase):
    def provider(self, root, writer=None):
        kernel = FileKernel(writer)
        constructions = []

        def factory():
            constructions.append(True)
            return kernel

        provider = ProcessSelectedStoryProvider(
            launch_spec(), MODEL, kernel_factory=factory, enabled=True,
            cleanup_seconds=0.05, exchange_root=root)
        self.addAsyncCleanup(provider.close)
        return provider, kernel, constructions

    async def test_explicit_root_contains_only_exchange_and_preserves_sibling_and_temp_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve() / 'private-exchange'
            root.mkdir(mode=0o700)
            sibling = root / 'operator-owned.txt'
            sibling.write_text('retain')
            before_tempdir = tempfile.tempdir
            before_env = os.environ.get('TMPDIR')
            seen = {}

            def writer(environment):
                request_path = Path(environment[process_module.REQUEST_ENV])
                response_path = Path(environment[process_module.RESPONSE_ENV])
                seen['directory'] = request_path.parent
                seen['request'] = request_path.read_bytes()
                request = json.loads(seen['request'])
                response_path.write_bytes(encoded_response(operation_id=request['operation_id']))

            provider, _kernel, factories = self.provider(root, writer)
            self.assertEqual(narrative(), await provider.prepare(bundle(), make_scope()))
            self.assertEqual([True], factories)
            self.assertEqual(root, seen['directory'].parent)
            self.assertTrue(seen['request'])
            scope = provider._active.scope
            self.assertTrue(await provider.stop_and_reconcile(scope))
            self.assertEqual('retain', sibling.read_text())
            self.assertEqual([sibling], list(root.iterdir()))
            self.assertEqual(before_tempdir, tempfile.tempdir)
            self.assertEqual(before_env, os.environ.get('TMPDIR'))

    def test_constructor_validates_spelling_without_filesystem_or_temp_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve() / 'private-exchange'
            before_tempdir = tempfile.tempdir
            before_env = os.environ.get('TMPDIR')
            with patch.object(Path, 'lstat', side_effect=AssertionError('filesystem access')):
                provider = ProcessSelectedStoryProvider(
                    launch_spec(), MODEL, kernel_factory=lambda: self.fail('kernel'),
                    enabled=False, exchange_root=root)
            self.assertFalse(provider.enabled)
            self.assertEqual(before_tempdir, tempfile.tempdir)
            self.assertEqual(before_env, os.environ.get('TMPDIR'))

    def test_invalid_root_spellings_refuse_in_constructor(self):
        for root in ('relative/path', '/tmp/../escape', '//server/share', '\\\\server\\share'):
            with self.subTest(root=root), self.assertRaises(ValueError):
                ProcessSelectedStoryProvider(launch_spec(), MODEL,
                    kernel_factory=lambda: None, exchange_root=root)

    def test_exchange_root_is_part_of_explicit_host_profile_but_none_hash_is_legacy_stable(self):
        launch = launch_spec()
        legacy = {key: getattr(launch, key) for key in (
            'executable', 'executable_sha256', 'argv', 'cwd', 'memory_limit',
            'process_limit', 'minimum_free_ram')}
        legacy['environment'] = dict(launch.environment)
        expected = hashlib.sha256(json.dumps(legacy, sort_keys=True, ensure_ascii=True,
            separators=(',', ':')).encode('utf-8')).hexdigest()
        self.assertEqual(expected, process_launch_digest(launch))
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            first_root = base / 'exchange-a'
            second_root = base / 'exchange-b'
            first = process_launch_digest(launch, exchange_root=first_root)
            second = process_launch_digest(launch, exchange_root=second_root)
            self.assertNotEqual(first, second)
            self.assertNotEqual(expected, first)

            mismatched_profile = HostResourceProfile('cpu', expected, 1, 1)
            host = HostInferenceAdmission(base / 'host', mismatched_profile,
                capacity_probe=lambda: None, enabled=False)
            constructed = []
            with patch.object(Path, 'lstat', side_effect=AssertionError('filesystem access')):
                with self.assertRaisesRegex(ValueError, 'Host admission launch binding mismatch'):
                    ProcessSelectedStoryProvider(launch, MODEL,
                        kernel_factory=lambda: constructed.append(True),
                        host_admission=host, exchange_root=first_root)
            self.assertEqual([], constructed)

    async def test_missing_unprivate_and_symlink_roots_refuse_before_payload_or_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            missing = base / 'missing'
            cases = [('missing', missing)]
            unprivate = base / 'unprivate'
            unprivate.mkdir(mode=0o700)
            if os.name == 'posix':
                unprivate.chmod(0o755)
                cases.append(('unprivate', unprivate))
                target = base / 'target'
                target.mkdir(mode=0o700)
                symlink = base / 'symlink'
                symlink.symlink_to(target, target_is_directory=True)
                cases.append(('symlink', symlink))
            for label, root in cases:
                with self.subTest(root=label):
                    provider, kernel, constructions = self.provider(root)
                    scope = make_scope()
                    with self.assertRaises(ProcessSelectedStoryError):
                        await provider.prepare(bundle(), scope)
                    self.assertEqual([], constructions)
                    self.assertNotIn('resume', kernel.events)
                    self.assertTrue(await provider.stop_and_reconcile(scope))
                    self.assertIsNone(provider._active)
                    self.assertEqual([], list(root.iterdir()) if root.exists() and root.is_dir() else [])

    async def test_parent_replacement_before_payload_write_retains_exchange_until_parent_repaired(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            root = base / 'private-exchange'
            root.mkdir(mode=0o700)
            moved = base / 'original-parent'
            original_chmod = os.chmod

            def replace_after_identity(path, mode, **kwargs):
                original_chmod(path, mode, **kwargs)
                root.rename(moved)
                root.mkdir(mode=0o700)
                return None

            provider, kernel, constructions = self.provider(root)
            scope = make_scope()
            with patch.object(process_module.os, 'chmod', side_effect=replace_after_identity):
                with self.assertRaises(ProcessSelectedStoryError):
                    await provider.prepare(bundle(), scope)
            self.assertEqual([], constructions)
            self.assertNotIn('resume', kernel.events)
            self.assertFalse(await provider.stop_and_reconcile(scope))
            self.assertIsNotNone(provider._active)
            retained = next(moved.iterdir())
            self.assertEqual([], list(retained.iterdir()))  # No request/source payload was written.
            root.rename(base / 'replacement-parent')
            moved.rename(root)
            self.assertTrue(await provider.stop_and_reconcile(scope))
            self.assertEqual([], list(root.iterdir()))

    async def test_parent_replacement_during_worker_read_holds_exchange_until_repaired(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            root = base / 'private-exchange'
            root.mkdir(mode=0o700)
            sibling = root / 'keep.txt'
            sibling.write_text('keep')
            moved = base / 'original-parent'

            def writer(environment):
                request = json.loads(
                    Path(environment[process_module.REQUEST_ENV]).read_bytes())
                Path(environment[process_module.RESPONSE_ENV]).write_bytes(
                    encoded_response(operation_id=request['operation_id']))
                root.rename(moved)
                root.mkdir(mode=0o700)

            provider, _kernel, _constructions = self.provider(root, writer)
            scope = make_scope()
            with self.assertRaises(ProcessSelectedStoryError):
                await provider.prepare(bundle(), scope)
            retained_dir = moved / next(item.name for item in moved.iterdir() if item.is_dir())
            self.assertTrue((retained_dir / 'request.json').is_file())
            self.assertTrue((retained_dir / 'response.json').is_file())
            self.assertFalse(await provider.stop_and_reconcile(scope))
            self.assertIsNotNone(provider._active)
            root.rename(base / 'replacement-parent')
            moved.rename(root)
            self.assertTrue(await provider.stop_and_reconcile(scope))
            self.assertEqual('keep', sibling.read_text())
            self.assertEqual([sibling], list(root.iterdir()))


if __name__ == '__main__':
    unittest.main()
