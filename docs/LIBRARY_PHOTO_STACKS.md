# Library-wide similar-photo stacks

> Current delivery update (2026-10-30): [October 29 release](RELEASE_2026-10-29.md)
> records the scoped Windows activation. Earlier default-off/source-only statements
> below describe the original increment; public defaults and physical-device
> acceptance remain separate.

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

### Web browsing refinement — October 21 local candidate

Expanded photos now sit together in a named inline region with one count,
one grouping explanation and a header collapse control. Other gallery positions
remain visible outside that region. Each member keeps its original open,
cover-selection and separation actions; the viewer still includes every original.
This presentation also works with the page-local v1 fallback.

Keyboard expansion focuses the collapse control. Collapse or Escape from inside
the group returns focus to its current cover's expand button. Escape in the modal
photo viewer closes that viewer without collapsing the group. The heading and
returned button scroll clear of the sticky navigation, including at enlarged
text sizes. Expand/collapse are local display actions and send no preference write.

The two focused generated Chromium journeys cover these interactions alongside
saved-choice, access-recovery and fallback regressions. Chinese/English phone
renders at 150% text and the desktop contact sheet are checked separately.
This is a Mac-local Web candidate, with no new Android build or live activation.

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
full capture times within five minutes and pHash distance at most eight, or absent
full times with the same uploader/batch and distance at most four. Known date
conflicts veto the fallback. Videos and uncertain comparisons stay separate.
Candidate discovery stores five disjoint hash bands for near-capture images and
three for same-upload images. It probes each exact band plus one-bit variants;
any pair within the respective eight/four-bit limit must share such a probe.
Capture times are stored in one bucket and checked in neighboring buckets.
This preserves eligible pairs while avoiding excessive candidates in dense batches.
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
postpones a refresh; failed tasks are preserved. Unchanged input and grouping
policy are a no-op. The source digest includes the algorithm, visual thresholds,
time window and group cap; a policy change rebuilds even unchanged source rows
on the next explicitly run refresh. Legacy row-only digests also rebuild once.
Refreshing does not rewrite originals or account-private display choices.
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

### Threshold adjustment — October 22 local candidate

The relaxed eight/four-bit policy passed 79 focused tests and 27 subtests,
including boundary distances, timestamp reliability, complete-link cohesion,
policy-triggered index refresh and preserved private choices. A deterministic
20,000-image same-timestamp synthetic batch completes within the existing
comparison budget after the candidate-lookup adjustment. These checks do not
establish matching quality for household photos, Windows qualification or live
delivery. The previously sealed Windows rehearsal uses its original source and
does not include this tuning.

## Generated Windows rehearsal

PR #99 merged the optional library index and clients into main. Its source and
hosted checks do not activate the schema or index on a household installation.
The follow-up qualifier is available at
[`qualify_library_photo_stacks.py`](../server/scripts/qualify_library_photo_stacks.py).
It accepts only `--out`, an absent absolute directory beneath an existing private
parent. It has no real-database, media, library, provider or service argument.

```sh
python -B server/scripts/qualify_library_photo_stacks.py --out /absolute/private/new-rehearsal
```

On Windows use the corresponding absolute Windows paths and an already qualified
Python environment. The CLI supervises its generated-data child in a Windows Job:
240 seconds, 2 GiB per process tree, eight processes and an 8 GiB free-RAM admission
floor. It passes a minimal environment, uses isolated Python and refuses a failed,
missing, oversized or inexact success receipt. There is no child-bypass CLI flag.
Portable runs exercise source behavior; only a completed native run establishes
Windows acceptance of this qualifier and its resource controller.

The rehearsal verifies:

- Interrupted a0→f2 DDL rolls back schema, rows and revision; the completed chain
  preserves existing rows, raw generated text/audio, caption, upload receipt and
  task evidence, adding exactly the thirteen expected tables.
- e7→f2 adds four empty index/preference tables and preserves older objects/rows.
- A V1 journal containing a valid deletion record upgrades to V2 with the same
  head and original data. Before/after primary-journal backups restore into
  separate files with matching history; every retained backup remains unchanged.
  This checks consistent pairs, not replay into a stale pair or power-loss recovery.
- Complete groups occupy one visible position across gallery pages; new assets
  remain visible before refresh. The one-shot synthetic worker waits for runnable
  hash work, refreshes after it finishes, and retains failed-task evidence.
- Cover/separation/reset choices stay private, stale preferences return conflict,
  changed similarity dissolves stale groups, and revoked members cannot read.
- Missing deletion guards and old restored metadata paired with newer deletion
  history cannot publish even a no-op index. Populated f2 downgrade is refused.

Only generated databases, audio bytes and receipts are written. No image/video
file is decoded; this is not codec, GPU, family similarity or device acceptance.
No scheduler or production worker is installed or started. Reports name production
state separately from the synthetic task and worker exercised by the rehearsal.

## Migration and refresh-host preparation

[The operations plan](PHOTO_STACK_OPERATIONS.md) defines the separate guarded
migration library and one-sweep CPU host. The current source extends the generated
qualifier to exercise those paths, preserving any supported journal format and
original rows. This changed package needs new native qualification before live
activation. The search release owns the current API/Web cutover; group activation
uses its completed delivery as the later baseline.

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
