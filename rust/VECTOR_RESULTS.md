# Vector kernel local qualification — November 20, 2026

Mac arm64, Python 3.14.8, NumPy 2.4.2. Generated 4,096 × 768 float32
vectors using 64 reused patterns; one warm-up and five measured calls per path.
Every derived matrix byte and every ranked ID/score matched the reference.
These are component measurements, excluding file admission, HTTP, databases,
model/provider and network time. They do not establish Windows performance.

| Component | Python/NumPy median | Rust median | Speedup |
|---|---:|---:|---:|
| Cold canonical matrix | 515.340 ms | 85.472 ms | 6.03× |
| Warm rank vs scalar | 117.087 ms | 55.036 ms | 2.13× |
| Warm rank vs NumPy | 66.507 ms | 55.036 ms | 1.21× |
| Cold construction + rank | 581.645 ms | 141.552 ms | 4.11× |

The warm NumPy comparison is the relevant baseline when that existing path is
available. The larger cold speedup must not be presented as every Search query's
speedup. Production remains on Python; the optional extension is not installed
by ordinary imports.

Validation passed:

- 481 exact recorded outcomes, including 225 errors; no float tolerance.
- All 11 rust-anything gates; adapter clippy has no warnings.
- 256 successful shadow comparisons, zero mismatches.
- 43 unchanged Python bulk contracts, 39 backend-neutral Rust bulk contracts,
  eight engine/native-boundary checks and ten API endpoint tests per engine.
- Original cancellation exceptions, callback counts/order, unselected-row
  checks, corrupt checksums/norms, memory block bounds and generation mutation
  refusal remain covered.

The separate JSON/hex characterization-envelope benchmark measured 1.71× over
its Python reference across the corpus. That adapter is not the production byte
bridge and is not a request-latency measurement.

Evidence, full samples and exact source/native hashes are retained locally in
`.runtime/vector-kernel/`. See [the integration contract](../docs/RUST_VECTOR_KERNEL.md)
for build commands, the four Python-implementation-specific tests, numerical
attribution and rollout limits. No Windows operation, deployment or GitHub CI
was performed for this development round.


## Windows native qualification — November 21, 2026

Source `cad2d0a34db1cce70bf9a58ead3eb1dab75bbef4`, CPython 3.12.10 x64,
NumPy 2.4.2. The ABI3 adapter and corpus core were built with the existing MSVC
and locked offline Cargo dependencies. The wheel preserves source provenance,
30 dependency-notice sets, the PSF license and the Rust bridge notice. It remains
unpublished and uninstalled in the live runtime.

The same generated 4,096 × 768 fixture (64 patterns) ran in seven fresh processes,
with one warmup and five measured calls per path. Matrix bytes, ranked IDs/scores
and callback counts matched exactly, without a numerical tolerance.

| Component | Python/NumPy median | Rust median | Speedup |
|---|---:|---:|---:|
| Cold canonical matrix | 1,055.747 ms | 151.562 ms | 6.97× |
| Warm rank vs scalar | 189.258 ms | 73.476 ms | 2.58× |
| Warm rank vs NumPy | 109.245 ms | 73.476 ms | 1.49× |
| Cold construction + rank | 1,252.150 ms | 233.452 ms | 5.36× |

These are CPU component timings, including the byte bridge, callbacks and sort,
excluding file admission, database, HTTP and model/provider work. They do not
predict complete live Search latency. Process peaks include common fixture and
Python-reference setup: 130.90/132.85 MiB for cold Python/Rust, and 106.29/106.88
MiB for warm NumPy/Rust. The test Job had a 2 GiB bound and 20% CPU hard cap;
compiler work had a separate 4 GiB bound. GPU use was zero.

Windows checks passed: 481 exact corpus cases (225 expected errors), 42 Python
and 38 Rust storage checks, eight native-boundary checks and ten generated
endpoint checks on each engine. Two POSIX-only fixtures per engine are explicitly
excluded from Windows coverage; their six changed-case checks passed on Mac.
The cross-platform hardlink refusal/recovery check passed on both engines.

The native build and remaining endpoint/benchmark evidence come from separate
source-bound operations using the same wheel. Earlier dependency/fence failures
remain failures. Only the successful operation's sealed scratch is removed;
failed scratch is preserved. Temporary NumPy lived only in D test scratch, with
all wheel RECORD entries checked. In-process ASGI tests used 36 owned stdlib
wakeup pairs per engine; all 144 sockets closed and no application server or
external network access was enabled. Live Search/grouping/AI settings and the
Python default remain unchanged. No GitHub Actions or production rollout ran.
