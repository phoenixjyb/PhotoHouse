#!/usr/bin/env python3
"""Build and optionally benchmark the opt-in photo-stack extension locally."""
import argparse
import json
import os
from pathlib import Path
import random
import shutil
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target-dir', type=Path)
    parser.add_argument('--benchmark', action='store_true')
    args = parser.parse_args()
    target = (args.target_dir or Path(os.environ.get(
        'CARGO_TARGET_DIR', ROOT / 'rust/photo-stack-python/target'))).absolute()
    if os.name == 'nt' and target.drive.upper() != 'D:':
        parser.error('Windows native build scratch must be on D:')
    environment = dict(os.environ)
    if os.name == 'nt':
        if Path(environment.get('CARGO_HOME', '')).drive.upper() != 'D:':
            parser.error('Windows CARGO_HOME must select a D: cache explicitly')
        temporary = target / 'tmp'
        temporary.mkdir(parents=True, exist_ok=True)
        environment.update(TEMP=str(temporary), TMP=str(temporary))
    cargo = shutil.which('cargo')
    if cargo is None:
        parser.error('cargo is required; add the existing Rust toolchain to PATH')
    subprocess.run([cargo, 'build', '--release', '--locked', '--manifest-path',
                    str(ROOT / 'rust/photo-stack-python/Cargo.toml'),
                    '--target-dir', str(target)], check=True, env=environment)
    filename = ('photohouse_photo_stack.dll' if os.name == 'nt' else
                'libphotohouse_photo_stack.dylib' if sys.platform == 'darwin' else
                'libphotohouse_photo_stack.so')
    output = target / 'python'
    output.mkdir(exist_ok=True)
    suffix = '.pyd' if os.name == 'nt' else '.abi3.so'
    shutil.copyfile(target / 'release' / filename, output / ('photohouse_photo_stack' + suffix))
    print(json.dumps({'native_import_directory': str(output)}))
    if not args.benchmark:
        return
    sys.path[:0] = [str(output), str(ROOT / 'server/backend')]
    from app.access.photo_stack_index import build_library_photo_stacks
    rng = random.Random(20261022)
    rows = [(i, 'image/jpeg', 'name.jpg', 1, 1, '2026-10-22T08:00:00Z',
             f'{rng.getrandbits(64):016x}', None, None) for i in range(1, 20001)]
    old = os.environ.get('PHOTOHOUSE_PHOTO_STACK_ENGINE')
    report = {}
    try:
        for label in ('python', 'rust', 'python_cancellable', 'rust_cancellable'):
            mode = label.split('_', 1)[0]
            os.environ['PHOTOHOUSE_PHOTO_STACK_ENGINE'] = mode
            options = {'stopped': lambda: False} if label.endswith('_cancellable') else {}
            assert build_library_photo_stacks(rows, **options) == []
            runs = []
            for _ in range(9):
                cpu = time.process_time()
                wall = time.perf_counter()
                result = build_library_photo_stacks(rows, **options)
                wall = time.perf_counter() - wall
                cpu = time.process_time() - cpu
                assert result == []
                runs.append({'wall_seconds': wall, 'process_cpu_seconds': cpu})
            report[label] = {'runs': runs, 'wall_median': statistics.median(
                r['wall_seconds'] for r in runs), 'cpu_median': statistics.median(
                r['process_cpu_seconds'] for r in runs)}
    finally:
        if old is None:
            os.environ.pop('PHOTOHOUSE_PHOTO_STACK_ENGINE', None)
        else:
            os.environ['PHOTOHOUSE_PHOTO_STACK_ENGINE'] = old
    report['speedup'] = report['python']['wall_median'] / report['rust']['wall_median']
    report['cancellable_speedup'] = (report['python_cancellable']['wall_median']
                                   / report['rust_cancellable']['wall_median'])
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
