"""Inert Windows selected-story factory forwarding tests; no Win32 calls."""

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'backend'))

import selected_story_native_owner as factory
from app.access.host_inference_admission import HostInferenceAdmission, HostResourceProfile
from app.access.selected_story_native import NativeStoryLaunch
from app.access.selected_story_process import ProcessSelectedStoryProvider, process_launch_digest


MODEL = 'synthetic-local'


def launch_spec():
    executable = r'C:\PhotoHouse\runtime\python.exe'
    return NativeStoryLaunch(
        executable, 'a' * 64, (executable, '-I', '-B'), r'C:\PhotoHouse\runtime',
        {'PATH': r'C:\Windows\System32'}, minimum_free_ram=0)


class WindowsStoryFactoryTests(unittest.TestCase):
    def test_default_factory_is_inert_and_disabled(self):
        with patch.object(factory, 'WindowsAPI') as windows_api:
            provider = factory.windows_story_process_provider(launch_spec(), MODEL)
        self.assertIs(type(provider), ProcessSelectedStoryProvider)
        self.assertFalse(provider.enabled)
        self.assertIsNone(provider.host_admission)
        self.assertIsNone(provider.exchange_root)
        windows_api.assert_not_called()

    def test_forwards_explicit_host_and_exchange_root_unchanged(self):
        spec = launch_spec()
        host, root = object(), Path(tempfile.gettempdir()).resolve() / 'ph-story-exchange'
        sentinel = object()
        with patch.object(factory, 'WindowsAPI') as windows_api, \
                patch.object(factory, 'ProcessSelectedStoryProvider', return_value=sentinel) as provider:
            result = factory.windows_story_process_provider(
                spec, MODEL, enabled=True, timeout=21, cleanup_seconds=4,
                host_admission=host, exchange_root=root)
        self.assertIs(result, sentinel)
        provider.assert_called_once_with(spec, MODEL, kernel_factory=windows_api,
            enabled=True, timeout=21, cleanup_seconds=4,
            host_admission=host, exchange_root=root)
        windows_api.assert_not_called()

    def test_real_provider_rejects_host_profile_bound_to_another_exchange_root_without_io(self):
        spec = launch_spec()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            root = base / 'exchange'
            host_directory = base / 'host-admission'
            old_profile = HostResourceProfile('cpu', process_launch_digest(spec), 1, 1)
            capacity_probe = Mock(side_effect=AssertionError('capacity read'))
            host = HostInferenceAdmission(host_directory, old_profile,
                capacity_probe=capacity_probe, enabled=False)
            with patch.object(factory, 'WindowsAPI') as windows_api, \
                    patch.object(host, 'acquire') as acquire, \
                    patch.object(host, 'set_maintenance') as maintenance:
                with self.assertRaisesRegex(ValueError, 'Host admission launch binding mismatch'):
                    factory.windows_story_process_provider(
                        spec, MODEL, enabled=True, host_admission=host, exchange_root=root)
            windows_api.assert_not_called()
            acquire.assert_not_called()
            maintenance.assert_not_called()
            capacity_probe.assert_not_called()
            self.assertFalse(root.exists())
            self.assertFalse(host_directory.exists())

    def test_explicit_matching_profile_constructs_without_initializing_or_clearing_admission(self):
        spec = launch_spec()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            root = base / 'exchange'
            host_directory = base / 'host-admission'
            profile = HostResourceProfile('cpu',
                process_launch_digest(spec, exchange_root=root), 1, 1)
            capacity_probe = Mock(side_effect=AssertionError('capacity read'))
            host = HostInferenceAdmission(host_directory, profile,
                capacity_probe=capacity_probe, enabled=False)
            with patch.object(factory, 'WindowsAPI') as windows_api, \
                    patch.object(host, 'acquire') as acquire, \
                    patch.object(host, 'set_maintenance') as maintenance:
                provider = factory.windows_story_process_provider(
                    spec, MODEL, host_admission=host, exchange_root=root)
            self.assertFalse(provider.enabled)
            self.assertIs(provider.host_admission, host)
            self.assertEqual(root, provider.exchange_root)
            windows_api.assert_not_called()
            acquire.assert_not_called()
            maintenance.assert_not_called()
            capacity_probe.assert_not_called()
            self.assertFalse(root.exists())
            self.assertFalse(host_directory.exists())


if __name__ == '__main__':
    unittest.main()
