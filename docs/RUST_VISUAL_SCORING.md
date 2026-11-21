# Optional Rust multi-photo scoring

The existing vector core supplies a second consumer: best-seed similarity for
`rank_visual_candidates` and `propose_memory_group`, including the protected
`POST /memory-groups/proposals` route. It accelerates the numeric comparison of
already validated vectors; it does not produce embeddings, add a model, broaden
the search cohort or change a saved group.

## Selection and compatibility

`PHOTOHOUSE_VISUAL_ENGINE` defaults to `python`. Setting it to `rust` explicitly
selects the optional adapter for this consumer, independently of
`PHOTOHOUSE_VECTOR_ENGINE`. Neither selector enables the other. Request data
cannot select an engine. Missing, incompatible or unknown selected engines
refuse the operation instead of silently falling back.

The adapter must retain base `KERNEL_VERSION=1` and
`canonical-f32-fsum-v1:4096:4194304`, and additionally expose `best_seed` with
`VISUAL_POLICY_FINGERPRINT=best-seed-fsum-v1:24:512:4096:4194304`.
The earlier bulk-only Windows wheel lacks this capability and must not be used
for this consumer. Existing bulk canonicalization and scoring remain compatible.

A single seed retains the Python scoring loop after selected-capability
validation: its measured bridge cost provided no useful improvement. In grouping,
an individual temporal bucket with one eligible seed also uses Python. Multiple
eligible seeds use one native call per bounded candidate block, rather than one
bridge call per pair.

## Policy stays with the caller

Python validates the entire cohort before selecting or calling the adapter:
library authorization, exact ID coverage, vector-space identity, checksums,
dimensions, finite components and unit norms. Seed membership and duplicate
records retain their original checks. No identifiers, paths, files or database
handles cross the numeric bridge.

Grouping applies recorded-time compatibility and exclusions first, batching only
candidates with the same eligible seed set. A seed outside that candidate's time
window is never scored against it. Minimum similarity, deterministic candidate
sorting, the twenty-result limit and the remaining slots in a 24-photo group
are unchanged. With 24 seeds, a grouping proposal still has zero additional
slots. Proposals still require review and save nothing automatically.

The Rust kernel accepts immutable native-endian binary64 buffers: 1–24 seeds,
1–4096 dimensions, at most 512 candidate rows and at most 4 MiB per candidate
block. The seed buffer is at most 786,432 bytes. Large validated cohorts are split
into blocks without changing the whole-cohort checks or result order.
Best-score ties choose the smallest numeric seed ID. Accurate binary64 summation
uses the existing PSF-attributed accumulator, preserving exact Python outcomes
without introducing a tolerance or fused multiply-add approximation.

Native numeric work releases the GIL and checks Python signals at each row.
The direct observer callback retains its original exception; failure publishes
no partial result. The kernel starts no native threads or child processes. Host,
request and data-admission limits remain separate from these buffer limits.

## Build and focused checks

Use the existing offline build and toolchain instructions in
[RUST_VECTOR_KERNEL.md](RUST_VECTOR_KERNEL.md). After building the adapter, put
`rust/vector-python/target/python`, `server/backend` and `server/tests/security`
on the test process's `PYTHONPATH`. Run:

```sh
python3 rust/build_vector_kernel.py
python3 -m unittest test_visual_rust test_visual_rust_http test_vector_rust
PHOTOHOUSE_VISUAL_ENGINE=python python3 -m unittest test_visual_candidates test_memory_grouping
PHOTOHOUSE_VISUAL_ENGINE=rust python3 -m unittest test_visual_candidates test_memory_grouping
cargo clippy --offline --locked --all-targets --manifest-path rust/vector-python/Cargo.toml -- -D warnings
rust-anything gate rust/vector-core
```

The generated ASGI fixture needs the project's CPU test dependencies, including
SQLAlchemy and Alembic. A skipped native suite is not a pass. No model, household
data or listening application server is needed. Windows execution additionally
requires current shared-host admission, D: scratch, bounded processes and the
already qualified stdlib wakeup-socket exception for in-process ASGI tests.
These commands do not grant Windows execution or change any live settings.

`rust/generate_visual_cases.py` generates the additional characterization inputs,
including all original bulk inputs. The recorded corpus is replayed exactly;
do not replace expected outcomes to accommodate a port difference.

`rust/benchmark_visual_kernel.py --engine python --seeds 24 --output <new-file>`
measures a generated full visual-ranker call; repeat with `--engine rust` in a
separate process. `--mode group --seeds 8` or `16` measures the grouping consumer
with nonempty proposals and actual recorded-time eligibility. Each run checks
full result equality and writes five timing samples, process peak memory and
source/native hashes. The output distinguishes selected and actual scoring
engines. Benchmark processes should run serially; on Windows source and output
must stay on D: within an admitted operation.

## Evidence and rollout status

See [VISUAL_RESULTS.md](../rust/VISUAL_RESULTS.md) for Mac and Windows measurements,
exact check counts and retained failures. The source-bound MSVC artifact passed
687 exact cases and all 78 integration checks; the final two protected API tests
and eight benchmark variants reused the accepted wheel without rebuilding or
replaying the 76 earlier passing tests. The captured Windows fixture failure was
a 264-character path, resolved by a new private operation root giving 221-character
paths; global path settings and application behavior were unchanged.
It has not been activated in production. A rollout needs the qualified artifact
and current runtime bindings, with rollback to the Python selector.
Search, grouping, models and providers remain unchanged on the live machine.
GitHub Actions stays paused.
