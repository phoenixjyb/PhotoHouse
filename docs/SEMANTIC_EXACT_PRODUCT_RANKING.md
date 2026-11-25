# Exact semantic product ranking — R80

语义检索仍关闭。本轮源码 `11fc08e` 优化向量乘法，保留原有精确求和、排序、权限与
完整性检查；尚未部署，也未取得 Windows、手机或家庭相关性验收。

The optional product path runs only for at least 128 selected rows and dimensions
of at least 128. NumPy is loaded lazily; an unavailable optional import keeps the
scalar path. No required dependency, route, configuration flag, database schema
or on-disk vector format was added.

## Behavior and bounds

The ranker gathers selected rows from the existing immutable native-f64 cache
and computes elementwise float64 products. Each score still uses the original
`math.fsum`; equal scores still sort by numeric asset ID. It uses no vectorized
sum or dot-product reduction.

Each call owns its product buffer, capped at 4 MiB, and one numeric offset array
of at most 32 KiB per block. The ordered cursor replaces a per-row lookup
dictionary. Concurrent calls share only immutable cache bytes. Small cohorts and
small dimensions keep scalar scoring.

Cancellation precedes the first selected block's product preparation and every
row's score reduction. A block may prepare bounded arithmetic for later rows;
cancellation prevents subsequent block preparation and result release. The
existing callback order and exception propagation remain tested.

Complete-cohort validation, source and eligibility checks, vector-file hashing,
current authorization, post-provider freshness and generation checks remain in
their existing paths. No authority, file-permission or source decision is cached
by this change.

## Local evidence

The focused suite passed **43 tests** with both Python 3.14.8 / NumPy 2.4.2 and
Python 3.12.12 / NumPy 2.2.6. The complete CPU API profile with the latter pair
passed **3,432 tests and 4,090 subtests**, plus the generated no-listener demo.
An earlier broad run retained one timing-sensitive workspace-test failure; that
case passed in isolation and the serialized full recheck passed without changing
application code or its timeout.

Generated benchmarks on macOS compared the actual frozen R71 scalar method to
`11fc08e`, using identical canonical float32 vectors in the native-f64 cache,
Python 3.12.12 and NumPy 2.2.6. Three alternating runs produced:

| Generated rows × dimensions | Original ranking median | R80 median |
| --- | ---: | ---: |
| 23,696 × 768 | 608.118 ms | 475.812 ms |
| 40,000 × 768 | 1,018.643 ms | 811.089 ms |

All score bits and complete ordering matched. Two concurrent 40,000-row calls
with different queries matched their separate scalar references and used
distinct buffers. Matrix hashes stayed unchanged. Both benchmark processes
remained below the 512 MiB experiment cap. The initial 40k harness's incorrect
block-count assertion was retained separately and corrected before accepting
the result.

These measure the ranking function on generated data. They establish neither
full-request latency, Windows performance, server concurrency, relevance nor
serving acceptance. NumPy 2.2.6 on this Mac is not a Windows execution result.

## Capacity and remaining gates

The 100,000 candidate-ID limit is a logical upper bound. Dimension, file-header,
source-read and byte limits can refuse earlier. At 768 dimensions, the unchanged
256 MiB native-f64 cache alone permits at most 43,690 rows; the complete bulk
file and other limits impose further bounds. This round checked a generated
40,000-row cache and raised no limit.

A fresh bounded Windows run must still bind the new source, current cohort,
model/index/policy and reviewed omissions, retain both audits and all protection
cases, and finish independent closure and release. The 2-second backend target,
phone/WAN checks, family relevance, serving omission approval, index lifecycle
and owner-only activation remain separate gates. See
[request latency](SEMANTIC_REQUEST_LATENCY.md),
[eligibility](SEMANTIC_ELIGIBILITY_DESIGN.md) and
[runtime configuration](SEMANTIC_RUNTIME_CONFIGURATION.md).
