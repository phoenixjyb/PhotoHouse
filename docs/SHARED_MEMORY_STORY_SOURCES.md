# Shared memories in story and memoir drafts

## Product behavior

A family member can tell a memory once, then explicitly share that original note
through an adjustable memory group. When a grouped photo or video is selected
for a story, its current shared notes are available alongside direct notes and
machine captions. The chapter keeps source IDs; the draft does not copy original
wording or author labels into saved content or revision history.

The original note's photo and voluntary byline remain its attribution. A shared
note may support several chapters or child stories, but the AI context includes
that canonical note once. Two separate authored notes remain separate even if
their wording matches. Sharing is context, not evidence that every linked frame
depicts the same event, person or activity. All generated prose remains a proposal
for family review.

## Authorization and lifecycle

The existing `memory_groups_enabled` setting gates the entire source adapter.
When off, story responses retain their legacy evidence shape and do not inspect
groups. When on, the exact e7 schema is required. No migration, model discovery,
inference, file access or writes occur during evidence collection.

The caller authorizes the library and full story selection in one transaction.
Every member of each participating group must still be active and visible in
that library. A withdrawn or moved member makes the complete group unavailable,
matching the group reader. A source must be a current, undeleted note originating
on a current group member in the same library. Sticky exclusions cannot acquire
sources. Neither old group revisions nor old note text are hydrated.

Editing or deleting a source, changing group membership, moving media or
revoking access changes or denies the current evidence snapshot. Story saves
require the current selection revision; reviewed references are filtered when
their evidence digest no longer matches. Jobs rehydrate before and after provider
I/O and discard stale proposals. A new narrative worker configuration must
explicitly set `memory_groups_enabled: true`; its schema preflight requires e7.
This setting is rejected for contribution workers.

Current group IDs, revisions and ID-only membership content are hashed into the
selection revision without adding fields to media responses. Thus even a group
revision that leaves note wording unchanged invalidates an earlier save/job
snapshot. A still-authorized, unchanged original note can keep its reviewed
chapter reference; group history is never used to resurrect withdrawn text.

## Wire and storage contract

Existing evidence IDs stay canonical: `family-<original-note-uuid>`. With group
sources enabled, family-note evidence also supplies:

- `origin_asset_id`: the canonical positive decimal ID of the original note's
  media. It can be outside the story selection, but must remain authorized in
  the same library.
- `byline`: the current voluntary display label, at most 256 UTF-8 bytes. It is
  not an account identifier and may be blank.

Both metadata fields are supplied together. Every occurrence of the same source
ID has identical evidence content and metadata. Repeated IDs are permitted across
items, refused within an item, and deduplicated per chapter and in title/narrative
source lists. Conflicting payloads for one ID are invalid. Android and Web accept
legacy responses with neither field.

At most eight groups per selected item, 24 selected media, 12 evidence entries
per item and 12 unique references per chapter are allowed. An oversized context
is refused rather than silently dropping reviewed memories. Existing response
and prompt byte budgets remain enforced. Saved stories retain evidence IDs and
digests only; memoir generation and original-source reads preserve the canonical
origin and source byline.

## Delivery boundary

The [group review and activation gates](ROADMAP.md#october-11-adjustable-shared-memory-groups)
still apply. This source change does not activate live groups, publish an APK,
run a model, or expose private sources through anonymous Home TV.
