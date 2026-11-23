# Optional Rust literal-search quality fast path

This source adds one isolated optional kernel. Production remains on its current
unchanged deployment; the new kernel is **not Windows-qualified or activated**.
It builds neither the qualified vector/visual kernels nor the grouping kernel.
Search, grouping, automatic importing, model/provider settings and GitHub CI
are unchanged.

## Boundary

The profile of the optimized 10,000-photo/two-source scan still attributed most
matching CPU to coverage/token construction. The Rust function fuses coverage,
whole-phrase boundary and code-point length in one direct extension call. It
handles ASCII, CJK Extension A/basic ideographs and an explicit small punctuation
set. Other scripts, combining marks, compatibility ideographs, emoji, lone
surrogates and strings above 64 KiB use the original Python calculation.
No Unicode table from the Rust compiler can broaden Python's word policy.

Python retains NFKC/casefolding, literal substring eligibility, current authorized
source loading, authored-source preference, the 43-reason cap, source IDs and
revisions, every original cancellation callback, quality ordering and card
projection. A reader holds only its original request-local phrase/token entry
plus a native function reference. No source text or results enter a global cache.
No model, network, filesystem or database operation is added to the kernel.

## Selector and failure behavior

`PHOTOHOUSE_LITERAL_TEXT_ENGINE` is read once when a request reader is created:

- `python` (default): original calculation; no native import.
- `rust`: exact supported-input fast path; unsupported inputs use Python.
- `shadow`: compute both for supported inputs, refuse a mismatch with a closed
  error code, return the original result on equality; never log source text.

Unknown selectors, an unavailable/wrong-version explicitly selected extension,
invalid native output or a shadow mismatch refuse. Missing binaries do not
silently override an explicit engine selection. This source does not forward a
new selector into the live Windows service or change its deployment manifest.

## Measured local evidence

Mac arm64, CPython 3.14.10, Rust 1.98.0; one warmup and five samples in fresh
processes for each variant. The baseline is the already optimized deployed-source
Python helper, not the older pre-cache implementation. These timings include
normalization, provenance, callbacks, Python/native crossing and final ranking.
They exclude authorization/DB reads, HTTP, inference and network time.

| Generated 10,000-photo fixture | Optimized Python | Rust fast path | Ratio |
| --- | ---: | ---: | ---: |
| cjk | 141.643 ms | 94.373 ms | 1.50× |
| ascii | 143.469 ms | 94.433 ms | 1.52× |
| mostly_miss | 45.482 ms | 36.102 ms | 1.26× |

All full-result/callback digests match. The new default-Python path also matched
and stayed within roughly one percent of the reference in this local run.
These are generated CPU-component results, not household request latency.
The separate JSON characterization bridge measured 5.84× across its 832 cases;
that number is not the full scan or a production latency claim.

- `rust-anything gate` passed fmt, warnings-as-errors clippy, unit tests,
  no-unsafe/no-panic checks, build, API and all **832/832 exact recorded cases**.
- **69 focused Python tests** passed: the existing literal/cache helpers and
  Search API/description cases, plus the actual new extension in Python/Rust/
  shadow modes. The new checks include 1,007 mixed-script cases, all 27,712
  code points in the fast character domain, unchanged callbacks at every
  cancellation point, the reason cap and sanitized native refusals.
- The direct binding passed warnings-as-errors clippy and formatting.
- No Windows check, production restart, kernel replacement or CI run is claimed.

## Build and qualify only this new unit

From the checkout root, use the existing CPU Python and cached Rust dependencies:

```sh
python rust/build_literal_kernel.py
PYTHONPATH=server/backend:server/tests/security:rust/literal-python/target/python \
  python -m unittest test_search_text_native test_search_text test_search_text_reuse
PYTHONPATH=server/backend:server/tests/security:rust/literal-python/target/python \
  PHOTOHOUSE_LITERAL_TEXT_ENGINE=rust python -m unittest \
  test_assistant_joint_search test_search_description
```

On Windows, source/build/cache/TEMP/TMP must be explicitly on D:, inside a fresh
bounded CPU-only qualification. The builder is locked/offline and refuses C:
scratch; it installs nothing into the live environment. Qualify the actual new
`.pyd` with the pinned Windows Python and these generated tests/three benchmark
pairs, then require identical results/callbacks and a bridge-inclusive gain.
Keep current live source/task bindings and old native binaries intact. Rollout
is a later concrete operation with its own source/config and rollback bindings;
local gate success does not authorize or establish Windows activation.
