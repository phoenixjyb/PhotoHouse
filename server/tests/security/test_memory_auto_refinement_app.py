"""Fail-closed auto-refinement app binding and shutdown behavior."""
from pathlib import Path
from dataclasses import replace
import tempfile
import sys
import unittest
import uuid
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))

from app.access.host_inference_admission import HostInferenceAdmission, HostResourceProfile
from app.access.selected_story_native import NativeStoryLaunch
from app.access.selected_story_process import ProcessSelectedStoryProvider, ProcessSavedStoryProvider, process_launch_digest
from app.access.runtime import RuntimeConfiguration
from app.access.transport import AccessRuntime
from app.main import create_app


def provider(*, enabled, worker='household_gguf_worker.py', admission_enabled=True):
    executable = r'C:\Synthetic\python.exe'
    script = 'C:\\Synthetic\\scripts\\' + worker
    launch = NativeStoryLaunch(executable, 'a' * 64,
        (executable, '-I', '-B', script), r'C:\Synthetic', {'PATH': r'C:\Windows\System32'},
        memory_limit=2 * 1024**3, process_limit=8, minimum_free_ram=8 * 1024**3)
    exchange = Path('/synthetic/exchange')
    profile = HostResourceProfile('cpu', process_launch_digest(launch, exchange_root=exchange),
        8 * 1024**3, 1024**3)
    admission = HostInferenceAdmission(Path('/synthetic/admission'), profile,
        capacity_probe=lambda: None, enabled=admission_enabled)
    return ProcessSelectedStoryProvider(launch, 'synthetic-local', kernel_factory=lambda: None,
        enabled=enabled, timeout=60, host_admission=admission, exchange_root=exchange)


class MemoryAutoRefinementAppTests(unittest.IsolatedAsyncioTestCase):
    def auto_app(self, selected_provider):
        return create_app(access_runtime=object(), selected_story_provider=selected_provider,
            memory_collaboration_enabled=True, memory_auto_refinement_enabled=True)

    async def test_auto_refinement_remains_default_off(self):
        app = create_app()
        self.assertFalse(app.state.memory_auto_refinement_enabled)

    async def test_saved_story_budget_does_not_increase_interactive_provider_budget(self):
        selected = provider(enabled=True)
        captured = {}
        def narrator(factory, *, timeout):
            captured.update(provider=factory(), timeout=timeout)
            return object()
        with patch('app.access.memory_processing.OwnedSavedStoryNarrator', side_effect=narrator):
            create_app(access_runtime=AccessRuntime(lambda: None, 'https://example.invalid'),
                       selected_story_provider=selected, memory_collaboration_enabled=True,
                       memory_auto_refinement_enabled=True)
        self.assertIs(type(captured['provider']), ProcessSavedStoryProvider)
        self.assertEqual((captured['provider'].timeout, captured['timeout'], selected.timeout), (180, 180, 60))
        kwargs = dict(kernel_factory=selected.kernel_factory, enabled=True,
                      host_admission=selected.host_admission, exchange_root=selected.exchange_root)
        with self.assertRaises(ValueError):
            ProcessSelectedStoryProvider(selected.launch, selected.model, timeout=61, **kwargs)
        with self.assertRaises(ValueError):
            ProcessSavedStoryProvider(selected.launch, selected.model, timeout=181, **kwargs)

    async def test_runtime_configuration_forwards_explicit_enabled_flag(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            config = RuntimeConfiguration(
                database=root / 'library.sqlite', web_origin='https://example.invalid',
                original_roots=(root / 'originals',), derived_root=root / 'derived',
                memory_collaboration_enabled=True,
                original_deletion_journal_path=root / 'deletions.jsonl',
                original_deletion_namespace=str(uuid.uuid4()),
                selected_story_provider=provider(enabled=True))
            enabled = replace(config, memory_auto_refinement_enabled=True)
            # The journal's filesystem policy is covered separately; this test
            # exercises only the RuntimeConfiguration -> create_app flag binding.
            with patch('app.access.original_deletions.OriginalDeletionJournal',
                       return_value=object()):
                app = enabled.build_app()
            self.assertTrue(app.state.memory_auto_refinement_enabled)

    async def test_disabled_provider_is_refused_before_worker_setup(self):
        with self.assertRaisesRegex(ValueError, 'enabled owned model provider'):
            self.auto_app(provider(enabled=False))

    async def test_disabled_host_admission_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'enabled owned model provider'):
            self.auto_app(provider(enabled=True, admission_enabled=False))

    async def test_legacy_selected_story_worker_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'household GGUF worker launch'):
            self.auto_app(provider(enabled=True, worker='selected_story_gguf_worker.py'))

    async def test_lifecycle_closes_even_when_refinement_worker_await_fails(self):
        selected_provider = provider(enabled=True)
        lifecycle = Mock()
        lifecycle.operations = object()
        lifecycle.close = AsyncMock()

        class FailedWorker:
            def cancel(self):
                pass

            def __await__(self):
                async def fail():
                    raise RuntimeError('synthetic refinement task failure')
                return fail().__await__()

        actual_create_task = __import__('asyncio').create_task

        def create_task(coroutine):
            if coroutine.cr_code.co_name == 'refine_stories':
                coroutine.close()
                return FailedWorker()
            return actual_create_task(coroutine)

        async def no_thread_work(_function, *_args, **_kwargs):
            return None

        with patch('app.access.selected_story_lifecycle.SelectedStoryLifecycle', return_value=lifecycle), \
                patch('app.main.run_in_threadpool', side_effect=no_thread_work), \
                patch('app.main.asyncio.create_task', side_effect=create_task):
            app = self.auto_app(selected_provider)
            with self.assertRaisesRegex(RuntimeError, 'synthetic refinement task failure'):
                async with app.router.lifespan_context(app):
                    await __import__('asyncio').sleep(0)
        lifecycle.start.assert_called_once_with()
        lifecycle.close.assert_awaited_once_with()


if __name__ == '__main__':
    unittest.main()
