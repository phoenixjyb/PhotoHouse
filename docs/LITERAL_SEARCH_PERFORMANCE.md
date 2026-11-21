# Literal text search: query-token reuse

This implements the Python-first text-search step from the Rust migration audit.
It does not add a new Rust extension or replace the existing optional vector and
grouping kernels. Literal matching, Unicode policy and result membership are
unchanged. No deployment or feature activation is included.

## What changed

Each `AssistantSearchReads` owns one empty `TextQueryCache`. After the existing
cancellation and literal-presence checks, the first matching source prepares the
query tokens; later matching sources and rows reuse that immutable entry. A
different phrase replaces the entry. Direct callers without a cache still
prepare the query once per row instead of once per matching source.

The cache holds only a phrase and its token tuple. It never caches source text,
revisions, membership, match reasons, cards or results. `SearchRuntime.call`
creates a new reader for every operation, so a new turn still authenticates and
loads current scoped facts before matching. No global cache or private filter
fields are introduced, and a query with no matching source does not prepare
tokens. Returning the locally captured immutable entry prevents a different
simultaneous phrase from mixing query/token pairs.

CJK extraction now uses the existing compiled regex's `findall` and `sub`
operations over each word, replacing repeated per-character Python calls to
`fullmatch`. The same three character ranges, Python Unicode word regex,
NFKC/casefolding, code-point boundary checks, integer coverage and sort policy
remain authoritative. `SEARCH_TEXT_POLICY_VERSION` stays 1 because behavior is
unchanged; literal eligibility is not broadened to fuzzy or semantic matching.

All source cancellation checks remain in their original positions. All current
matching sources are still examined, including sources beyond the 43-reason cap.
No stale source token sets can survive a caption/note edit because source tokens
are recomputed from every current normalized source.

## Local evidence

Sixty-four focused test runs passed without failures or skips: six existing
literal helper tests, seven new differential/cache tests, 36 existing assistant
joint-search API tests, 14 descriptive-search checks and one new API cache test.
The new checks compare the full token sequence for all 1,114,112 Unicode code
points against the frozen old implementation, compare 1,000 deterministic mixed
script/normalization cases, and preserve every cancellation boundary, callback
filter mutation, current revision, reason cap and privacy projection. The new
API test proves one query preparation per actual search and fresh preparation
on the next turn. Existing tests cover authorization, joint hard filters,
paging, current-source checks and stale context refusal.

Mac arm64/CPython 3.14.8, 10,000 generated assets with two sources each, one warmup
and five measured scans per variant:

| Fixture | Original median | Optimized median | Ratio |
|---|---:|---:|---:|
| All sources match a CJK phrase | 227.201ms | 157.377ms | 1.44× |
| All sources match an ASCII phrase | 202.685ms | 142.439ms | 1.42× |
| Twenty percent match a CJK phrase | 61.999ms | 48.671ms | 1.27× |

Full ranked cards, reasons, qualities and cancellation-check counts have identical
digests for each pair. Positive scans retain 90,004 checks; the mostly-miss scan
retains 74,004. In the separate CJK profile, total tokenizations fall from 40,000
to 20,001 (20,000 current source tokenizations plus one query). Per-character
`fullmatch` calls fall from 600,000 to zero. Profiling attribution is separate
from these unprofiled wall medians.

These are generated source normalization/matching/ranking component measurements.
They exclude authorization transactions, file/DB reads, HTTP and model/network
time, and do not establish live request latency or a household distribution.
No Windows qualification or live rollout was performed in this round.

## Reproduce and continue

`rust/benchmark_text_search.py` measures the complete component call. Use
`--case cjk`, `ascii` or `mostly_miss`, `--prepare` for reader-style query reuse,
and a new `--output` file. `--reference` selects an explicit frozen original
module for comparison. Source/tool hashes, all five samples, full result digest,
check counts and an optional separate `--profile` are recorded. On Windows,
source and output must be on D: within a separately admitted bounded operation.

The ordinary CPU test dependencies suffice for the API fixtures. No Rust build,
model, household data or listening application server is needed:

```sh
PYTHONPATH=server/backend:server/tests/security python3 -m unittest \
  test_search_text test_search_text_reuse test_assistant_joint_search test_search_description
```

The final token operations already run through Python's compiled regex engine.
A further Rust batch has no measured gain yet and would need its own exact
Unicode, cancellation and bridge-overhead proof. Keep this measured improvement
without introducing another native dependency on that assumption. Windows
qualification and deployment remain separate next steps; existing live settings
and the GitHub Actions cost pause are unchanged.
