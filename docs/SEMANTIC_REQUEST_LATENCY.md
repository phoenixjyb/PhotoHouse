# Protected semantic request latency

Semantic remains **OFF**. The latest full-catalog Windows CPU qualification at
`e85c6e4` passed all **15 protection checks**. Nine English/Chinese/mixed loopback
HTTPS/TCP requests measured **7.860 seconds median / 8.328 seconds maximum**;
the cold request took **14.843 seconds**. The 2-second backend target remains unmet.

The earlier same-catalog baseline at `a46d9f5` measured 14.516 seconds median,
17.281 seconds maximum and 24.984 seconds cold. The observed warm median fell
by 6.656 seconds (about 46%). These are separate instrumented runs on the shared
host, not a randomized benchmark or phone/WAN measurement. Both retain 23,761
catalog entries, 23,696 vectors, 65 qualification-only omissions and the same
15 protection cases. See the [native record](SEMANTIC_PARTIAL_CATALOG_QUALIFICATION.md).

The latest median warm phases identify the remaining costs:

| Phase | Calls | Inclusive | Exclusive |
| --- | ---: | ---: | ---: |
| Source extension | 2 | 2.203 s | 0.915 s |
| Source SQL and packing | 18 | 1.185 s | 1.185 s |
| Prepared facts | 2 | 1.086 s | 0.938 s |
| Artifact selection | 1 | 0.048 s | 0.048 s |
| Bulk snapshot | 2 | 1.254 s | 1.254 s |
| Eligibility validation | 2 | 0.504 s | 0.504 s |
| Canonical hashing | 23,770 | 0.572 s | 0.572 s |
| Encoder round trip | 1 | 0.406 s | 0.406 s |
| Ranking | 1 | 3.520 s | 1.755 s |

These are nested per-phase medians and must not be added. Sixteen model encodes
took 2.300 seconds total, about 144 ms each; encoder transport time is separate.
Both mandatory full index audits took **1,119.002 seconds** of setup. The complete
canary took 1,409.515 seconds; that setup duration is not interactive query latency.
Independent readback verified input pins, audits, measurements and zero remaining
test processes/listeners. Live API/gateway/site/task/feed pins and the catalog
were unchanged; all 69 furniture-report assets passed before and after the run.
No production policy, vector publication, service deployment or activation occurred.

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

Semantic remains **OFF**. The new source, together with the already merged
R61/R62 changes, still needs a newly frozen native qualification on matching
catalog, policy, model and workload pins. The latest verified native timing
remains the `e85c6e4` result above; no newer native latency is claimed here.

The next measured priorities are ranking CPU work, both protected bulk snapshots,
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
