"""Renderer touches only explicit extension points; existing guards stay intact."""
import ast
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'rust'))
import render_literal_overlay as renderer

LAUNCHER = '''import os
STAGE = None
NATIVE_REPORT = None
def need(value, code):
    if not value: raise RuntimeError(code)
def original_guard():
    raise RuntimeError('original_guard_still_mandatory')
def activate_native(plan):
    global NATIVE_REPORT
    original_guard()
    NATIVE_REPORT = {'fixed_generated_probes': 3}
    return NATIVE_REPORT
def bootstrap(plan, original_environment):
'''+renderer.ENVIRONMENT_BEFORE+'''
    return selected_environment
'''
GUARD = '''def need(value, code):
    if not value: raise RuntimeError(code)
def verify(plan):
    need(plan['original_pin'] == 'pinned', 'original_pin')
'''+renderer.NATIVE_BEFORE+'''
    return True
'''


class LiteralOverlayRendererTests(unittest.TestCase):
    def test_embedded_contract_and_untouched_guard_are_traceable(self):
        contract = renderer.CONTRACT.read_text()
        result = renderer.render_launcher(LAUNCHER, contract)
        before = {n.name: n for n in ast.parse(LAUNCHER).body if isinstance(n, ast.FunctionDef)}
        after = {n.name: n for n in ast.parse(result).body if isinstance(n, ast.FunctionDef)}
        for name in ('need', 'original_guard'):
            self.assertEqual(ast.dump(before[name]), ast.dump(after[name]))
        self.assertIn(contract, result)
        namespace = {'__name__': 'generated_fixture'}
        exec(compile(result, 'generated_fixture', 'exec'), namespace)
        selectors = dict(namespace['LEGACY_RUST_SELECTORS'])
        native = {name: {'path': 'native/' + name + '.pyd', 'sha256': 'a' * 64}
                  for name in ('photohouse_vector_kernel', 'photohouse_photo_stack')}
        plan = {'selectors': selectors, 'native': native}
        with self.assertRaisesRegex(RuntimeError, '^original_guard_still_mandatory$'):
            namespace['activate_native'](plan)
        environment = namespace['bootstrap'](plan, lambda q, r: {'PATH': 'fixture'})(None, None)
        self.assertEqual(environment['PHOTOHOUSE_LITERAL_TEXT_ENGINE'], 'python')

    def test_group_guard_keeps_original_pin_and_extends_only_declared_roster(self):
        result = renderer.render_grouping_guard(GUARD, renderer.CONTRACT.read_text())
        namespace = {'__name__': 'guard_fixture'}; exec(result, namespace)
        plan = {'original_pin': 'wrong', 'selectors': {}, 'native': {}}
        with self.assertRaisesRegex(RuntimeError, '^original_pin$'):
            namespace['verify'](plan)
        plan['original_pin'] = 'pinned'
        with self.assertRaisesRegex(RuntimeError, '^overlay_exact_selectors$'):
            namespace['verify'](plan)

    def test_source_shape_and_input_hash_drift_refuse_without_output(self):
        with self.assertRaisesRegex(ValueError, 'source_shape_changed'):
            renderer.render_launcher(LAUNCHER.replace('global NATIVE_REPORT', 'global CHANGED'),
                                     renderer.CONTRACT.read_text())
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); launcher = root / 'base.py'; guard = root / 'guard.py'
            launcher.write_text(LAUNCHER); guard.write_text(GUARD)
            output = root / 'rendered'
            with self.assertRaisesRegex(ValueError, '^reviewed_overlay_input_hash_mismatch$'):
                renderer.render_files(launcher, guard, output, launcher_sha256='0'*64,
                    guard_sha256=hashlib.sha256(guard.read_bytes()).hexdigest())
            self.assertFalse(output.exists())
