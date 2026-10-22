"""RuntimeConfiguration forwards an explicitly injected selected-story owner."""
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))

import test_library_reads as library_fixture
from app.access.runtime import RuntimeConfiguration


class SyntheticProvider:
    def __init__(self):
        self.calls = []

    async def prepare(self, bundle, scope):
        self.calls.append(('prepare', bundle, scope))

    async def stop_and_reconcile(self, scope):
        self.calls.append(('stop_and_reconcile', scope))
        return True


class SelectedStoryRuntimeBindingTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        library_fixture.LibraryReadTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        library_fixture.LibraryReadTests.tearDownClass()

    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='photohouse-story-runtime-')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.database = self.root / 'synthetic.sqlite'
        with closing(sqlite3.connect(self.database)) as target:
            library_fixture.LibraryReadTests.template.backup(target)
        self.originals = self.root / 'originals'
        self.derived = self.root / 'derived'
        self.originals.mkdir()
        self.derived.mkdir()

    def configuration(self, **overrides):
        values = dict(database=self.database, web_origin='https://photohouse.test',
                      original_roots=(self.originals,), derived_root=self.derived)
        values.update(overrides)
        return RuntimeConfiguration(**values)

    async def test_default_is_off_and_api_and_ui_flags_are_independent(self):
        default = self.configuration().build_app()
        self.assertFalse(default.state.selected_story_drafts_enabled)
        self.assertFalse(default.state.selected_story_ui_enabled)
        self.assertIsNone(default.state.selected_story_lifecycle)

        provider = SyntheticProvider()
        api_only = self.configuration(selected_story_provider=provider,
            selected_story_drafts_enabled=True, memory_collaboration_enabled=True).build_app()
        self.assertTrue(api_only.state.selected_story_drafts_enabled)
        self.assertFalse(api_only.state.selected_story_ui_enabled)
        self.assertIs(api_only.state.selected_story_lifecycle.provider, provider)

        api_and_ui = self.configuration(selected_story_provider=provider,
            selected_story_drafts_enabled=True, selected_story_ui_enabled=True,
            memory_collaboration_enabled=True).build_app()
        self.assertTrue(api_and_ui.state.selected_story_drafts_enabled)
        self.assertTrue(api_and_ui.state.selected_story_ui_enabled)

    async def test_invalid_binding_is_rejected_before_database_or_provider_work(self):
        from app.access import runtime

        missing_database = self.root / 'must-not-be-created.sqlite'
        base = dict(database=missing_database, web_origin='https://photohouse.test',
                    original_roots=(self.originals,), derived_root=self.derived)
        provider = SyntheticProvider()
        invalid = (
            ({'selected_story_drafts_enabled': True}, 'API opt-in and provider'),
            ({'selected_story_drafts_enabled': 'true', 'selected_story_provider': provider},
             'API opt-in and provider'),
            ({'selected_story_provider': provider, 'memory_collaboration_enabled': False},
             'requires collaboration'),
            ({'selected_story_provider': provider, 'memory_collaboration_enabled': 1},
             'memory opt-in'),
            ({'selected_story_ui_enabled': True}, 'UI and API opt-in'),
            ({'selected_story_drafts_enabled': True, 'selected_story_ui_enabled': 1,
              'selected_story_provider': provider, 'memory_collaboration_enabled': True},
             'UI and API opt-in'),
        )
        with patch.object(runtime, 'ExistingDatabase',
                          side_effect=AssertionError('storage reached before binding validation')) as store:
            for options, message in invalid:
                settings = RuntimeConfiguration(**(base | options))
                with self.subTest(options=options), self.assertRaisesRegex(ValueError, message):
                    settings.build_app()
            store.assert_not_called()
        self.assertFalse(missing_database.exists())
        self.assertEqual(provider.calls, [])

    async def test_injected_async_provider_is_owned_without_build_time_calls(self):
        from app.access import memory_jobs

        provider = SyntheticProvider()
        app = self.configuration(selected_story_provider=provider,
            selected_story_drafts_enabled=True, selected_story_ui_enabled=True,
            memory_collaboration_enabled=True).build_app()
        lifecycle = app.state.selected_story_lifecycle
        self.assertIs(lifecycle.provider, provider)
        self.assertIsNone(app.state.selected_story_operations)
        self.assertEqual(provider.calls, [])

        with patch.object(memory_jobs, 'maintenance', return_value=None):
            async with app.router.lifespan_context(app):
                self.assertTrue(lifecycle.started)
                self.assertIs(app.state.selected_story_operations, lifecycle.operations)
                self.assertEqual(provider.calls, [])
        self.assertTrue(lifecycle.closing)
        self.assertTrue(lifecycle.shutdown_clean)
        self.assertEqual(provider.calls, [])


if __name__ == '__main__':
    unittest.main()
