"""Closed deployment-plan selectors with generated modules; no native install."""
import copy
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import rust_overlay_selection as contract


class RustOverlaySelectionTests(unittest.TestCase):
    def setUp(self):
        self.selectors = dict(contract.LEGACY_RUST_SELECTORS)
        self.native = {name: {'path': 'native/' + name + '.pyd', 'sha256': 'a' * 64}
                       for name in ('photohouse_vector_kernel', 'photohouse_photo_stack')}
        self.stage = Path('/synthetic-stage')

    def select_literal(self, engine='rust'):
        self.selectors[contract.LITERAL_SELECTOR] = engine
        self.native[contract.LITERAL_MODULE] = {
            'path': 'native/photohouse_literal_kernel.pyd', 'sha256': 'b' * 64}

    def module(self):
        def quality(content, phrase):
            return {'周末海边合影。': (1000, 0, -7),
                    'family picnic': (1000, 1, -13), 'café': None}[content]
        return types.SimpleNamespace(
            __file__=str(self.stage / 'native/photohouse_literal_kernel.pyd'),
            POLICY_VERSION=1, quality=quality)

    def preflight(self, module=None, **kwargs):
        module = self.module() if module is None else module
        return contract.preflight_literal_kernel(self.selectors, self.native, self.stage,
            kwargs.pop('read', Mock()), importer=kwargs.pop('importer', Mock(return_value=module)),
            finder=kwargs.pop('finder', Mock(return_value=types.SimpleNamespace(origin=module.__file__))),
            **kwargs)

    def test_legacy_and_explicit_python_never_read_or_load_literal(self):
        for explicit in (False, True):
            if explicit:
                self.select_literal('python')
            read, load = Mock(), Mock()
            value = contract.preflight_literal_kernel(self.selectors, self.native, self.stage, read,
                                                       importer=load, finder=load)
            self.assertFalse(value['native_imported'])
            read.assert_not_called(); load.assert_not_called()
            original = {'PATH': 'generated-path', 'TMP': 'generated-temp'}
            value = contract.rust_overlay_environment(self.selectors, self.native, original)
            self.assertEqual(original, {'PATH': 'generated-path', 'TMP': 'generated-temp'})
            self.assertEqual(value[contract.LITERAL_SELECTOR], 'python')
            self.assertEqual({k: value[k] for k in contract.LEGACY_RUST_SELECTORS},
                             contract.LEGACY_RUST_SELECTORS)

    def test_rust_shadow_and_python_rollback_are_explicit(self):
        for engine in ('rust', 'shadow', 'python'):
            self.select_literal(engine)
            value = contract.rust_overlay_environment(self.selectors, self.native, {'PATH': 'fixture'})
            self.assertEqual(value[contract.LITERAL_SELECTOR], engine)
            if engine != 'python':
                read = Mock()
                result = self.preflight(read=read)
                self.assertEqual(result['fixed_generated_probes'], 3)
                self.assertEqual(result['native_sha256'], 'b' * 64)
                self.assertEqual(read.call_count, 2)

    def test_unknown_or_changed_legacy_settings_and_rosters_refuse_before_effects(self):
        self.select_literal()
        changes = [lambda s, n: s.update(UNRELATED='rust'),
                   lambda s, n: s.update(PHOTOHOUSE_VECTOR_ENGINE='python'),
                   lambda s, n: s.update(PHOTOHOUSE_LITERAL_TEXT_ENGINE='yes'),
                   lambda s, n: n.pop(contract.LITERAL_MODULE),
                   lambda s, n: n.update(extra={'path': 'native/extra.pyd', 'sha256': 'a' * 64}),
                   lambda s, n: n[contract.LITERAL_MODULE].update(path='native/../other.pyd'),
                   lambda s, n: n[contract.LITERAL_MODULE].update(sha256='A' * 64),
                   lambda s, n: n[contract.LITERAL_MODULE].update(extra=True)]
        for change in changes:
            selectors, native = copy.deepcopy(self.selectors), copy.deepcopy(self.native)
            change(selectors, native)
            read, load = Mock(), Mock()
            with self.assertRaises(RuntimeError):
                contract.preflight_literal_kernel(selectors, native, self.stage, read,
                                                   importer=load, finder=load)
            read.assert_not_called(); load.assert_not_called()

    def test_ambient_selector_is_not_inherited(self):
        for name in [*contract.LEGACY_RUST_SELECTORS, contract.LITERAL_SELECTOR]:
            with self.assertRaisesRegex(RuntimeError, '^rust_overlay_ambient_selector$'):
                contract.rust_overlay_environment(self.selectors, self.native, {name: 'rust'})

    def test_grouping_guard_uses_existing_closed_diagnostics(self):
        self.select_literal()
        self.selectors[contract.LITERAL_SELECTOR] = 'invalid'
        with self.assertRaisesRegex(RuntimeError, '^overlay_exact_selectors$'):
            contract.validate_rust_overlay_for_grouping(self.selectors, self.native)
        self.selectors[contract.LITERAL_SELECTOR] = 'rust'
        self.native[contract.LITERAL_MODULE]['path'] = 'native/../escape.pyd'
        with self.assertRaisesRegex(RuntimeError, '^overlay_relative_native$'):
            contract.validate_rust_overlay_for_grouping(self.selectors, self.native)

    def test_wrong_runtime_pin_origin_cached_module_and_policy_refuse(self):
        self.select_literal()
        with patch.object(sys, 'version_info', (3, 11)), self.assertRaisesRegex(RuntimeError, 'runtime_version'):
            self.preflight()
        with self.assertRaisesRegex(RuntimeError, '^private_pin_refused$'):
            self.preflight(read=Mock(side_effect=RuntimeError('private_pin_refused')))
        with self.assertRaisesRegex(RuntimeError, '^literal_native_origin$'):
            self.preflight(finder=Mock(return_value=types.SimpleNamespace(origin='/other/native.pyd')))
        with patch.dict(sys.modules, {contract.LITERAL_MODULE: object()}), \
                self.assertRaisesRegex(RuntimeError, '^literal_native_preloaded$'):
            self.preflight()
        module = self.module(); module.POLICY_VERSION = True
        with self.assertRaisesRegex(RuntimeError, '^literal_native_policy$'):
            self.preflight(module)

    def test_wrong_probe_and_import_failure_are_closed_errors(self):
        self.select_literal()
        module = self.module(); module.quality = lambda *args: (0, 0, 0)
        with self.assertRaisesRegex(RuntimeError, '^literal_native_probe$'):
            self.preflight(module)
        with self.assertRaisesRegex(RuntimeError, '^literal_native_unavailable$'):
            self.preflight(importer=Mock(side_effect=ImportError('private input')))
