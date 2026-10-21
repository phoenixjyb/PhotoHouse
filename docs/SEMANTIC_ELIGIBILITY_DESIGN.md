# Semantic eligibility and visible coverage

Status: implemented in local source, October 21, 2026; runtime qualification is
pending. Semantic search remains OFF. This implementation does not approve the
family index's omissions, publish an index, enable a provider or change ordinary
discovery. Refresh, swap and retirement below remain future requirements.

## Why this is needed

The completed candidate has 23,696 ready vectors and 65 recorded failures across
23,761 frozen photos. The current semantic reader correctly refuses a candidate
set containing an image without a compatible ready vector. The performance
canary builds its synthetic catalog from ready records only, so a successful
benchmark cannot establish how production's failed inputs are handled.

`ReviewedIndex.scope_ids` must match the full current discovery source. Its
`indexed_ids` control metadata availability, not semantic-only eligibility;
media-only search still iterates the complete source. Narrowing these fields
would alter ordinary discovery or invalidate its source receipt. The policy
therefore applies only inside semantic search.

## Reviewed policy contract

Optional semantic configuration version **5** preserves versions 1–4 and their
existing strict behavior. It adds `eligibility`, exactly `{path,file_sha256}`,
to version 4's owner-only bulk runtime. The separately pinned private document
is read only after owner authorization. Loading or building a candidate does not
manufacture a review attestation.

The document has exactly `format_version` (1), `operator_reviewed` (true),
`library_id`, `binding_sha256`, `bulk_sha256`, `index_evidence_sha256`, `eligible`
and `omitted`. The joint binding pins both model identities; the bulk hash pins
the complete ready-artifact payload. The full ID/source-SHA partition must match
the deterministic current active-image roster on every request. Each image is
in exactly one of:

- Eligible: current asset ID and catalog source SHA, plus the exact reviewed
  ready record ID (`{asset_id,source_sha256,record_id}`). The bulk cohort binds
  the full artifact metadata.
- Omitted: current asset ID and catalog source SHA, an allowed failure reason
  and pinned failure evidence (`{asset_id,source_sha256,reason}`). Allowed reasons
  are `preparation_unavailable` and `source_missing`. A missing original's catalog
  SHA remains bound even when no observed original-byte SHA exists. The evidence
  hash is an operator attestation; this loader does not independently reopen or
  diagnose failed originals.

The private document is limited to 16 MiB and 100,000 images, with at least one
eligible image. Strict JSON, current private permissions, canonical non-aliasing
paths, single-link regular files and stable open/read/final identities are checked
on every read. Reads reserve bytes before I/O and observe the request's deadline
and cancellation; the separate aggregate policy allowance is 64 MiB per request.
No duplicates, foreign IDs, unknown omissions or silently unindexed images are
allowed. An omitted image remains available to ordinary search and existing media
access rules. Omission is not deletion, identity review or permission to weaken
people, date, location, literal-text or exclusion conditions.

The partition binds image membership and source hashes. Normal discovery still
rechecks its complete current source, reviewed identity layer and hard filters.
The eligibility descriptor also enters the opaque semantic request binding,
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

Return optional `semantic.coverage_details` with exactly `version` (1),
`policy_sha256`, `state`, `catalog_images`, `searchable_images`, `omitted_images`
and `matched_omitted_images`. State is `partial` whenever the library has any
omissions, even if the current filters match none. Searchable plus omitted must
equal catalog images; candidate count cannot exceed searchable images. Web and
Android validate these closed fields and bounds. Chinese/English workspace
replies disclose global and filtered omissions. Empty results under
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

## Checks and remaining pilot gates

Generated checks cover complete and partial policies, including 65 omitted images,
exact partition/source/model/library binding, duplicate and unknown omission
refusal, and unchanged legacy configuration behavior. Ordinary literal search
retains all 65 generated omissions. Endpoint tests cover hard filters, empty
eligible subsets, corrupt bulk refusal even for empty subsets, policy/source/
membership changes, page receipts, bilingual disclosure and no-inference recovery.
Source `7be2f7b` passed the complete API profile: **2,891 tests / 3,703 subtests**
plus the generated no-listener demo, with unchanged revision and profile inputs.
All seven isolated archive checks passed; the new module is included in the
explicit API package and imported without checkout fallback. Web wire validation
passed **22 tests**; all **1,157 live-core JVM tests in 95 suites** passed. The
generated coverage browser journey passed **nine checkpoints**; the unchanged
legacy journey passed **eight**. Chinese/English full disclosure paragraphs were inspected
at desktop and 390-pixel / 150% text sizes without horizontal overflow. These
checks use synthetic identities/photos, generated vectors and a mock encoder;
they do not establish native or family relevance, latency or physical-device
acceptance.

To repeat the optional coverage Web journey, run
`PH_SCENE_COVERAGE=1 node server/tests/security/test_assistant_scene_browser.cjs`
with the existing documented browser/Python/artifact environment. The private
bridge creates its owner and reviewed policy only in a disposable synthetic DB;
the ordinary journey still tests the legacy configuration without this flag.

The family policy still needs an explicit review and private preparation, followed
by bounded native qualification against a catalog retaining the omitted assets.
Qualify generation refresh, removal/retirement and rollback
without changing originals or silently deleting failed evidence.

After source and native checks pass, prepare an activation proposal with the
exact owner, library, generation, disclosed omissions, provider lifecycle and
rollback. Broad family relevance and phone/device acceptance remain separate.
See [the readiness record](SEMANTIC_LIBRARY_SCALE.md#completed-index-and-lifecycle-qualification--october-21-2026)
for measured evidence and remaining gates.
