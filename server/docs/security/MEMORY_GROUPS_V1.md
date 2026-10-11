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
