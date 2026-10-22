# Full-catalog semantic qualification and private timing

Semantic remains **OFF**. These tools use new disposable accounts, a synthetic
database and private candidate outputs. They do not install a production policy,
publish an index or change services.

## Explicit omission review

`qualify_library_semantic.prepare_omission_review(index_path, output_directory)`
validates the complete frozen snapshot, index and failure partition, then writes
an **unreviewed** draft in a fresh private directory. It performs no model call.
The draft has exactly `format_version` (1), `operator_reviewed` (false),
`index_sha256`, `snapshot_sha256` and `omitted`. Each omission has `asset_id`,
`source_sha256` and `reason`. A missing original still needs its catalog SHA;
an absent observed-byte SHA does not remove that binding.

An operator must review the exact omissions and pins before supplying a separate
copy with `operator_reviewed: true`. The original draft remains evidence.
`semantic_coverage_qualification.py` refuses incomplete, duplicate, changed,
unknown or unreviewed entries. It never infers approval from an index failure.
The runtime policy is constructed only after validation, bound to the disposable
library, joint model binding and newly built bulk container.

On October 21 the owner approved **65 omissions for qualification only**:
64 preparation failures and one missing source. A read-only comparison matched
all 23,761 frozen catalog rows with no additions, removals or source-hash changes.
That is point-in-time evidence; it does not authorize production installation,
activation or family rollout. Private review documents stay outside Git.

## Bounded full-catalog canary

`measure(..., bulk_vectors=True, omission_review_path=review_path,
profile_requests=True)` opts into the reviewed full frozen catalog and private
timing. Without the new options, ready-only qualification is unchanged.
The index and review inputs are pinned and checked again before a successful
measurement is published. Snapshot/review JSON reads have explicit size limits.

The synthetic database retains every frozen asset ID and source hash, including
omissions, while accounts, dates, paths and captions are generated fixtures.
All ready vectors remain part of ranking. This tests coverage and protection
behavior; it does not establish actual family-caption relevance. The canary
retains the existing ten protection checks and adds five:

- An omitted-only hard filter discloses coverage without calling the encoder.
- Ordinary literal search retains omitted images.
- A changed policy refuses before bulk reads and inference.
- A changed omitted source refuses even when filters exclude it.
- An omitted source changed during encoding withholds result cards.

Native work still needs a fresh process/resource/configuration preflight, pinned
source and model identities, a private one-shot stage, a bounded Windows Job,
loopback-only test listeners and independent completion/closure readback.
Two complete index audits inside `measure` remain mandatory. Avoid an additional
redundant worker audit; setup savings are not query-latency improvements.

## Private request profiler

`semantic_request_profile.instrument_requests()` patches only within its explicit
context and restores exact module/class attributes on exit. Overlapping contexts
refuse. Request-local state separates concurrent requests. At most 256 request
summaries are retained, with an explicit dropped count. No queries, arguments,
IDs, paths, hashes, tokens, SQL, scores or exception text are captured.

Fixed phases include authorization, source binding/SQL/extra work, prepared
facts, artifacts, bulk snapshot, eligibility validation, canonical hashing,
encoder round trip and ranking. Each reports calls, errors, inclusive, exclusive
and maximum milliseconds. Inclusive nested phases must not be added together.
The SQL phase includes the bounded read callback and packing/accounting. Encoder
round trip includes transport and is not model-only inference time. Runtime root
time excludes outer HTTP/TLS/admission/serialization; observer overhead is included.
Sample ordinals link timings to their private request summaries.

Generated tests cover 515 ready vectors plus 65 omissions, review/pin mutation,
size refusal, concurrent isolation, exact patch restoration and measurement
publication failure. Focused qualification/profiler suites passed **33 tests**.
At source `a46d9f5`, the full API profile passed **2,916 tests / 3,703 subtests**
plus the generated demo, with unchanged source/revision. Seven isolated archive
checks passed for the 274-file package. See the
[eligibility contract](SEMANTIC_ELIGIBILITY_DESIGN.md) and
[library qualification record](SEMANTIC_LIBRARY_SCALE.md).

## Latest optimized native result, October 22, 2026

