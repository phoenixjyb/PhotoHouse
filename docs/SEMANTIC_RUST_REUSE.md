# Reuse the vector kernel for non-bulk semantic Search

The optional Rust selector now also covers per-record canonicalization in the
small-cohort and streaming semantic rankers. It reuses the existing vector
kernel and policy fingerprint. No Rust source, compiled binary, provider, model,
schema, approximate index or Search eligibility rule changes in this increment.
Python remains the default. Source/local checks do not activate Windows.

## Preserve the request boundary

Python still validates exact record/identity/component types, dimension and
finite float32 packing. The Rust kernel verifies the checksum and unit norm,
then returns the same canonical float64 components. The adapter checks its
single-row callback, output type/size and finite values. Unsupported or corrupt
input refuses; explicitly selecting an unavailable Rust kernel never falls back
silently. The Python implementation is retained for ordinary operation and
comparison.

Each current row crosses the bridge separately. This deliberately preserves the
original cancellation and callback-time mutation boundary before the next row.
It does not pack future rows early to obtain a larger synthetic speedup. The
same authorized cohort, duplicate/omission checks, scoring, tie ordering, source
revision checks and post-query authorization remain outside the kernel.

The shared packing helper also avoids one Python generator frame per component
by using builtin type mapping and membership checks. It still accepts only exact
`int`/`float`, refuses booleans and numeric subclasses, and freezes mutable lists
before validation. The original list-replacement/growth regression tests now
instrument the current validation boundary and still require the mutation to
occur. No acceptance assertion was removed.

## Measured local result

Mac arm64, Python 3.12.12, 768-dimensional generated vectors, one warmup and
seven measured complete canonicalization/scoring/ranking calls per engine:

| Generated component | Improved Python | Existing Rust kernel | Ratio |
| --- | ---: | ---: | ---: |
| Small cohort, 512 vectors | 50.794 ms | 44.591 ms | 1.14x |
| Streaming, 4,096 vectors | 397.688 ms | 368.307 ms | 1.08x |

The pre-change small-cohort Python observation was 61.577 ms; the separate
packing improvement accounts for part of the gain before enabling Rust. These
are modest component improvements, not whole-application or household latency
claims. Both engines produced identical full ranked score digests and retained
1,540 / 8,226 callbacks respectively. Timings exclude file/DB admission, HTTP,
model/provider time and household relevance. No native build occurred.

Six new generated tests cover exact components/ranks at 4, 768 and 4,096
dimensions, stable ties, cancellation at every original boundary, callback-time
source mutation, invalid input/wire results and explicit unavailable selection.
The affected Python-default cohort completed 83 tests: 82 passed and one
platform-specific case was skipped. A 51-test cohort with the saved real Mac
extension selected completed with 50 passes and the same platform skip. The
new consumer paths have the separate Windows evidence below; controlled rollout
remains a distinct step. The old binary's qualification is retained.

## Windows generated qualification — November 24

The same existing 308,224-byte extension was used with CPython 3.12.10 x64;
no native build, model request or production configuration change occurred.
The actual Windows test suite returned **56 passes, zero failures/errors and
two explicit POSIX-only skips** across 58 cases. The skipped fixtures concern
POSIX mode/symlink behavior; this increment does not qualify Windows reparse
or DACL behavior. Existing storage controls remain separate and unchanged.

The original qualification wrapper rejected those skips and stopped before
benchmarking. Its failed result was retained. A separate benchmark-only operation
bound that exact source/native/test receipt and ran only the missing two cases;
it did not repeat the suite or relabel the original operation as successful.

| Windows generated component | Python | Existing Rust kernel | Ratio |
| --- | ---: | ---: | ---: |
| Small cohort, 512 vectors | 107.873 ms | 90.159 ms | 1.20x |
| Streaming, 4,096 vectors | 862.647 ms | 724.817 ms | 1.19x |

Each case used 768 dimensions, one warmup and seven samples per engine under a
20% CPU hard cap, a 2 GiB/four-process native Job, no GPU, and at least 12 GiB
free RAM and D: disk reserve. Both engines produced identical full ranked
results and callback counts: 1,540 for small and 8,226 for streaming. These are
component wall-time medians under that profile, not household Search latency.
The native Job drained, its handles closed, successful D: scratch was removed,
and transport/source/offline closure was accepted. Live API activation remains
outside this generated qualification.

## Reproduce without rebuilding

Use the existing CPU development environment and an existing compatible native
extension. On Windows, source/native inputs/output must be on D: inside the
separately admitted resource and cleanup scope.

```sh
python -B rust/benchmark_semantic_rank.py --case small \
  --native-dir "$existing_native_directory" --output "$new_report"
python -B rust/benchmark_semantic_rank.py --case streaming \
  --native-dir "$existing_native_directory" --output "$another_new_report"
PYTHONPATH=server/backend:server/tests/security python -B -m unittest \
  test_semantic_rust_reuse test_semantic_encoder test_semantic_streaming_search
```

This work is an incremental consumer of the
[existing vector kernel](RUST_VECTOR_KERNEL.md), not another independent port or
copy of it. Keep GitHub Actions off and preserve live Search, grouping and
automatic importing until a reviewed rollout.
