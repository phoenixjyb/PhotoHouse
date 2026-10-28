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


class PersistentWindowsStoryFactoryTests(unittest.TestCase):
    def inputs(self, base):
        from app.access.windows_story_capacity import WindowsProbeIdentity
        from app.access.windows_story_service_capacity import windows_service_probe_digest
        spec = launch_spec()
        spec = NativeStoryLaunch(spec.executable, spec.executable_sha256, spec.argv,
            spec.cwd, dict(spec.environment), memory_limit=2*1024**3, minimum_free_ram=8*1024**3)
        identity = WindowsProbeIdentity('synthetic-host', 'S-1-5-21-111-1001',
                                       '44444444-4444-4444-8444-444444444444')
        policy = '33333333-3333-4333-8333-333333333333'
        images = (r'C:\Synthetic\caption.exe',)
        root, capacity = base/'exchange', base/'capacity'
        profile = HostResourceProfile('cpu', process_launch_digest(spec, exchange_root=root),
            8*1024**3, 1024**3, capacity_sha256=windows_service_probe_digest(identity, capacity, policy, images))
        return spec, dict(host_directory=base/'admission', capacity_directory=capacity,
            profile=profile, policy_id=policy, identity=identity, conflict_images=images, exchange_root=root)

    def test_service_composes_real_producer_without_activation_storage_or_native_calls(self):
        from app.access.windows_story_service_capacity import WindowsStoryServiceCapacityProbe
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory).resolve();spec, kwargs=self.inputs(base)
            with patch.object(factory,'WindowsAPI') as kernel, patch.object(HostInferenceAdmission,'set_maintenance') as activate:
                provider=factory.windows_story_service_provider(spec,MODEL,**kwargs)
            self.assertFalse(provider.enabled);self.assertFalse(provider.host_admission.enabled)
            self.assertIs(type(provider.host_admission.probe),WindowsStoryServiceCapacityProbe)
            self.assertFalse(provider.host_admission.probe.enabled);self.assertEqual(provider.timeout,30)
            self.assertIsNone(provider.host_admission.probe._metrics)
            self.assertIsNone(provider.host_admission.probe._conflicts)
            self.assertEqual(list(base.iterdir()),[]);kernel.assert_not_called();activate.assert_not_called()

    def test_service_refuses_relaxed_worker_limits_missing_conflicts_or_long_timeout(self):
        from dataclasses import replace
        with tempfile.TemporaryDirectory() as directory:
            spec,kwargs=self.inputs(Path(directory).resolve())
            for changes in [dict(memory_limit=4*1024**3),dict(process_limit=9),dict(minimum_free_ram=0)]:
                invalid=NativeStoryLaunch(spec.executable,spec.executable_sha256,spec.argv,spec.cwd,
                    dict(spec.environment),memory_limit=changes.get('memory_limit',spec.memory_limit),
                    process_limit=changes.get('process_limit',spec.process_limit),minimum_free_ram=changes.get('minimum_free_ram',spec.minimum_free_ram))
                with self.assertRaises(ValueError):factory.windows_story_service_provider(invalid,MODEL,**kwargs)
            for extra in [dict(timeout=31),dict(conflict_images=()),dict(profile=replace(kwargs['profile'],capacity_sha256='f'*64))]:
                with self.assertRaises(ValueError):factory.windows_story_service_provider(spec,MODEL,**dict(kwargs,**extra))


def load_tests(loader, tests, pattern):
    tests.addTests(loader.loadTestsFromName('test_selected_story_service_recipe'))
    return tests


if __name__ == '__main__':
    unittest.main()
