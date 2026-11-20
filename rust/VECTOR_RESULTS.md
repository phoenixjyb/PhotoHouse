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
