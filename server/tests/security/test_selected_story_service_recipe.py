"""Closed persistent service recipe parsing and inert factory composition."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'backend'))

from app.access.host_inference_admission import HostResourceProfile, resource_profile_digest
from app.access.selected_story_native import NativeStoryLaunch
from app.access.selected_story_process import process_launch_digest, ProcessSelectedStoryProvider
from app.access.windows_story_capacity import WindowsProbeIdentity
from app.access.windows_story_service_capacity import windows_service_probe_digest
from selected_story_service_recipe import (
    SCHEMA, build_recipe_provider, strict_recipe,
)


MODEL = 'synthetic-local'
POLICY = '33333333-3333-4333-8333-333333333333'
HOST = 'synthetic-windows-host'
SID = 'S-1-5-21-111-222-333-1001'
VOLUME = '44444444-4444-4444-8444-444444444444'
IMAGES = [r'C:\PhotoHouse\runtime\caption.exe', r'C:\PhotoHouse\runtime\upscale.exe']
GiB = 1024 ** 3


class RecipeFixture(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.identity = WindowsProbeIdentity(HOST, SID, VOLUME)
        executable = r'C:\PhotoHouse\runtime\python.exe'
        self.launch = {
            'executable': executable,
            'executable_sha256': 'a' * 64,
            'argv': [executable, '-I', '-B'],
            'cwd': r'C:\PhotoHouse\runtime',
            'environment': {'PATH': r'C:\Windows\System32'},
            'memory_limit': 2 * GiB,
            'process_limit': 8,
            'minimum_free_ram': 8 * GiB,
        }
        exchange = str(self.root / 'exchange')
        self.launch_object = NativeStoryLaunch(**(self.launch | {'argv': tuple(self.launch['argv'])}))
        launch_sha = process_launch_digest(self.launch_object, exchange_root=exchange)
        capacity_dir = str(self.root / 'capacity')
        profile = HostResourceProfile('cpu', launch_sha, 8 * GiB, GiB,
            capacity_sha256=windows_service_probe_digest(self.identity, capacity_dir, POLICY, tuple(IMAGES)))
        self.profile = {
            'resource_id': profile.resource_id,
            'launch_sha256': profile.launch_sha256,
            'minimum_free_ram': profile.minimum_free_ram,
            'minimum_free_disk': profile.minimum_free_disk,
            'minimum_free_vram': profile.minimum_free_vram,
            'capacity_sha256': profile.capacity_sha256,
        }
        self.recipe = {
            'schema': SCHEMA,
            'launch': self.launch,
            'model': MODEL,
            'resource_profile': self.profile,
            'capacity': {
                'directory': capacity_dir,
                'policy_id': POLICY,
                'identity': {'host_id': HOST, 'principal_sid': SID, 'volume_id': VOLUME},
                'conflict_images': IMAGES,
            },
            'admission_directory': str(self.root / 'admission'),
            'exchange_root': exchange,
            'timeout_seconds': 30,
            'cleanup_seconds': 10,
        }
        self.raw = self.encode(self.recipe)
        self.expected_launch_sha256 = launch_sha
        self.expected_profile_sha256 = resource_profile_digest(profile)

    @staticmethod
    def encode(value):
        return json.dumps(value, separators=(',', ':')).encode('utf-8')

    def invalid(self, raw):
        with self.assertRaises(ValueError) as caught:
            strict_recipe(raw)
        self.assertEqual('Invalid selected-story service recipe', str(caught.exception))
        self.assertNotIn(str(self.root), str(caught.exception))

    def rebind_launch(self, **launch_changes):
        launch = self.launch | launch_changes
        launch_object = NativeStoryLaunch(**(launch | {'argv': tuple(launch['argv'])}))
        digest = process_launch_digest(launch_object, exchange_root=self.recipe['exchange_root'])
        profile = self.profile | {'launch_sha256': digest}
        return self.encode(self.recipe | {'launch': launch, 'resource_profile': profile})


class SelectedStoryServiceRecipeTests(RecipeFixture):
    def test_parser_returns_validated_value_objects_and_normalized_sequences(self):
        result = strict_recipe(self.raw)
        self.assertEqual(SCHEMA, result['schema'])
        self.assertIs(type(result['launch']), NativeStoryLaunch)
        self.assertEqual(tuple(self.launch['argv']), result['launch'].argv)
        self.assertEqual(self.profile['launch_sha256'], result['resource_profile'].launch_sha256)
        self.assertIs(type(result['resource_profile']), HostResourceProfile)
        self.assertIs(type(result['capacity']['identity']), WindowsProbeIdentity)
        self.assertEqual(tuple(IMAGES), result['capacity']['conflict_images'])

    def test_parser_rejects_duplicate_nan_invalid_utf8_unknown_and_oversized_json(self):
        self.invalid(b'{"schema":"x","schema":"x"}')
        self.invalid(self.raw.replace(b'"timeout_seconds":30', b'"timeout_seconds":NaN'))
        self.invalid(b'\xff')
        self.invalid(self.encode(self.recipe | {'extra': True}))
        self.invalid(b' ' * (64 * 1024 + 1))

    def test_closed_schema_rejects_old_experimental_and_unknown_nested_fields(self):
        old = self.recipe | {'schema': 'photohouse.selected_story_admission_recipe.v1'}
        self.invalid(self.encode(old))
        self.invalid(self.encode(self.recipe | {'purpose': 'persistent service'}))
        for legacy in (
            {'clearance_file': '/private/receipt.json'},
            {'clearance_id': POLICY},
            {'receipt_sha256': 'd' * 64},
        ):
            with self.subTest(legacy=legacy):
                capacity = self.recipe['capacity'] | legacy
                self.invalid(self.encode(self.recipe | {'capacity': capacity}))
        launch = self.recipe['launch'] | {'unexpected': 'value'}
        self.invalid(self.encode(self.recipe | {'launch': launch}))
        identity = self.recipe['capacity']['identity'] | {'principal': 'wrong-key'}
        capacity = self.recipe['capacity'] | {'identity': identity}
        self.invalid(self.encode(self.recipe | {'capacity': capacity}))

    def test_parser_rejects_bad_types_caps_path_spellings_and_cpu_bindings(self):
        self.invalid(self.encode(self.recipe | {'timeout_seconds': True}))
        self.invalid(self.encode(self.recipe | {'timeout_seconds': 60.01}))
        self.invalid(self.encode(self.recipe | {'cleanup_seconds': 10.01}))
        self.invalid(self.encode(self.recipe | {'model': 'http://model'}))
        self.invalid(self.encode(self.recipe | {'model': 'model\nname'}))
        self.invalid(self.encode(self.recipe | {'exchange_root': str(self.root / '..' / 'escape')}))
        self.invalid(self.encode(self.recipe | {'admission_directory': r'\\server\share\admission'}))
        self.invalid(self.encode(self.recipe | {'exchange_root': str(self.root / 'bad\npath')}))
        capacity = self.recipe['capacity'] | {'conflict_images': []}
        self.invalid(self.encode(self.recipe | {'capacity': capacity}))
        capacity = self.recipe['capacity'] | {'conflict_images': [r'1:\PhotoHouse\runtime\caption.exe']}
        self.invalid(self.encode(self.recipe | {'capacity': capacity}))
        profile = self.profile | {'resource_id': 'gpu:12345678-1234-4234-8234-123456789abc'}
        self.invalid(self.encode(self.recipe | {'resource_profile': profile}))
        profile = self.profile | {'capacity_sha256': 'f' * 64}
        self.invalid(self.encode(self.recipe | {'resource_profile': profile}))

    def test_parser_enforces_launch_limits_and_exact_exchange_profile_binding(self):
        self.invalid(self.rebind_launch(memory_limit=2 * GiB + 1))
        self.invalid(self.rebind_launch(process_limit=9))
        self.invalid(self.rebind_launch(minimum_free_ram=8 * GiB - 1))
        profile = self.profile | {'minimum_free_ram': 4 * GiB}
        self.invalid(self.encode(self.recipe | {'resource_profile': profile}))
        profile = self.profile | {'launch_sha256': 'b' * 64}
        self.invalid(self.encode(self.recipe | {'resource_profile': profile}))

    def test_build_requires_all_operator_pins_and_runtime_joins(self):
        kwargs = dict(expected_model=MODEL,
            expected_launch_sha256=self.expected_launch_sha256,
            expected_profile_sha256=self.expected_profile_sha256)
        for changes in (
            {'expected_model': 'other-model'},
            {'expected_launch_sha256': 'b' * 64},
            {'expected_profile_sha256': 'c' * 64},
            {'expected_model': ''},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                build_recipe_provider(self.raw, **(kwargs | changes))
        with self.assertRaises(ValueError):
            build_recipe_provider(self.raw, expected_model=MODEL,
                expected_launch_sha256='bad', expected_profile_sha256=self.expected_profile_sha256)

    def test_service_accepts_the_application_work_window_and_shorter_request_limits(self):
        for seconds in (30, 60):
            with self.subTest(seconds=seconds):
                raw = self.encode(self.recipe | {'timeout_seconds': seconds})
                provider = build_recipe_provider(raw, expected_model=MODEL,
                    expected_launch_sha256=self.expected_launch_sha256,
                    expected_profile_sha256=self.expected_profile_sha256)
                self.assertEqual(seconds, provider.timeout)
                self.assertFalse(provider.enabled)
                self.assertEqual([], list(self.root.iterdir()))

    def test_real_provider_factory_is_inert_default_off_and_does_not_initialize_paths(self):
        import selected_story_native_owner as factory
        from app.access.host_inference_admission import HostInferenceAdmission

        with patch.object(factory, 'WindowsAPI') as windows_api, \
                patch.object(HostInferenceAdmission, 'set_maintenance') as maintenance:
            provider = build_recipe_provider(self.raw, expected_model=MODEL,
                expected_launch_sha256=self.expected_launch_sha256,
                expected_profile_sha256=self.expected_profile_sha256)
        self.assertIs(type(provider), ProcessSelectedStoryProvider)
        self.assertFalse(provider.enabled)
        self.assertFalse(provider.host_admission.enabled)
        self.assertFalse(provider.host_admission.probe.enabled)
        self.assertEqual(self.root / 'exchange', provider.exchange_root)
        self.assertEqual(30, provider.timeout)
        self.assertEqual(10, provider.cleanup_seconds)
        windows_api.assert_not_called()
        maintenance.assert_not_called()
        self.assertEqual([], list(self.root.iterdir()))


if __name__ == '__main__':
    unittest.main()
