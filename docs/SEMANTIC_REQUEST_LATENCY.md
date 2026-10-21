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

All three fresh source/policy passes, per-row cancellation checks, candidate/source
hash checks, both bulk-file snapshots and final authorization remain. The bulk
file is still securely reopened and hashed around encoding. Ordinary discovery
and older strict configurations keep their existing behavior.

Generated regression checks include a changed row after policy validation, a
failed next source read, a changed expected model identity before bulk I/O,
changed/invalid warm hash inputs and bounded cache size. The loader's 23,761-row
microbenchmark verifies identical complete outputs and halves full validation
calls from 47,522 to 23,761. Timing this loop on a shared Mac does not establish
end-to-end or native request improvement. Native qualification of these changes
and a complete integrated API receipt remain pending.

## Qualification and remaining work

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
