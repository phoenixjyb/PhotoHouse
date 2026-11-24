"""Closed selector/roster extension for the existing qualified Rust API overlay.

The legacy vector/visual/grouping choices are fixed. This adds only an explicit
literal choice; importing this module never loads a native library or sets env.
"""
import importlib
import importlib.util
from pathlib import Path
import re
import sys

LEGACY_RUST_SELECTORS = {
    'PHOTOHOUSE_VECTOR_ENGINE': 'rust',
    'PHOTOHOUSE_VISUAL_ENGINE': 'rust',
    'PHOTOHOUSE_PHOTO_STACK_ENGINE': 'rust',
}
LITERAL_SELECTOR = 'PHOTOHOUSE_LITERAL_TEXT_ENGINE'
LITERAL_MODULE = 'photohouse_literal_kernel'
_LEGACY_NATIVE = {'photohouse_vector_kernel', 'photohouse_photo_stack'}


def _literal_need(value, code):
    if not value:
        raise RuntimeError(code)


def validate_rust_overlay_selection(selectors, native):
    """Accept the frozen legacy shape or one explicit, fully bound extension."""
    _literal_need(type(selectors) is dict and type(native) is dict,
                  'rust_overlay_selection_shape')
    legacy = set(selectors) == set(LEGACY_RUST_SELECTORS)
    _literal_need(legacy or set(selectors) == set(LEGACY_RUST_SELECTORS) | {LITERAL_SELECTOR},
                  'rust_overlay_selector_keys')
    _literal_need(all(selectors[k] == v for k, v in LEGACY_RUST_SELECTORS.items()),
                  'rust_overlay_legacy_selection_changed')
    engine = 'python' if legacy else selectors[LITERAL_SELECTOR]
    _literal_need(type(engine) is str and engine in ('python', 'rust', 'shadow'),
                  'rust_overlay_literal_engine')
    expected = _LEGACY_NATIVE if legacy else _LEGACY_NATIVE | {LITERAL_MODULE}
    _literal_need(set(native) == expected, 'rust_overlay_native_roster')
    for name, row in native.items():
        _literal_need(type(row) is dict and set(row) == {'path', 'sha256'},
                      'rust_overlay_native_row')
        _literal_need(row['path'] == 'native/' + name + '.pyd',
                      'rust_overlay_native_path')
        _literal_need(type(row['sha256']) is str and re.fullmatch('[0-9a-f]{64}', row['sha256']),
                      'rust_overlay_native_pin')
    return engine


def rust_overlay_environment(selectors, native, inherited):
    """Forward only the reviewed selection; an ambient selector is a refusal."""
    engine = validate_rust_overlay_selection(selectors, native)
    _literal_need(type(inherited) is dict and all(type(k) is str and type(v) is str
                                                for k, v in inherited.items()),
                  'rust_overlay_environment_shape')
    _literal_need(not (set(LEGACY_RUST_SELECTORS) | {LITERAL_SELECTOR}) & inherited.keys(),
                  'rust_overlay_ambient_selector')
    return dict(inherited, **selectors, **({LITERAL_SELECTOR: engine}
                if LITERAL_SELECTOR not in selectors else {}))


def validate_rust_overlay_for_grouping(selectors, native):
    """Retain the refresh worker's existing closed diagnostic vocabulary."""
    codes = {
        'rust_overlay_selection_shape': 'overlay_contract_shape',
        'rust_overlay_selector_keys': 'overlay_exact_selectors',
        'rust_overlay_legacy_selection_changed': 'overlay_exact_selectors',
        'rust_overlay_literal_engine': 'overlay_exact_selectors',
        'rust_overlay_native_roster': 'overlay_exact_native_set',
        'rust_overlay_native_row': 'overlay_exact_native_set',
        'rust_overlay_native_path': 'overlay_relative_native',
        'rust_overlay_native_pin': 'pinned_input',
    }
    try:
        return validate_rust_overlay_selection(selectors, native)
    except RuntimeError as error:
        code = codes.get(str(error))
        if code is None:
            raise
        raise RuntimeError(code) from None


def preflight_literal_kernel(selectors, native, stage, read_pinned, *,
                             importer=None, finder=None):
    """Pin then load the new literal binary and probe generated text only.

    The enclosing launcher retains private-path, ACL, manifest and lifetime
    guards through its existing read_pinned callback. Existing native kernels
    and their probes remain owned by that launcher's original implementation.
    """
    engine = validate_rust_overlay_selection(selectors, native)
    if engine == 'python':
        return {'engine': engine, 'native_imported': False, 'fixed_generated_probes': 0}
    _literal_need(sys.version_info >= (3, 12), 'literal_native_runtime_version')
    row = native[LITERAL_MODULE]
    expected = Path(stage) / row['path']
    _literal_need(LITERAL_MODULE not in sys.modules, 'literal_native_preloaded')
    read_pinned(expected, row['sha256'], 2 * 1024**2)
    importer = importlib.import_module if importer is None else importer
    finder = importlib.util.find_spec if finder is None else finder
    try:
        spec = finder(LITERAL_MODULE)
        _literal_need(spec is not None and spec.origin is not None
                      and Path(spec.origin) == expected, 'literal_native_origin')
        module = importer(LITERAL_MODULE)
    except ImportError:
        raise RuntimeError('literal_native_unavailable') from None
    _literal_need(Path(getattr(module, '__file__', '')) == expected,
                  'literal_native_origin')
    _literal_need(type(getattr(module, 'POLICY_VERSION', None)) is int
                  and module.POLICY_VERSION == 1
                  and callable(getattr(module, 'quality', None)), 'literal_native_policy')
    for content, phrase, wanted in (
            ('周末海边合影。', '海边合影', (1000, 0, -7)),
            ('family picnic', 'picnic', (1000, 1, -13)),
            ('café', 'café', None)):
        value = module.quality(content, phrase)
        _literal_need(value is None if wanted is None else
                      type(value) is tuple and all(type(n) is int for n in value) and value == wanted,
                      'literal_native_probe')
    read_pinned(expected, row['sha256'], 2 * 1024**2)
    return {'engine': engine, 'native_imported': True, 'fixed_generated_probes': 3,
            'native_sha256': row['sha256']}
