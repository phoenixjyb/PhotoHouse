# Proposed semantic eligibility and visible coverage

Status: design only, October 21, 2026. Semantic search remains OFF. This document
records the next source requirement; it does not approve omissions, publish an
index, enable a provider or change ordinary discovery.

## Why this is needed

The completed candidate has 23,696 ready vectors and 65 recorded failures across
23,761 frozen photos. The current semantic reader correctly refuses a candidate
set containing an image without a compatible ready vector. The performance
canary builds its synthetic catalog from ready records only, so a successful
benchmark cannot establish how production's failed inputs are handled.

`ReviewedIndex.scope_ids` must match the full current discovery source. Its
`indexed_ids` control metadata availability, not semantic-only eligibility;
media-only search still iterates the complete source. Narrowing these fields
would alter ordinary discovery or invalidate its source receipt. The proposed
policy must therefore apply only inside semantic search.

## Reviewed policy contract

Use an explicit optional semantic configuration version, preserving versions 1–4
and their existing strict behavior. The new policy would require an owner-only
bulk runtime and a separately pinned private eligibility document. Loading or
building a candidate must not manufacture a review attestation.

The document should bind one library, image/text model identities, completed
index evidence, bulk descriptor and a deterministic active-image cohort digest.
It must partition every current image into exactly one of:

- Eligible: current asset ID and catalog source SHA, plus the exact reviewed
  ready artifact identity/record ID.
- Omitted: current asset ID and catalog source SHA, an allowed failure reason
  and pinned failure evidence. A missing original's catalog SHA remains bound
  even when no observed original-byte SHA exists.

No duplicates, foreign IDs, unknown omissions or silently unindexed images are
allowed. An omitted image remains available to ordinary search and existing media
access rules. Omission is not deletion, identity review or permission to weaken
people, date, location, literal-text or exclusion conditions.

The active-image digest should bind image membership and source hashes rather
than falsely freezing unrelated metadata forever. Normal discovery must still
recheck its complete current source, reviewed identity layer and hard filters.
The eligibility descriptor must also enter the opaque semantic request binding,
including paging and trusted conversation recovery.

## Request behavior

Authorize the exact configured owner and library before reading policy, vectors
or provider data. Validate the full policy partition against the complete current
active image source and ready artifacts on every request. Filtering to a small
result set must not conceal a stale global cohort. Unknown additions, removals,
source changes, incompatible artifacts, changed policy bytes, unsafe paths or
corrupt bulk data refuse before inference; a warm cache cannot bypass these checks.

Apply the existing hard filters and unsupported-condition clarification rules.
Then select eligible candidates for ranking while retaining coverage information
for omitted candidates. Recheck membership, source and policy before releasing
results. Do not use a narrower global discovery provider or fabricate scores for
omitted images.

Return an explicit coverage object with a policy receipt, complete/partial state,
current authorized image count, searchable count and omitted count. Also disclose
when the current filtered request has omitted candidates. Empty results under
partial coverage must mean no matches in the searchable subset, rather than no
matching photo exists in the library. Keep private paths, source hashes and
failure traces out of user-visible responses.

Suggested user text, with current counts as an illustration rather than a fixed
runtime value:

- 中文：语义检索覆盖 23,696 张照片；65 张尚未建立索引。这些照片仍可通过普通搜索查找。
- English: Semantic search covers 23,696 photos; 65 are not indexed yet. You can
  still look for those photos using ordinary search.

## Refresh and retirement

Build each replacement generation in a fresh private location and validate it
fully before selecting it. Preserve the old generation until the new generation
and rollback are qualified. Never overwrite a serving bulk file in place or
mutate append-only vector rows to make a stale cohort appear current.

A new catalog generation needs explicit handling of added, deleted, changed and
retired artifacts. Unknown or duplicate ready metadata must continue to refuse.
The existing artifact schema and erasure rules need a reviewed retirement design;
a coverage document alone is not a refresh, atomic swap or deletion workflow.
Production data changes and rollout remain separately authorized operations.

## Acceptance checks before an owner-only pilot

Use generated complete and partial catalogs, including a 65-missing-shaped case.
Verify exact partition/source/model/library binding, duplicate and unknown
omission refusal, and unchanged legacy configuration behavior. Confirm that
ordinary literal discovery still sees the full authorized roster.

Exercise people/date/text filters, zero matches with omitted candidates,
English/Chinese coverage text, page binding and conversation recovery. Inject
membership/source/policy changes during encoding and stale-cache reuse; no old
cards may escape. Qualify generation refresh, removal/retirement and rollback
without changing originals or silently deleting failed evidence.

After source and native checks pass, prepare an activation proposal with the
exact owner, library, generation, disclosed omissions, provider lifecycle and
rollback. Broad family relevance and phone/device acceptance remain separate.
See [the readiness record](SEMANTIC_LIBRARY_SCALE.md#completed-index-and-lifecycle-qualification--october-21-2026)
for measured evidence and remaining gates.
