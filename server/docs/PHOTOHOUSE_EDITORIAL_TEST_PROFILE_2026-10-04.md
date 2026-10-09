# Editorial synthetic test environment

This profile provides a reproducible CPython 3.12 environment for the synthetic memoir-editorial and approved-worker tests. It is separate from serving and GPU environments. It includes the pinned protected API dependencies, the existing Pillow 12.3.0 preparation pin, pytest 9.0.3, NumPy 2.2.6, and the CPU perceptual-hash dependencies ImageHash 4.3.2, PyWavelets 1.9.0, and their SciPy dependency. Windows installs select the conditional Colorama 0.4.6 dependency. The lock contains hashes; its resolver input and download/install commands require binary wheels so source archives are not used.

The test profile pins pytest 9.0.3 because [PyPI's pytest 8.4.1 metadata](https://pypi.org/pypi/pytest/8.4.1/json) lists CVE-2025-71176 / PYSEC-2026-1845 as affecting versions through 9.0.2 on Unix; 9.0.3 is the fixed release.

The input file references the existing [home preparation lock](../backend/requirements-home-preparation.lock); that lock and the serving/runtime locks were left unchanged. The new lock was resolved for CPython 3.12 across supported platforms. The macOS ARM64 and Windows AMD64 wheelhouse downloads were checked against the lock hashes. The Windows wheel set was cross-downloaded from macOS; pip evaluates environment markers on the host during cross-download, so Colorama was separately added from its locked requirement. This qualifies wheel availability and hashes, not execution on Windows.

## Offline installation

Prepare a wheelhouse while connected to the approved package index. On macOS ARM64:

```sh
python3.12 -m pip download --require-hashes --only-binary=:all: \
  -r backend/requirements-editorial-test.lock -d wheelhouse
```

Then create a fresh virtual environment and install from that wheelhouse with network access disabled. Keep `--only-binary=:all:` on both download and install commands so a source archive hash cannot trigger a local build:

```sh
python3.12 -m venv .venv-editorial-test
. .venv-editorial-test/bin/activate
python -m pip install --no-index --find-links wheelhouse --require-hashes --only-binary=:all: \
  -r backend/requirements-editorial-test.lock
```

On Windows, use `py -3.12 -m pip download --require-hashes --only-binary=:all: -r backend/requirements-editorial-test.lock -d wheelhouse`, create the environment with `py -3.12 -m venv .venv-editorial-test`, activate `.venv-editorial-test\Scripts\Activate.ps1`, then run the same offline install command. Preparing the wheelhouse on the target OS ensures pip evaluates the Windows-only Colorama marker. Do not install this profile into the server, worker, or model environment.

## Synthetic checks

Run each command in a fresh process from the repository root. Disable third-party pytest plugin autoload and pytest's cache provider. On POSIX shells:

```sh
export PYTHONPATH=backend:tests/security
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
python -m pytest -o addopts= -p no:cacheprovider -q \
  tests/security/test_memory_book_editorial_migration.py \
  tests/security/test_memory_book_editorial_http.py \
  tests/security/test_memory_book_editorial_service.py \
  tests/security/test_memory_book_editorial_deletions.py \
  tests/security/test_memory_book_editorial_contract.py \
  tests/security/test_memory_book_editorial_schema.py \
  tests/security/test_memory_book_editorial_erasure.py
python -m pytest -o addopts= -p no:cacheprovider -q tests/security/test_approved_cpu_worker.py
python -m pytest -o addopts= -p no:cacheprovider -q tests/security/test_approved_face_worker.py
python -m pytest -o addopts= -p no:cacheprovider -q tests/security/test_approved_image_embed_worker.py
python -m pytest -o addopts= -p no:cacheprovider -q tests/security/test_approved_video_embed_worker.py
python -m pytest -o addopts= -p no:cacheprovider -q tests/security/test_approved_video_worker.py
```

On Windows PowerShell, set `$env:PYTHONPATH='backend;tests/security'` and `$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'`, then run the same six `python -m pytest` invocations. These checks use synthetic fixtures and temporary SQLite files. On source snapshot `eaaca0dfb7db6c6881308233cff9350e8d182e02`, a fresh CPython 3.12 macOS ARM64 environment passed the six groups with **47, 12, 8, 14, 7, and 15 tests** (103 total). No test result here establishes a live database migration, serving-worker readiness, model/GPU availability, or Windows execution.