The frozen `e85c6e4` source completed a new one-shot Windows CPU canary with the
same 23,761-entry catalog, 23,696 vectors, 65 qualification-only omissions and
15 protection checks. All checks passed. Nine English/Chinese/mixed loopback
HTTPS/TCP samples measured **7.860 seconds median / 8.328 seconds maximum**;
cold latency was **14.843 seconds**. There were zero individual NPY query reads.
The earlier baseline below measured 14.516 / 17.281 / 24.984 seconds respectively.
The observed warm-median reduction is about 46%; separate shared-host runs do not
establish a controlled causal speedup or phone/WAN performance.

Both complete vector/metadata/stat-identity audits passed and took 1,119.002
seconds total. The complete canary took 1,409.515 seconds under the unchanged
1,800-second / 8 GiB / four-process Job with CPU-only model execution. Sixteen
encodes took 2.300 seconds total. Audit/setup time is separate from query latency.

Independent completion readback verified all 12 staged inputs, source identity,
reviewed omissions, measurement hash, nine sample/profile ordinals, both audits,
Job limits and resource closure. No test process or test-port listener remained.
Live API/gateway/site/task/feed pins stayed unchanged. A fresh read-only catalog
comparison found no additions, removals or source-hash changes. All 69 assets of
the separately hosted furniture report passed exact byte/hash/MIME checks before
and after the run. These are sampled HTTP checks, not continuous uptime or browser
rendering acceptance. The Windows lane was explicitly released after closure.

Semantic remains **OFF**. The 2-second backend target is unmet. Production
omission approval, family relevance, phone/WAN, concurrency, refresh/retirement
and activation remain separate. The later R61 request-local parsed-row cache
passed source checks but was not in this native package. See the
[phase comparison and next work](SEMANTIC_REQUEST_LATENCY.md).

## Earlier native baseline, October 21–22, 2026

The one-shot CPU qualification completed in **1,427.812 seconds** under the
1,800-second / 8 GiB / four-process Job. Both full index audits passed and took
985.121 seconds in total; they verified vector/metadata payloads and original
stat identities without rehashing original media bytes. The synthetic catalog
retained 23,761 entries: 23,696 ready vectors and all 65 reviewed omissions.
All **15 protection checks** passed, with zero individual NPY query reads.
Nine English/Chinese/mixed loopback HTTPS/TCP samples measured **14.516 seconds
median / 17.281 seconds maximum**; the cold request took **24.984 seconds**.
Sixteen model encodes took 2.192 seconds total (about 137 ms average).

The new request profiler recorded these median warm-sample phase totals. Values
are nested; exclusive time excludes instrumented child phases. Per-phase medians
do not necessarily sum to the median request.

| Phase | Calls per sample | Inclusive time | Exclusive time |
| --- | ---: | ---: | ---: |
| Source extension | 3 | 6.124 s | 3.983 s |
| Bounded source reads and packing | 27 | 2.088 s | 2.088 s |
| Artifact selection/validation | 1 | 1.366 s | 1.366 s |
| Bulk snapshot | 2 | 1.955 s | 1.955 s |
| Eligibility validation | 3 | 0.817 s | 0.817 s |
| Canonical hashing | 23,774 | 1.013 s | 1.013 s |
| Encoder round trip | 1 | 0.384 s | 0.384 s |
| Ranking | 1 | 5.445 s | 1.752 s |

Independent Windows readback verified all 11 staged input pins, the exact
reviewed omission document, full-catalog counts, all checks, warmup and nine
request-profile ordinals, both audit calls, measurement hash and Job proof.
No candidate process or test-port listener remained. Postflight retained the
production API task/action/entry/config/listener and phone/TV feed pins. A fresh
read-only production comparison still matched all frozen catalog rows and hashes.
The Windows execution window was released after verification.

Semantic remains **OFF**. No production policy was installed and no index,
configuration, account, service, task or feed was changed. The socket guard and
observed loopback transport are qualified; no OS-firewall claim is made.
These are synthetic-account/catalog loopback measurements using real existing
model/vectors, not family-caption relevance, phone/WAN, concurrent-load or
service-SLO acceptance. The 2-second backend target remains unmet. No controlled
speedup ratio is claimed against the older ready-only run: catalog/policy and
workload differ, and observer overhead is included.
