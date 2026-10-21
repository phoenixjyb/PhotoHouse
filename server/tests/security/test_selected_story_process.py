"""Synthetic file-protocol tests for the owned selected-story worker."""

import asyncio
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from backend.app.access.memory_narrative import MAX_PROVIDER_BYTES, _generation_payload
from backend.app.access.selected_story_native import NativeStoryLaunch
from backend.app.access.selected_story_operations import PreparationScope
from backend.app.access.selected_story_process import (
    MAX_REQUEST_BYTES, REQUEST_ENV, RESPONSE_ENV, ProcessSelectedStoryError,
    ProcessSelectedStoryProvider,
)
from test_selected_story_local import MODEL, bundle, make_scope, narrative
from test_selected_story_native import EXE, EXE_HASH, launch_spec


OTHER_ID = '12345678-1234-4234-8234-123456789abc'


def encoded_response(*, operation_id='abcdefab-cdef-4abc-8def-abcdefabcdef',
                     model=MODEL, version=1, result=None):
    value = {'version': version, 'operation_id': operation_id, 'model': model,
             'result': narrative() if result is None else result}
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()


class FileKernel:
    """Native owner test double; writes only synthetic files at resume."""

    def __init__(self, writer=None, *, exited=True):
        self.writer = writer
        self.exited = exited
        self.events = []
        self.environment = None
        self.active = 0

    def free_ram(self):
        return 16 * 1024**3

    def sha256_file(self, _path, _deadline):
        return EXE_HASH

    def create_job(self, _memory, _processes):
        return object()

    def create_suspended(self, _executable, _argv, environment, _cwd):
        self.environment = environment
        return 'process', 'thread', 101

    def assign(self, _job, _process):
        return True

    def resume(self, _thread):
        self.events.append('resume')
        if self.writer:
            self.writer(self.environment)
        return True

    def wait_process(self, _process, _milliseconds):
        return 'exited' if self.exited else 'timeout'

    def exit_code(self, _process):
        return 0

    def active_processes(self, _job):
        return self.active

    def terminate_job(self, _job):
        self.active = 0
        self.exited = True
        return True

    def terminate_process(self, _process):
        self.exited = True
        return True

    def close(self, _handle):
        pass


