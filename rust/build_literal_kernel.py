"""Build only the new optional literal kernel from locked, cached dependencies.

On Windows, run within the separately admitted CPU build/qualification scope.
This command neither installs into a live environment nor enables an engine.
"""
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
crate = ROOT / 'rust/literal-python'
target = crate / 'target'
if os.name == 'nt':
    for name, path in {'source': ROOT, 'target': target,
                       'Cargo cache': Path(os.environ.get('CARGO_HOME', 'C:/')),
                       'TEMP': Path(os.environ.get('TEMP', 'C:/')),
                       'TMP': Path(os.environ.get('TMP', 'C:/'))}.items():
        if path.drive.upper() != 'D:':
            raise SystemExit(f'{name} must be explicitly located on D:')
cargo = shutil.which('cargo') or str(Path.home() / '.cargo/bin/cargo')
subprocess.run([cargo, 'build', '--release', '--locked', '--offline',
                '--manifest-path', str(crate / 'Cargo.toml')], check=True,
               env=dict(os.environ, PYO3_PYTHON=sys.executable))
name = ('photohouse_literal_kernel.dll' if os.name == 'nt' else
        'libphotohouse_literal_kernel.dylib' if sys.platform == 'darwin' else
        'libphotohouse_literal_kernel.so')
output = target / 'python'
output.mkdir(exist_ok=True)
destination = output / ('photohouse_literal_kernel.pyd' if os.name == 'nt' else
                        'photohouse_literal_kernel.so')
shutil.copyfile(target / 'release' / name, destination)
print(json.dumps({'status': 'NEW_LITERAL_EXTENSION_BUILT_NOT_ACTIVATED',
                  'python': platform.python_version(), 'machine': platform.machine(),
                  'output': str(destination.relative_to(ROOT))}))
