# Protected semantic request latency

Semantic remains **OFF**. The [full-catalog native baseline](SEMANTIC_PARTIAL_CATALOG_QUALIFICATION.md)
at `a46d9f5` passed all 15 protection checks but measured 14.516 seconds median
and 17.281 seconds maximum across nine loopback HTTPS/TCP requests. The cold
request took 24.984 seconds. The 2-second backend target remains unmet.

The request profiler identifies repeated metadata work as a useful first target:
source extension took 3.983 seconds exclusive across three fresh reads; artifact
selection/validation took 1.366 seconds; two bulk snapshots took 1.955 seconds.
These are nested median phase observations, not independent additive budgets.

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
and 3,703 subtests, plus the generated demo. Native qualification of the performance changes remains pending.

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
Native latency measurement remains required before claiming an interactive gain.

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
Native performance qualification remains pending, separate from the R58 receipt.

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