class ProcessSelectedStoryTests(unittest.IsolatedAsyncioTestCase):
    def provider(self, writer=None, *, enabled=True, environment=None, kernel=None,
                 model=MODEL, **kwargs):
        kernel = kernel or FileKernel(writer)
        factories = []

        def factory():
            factories.append(True)
            return kernel

        base = launch_spec(environment=environment or {'PATH': '/synthetic/bin'})
        provider = ProcessSelectedStoryProvider(base, model, kernel_factory=factory,
            enabled=enabled, cleanup_seconds=0.05, **kwargs)
        self.addAsyncCleanup(provider.close)
        return provider, kernel, factories

    async def cleanup_call(self, provider, scope):
        self.assertTrue(await asyncio.wait_for(provider.stop_and_reconcile(scope), 2))

    async def test_default_off_does_not_create_directory_or_kernel(self):
        provider, _kernel, factories = self.provider(enabled=False)
        scope = make_scope()
        with patch('backend.app.access.selected_story_process.tempfile.mkdtemp') as mkdtemp:
            with self.assertRaises(ProcessSelectedStoryError) as caught:
                await provider.prepare(bundle(), scope)
        self.assertEqual('disabled', caught.exception.category)
        mkdtemp.assert_not_called()
        self.assertEqual([], factories)

    def test_reserved_environment_and_invalid_models_fail_at_configuration(self):
        for environment in (
                {'PATH': '/bin', REQUEST_ENV.lower(): '/attacker/request'},
                {'PATH': '/bin', RESPONSE_ENV.lower(): '/attacker/response'}):
            with self.subTest(environment=environment), self.assertRaises(ValueError):
                self.provider(environment=environment)
        for model in ('', 'model with spaces', 'https://example.test/model', 'x' * 121):
            with self.subTest(model=model), self.assertRaises(ValueError):
                self.provider(model=model)

    async def test_request_binding_private_permissions_and_valid_response(self):
        observed = {}

        def writer(environment):
            request_path = Path(environment[REQUEST_ENV])
            response_path = Path(environment[RESPONSE_ENV])
            observed['request'] = request_path.read_bytes()
            observed['request_mode'] = stat.S_IMODE(request_path.stat().st_mode)
            observed['directory_mode'] = stat.S_IMODE(request_path.parent.stat().st_mode)
            observed['operation'] = environment['PHOTOHOUSE_NATIVE_STORY_OPERATION']
            observed['response_path'] = response_path
            request = json.loads(observed['request'])
            observed['request_object'] = request
            response_path.write_bytes(encoded_response(operation_id=request['operation_id']))

        provider, kernel, factories = self.provider(writer)
        scope = make_scope()
        result = await provider.prepare(bundle(), scope)
        self.assertEqual(narrative(), result)
        self.assertEqual([True], factories)
        self.assertEqual(scope.operation_id, observed['operation'])
        self.assertEqual(scope.operation_id, observed['request_object']['operation_id'])
        self.assertEqual(1, observed['request_object']['version'])
        self.assertEqual(MODEL, observed['request_object']['generation']['model'])
        self.assertEqual(_generation_payload(bundle(), 'narrative', MODEL),
                         observed['request_object']['generation'])
        self.assertLessEqual(len(observed['request']), MAX_REQUEST_BYTES)
        if os.name == 'posix':
            self.assertEqual(0o600, observed['request_mode'])
            self.assertEqual(0o700, observed['directory_mode'])
        self.assertEqual('resume', kernel.events[0])
        await self.cleanup_call(provider, scope)
        self.assertFalse(observed['response_path'].parent.exists())

    async def test_closed_response_envelope_rejects_binding_and_json_faults(self):
        invalid = {
            'wrong operation': encoded_response(operation_id=OTHER_ID),
            'wrong model': encoded_response(model='other-model'),
            'wrong version': encoded_response(version=2),
            'boolean version': encoded_response(version=True),
            'nonfinite': encoded_response().replace(b'"version":1', b'"version":NaN', 1),
            'invalid narrative': encoded_response(result={'version': 1}),
            'unknown field': encoded_response()[:-1] + b',"extra":true}',
            'duplicate key': b'{"version":1,"version":1,"operation_id":"abcdefab-cdef-4abc-8def-abcdefabcdef","model":"qwen-local","result":{}}',
            'invalid utf8': b'\xff',
            'truncated': encoded_response()[:-4],
            'oversized': b' ' * (MAX_PROVIDER_BYTES + 1),
        }
        for label, body in invalid.items():
            with self.subTest(label=label):
                def writer(environment, body=body):
                    Path(environment[RESPONSE_ENV]).write_bytes(body)

                provider, _kernel, _factories = self.provider(writer)
                scope = make_scope()
                with self.assertRaises(ProcessSelectedStoryError) as caught:
                    await provider.prepare(bundle(), scope)
                self.assertEqual('invalid_response', caught.exception.category)
                await self.cleanup_call(provider, scope)

    @unittest.skipUnless(os.name == 'posix', 'POSIX link fixtures; Windows qualification separate')
    async def test_symlink_hardlink_and_nonregular_responses_fail_closed(self):
        for label in ('symlink', 'hardlink', 'directory'):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as external:
                target = Path(external) / 'target.json'
                target.write_bytes(encoded_response())

                def writer(environment, label=label):
                    path = Path(environment[RESPONSE_ENV])
                    if label == 'symlink':
                        path.symlink_to(target)
                    elif label == 'hardlink':
                        path.write_bytes(encoded_response())
                        os.link(path, path.parent / 'alias.json')
                    else:
                        path.mkdir()

                provider, _kernel, _factories = self.provider(writer)
                scope = make_scope()
                with self.assertRaises(ProcessSelectedStoryError) as caught:
                    await provider.prepare(bundle(), scope)
                self.assertEqual('invalid_response', caught.exception.category)
                self.assertFalse(await provider.stop_and_reconcile(scope))
                # Test fixture removes only the attack artifact it created, so
                # the retained provider can finish normal cleanup afterward.
                active = provider._active
                if label == 'symlink' and active:
                    (active.directory / 'response.json').unlink()
                elif label == 'hardlink' and active:
                    (active.directory / 'alias.json').unlink()
                    (active.directory / 'response.json').unlink()
                elif label == 'directory' and active:
                    (active.directory / 'response.json').rmdir()
                await self.cleanup_call(provider, scope)
                self.assertIsNone(provider._active)

    async def test_unknown_entry_and_failed_unlink_retain_exchange_until_repaired(self):
        created = {}

        def writer(environment):
            path = Path(environment[RESPONSE_ENV])
            path.write_bytes(encoded_response())
            (path.parent / 'unknown.tmp').write_text('fixture')
            created['directory'] = path.parent

        provider, _kernel, _factories = self.provider(writer)
        scope = make_scope()
        self.assertEqual(narrative(), await provider.prepare(bundle(), scope))
        self.assertFalse(await provider.stop_and_reconcile(scope))
        self.assertIsNotNone(provider._active)
        self.assertTrue(created['directory'].exists())
        (created['directory'] / 'unknown.tmp').unlink()
        with patch('backend.app.access.selected_story_process.Path.unlink',
                   side_effect=OSError('synthetic unlink failure')):
            self.assertFalse(await provider.stop_and_reconcile(scope))
        self.assertIsNotNone(provider._active)
        self.assertTrue(created['directory'].exists())
        self.assertTrue(await provider.stop_and_reconcile(scope))
        self.assertFalse(created['directory'].exists())

    async def test_wrong_scope_and_busy_call_cannot_replace_or_reconcile_active_exchange(self):
        written = threading.Event()

        def writer(environment):
            Path(environment[RESPONSE_ENV]).write_bytes(encoded_response())
            written.set()

        kernel = FileKernel(writer, exited=False)
        provider, _kernel, _factories = self.provider(kernel=kernel)
        scope = make_scope()
        pending = asyncio.create_task(provider.prepare(bundle(), scope))
        self.assertTrue(await asyncio.to_thread(written.wait, 2))
        await asyncio.sleep(0.03)
        with self.assertRaises(ProcessSelectedStoryError) as caught:
            await provider.prepare(bundle(), make_scope(OTHER_ID))
        self.assertEqual('busy', caught.exception.category)
        self.assertFalse(await provider.stop_and_reconcile(make_scope(OTHER_ID)))
        kernel.exited = True
        self.assertEqual(narrative(), await asyncio.wait_for(pending, 2))
        await self.cleanup_call(provider, scope)


    async def test_invalid_or_oversized_input_never_creates_exchange(self):
        provider, kernel, factories = self.provider()
        cases = [bundle(), bundle()]
        cases[0]['version'] = 1
        cases[0].pop('selection_revision')
        cases[1]['sources'][0]['text'] = 'z' * (MAX_REQUEST_BYTES + 1)
        with patch('backend.app.access.selected_story_process.tempfile.mkdtemp') as created:
            for value in cases:
                with self.subTest(version=value['version']), self.assertRaises(ProcessSelectedStoryError) as caught:
                    await provider.prepare(value, make_scope())
                self.assertEqual('invalid_input', caught.exception.category)
            created.assert_not_called()
        self.assertEqual([], factories)

    async def test_closed_provider_refuses_future_work_without_side_effects(self):
        provider, kernel, factories = self.provider()
        self.assertTrue(await provider.close())
        with self.assertRaises(ProcessSelectedStoryError) as caught:
            await provider.prepare(bundle(), make_scope())
        self.assertEqual('closed', caught.exception.category)
        self.assertEqual([], factories)

    def test_process_exchange_cannot_certify_independent_http_cleanup(self):
        from backend.app.access.selected_story_local import LocalSelectedStoryProvider
        provider, _, _ = self.provider()
        with self.assertRaisesRegex(ValueError, 'Qualified provider-to-process binding required'):
            LocalSelectedStoryProvider('http://127.0.0.1:11434', MODEL,
                                       enabled=True, native_owner=provider)

    async def test_private_storage_refusal_precedes_payload_write_and_native_launch(self):
        for guard in ('require_private_directory', '_regular'):
            with self.subTest(guard=guard):
                provider, kernel, factories = self.provider()
                scope = make_scope()
                observed = []
                def refuse(path):
                    path = Path(path)
                    observed.append(path)
                    if guard == '_regular':
                        self.assertEqual(b'', path.read_bytes())
                    raise ValueError('Synthetic private storage refusal')
                with patch('backend.app.access.selected_story_process.' + guard, side_effect=refuse):
                    with self.assertRaises(ProcessSelectedStoryError):
                        await provider.prepare(bundle(), scope)
                self.assertEqual([], factories)
                self.assertEqual(1, len(observed))
                self.assertTrue(await provider.stop_and_reconcile(scope))
                self.assertIsNone(provider._active)

    def test_windows_regular_file_guard_checks_private_acl(self):
        import types
        from backend.app.access import selected_story_process as module
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'synthetic.json'
            path.write_bytes(b'{}')
            native_os = types.SimpleNamespace(name='nt', getuid=os.getuid) if hasattr(os, 'getuid') else types.SimpleNamespace(name='nt')
            with patch.object(module, 'os', native_os), patch.object(module, 'require_private_file') as check:
                module._regular(path)
                check.assert_called_once_with(path)

    async def test_running_native_invalidation_has_cancelled_category_and_cleans_up(self):
        written = threading.Event()
        def writer(environment):
            Path(environment[RESPONSE_ENV]).write_bytes(encoded_response())
            written.set()
        kernel = FileKernel(writer, exited=False)
        provider, _, _ = self.provider(kernel=kernel)
        scope = make_scope()
        pending = asyncio.create_task(provider.prepare(bundle(), scope))
        self.assertTrue(await asyncio.to_thread(written.wait, 2))
        scope._invalidation.set()
        with self.assertRaises(ProcessSelectedStoryError) as caught:
            await asyncio.wait_for(pending, 2)
        self.assertEqual('cancelled', caught.exception.category)
        self.assertTrue(await provider.stop_and_reconcile(scope))
        self.assertIsNone(provider._active)
