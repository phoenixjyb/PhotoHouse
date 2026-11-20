# Optional Rust vector kernel

The first consumer is bulk semantic Search: cold canonical matrix construction
and warm exact ranking. The same immutable-buffer core can support other rankers,
but visual suggestions and non-bulk semantic paths still use their existing
Python implementations. No model, provider, vector space, search eligibility,
authorization, database schema, file format or feature setting changes here.

Python is the default. The extension is not installed or activated by importing
the application. `PHOTOHOUSE_VECTOR_ENGINE=rust` is an explicit process-level
choice for a separately qualified deployment. An unavailable or incompatible
extension refuses the operation; it does not silently select a different engine.
An unknown selector also refuses. No API request may choose this environment.

## Boundary and numerical behavior

`rust/vector-core` validates dimension-tagged big-endian float32 checksums,
rejects nonfinite/non-unit inputs and emits the existing normalized float64
matrix layout. `rust/vector-python` supplies the direct PyO3 immutable-byte
bridge; JSON and hex are used only by the characterization corpus, never in the
production numeric loop. Native calls release the GIL and reattach at each
existing row callback, preserving original callback exceptions and row order.
No native threads or child processes are spawned by the kernel.

Bulk source/cohort/identity/permission checks, secure file rereads, cache sealing,
current generation checks, selected IDs and deterministic sorting remain in
Python. Callbacks still visit unselected rows, and cancellation publishes no
partial result. Mutable or noncontiguous internal cold buffers retain the
reference path; admitted file payloads are immutable bytes.

One canonical output or score input block is at most 4 MiB; dimension remains
1–4096. These are block limits, not a replacement for the existing whole-cache,
request or host resource limits. Existing snapshot and file formats are unchanged.

Products and normalization retain accurate binary64 summation and half-even
rounding, not a plain sum, FMA or float32 approximation. The accumulator adapts
[CPython's math_fsum](https://github.com/python/cpython/blob/v3.12.10/Modules/mathmodule.c).
The PSF license, attribution and change notice are in
[third_party/python](../third_party/python/NOTICE.md). No numerical tolerance was
added or widened.

## Local build and checks

Use a Rust toolchain and the locked cached dependencies. The default CPU
application does not need either Rust or the extension.

```sh
python3 rust/build_vector_kernel.py
python3 rust/validate_vector_integration.py
python3 rust/benchmark_vector_kernel.py
cargo clippy --all-targets --manifest-path rust/vector-python/Cargo.toml -- -D warnings
rust-anything gate rust/vector-core
```

The helper builds offline and copies only the extension into
`rust/vector-python/target/python`. That directory is on the validation scripts'
private import path, not the live server's path. On Windows it refuses a source,
target, Cargo cache or temporary directory on C:; all must explicitly be on D:.
This check does not grant a Windows build or production admission. No global TEMP
or application environment is changed.

For a source-bound Windows ABI3 artifact, `rust/package_vector_kernel.py` packages
an already built MSVC x64 DLL and locked vendored license notices. It performs no
build, download or installation and refuses an existing output. Native imports,
parity and host qualification remain separate from packaging.

`rust/benchmark_vector_kernel.py --case warm_numpy --output <new-file>` runs one
case per fresh process; the other cases cover cold Python/Rust, scalar ranking,
Rust ranking and cold-plus-rank. Use the same generated 4,096 × 768 fixture on
both engines. Each output includes exact matrix/rank digests, callback counts,
all five timing samples and peak process memory, including the common reference
setup. An absent NumPy baseline refuses the benchmark rather than substituting a
slower comparator. `--native-dir` and `--dependency-root` select only explicit
operator inputs; they are not application request options. On Windows source,
native scratch and output must be on D:.

`rust/generate_vector_cases.py` regenerates public/synthetic inputs. The golden
corpus in `rust/vector-core/cases.jsonl` characterizes the Python reference;
keep original errors and expected outputs intact when modifying the Rust code.
Read JSONL as LF-delimited records, not `str.splitlines()`, which also splits
Unicode separators that can legally occur inside recorded strings.

## Acceptance evidence and limits

The initial Mac arm64/Python 3.14.8 qualification records:

- 481/481 exact corpus outcomes, including 225 expected errors.
- All 11 rust-anything gates, plus warning-free adapter clippy.
- 256 successful shadow calls with zero mismatches; failed outcomes are covered
  by the exact corpus replay, not by shadow's success-only comparison.
- 43 unchanged bulk storage tests on Python and 39 backend-neutral tests on Rust.
  Four tests instrument the Python canonicalizer or NumPy allocation directly;
  they remain mandatory on Python. Eight additional native/selector tests cover
  equivalent mutation, cancellation, checksum, norm, bound and exception behavior.
- Ten bulk Search endpoint tests on each engine, using generated local data.

The same-call benchmark uses 4,096 rows × 768 dimensions, one warm-up and five
measured calls, including the byte bridge, row callbacks and final ranking.
It compares cold construction, scalar warm ranking, NumPy warm ranking and Rust.
The fixture reuses 64 generated vector patterns and exercises stable ties; it is
not a household distribution. Raw timings and source/binary hashes are written
to `.runtime/vector-kernel/benchmark.json`; validation logs remain under the same
ignored directory. These component measurements exclude secure file admission,
HTTP, database, provider and network work and are not live request latency.

No Windows-native comparison, actual installed extension, production activation,
model change or physical-device acceptance is established by these local checks.
Keep the deployed Search/grouping/model configuration unchanged until the exact
new Windows artifact and host operation are independently qualified. Roll back
an optional deployment by restoring the Python engine and its prior pinned
runtime; do not reinterpret earlier successful scopes as a new deployment grant.
GitHub Actions remains paused.
