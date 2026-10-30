"""Fail-closed auto-refinement app binding and shutdown behavior."""
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))

from app.access.host_inference_admission import HostInferenceAdmission, HostResourceProfile
from app.access.selected_story_native import NativeStoryLaunch
from app.access.selected_story_process import ProcessSelectedStoryProvider, process_launch_digest
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
