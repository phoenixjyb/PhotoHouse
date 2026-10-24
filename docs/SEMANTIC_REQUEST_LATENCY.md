# Protected semantic request latency

The [October 24 readiness checkpoint](SEMANTIC_SEARCH_READINESS_2026-10-24.md)
separates the current undeployed source candidate, the latest complete native
measurement and the allocation-only preparation failure. Semantic remains OFF.

The [exact artifact field copying note](SEMANTIC_ARTIFACT_FIELD_COPY.md) records
a later source-only optimization and an alternating complete-request comparison
on generated data. Its mean local request time was 2.775 versus 2.987 seconds;
the 2-second target remains unmet, and Windows qualification is still required.

The [R80 exact-product source note](SEMANTIC_EXACT_PRODUCT_RANKING.md) records a
later local ranking optimization, its generated 23,696/40,000-row comparisons
and unchanged activation gates. It is not included in the Windows measurements
below; semantic search remains **OFF**.

Semantic remains **OFF**. The latest complete bounded Windows CPU qualification
(R68, October 23, exact code `13a94dd`) passed both full audits and all
**15 protection checks**. Nine English/Chinese/mixed loopback HTTPS/TCP requests
measured **8.000 seconds median / 8.438 seconds maximum**; the cold request took
**15.594 seconds**. The 2-second backend target remains unmet.

The prior successful `e85c6e4` run measured 7.860 / 8.328 / 14.843 seconds
respectively. The earlier `a46d9f5` baseline measured 14.516 / 17.281 / 24.984.
These are separate instrumented runs on a shared host, not a randomized benchmark
or phone/WAN measurement. The latest run does not show a further query-latency
improvement. All retain 23,761 catalog entries, 23,696 vectors, 65
qualification-only omissions and the same 15 protected cases.

The latest nine warm samples identify the remaining costs:

| Phase | Calls | Inclusive | Exclusive |
| --- | ---: | ---: | ---: |
| Source extension | 2 | 2.081 s | 0.718 s |
| Source SQL and packing | 18 | 1.192 s | 1.192 s |
| Prepared facts | 2 | 1.355 s | 0.985 s |
| Artifact selection | 1 | 0.119 s | 0.119 s |
| Bulk snapshot | 2 | 1.011 s | 1.011 s |
| Eligibility validation | 2 | 0.515 s | 0.515 s |
| Canonical hashing | 23,770 | 0.811 s | 0.811 s |
| Encoder round trip | 1 | 0.455 s | 0.455 s |
| Ranking | 1 | 3.485 s | 1.782 s |

These are nested per-phase medians and must not be added. The 16 model encodes
took 2.261 seconds total; encoder transport time is separate. The initial audit
took **957.516 s**, and the independent final audit took **282.750 s** (durable
phase wall times); bulk construction took 21.296 s and the canary phase 198.640 s.
The complete run took **1,582.750 s**. Setup cost is separate from interactive
query latency, and the two audits' different times do not establish a causal
source-change speedup.

