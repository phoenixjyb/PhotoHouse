# Shared memory groups v1

## Product behavior

An original family note belongs to its original photo and author. A private
memory group links that note to an ordered set of up to 24 photos or videos in
the same library. It stores source IDs, theme, membership and exclusions; it
does not duplicate text, audio, authorship or captions. Editing the original
changes subsequent group reads. Deleted or moved sources are omitted. A
withdrawn or moved group member makes the entire group unavailable.

The Web photo viewer has a collapsed group panel. Creating a group, linking
notes, including media and saving are explicit actions. Users can add or remove
media and choose a theme. Removed suggestions remain excluded on refresh and
after saving. Group sources show their original attribution. An uncertain save
retains the exact mutation ID and body for retry; no draft is stored in browser
storage. Library/account/session changes discard late responses and private UI.

## Suggestions

The operator must explicitly enable the feature and supply a prepared vector
root and exact `VectorSpaceIdentity` using `GroupVectorConfiguration`. The
private staging JSON accepts `memory_groups_enabled`, `memory_group_vector_root`
and `memory_group_vector_identity` (artifact/preprocessing SHA-256, vector-space
ID, model version, dimension, normalization). Manual groups may omit both vector
fields; partial profiles are refused. The vector root can be the derived root,
a child of it, or a separate private directory, and cannot overlap originals,
incoming files, OTA files or private journals. Lookup
does not invoke inference or use the global index. Default settings remain off.

Every image seed and candidate is currently active and mapped to the library.
The reader validates the full bounded cohort, source digest, checkpoint,
preprocessing, version, dimension, normalization, file and component checksums
before scoring. It refuses corrupt, mixed or oversized cohorts rather than
ranking an ID prefix. Limits: 24 seeds, 512 candidates, 4096 dimensions, 20
suggestions, and no more than 24 members including seeds.

Default proposal rules require cosine similarity of at least 0.9 and recorded
capture timestamps within six hours of an explicit anchor. Aware timestamps
compare instants; naive timestamps compare wall time; mixed precision/timezone
pairs are not guessed. Date-only records can match their written calendar day.
Missing or invalid capture metadata does not use filename or upload dates.
Time eligibility is applied before ranking. Matches remain anchored to explicit
seeds, with no transitive expansion or claim about the actual activity, people
or place. Video membership is manual until a video vector contract is qualified.
These defaults are heuristics, not family-confirmed event boundaries.

## Protected API

All routes require current library access. Cookie writes require origin and
CSRF validation; native bearer requests use the existing admission contract.

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/memory-groups/capabilities?library=…` | Availability and edit/suggestion capabilities |
| POST | `/memory-groups/proposals?library=…` | Read-only time and visual candidates |
| GET | `/assets/{id}/memory-groups?library=…` | Bounded complete groups for this asset |
| GET | `/memory-groups/{id}?library=…` | Current group and dynamically hydrated notes |
| POST | `/memory-groups?library=…` | Explicitly create a group |
| PUT | `/memory-groups/{id}?library=…` | Revision-checked manual adjustment |

Proposals accept string fields `asset_ids` and `excluded_asset_ids`, canonical
CSV IDs. Saves accept exactly `asset_ids`, `excluded_asset_ids`,
`source_story_ids`, `theme`, `revision`, `mutation_id`, all strings. Up to 512
exclusions and 12 source-note UUIDs are allowed. Included/excluded IDs are
disjoint. Every source must currently belong to an included asset in this
library. Owner or creating contributor can edit; viewers can read. Saves use
revision comparison and actor-bound idempotency in the same write transaction
as authorization and membership validation.

Responses have a 1 MiB ceiling and return no vectors, source filesystem paths
or model identities. Per-asset listing examines at most 64 matching groups,
returns up to eight complete groups, and reports `has_more` for further or
uninspected matches. It does not return partial groups or truncate original prose.

## Schema and delivery gates

Additive migration `e7c1a9d5b304` follows `d1f6a8c3e920`. It creates
`access_memory_groups` and `access_memory_group_revisions`. Startup does not
migrate. Downgrade refuses if either table contains records; restoration of a
reviewed backup is a separate operator operation. Existing older revisions
remain supported with groups unavailable.

Local synthetic tests cover the pure rules, protected loader/routes, source
revision/deletion behavior, ownership, CSRF, idempotency, scope withdrawal and
migration preservation. Windows qualification must check the migration and
backup restore, the companion upload-worker package, current image-vector
coverage and producer provenance. Live activation, phone release and family
acceptance remain separate. The existing capture-day picker stays available.

The phone now has a default-off source implementation of the same review/edit
workflow; see [its contract](../../../docs/PHONE_MEMORY_GROUPS.md).
Next: carry deduplicated group references into story/editorial evidence. Group membership does not yet
generate an essay or rewrite notes automatically.

## Generated upgrade qualification

The pinned API package includes `scripts/qualify_memory_groups.py`. It accepts
only `--out <new-absolute-directory>` beneath an existing private parent, with
no database, media, model or service argument. It generates the actual d1 schema,
synthetic accounts/session grants, photo/video metadata, caption, upload receipt,
pending task and an original note. It checks an injected interruption between
the two e7 table creations rolls back DDL and the revision; then verifies a
successful additive upgrade preserves every existing generated table row and
schema object. No authored text is backfilled into groups.

Explicit group operations check original attribution/latest wording, viewer
write denial, revoked read denial, manual exclusions and retry after a later
edit. Separate copies restore both the pre-group d1 backup and the e7 backup
containing original notes, group state and revision history. Both backup digests
stay unchanged. Current-row and deliberately orphaned audit-only fixtures each
refuse downgrade without losing their stored history. The audit-only fixture is
intentionally foreign-key-invalid and is retained separately; it is not a
restored healthy database or a supported application state.

On Windows, the CLI starts an isolated child in a Job capped at 15 minutes,
2 GiB memory and four processes, with an 8 GiB free-RAM admission floor. It
requires inherited private Windows ACLs, checks UTF-16 path/sidecar budgets
before creating files, and validates the complete bounded success report.
Failures retain a sanitized phase/class/Windows-code receipt where possible.
It changes no existing ACL or service and cannot target the live database.

Portable source tests cover the generated cases and controller/refusal behavior.
The approved native Windows run passed at source `665bed5`; independent readback
verified the manifest, report and generated databases. See
[the exact native result](../../../docs/WINDOWS_CPU_CHECKS.md#october-11-memory-group-native-result).
This runner does not execute
upload workers, qualify the installed vector producer or coverage, make a live
backup, apply a live migration, or establish power-loss recovery. Use the
separate companion worker canary and approved live cutover plan for those steps.

## Full-chain maintenance preparation

The live source and schema are separate facts: an October 11 read-only query
found the primary at a0, with no optional b1/c2/d1/e7 tables. The
[guarded application tool](MEMORY_GROUP_SCHEMA_APPLICATION.md) requires the exact
reviewed starting revision and matching private offline backup. From a0 it adds
nine empty tables through e7 with no historical backfill; from d1 it adds two.
Its generated full-chain interruption and actual guarded apply are included in
the new companion-worker canary. Local tests and the earlier native d1 result do
not establish native acceptance of this guard, live maintenance or activation.

The new `18eb1cc` generated full-chain guard and actual CPU/video worker run
passed on Windows, followed by independent readback of both source packages,
all three databases, exact queues and decoded previews. See the
[bound native result](../../../docs/WINDOWS_CPU_CHECKS.md#october-11-full-chain-and-companion-native-result).
This does not activate the live schema, group routes, models or phone release.
