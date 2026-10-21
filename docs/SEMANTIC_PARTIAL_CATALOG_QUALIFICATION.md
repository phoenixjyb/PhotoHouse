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
A full API receipt and native phase measurements are pending for this revision.
No speedup or activation readiness is claimed. See the
[eligibility contract](SEMANTIC_ELIGIBILITY_DESIGN.md) and
[library qualification record](SEMANTIC_LIBRARY_SCALE.md).