Independent readback verified all 12 inputs, source identity, reviewed omissions,
measurement/sample ordinals, two audits, the closed 322-checkpoint journal and
8 GiB/four-process Job limits. Owned test Python processes/listeners were zero.
Fresh postflight kept the live API, stores, task states, catalog, models/index,
permissions and policy unchanged. All 83 preservation pins, 12 retained report
trees and 200 current report assets passed, including trusted HTTPS. No production
deployment, vector publication, family relevance acceptance or activation occurred.
See [the native record](SEMANTIC_PARTIAL_CATALOG_QUALIFICATION.md#latest-complete-native-result-october-23-2026).

## Local validation improvements

Current development removes duplicate pure work without reusing a prior source
read's authority or policy decision:

- A database artifact row is parsed and completely validated once against its
  expected identity. The standalone parser still validates its own identity.
  Wrong identities, malformed metadata and duplicate assets continue to refuse.
- For bulk serving with eligibility, each fresh source extension validates its
  complete current cohort and policy. Artifact selection reuses that generation's
  validated map only when every selected row and the current model identity
  digest match the copied snapshot. The generation clears before every new read,
  including failures. A mismatch refuses before inference.
- The canonical model-identity digest memoizes at most 128 exact primitive-field
  tuples, including its format version. Strict field/type validation runs on
  every call. The canonical JSON/hash and historical persisted digest remain
  unchanged. Artifact IDs, source hashes, policy/approval, file and permission
  state never enter this pure computation cache.

Each ranking pass retains full fresh source/policy validation, per-row cancellation
checks, candidate/source hash checks, both bulk-file snapshots and final authorization. The bulk
file is still securely reopened and hashed around encoding. Ordinary discovery
and older strict configurations keep their existing behavior.

Generated regression checks include a changed row after policy validation, a
failed next source read, a changed expected model identity before bulk I/O,
changed/invalid warm hash inputs and bounded cache size. The loader's 23,761-row
microbenchmark verifies identical complete outputs and halves full validation
calls from 47,522 to 23,761. Timing this loop on a shared Mac does not establish
end-to-end or native request improvement. The R57 API receipt passed 2,922 tests
and 3,703 subtests, plus the generated demo. The combined R60 native result above now measures these changes.

## Bounded source-read accounting

The full-catalog baseline also spent 2.088 seconds in source SQL and packing
across 27 reads. R58 preserves the exact sum of canonical JSON row byte sizes,
but eligible chunks use one serialization instead of one per row. A nonempty
chunk of N tuple rows adds exactly N+1 outer-list bytes; those bytes are removed
from the measured size. No database or source state is cached.

Before allocating the serialized chunk, a conservative bound requires at most
128 rows, 32 exact builtin cells per row, and the smaller of the remaining source
budget and 2 MiB. Unicode strings include the worst-case ASCII escape expansion;
integers are limited to SQLite's signed 64-bit range and floats must be finite.
Unsupported or larger chunks use the original per-row path. The actual byte
limit, row limit, cancellation cadence and shared admission slots remain intact.
Regression checks compare exact bytes for Unicode, control characters and numeric
boundaries, exercise real SQLite at exact and one-byte-short budgets, and retain
binary/nonfinite errors and cancellation. Source `e37c97c` passed the integrated
API profile (2,969 tests / 3,717 subtests plus the generated demo), ten archive
checks, the nine-checkpoint partial-coverage browser journey, and the integrated
photo-stack browser journey. Source stayed unchanged during the API receipt.
The Chinese/English phone disclosures were inspected at 390 pixels and 150% text.
The combined R60 native result above measures the later integrated source.

## First-page binding in the ranking read

R59 removes the separate binding-only source read for a new unbound first page:
exact integer page 1, no fingerprint and no server-owned recovery snapshot. The
ranking transaction derives its current binding after complete source, cohort and
eligibility validation. The final fresh source/policy read and exact-owner
authorization still precede release. This reduces that path from three complete
source reads to two without changing the binding or fingerprint format.

A private search-action factory preserves ordinary discovery's supplied-binding
requirement. Supplied bindings, fingerprint and pagination cases, and trusted
conversation recovery keep their existing paths. The refusal path captures the
ranking generation's binding before inference; even a provider's unsupported-query
response must pass a final comparison against that binding. A missing captured
binding fails closed. Mid-request source or membership changes still withhold cards.
Generated tests verify source-read counts, identical current binding/fingerprint,
provider and heuristic refusals after mutation, retained page guards and recovery
without another model call. Source `265034e` passed the integrated API profile:
2,989 tests / 3,717 subtests plus the generated demo, with unchanged source. All
ten archive checks and the nine-checkpoint partial-coverage browser journey passed.
The first integrated run caught a profiler assertion that still expected three
policy validations; the corrected contract requires ranking plus final validation.
The combined R60 native result above supersedes this milestone's pending timing status.

## Qualification and remaining work

R60 additionally bounds pure identity grammar validation to 128 copied primitive
tuples. Each call still checks the exact identity type and current field types,
lengths and ranges before looking up regex validity. Oversized values, subclasses
and boolean dimensions bypass the cache and refuse. Mutation produces a new key;
artifact metadata, source hashes, files, permissions and eligibility are never
cached by this change. Focused tests compare complete cached and uncached endpoint
responses and exercise mutation, invalid values and eviction. A generated
4,098-candidate local experiment suggested a modest improvement; it is separate
from native qualification and does not establish the 2-second target.

R61 adds a separate request-local parsed-row cache. Every pass still performs
fresh artifact/source-hash SQL, schema/identity checks, policy file reading and
validation, byte charging and final authorization/source checks. Only an exact
library, identity digest and typed ordered row match reuses immutable primitive
field tuples. Each pass reconstructs fresh artifact objects; mutable instances
never enter the cache. Failure/cancellation clears both exposed state and cache.
Focused tests verify two SQL pairs and two policy reads despite one parse, changed
rows/identity/source/policy refusals, cancellation and prior-object mutation.
The full source API profile passed **2,999 tests / 3,727 subtests** plus the
generated demo with unchanged source during the receipt. Independent focused
review passed 55 tests. **R61 is not part of the measured e85c6e4 native run**;
its native latency and memory impact remain unqualified.

R62 separately fixes a warm bulk-store metadata alias: its cache key now copies
all 16 artifact fields into immutable primitive tuples rather than retaining
artifact-object references. A grammar-valid mutation must refuse on both warm
and cold stores. Restoring exact metadata may reuse the verified matrix only
after a fresh secure file read. The 18-test bulk suite covers these cases and
unchanged exact ranking; ranking arithmetic and file/header checks are unchanged.
The full API profile passed **3,000 tests / 3,732 subtests** plus the generated
demo, with unchanged source; independent related checks passed 33 tests. This is
a correctness fix, not a measured latency improvement. **R62 is also
outside the native e85c6e4 package** and needs native qualification.

## R63 exact warm-cohort metadata proof

R63 avoids repeating pure artifact grammar, duplicate and ordering validation
only when every current artifact has its exact class and all 16 current fields
are copied into exact builtin primitive tuples matching the previously validated,
ordered cohort. The pinned file, library and current model identity must match.
Identity is checked again after callbacks copy the fields. Any difference takes
the full validator/sort path; wrong types, duplicates, changed scope, identity
or metadata still refuse when they cannot match the pinned container.

Only the metadata proof is reused. Every snapshot still securely opens and fully
hashes the current bulk file, validates its header and complete cohort binding,
charges its bytes and checks cancellation. Source SQL, eligibility policy,
current permissions, the pre/post-encoder snapshots and final authorization are
unchanged. Cold canonical-matrix verification and exact `math.fsum` scores and
tie ordering remain unchanged. The cache stores copied primitives, never mutable
artifact references or an authorization decision. Downstream header, matrix and
ranking inputs are rebuilt as private copies of the captured primitive rows, so
later callbacks cannot change a snapshot through caller-held artifact aliases.

The focused storage/search/eligibility/coverage/profiler suites passed **69 tests
and 53 subtests**. Regression cases include all 16 wrong-type fields, boolean and
float integer aliases, callback-driven valid/invalid identity mutations, cloned
metadata, reordered cohorts, duplicates and unchanged secure file reads. A
separate generated 4,098-vector / 768-dimension Mac experiment recorded a warm
snapshot median of **49.16 ms before / 21.86 ms after**, with the identical exact
ranking digest. These are separate local runs, not a native end-to-end speedup
or service-SLO claim. A generated 4,163-entry canary, including 65 synthetic
omissions, passed all 15 protection checks with a synthetic encoder.

The frozen R63 source passed the full local API profile: **3,346 tests / 4,037
subtests**, plus the generated no-listener demo. An earlier run hit a positive-
control 503 and was interrupted; that isolated suite then passed 8 tests / 113
subtests and the full recheck passed. No timeout or refusal gate was loosened.

The new source, including merged R61/R62 changes, was packaged as an independently
attested 293-file candidate and attempted once on the matching Windows model,
index, snapshot, 23,761-row catalog and query workload. The child hit its fixed
1,800-second Job deadline; the coordinator recorded `process_timeout` and exited
unsuccessfully. Retained artifacts show index preflight and bulk/eligibility/
synthetic-database preparation were reached. They do not establish which phase
consumed the remaining time. No completed measurement or phase profile survived,
so no partial timing or protection result is accepted as qualification.

Fresh postflight preserved all 106 task definitions, 28 runtime identities,
55 preservation-file pins, 293 live API files, four read-only stores, model and
index pins, the unchanged current catalog, private ACLs and phone v75 / TV v30.
All 125 furniture assets passed trusted-TLS verification before and after. The
independent observer found zero owned candidate processes. No test-port record
survived; direct per-port readback is therefore unavailable. The exact full
Python-process roster and the bounded Job cleanup provide process-level closure.
No production policy, service, task, database, media or index publication changed.
After 272 seconds of conservative offline cleanup, both active sessions received
explicit Windows release at 2026-10-22 16:42:20 Asia/Shanghai (08:42:20 UTC).

Semantic remains **OFF**. Native qualification of this increment is **failed**,
not pending acceptance or ready for deployment. At that checkpoint, the latest
verified native timing was `e85c6e4`; the later complete R68 result is recorded
at the top of this document.

The next qualification priority is durable aggregate phase checkpoints and
audit/setup profiling under the same bounded Job, so a timeout retains useful
progress without exposing queries, media paths or asset identifiers. Keep both
full audits and the fixed deadline; do not extend the timeout to manufacture a pass.
For interactive requests, the last successful profile points to ranking CPU work,
both protected bulk snapshots,
and fresh SQL/fact construction. The request-local metadata increment may save
only a fraction of the remaining gap. A synthetic Mac subphase experiment is not
an end-to-end speedup claim. Do not remove fresh policy/source/owner checks or
weaken file integrity to meet the latency target.

Freeze the committed source and exact candidate inputs before a new native run.
Use the same reviewed omission document only while index/snapshot/current-catalog
pins remain valid. Retain all 15 protection checks, three languages, cold/warm
samples, phase mapping, both complete audits and independent resource closure.
Compare matching catalog/policy/workload and include observer overhead. A change
in setup audit cost is separate from interactive request latency.

Coordinate each Windows execution window with the active grouping and AI-harness
sessions. This source work does not authorize production installation or activation.
Relevance, phone/WAN, concurrent load, refresh/retirement and a concrete owner-only
serving-policy proposal remain separate gates.

## R64 durable qualification diagnostics

The explicit library qualification call now accepts `profile_setup=True` and an
optional `checkpoint_directory`. Both default to disabled. The checkpoint path
must be a new private directory outside application source, the candidate index,
the reviewed input and the measurement output. A durable `initial_audit` start
is published before the first full inspection. Fixed phase boundaries cover
artifact validation, vector hashes, omission review, bulk construction, fixture
setup, scoped source projection, eligibility, model binding, the protected canary,
the final hashes/audit/review and report publication. Both complete audits remain.

The scoped setup observer counts and times JSON/checkpoint verification, source
stats, vector reads, bulk cohort/component/write/hash work, fixture construction,
source projection/digest and coverage validation. These are inclusive timings:
nested totals must not be added as independent costs. Counts represent operation
calls, not distinct assets. Fractional milliseconds are retained rather than
rounding each short operation before summation. The observer retains no inputs,
queries, paths, identifiers, database values, results or exception text, and
restores every patched alias when its explicit context exits.

Completed operations can emit a checkpoint at most once every five seconds.
Phase starts/ends are also forced checkpoints. There is no background writer:
an operation stalled inside native code leaves the last completed checkpoint and
its phase start. The private journal publishes complete fsynced files atomically
without overwriting earlier records, and caps output at 512 records, 16 KiB each
and 8 MiB overall, reserving one terminal record. Windows file fsync does not
establish power-loss recovery or portable directory durability. Reader validation
rejects malformed published records and ignores only bounded private temporary
remnants. `qualification_passed` is always false in diagnostic records.

An interrupted phase, missing terminal checkpoint or retained measurement alone
cannot qualify a run. In particular, a final checkpoint storage failure can leave
`measurement.json` while the call raises; independent acceptance must require the
successful worker/coordinator exit, complete journal, both audits, all 15
protections, nine matching English/Chinese/mixed samples, exact pins and resource
closure. Setup/audit costs are separate from interactive query latency. The
1,800-second child Job deadline and existing integrity checks are unchanged.
The single native R64 attempt on source `8fbffd8` reached the unchanged
1,800-second child deadline during `final_audit`; it was not replayed. Independent
readback verified the 12 frozen inputs, the exact 295 extracted source files plus
their manifest, and a strict valid prefix of 365 checkpoints. The last checkpoint
was still running, with no terminal close, completed measurement or final report.
The Windows generated checkpoint publication/collision smoke retained its three
records. This proves useful interruption diagnostics, not qualification.

Retained completed phase boundaries give:

| Phase | Duration | Evidence limit |
| --- | ---: | --- |
| Model load | 56.172 s | Separate start/completion marker, includes imports |
| Initial full audit | 1,238.686 s | Completed phase, both artifact passes |
| Bulk-vector construction | 19.171 s | Completed phase, 23,696 vector reads |
| Protected canary | 193.860 s | Phase completed; full result/report not retained |
| Final full audit | Interrupted | Last checkpoint at 1,741.907 s after journal start |

The canary duration includes many checks and requests; it is not a single-query
latency or evidence that every protection and sample passed. No new native
latency replaces the latest successful result above. Aggregate operation timings
are inclusive and nested. For example, `audit_json` includes its checkpoint
inspection; `audit_checkpoint_verify` labels calls to `inspect_checkpoint`, not
`verify_checkpoint`. Counts are function invocations, not distinct images. Each
full audit has a committed-batch artifact pass followed by a separate manifest
record pass; a partial counter must not be divided by two to infer coverage.

All 73 preflight pins, the 293-file live API, four stores, parent ACL, semantic-off
policy, model/index/snapshot and 23,761-row catalog evidence matched after the
attempt. A separate human-authorized publisher added a homepage and navigation
during the run, replacing the report task/process pair. Consequently the original
unchanged-baseline/TLS gate refused; its preflight was retained unchanged.
Separate checks verified the current 148-file report, its retained predecessors
and normal trusted HTTPS. The other 105 task definitions/enabled states matched;
a transient scheduled DNS-task state returned to its preflight state in the final
inventory. These observations do not establish an unchanged timed environment.
Owned candidate processes were zero. No test-port record survived, so closure
claims are limited to process scope and the final runtime inventory, not direct
per-port checks. No production deployment or semantic activation occurred.

Next, investigate repeated path/identity/hash/JSON checks within a single full
audit and qualify any immutable-artifact reuse with mutation/refusal cases.
Retain two independent complete audits and fresh file, source, membership,
policy, hash and canonical-vector checks; do not share a permissive cache across
audits or extend the deadline to manufacture acceptance. Semantic search remains
**OFF** until a complete protected run and the remaining activation gates pass.


## R65 audit artifact pass

`inspect_library_index` used to read and validate every metadata/vector artifact
while traversing committed batches, then repeat that work in its manifest-record
loop. It now checks every batch's complete structure, source identity and failure
semantics; exactly matches checkpoint records/failures to the manifest; validates
all directory/name coverage; and performs one artifact-verification pass using
the matched manifest. The remaining pass explicitly retains metadata digest,
source/identity/canonical path binding, vector checkpoint inspection and rehash,
the protected vector reader, canonical checksum and component validation.

This is not a cache. No verified result survives an inspection, file, request or
qualification phase. Both complete initial and final inspections remain, and the
writer/resume path retains its independent committed-artifact checks. The JSON
reader and vector checkpoint wrappers retain their existing repeated byte/hash
and stable-identity checks. One read/decode call is not one physical hash pass.

The focused suites passed 54 tests / four subtests, including corruption after an
independent audit, checkpoint/manifest tail disagreement before vector I/O,
canonical-but-stale metadata, jointly rebound incorrect identity/source/path/file
or component checksums, metadata/vector links, and source drift after checkpoint
validation. A generated 515-image comparison returned identical manifest,
artifact records and identities across three alternating baseline/optimized runs:

| Per-audit observation | Before | R65 |
| --- | ---: | ---: |
| Vector read/decode calls | 1,030 | 515 |
| JSON load calls | 1,098 | 583 |
| Checkpoint inspection calls | 2,128 | 1,098 |
| Mac median audit duration | 1,453.685 ms | 827.143 ms |

These model-free generated measurements do not establish Windows performance,
interactive request latency, relevance or full protected qualification. Keep the
1,800-second child limit, both complete audits, 15 protected cases, nine matching
samples, fresh current coverage/model/source/policy pins and independent closure.
The later R68 run completed native qualification of this exact source; semantic
search remains **OFF**.


### R66 transport checkpoint

Direct Windows SSH authentication, the fresh before-baseline and host admission
passed for exact source `13a94dd`. The single staging attempt reached the
unchanged 180-second SFTP deadline. Readback found ten exact small input files,
an incomplete source archive (1,827,840 of 5,272,648 bytes) and no final expected
input. There was no model load or native qualification attempt; the stage was
preserved without replay or deletion.

Fresh read-only closure found zero owned test processes, SFTP servers or recorded
test listeners. The private ACL and production configuration hash were unchanged,
semantic search was off, and preservation checks covered 83 pins, 293 live source
files, 12 report trees and the current 200 report assets. An independent review
and 195.63 seconds without host access preceded explicit resource release.

R67 compressed the identical 296 ZIP entries, including the source
manifest, from 5,272,648 to 1,412,632 bytes. The 295 source payload hashes and
manifest are unchanged. Its operator wrapper captures partial transfer output
and bounds cleanup of its own process group. This reduces transfer bytes; it
does not establish network throughput, query latency or native qualification.
R67 completed staging but refused a native start after its reserve cutoff. R68
then completed fresh admission, both audits, all 15 cases and nine samples using
the same source archive under the unchanged runtime limits. Semantic search
remains **OFF**.

### R65 validation and native admission status

The exact optimized code commit `13a94dd` passed the full generated-media API
check: **3,389 tests / 4,037 subtests**, plus the generated demo. The source stayed
clean and unchanged for the complete check. A 295-file runtime source archive
was matched to that commit and independently reviewed.

No R65 native qualification/model attempt or candidate staging occurred. The
read-only preparation retained its failed probes and successful baselines. It
correctly refused a transient scheduled-task state change; fresh host admission
subsequently passed after the task naturally returned to its prior state. A
local final-delta checker then incorrectly compared the current catalog row
revision with a distinct historical observations digest and refused before any
candidate write. The checker now binds each digest to its actual contract;
current roster/index/snapshot and the existing qualification-only 65-omission
review remain required. The rejected local seal and its exact control bodies
were retained rather than rewritten into a success.

The next R65 acquisition failed before connecting to the established SSH relay.
Neither failed probe started a remote reader. Its baseline, host admission and
reservation expired and were not reused as fresh authority. The public report
check at that checkpoint verified all 200 assets with normal certificates.

R66 later restored access through a verified existing-key direct route. R68
acquired fresh operation-specific coordination, baseline and host admission and
completed the bounded run reported above. The R65 failed probes remain evidence;
they are not native measurements or protection acceptance. The unchanged
child/parent/transport limits, both audits, 15 protections, nine samples,
independent readback and owned closure remained required. Semantic stays **OFF**.

## R69 bounded two-pass metadata reader

The inspector reads each canonical JSON document through one bounded descriptor
for parsing, canonical-byte comparison and hashing, then retains an independent
final `verify_checkpoint` digest/identity pass. Expected artifact metadata SHA
binds the same bytes. Before/open/after file identities, private ACL checks,
regular-file/link/reparse checks and size limits remain enforced. The writer and
resume reader is unchanged. Both complete audits and all source/vector checks
remain; neither permissions nor file state is cached.

Focused suites passed 41 tests, including growth during reading, replacement,
same-size restored-mtime mutation, canonical/duplicate/nonfinite/digest refusal,
link refusal and the final private-file gate. Independent source review found no
blocking regression. Exact code `c534805` passed 3,405 API tests / 4,037
subtests plus the generated demo with a clean, unchanged checkout. R68 measured `13a94dd`,
which does not include this reader. No Windows setup saving or interactive
latency gain is claimed for R69; the 2-second target remains unmet.
