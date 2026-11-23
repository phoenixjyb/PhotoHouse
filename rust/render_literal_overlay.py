"""Render only the literal additions to separately pinned protected launch code.

This reads source text and writes new inert source files. It never imports that
code, reads runtime configuration, installs a task, or performs a cutover.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / 'server/scripts/rust_overlay_selection.py'
ENVIRONMENT_BEFORE = '''    def selected_environment(q, run):
        value = original_environment(q, run)
        need(not set(plan['selectors']).intersection(value), 'new_selector_keys_only')
        value.update(plan['selectors'])
        return value'''
ENVIRONMENT_AFTER = '''    def selected_environment(q, run):
        return rust_overlay_environment(plan['selectors'], plan['native'],
                                        original_environment(q, run))'''
NATIVE_BEFORE = """    need(type(plan['native']) is dict and set(plan['native']) == {'photohouse_vector_kernel','photohouse_photo_stack'}, 'overlay_exact_native_set')
    need(plan['selectors'] == {'PHOTOHOUSE_VECTOR_ENGINE':'rust','PHOTOHOUSE_VISUAL_ENGINE':'rust','PHOTOHOUSE_PHOTO_STACK_ENGINE':'rust'}, 'overlay_exact_selectors')"""


def _replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('reviewed_overlay_source_shape_changed')
    return text.replace(old, new, 1)


def _embed_contract(text, contract):
    tree = ast.parse(text)
    first = next(n for n in tree.body if isinstance(n, ast.FunctionDef))
    offset = sum(len(line) for line in text.splitlines(keepends=True)[:first.lineno - 1])
    digest = hashlib.sha256(contract.encode()).hexdigest()
    return text[:offset] + '# BEGIN literal contract ' + digest + '\n' + contract + \
        '\n# END literal contract\n\n' + text[offset:]


def render_launcher(source, contract):
    ast.parse(source); ast.parse(contract)
    source = _replace_once(source,
        'def activate_native(plan):\n    global NATIVE_REPORT\n',
        "def activate_native(plan):\n    global NATIVE_REPORT\n"
        "    validate_rust_overlay_selection(plan['selectors'], plan['native'])\n")
    source = _replace_once(source, ENVIRONMENT_BEFORE, ENVIRONMENT_AFTER)
    source = _replace_once(source, '    return NATIVE_REPORT\n',
        "    NATIVE_REPORT['literal'] = preflight_literal_kernel(\n"
        "        plan['selectors'], plan['native'], STAGE, read_pinned)\n"
        '    return NATIVE_REPORT\n')
    source = _embed_contract(source, contract)
    ast.parse(source)
    return source


def render_grouping_guard(source, contract):
    ast.parse(source); ast.parse(contract)
    source = _replace_once(source, NATIVE_BEFORE,
        "    validate_rust_overlay_for_grouping(plan['selectors'], plan['native'])")
    source = _embed_contract(source, contract)
    ast.parse(source)
    return source


def render_files(launcher, guard, output, *, launcher_sha256, guard_sha256):
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError('new_overlay_output_required')
    raw_launcher, raw_guard = Path(launcher).read_bytes(), Path(guard).read_bytes()
    if (hashlib.sha256(raw_launcher).hexdigest() != launcher_sha256
            or hashlib.sha256(raw_guard).hexdigest() != guard_sha256):
        raise ValueError('reviewed_overlay_input_hash_mismatch')
    contract = CONTRACT.read_text(encoding='utf-8')
    rendered = {'launcher.py': render_launcher(raw_launcher.decode('utf-8'), contract),
                'api_overlay_contract.py': render_grouping_guard(raw_guard.decode('utf-8'), contract)}
    # Render/parse both completely before creating any output directory.
    output.mkdir(mode=0o700)
    for name, text in rendered.items():
        path = output / name
        with path.open('x', encoding='utf-8') as stream:
            stream.write(text)
        path.chmod(0o600)
    result = {'status': 'INERT_LITERAL_OVERLAY_SOURCES_RENDERED',
        'input_launcher_sha256': launcher_sha256, 'input_guard_sha256': guard_sha256,
        'contract_sha256': hashlib.sha256(contract.encode()).hexdigest(),
        'files': {name: hashlib.sha256(text.encode()).hexdigest() for name, text in rendered.items()},
        'production_effects': 0, 'native_builds': 0}
    (output / 'SOURCE-BINDING.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    (output / 'SOURCE-BINDING.json').chmod(0o600)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('launcher', 'guard', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    for name in ('launcher-sha256', 'guard-sha256'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    print(json.dumps(render_files(args.launcher, args.guard, args.output,
        launcher_sha256=args.launcher_sha256, guard_sha256=args.guard_sha256)))


if __name__ == '__main__':
    main()
