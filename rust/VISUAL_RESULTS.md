# Multi-photo Rust scoring — November 21, 2026

This round extends the existing vector core and PyO3 adapter. It connects the
new best-seed batch to both the pure visual ranker and the real protected grouping
proposal route. All authorization, checksum, temporal eligibility and review/save
policy remains with the existing Python callers. The default remains Python;
visual acceleration has its own process selector, separate from bulk Search.

## Exact behavior and integration

- 687/687 characterization outcomes match, including 279 expected errors.
  The original 481 outcomes remain unchanged; 206 new inputs cover best-seed
  scoring, numeric ties, both byte orders, bounds and nonfinite refusals.
- All eleven rust-anything gates pass; the direct adapter also passes clippy
  with warnings denied. Authored Rust forbids unsafe code.
- 408 successful shadow calls report zero mismatches. Failed outcomes are
  covered by exact replay, not by shadow's success-only comparison.
- 19 visual and nine grouping checks pass on each selected engine (56 runs).
- Twelve new selector/native checks cover exact scores and ties, capability
  refusal, authorization before import, bounded chunks, callback exceptions,
  malformed outputs and recorded-time/exclusion policy before scoring.
- Two generated ASGI checks exercise the protected grouping proposal route,
  including actual native calls, full Python response parity, no save and no
  scoring of excluded/stale/unauthorized photos.
- Eight existing bulk-native boundary checks still pass. Overall, the final
  focused Python integration run executes 78 tests, with no failures or skips.

The initial generated HTTP fixture tried inserting an ID already present in its
shared fixture. That failed locally with a unique-key error; it was corrected to
update the existing generated row, with explicit row-count/membership assertions.
No production data or application policy was changed to fix the fixture.

## Same-call Mac benchmark

Mac arm64, CPython 3.14.8; 512 candidates × 768 dimensions, 64 generated vector
patterns, one warmup and five measured calls in a fresh process per variant.
These are complete Python consumer calls, including validation, eligibility,
buffer packing, bridge and sort. Full result digests match for each engine pair.

| Consumer | Seeds | Python median | Rust-selected median | Ratio |
|---|---:|---:|---:|---:|
| Visual ranking | 1 | 70.990 ms | 69.943 ms | Same Python scoring path |
| Visual ranking | 24 | 345.941 ms | 213.235 ms | 1.62× |
| Grouping proposal | 8 | 158.459 ms | 116.827 ms | 1.36× |
| Grouping proposal | 16 | 256.808 ms | 168.023 ms | 1.53× |

The one-seed path remains Python because the initial bridge experiment provided
no meaningful speedup. Its final timing difference is ordinary run variation.
Visual ranking returns twenty results; the grouping cases return sixteen and
eight respectively, retaining the 24-member group limit. A 24-seed grouping
benchmark would have no additional slots and is not used to claim a useful win.

Whole-process peaks, including fixture/reference setup, were 45.77/52.72 MiB for
24-seed visual Python/Rust, 44.91/50.69 MiB for eight-seed grouping and
44.06/53.64 MiB for sixteen-seed grouping. The optimization trades a modest
bounded buffer allocation for lower multi-seed scoring time.

Timings exclude file/DB admission, HTTP, embeddings, model/provider calls and
network work. This generated cohort is not a household distribution or live
request-latency measurement. Full samples and source/native hashes are retained
in the private `rust-visual-20261121` handoff. See the
[consumer contract](../docs/RUST_VISUAL_SCORING.md) for selectors and checks.

## Delivery boundary

This round establishes local Mac native-extension and API integration evidence.
The Windows follow-up below adds partial native evidence; production installation
and activation have not been performed. Earlier bulk-only Windows artifacts lack
this visual capability. No live settings, media, schema, models, providers or
saved groups changed. GitHub Actions remains off; no push or deployment ran.

## Windows follow-up — partial, not rollout qualification

Source `8b10e0aefbe4c45a324c882a8f29857b12123e32` built successfully with
MSVC and the existing CPython 3.12.10 runtime, using locked offline dependencies
and private D: scratch. A source-bound ABI3 wheel was produced and clean-imported.
The independently built characterization image passed all 687 exact outcomes,
including 279 expected errors. The visual/grouping tests passed on both selected
engines, and all twenty non-HTTP native/selector tests passed: 76 tests total.

Two generated HTTP tests failed because a fixture cached the dependency-probe's
temporary socket-bind mock at import. That failure remains a failure. The
operator was corrected locally to compose the fixture's saved socket functions
with the existing outer wakeup-pair fence. Reproducing the poisoned import and
Windows fallback locally then passed both HTTP tests, with five pairs and all
ten pair sockets normally closed. The application and numerical code did not
change for this operator correction.

A separate, narrow Windows operation reused the same wheel to attempt only the
two missing HTTP tests and eight benchmark variants. Its child exited 1 after
17.125 seconds. The original result-read connection and one separately granted
diagnostic read both closed before returning stdout. The inner error and
individual HTTP/benchmark outcomes were therefore **not retrieved**. Local
correction evidence is not promoted to Windows acceptance, and Mac speedups are
not relabeled as Windows measurements. No further SSH attempts were made.

Both operations' test Jobs naturally drained to zero, with five handles closed
per Job. The build Job also drained after its explicitly allowed owned-descendant
teardown. Failed D: scratch and original evidence are retained; normal success
cleanup was not used. Each scope requires its own offline/local-owned audit and
explicit release, recorded in the private coordinator records. This is bounded
owned-Job closure evidence, not a global Windows process inventory.

The new consumer remains **partially qualified on Windows and inactive**. The
next step is to retrieve the exact retained child failure/result files through a
working authorized connection or a Windows-local session, diagnose that concrete
error, and qualify only the remaining gap. The successful build, corpus and
76 tests need no replay while their source contracts remain unchanged. The
default stays Python; GitHub CI and production activation remain off.
