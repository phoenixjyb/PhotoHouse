# Library-wide similar-photo stacks

## Status and purpose

**October 20 source candidate.** The delivered v74/API gallery still uses the
[page-local v1 contract](SIMILAR_PHOTO_STACKS.md). This increment adds a separately
prepared library index, consistent collapsed pagination and account-private saved
cover/separation choices. It has not been migrated, indexed, deployed or published.
Original files and ordinary asset reads remain unchanged; every group member is
available to the full viewer. No album, shared-memory group or story is assigned.

## Presentation and compatibility

Web and phone request the optional indexed gallery for an unfiltered All/Photos
view. A 404 negotiates the existing v1 gallery. An absent or invalid extension
cannot hide an ordinary photo. Other errors retain the normal access/recovery
path; they do not bypass authorization. Video-only, search and album views keep
their existing readers. Home TV's separate catalog is unchanged.

Each indexed page has **12 visible positions**. A position is one ordinary asset
or one complete stack of **2–24 images**. All member metadata is in that response
(up to 288 items), so the viewer can step through every original. The grid loads
only visible covers/singles, then member thumbnails on explicit expansion. A
stack appears on one page rather than being repeated at raw-item boundaries.
Pagination is read against one current snapshot; a later edit or refresh can
change page membership. No multi-page snapshot session is implied.

Members can expand, choose a cover, show one photo separately, or reset their
library's display choices. The private choice persists across reloads/devices
using the same account. It does not change another member's view. Saved covers
remain eligible when matching photos join the same canonical group; disappeared
covers or changed group IDs revert to the default. Expanded/collapsed state stays
local to the current view. Reset remains available when all groups have dissolved.

## Protected wire contract

`GET /photo-stacks/gallery?library=<id>&page=1&media=all|image` returns ordinary
Gallery keys with fixed `page_size: 12`. `total` counts visible positions. Each
`items` entry is an ordinary authorized asset, including the existing date hint.
The `photo_stacks` extension contains:

- `version: 2`, `scope: "library"`, canonical UUID `index_revision`;
- nonnegative integer `preference_revision` for the current account/library;
- disjoint groups with canonical decimal `id`, member `asset_ids`, a member
  `cover_asset_id`, `count`, and `near_capture` or `same_upload` reason.

The group ID is the original minimum member ID and can survive that member's
private separation. Every returned current member must be in `items`. No hashes,
source paths, uploader identifiers or upload-batch identifiers are exposed.

`POST /photo-stacks/preferences?library=<id>` accepts exactly these string fields:

```json
{
  "index_revision": "<current UUID>",
  "revision": "<current private revision>",
  "group_id": "<group ID or empty for reset>",
  "cover_asset_id": "<member ID or empty>",
  "separate_asset_id": "<member ID or empty>",
  "reset": "0"
}
```

Choose exactly one cover/separation target, or send `reset: "1"` and empty target
fields. The response contains only `index_revision` and `preference_revision`.
Current library membership/read access is required for every operation; Web
mutations also require same-origin/CSRF checks. Index and private revision use
compare-and-swap. Clients refetch after success, conflict or an uncertain outcome,
and never automatically replay a write. One preference write is in flight per
view; account/library/generation changes discard late replies. A denied mutation
clears protected UI through the existing access-failure path.

## Index and lifecycle

The pure CPU builder uses the same conservative complete-link rules as v1:
full capture times within five minutes and pHash distance at most six, or absent
full times with the same uploader/batch and distance at most two. Known date
conflicts veto the fallback. Videos and uncertain comparisons stay separate.
Seven pHash bands/time buckets and three upload bands bound candidate discovery.
A build accepts at most 100,000 authorized assets and 10 million pair comparisons;
exceeding a bound rejects the build without publishing partial output.

The additive Alembic revision `f2a8c5d1e640` follows `e7c1a9d5b304` and adds four
private derivative tables: index generations, groups, member fingerprints and
account preferences. Startup does not create tables. Migration alone does not
create an index or activate another optional feature. The last verified live
schema remains `a0c9d2e4f817`; the new head is a source contract only. Populated
photo-stack tables prevent downgrade; recovery needs a reviewed offline plan.

`PhotoStackRefreshWorker.run_once()` is a CPU-only integration entry point for an
explicit tuple of 1–32 libraries, using fresh foreign-key-enabled connections.
It does not start a thread, scheduler, service or task. Runnable scoped pHash work
postpones a refresh; failed tasks are preserved. Unchanged input is a no-op.
Clustering runs outside the write transaction. Atomic publication rechecks the
source digest, generation and any attached deletion-history guard. A bound primary
requires its current external deletion-history guard, including on no-op refresh;
an unguarded raw connection is refused. Concurrent
changes preserve the previous index and preferences.

Every gallery read rechecks library access and current member metadata/mapping.
A removed, moved, suppressed or changed member dissolves the entire stale group;
still-authorized originals appear individually. New unindexed uploads are visible
individually. No index/schema or a library above the asset cap yields 404 for
fallback. Indexed SQL is additionally limited to three seconds and 20 million
SQLite VM steps, with an unavailable response when interrupted. Preferences are
bounded to 4,096 covers/separations and 256 KiB per account/library.

## Local source evidence — October 20

- 22 migrated-database/API cases, ten pure index cases and 14 migration checks
  pass, including atomic upgrade/downgrade refusal and bound-history rejection.
- 93 worker-admission cases pass; all five approved worker readers and exact
  candidate scope are checked on a generated f2 database without model execution.
- Both generated Chromium 151 gallery journeys pass: v1 temporary choices and
  v2 cross-page groups/private preferences, including 409/uncertain outcome
  read-reconciliation without write replay, single-flight writes, scope fencing
  and denied-access recovery. Chinese/English 150% phone and desktop renders
  were inspected.
- 1,156 Android live-core cases, connected lint and instrumentation compilation
  pass. Two separate QA-app emulator UI cases pass: enlarged v1 stack controls
  and v2 reset availability when no groups remain. The existing AVD was shut down
  after the run. These are synthetic fixtures, not a Samsung/family-photo trial.

The complete source/hosted profiles remain release gates, distinct from these
focused results. No real household database, model, media or device was used.

## Qualification and delivery gates

The generated-data checks exercise actual migrations, routes, index publication,
private choices, cross-page grouping and access revocation. Browser fixtures do
not substitute a mock preference store. Android parser/store/transport tests
cover compatibility, epoch fencing and complete member metadata. These are source
checks, separate from native Windows execution or real-family similarity quality.

Before activation, prepare and review: the full upgrade path from the actual live
schema, stopped-writer backups and restore rehearsal, compatible API/workers,
Windows CPU/resource and deletion-history qualification, a bounded cancellable
refresh host with an explicit library set, and exact switch/rollback controllers.
Then qualify/publish the phone artifact separately and test the Samsung gallery.
No automatic migration, new scheduled task, production index write or APK
publication is authorized by this document.

Family acceptance should check a burst spanning an old page boundary, expand and
view every original, save a cover, separate a member, restart/refresh, and compare
a second account. Review false positives before changing similarity thresholds.
