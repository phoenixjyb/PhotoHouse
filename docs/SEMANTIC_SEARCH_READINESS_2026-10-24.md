# Semantic search readiness — October 24, 2026

Semantic search remains **OFF**. The current source candidate is not deployed
or qualified on Windows. This checkpoint separates the earlier native result
from the later source improvements; it does not authorize activation.

| Evidence | Result and limit |
| --- | --- |
| Latest complete protected Windows run | R68 on `13a94dd`: both full audits and all 15 protection checks passed. Nine warm HTTPS requests measured 8.000 s median / 8.438 s maximum; cold request 15.594 s. The 2 s backend target remains unmet. |
| Later application candidate | `c01758491b87c6e2a7fb3f8bfff66d949df8e2c2`, including the subsequent ranking and artifact-copy work. No complete Windows run of this candidate exists. |
| Focused source validation | 122 unique cases across overlapping field-copy, semantic search and streaming checks. The 70 focused cases also passed on both Python 3.12 and 3.14. This is not a new full API-suite result. |
| Generated complete-request comparison | 23,696 eligible vectors plus 65 omissions; 18 measured requests in nine alternating English/Chinese/mixed pairs. Full responses and every ranked ID/score bit matched. Mean 2.775 s versus 2.987 s; maximum did not improve. Generated data and a fixed encoder fixture do not establish family relevance or native latency. |
| October 24 Windows preparation attempt | Only a private metadata directory was allocated. The local coordinator stopped before preparing the next phase request. No source upload, model start or native qualification occurred. |
| Owned scope closure | The completed allocation transport exited normally. Its captured streams and exact source/arguments were reaccepted, followed by more than 121 s without access and a fresh complete local owned-process audit. Release covers that transport only; the empty private directory and original evidence are retained. |

The preparation stderr also contained PowerShell first-use progress, beyond the
strictly allowed SSH advisory. That capture does **not** pass qualification's
stderr rule. Normal process closure and qualification acceptance are separate
results; the limited release does not waive that failure or establish whole-host
preservation.

Follow-up source proposals passed 12 real-driver regression checks and seven
progress-suppression checks, with independent source review. An isolated
four-phase integration check also exercised the actual central grant issuer,
request helper and phase driver against temporary state and a fake execution
backend. It reproduced the old missing-request failure, then verified matching
request hashes and one fake execution per phase after correcting the ordering.
The helper refuses the consumed operation. These are local regression results;
a newly bound operational successor and Windows verification are still pending.

## Before another full Windows run

1. Integrate the reviewed request-before-grant proposal into a fresh operation. Each
   next request must bind the current completed prefix and result chain, without
   dispatching a phase or creating its claim before admission.
2. Prevent PowerShell startup progress at its source in a newly reviewed
   allocation wrapper. Preserve the failed capture and the existing strict
   stderr rule. Do not modify or replay the consumed operation.
3. Prepare a fresh operation with the exact reviewed application archive and
   operator source. Obtain current central admission and preservation/runtime
   observations, including the report publisher, with enough time for the full
   run and owned cleanup. Earlier holds and baselines are historical.
4. Complete both audits, all 15 protected cases, nine English/Chinese/mixed
   HTTPS samples, independent result readback, postflight preservation and
   owned closure under the existing resource and time limits. A slow but
   otherwise complete run must report the latency failure.

## Before enabling semantic search

The native performance target still needs to pass. Family-library relevance,
coverage and the production treatment of omissions need their own acceptance;
the 65 omissions were approved only for isolated qualification. Current-source
release checks, reviewed runtime configuration and an explicit owner-only
activation/rollback decision remain separate gates. Android delivery and
physical-device acceptance also remain separate from an API or local fixture
result. No source benchmark or coordination release enables serving.

For measurements and preserved behavior, see the
[latency record](SEMANTIC_REQUEST_LATENCY.md),
[exact field-copy comparison](SEMANTIC_ARTIFACT_FIELD_COPY.md),
[exact-product ranking note](SEMANTIC_EXACT_PRODUCT_RANKING.md), and
[full-catalog qualification record](SEMANTIC_PARTIAL_CATALOG_QUALIFICATION.md).
