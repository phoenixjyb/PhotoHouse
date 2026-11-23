"""Build the optional vector extension locally from locked cached dependencies."""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CRATE = ROOT / "rust/vector-python"

if __package__:
    from .build_paths import selected_target, validate_windows_paths
else:
    from build_paths import selected_target, validate_windows_paths


def _extension_name() -> str:
    return ("photohouse_vector_kernel.dll" if os.name == "nt" else
            "libphotohouse_vector_kernel.dylib" if sys.platform == "darwin" else
            "libphotohouse_vector_kernel.so")


def build(target_dir: str | Path | None = None, *, environ=None, run=None,
          copyfile=None, root: Path = ROOT, crate: Path = CRATE) -> dict:
    values = dict(os.environ if environ is None else environ)
    target = selected_target(crate, target_dir, values)
    validate_windows_paths(root, target, values)
    cargo = shutil.which("cargo") or str(Path.home() / ".cargo/bin/cargo")
    command = [cargo, "build", "--release", "--locked", "--offline",
               "--manifest-path", str(crate / "Cargo.toml"), "--target-dir", str(target)]
    (run or subprocess.run)(command, check=True, env=values)
    output = target / "python"
    output.mkdir(exist_ok=True)
    validate_windows_paths(root, output, values)
    destination = output / ("photohouse_vector_kernel.pyd" if os.name == "nt" else
                            "photohouse_vector_kernel.so")
    (copyfile or shutil.copyfile)(target / "release" / _extension_name(), destination)
    return {"status": "LOCAL_EXTENSION_BUILT", "python": platform.python_version(),
            "machine": platform.machine(), "output": str(output)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-dir", help="Cargo target/cache directory (overrides CARGO_TARGET_DIR)")
    args = parser.parse_args(argv)
    print(json.dumps(build(args.target_dir)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
