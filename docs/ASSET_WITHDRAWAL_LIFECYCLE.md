# Durable asset withdrawal and restore

**Status:** internal source contract, tested with generated SQLite/vector data.
No HTTP deletion route, live journal upgrade, migration or physical erasure is
enabled by this work.

## Meaning and scope

Withdrawal retains the asset parent and sets `assets.status='deleted'`.
Protected media reads and visual candidate loading exclude that parent. This
does not erase original media, family contributions, story prose or vector files.
Permanent media/prose erasure needs its own reviewed dependency closure and
filesystem execution protocol.

The current contract accepts only an active image/video asset with exactly one
active library mapping and one assigned upload receipt matching its source hash
and byte count. Imported, unassigned, empty, ambiguous or remapped sources refuse;
no identity or library history is inferred.

## Durable identity and ordering

[`asset_tombstones.py`](../server/backend/app/access/asset_tombstones.py) prepares
a canonical content-free binding: asset ID, source SHA-256, byte count, MIME,
path SHA-256, library ID and mapping digest. Neither filename nor media bytes is
written into the journal. IDs are canonical positive SQLite integers.

[`OriginalDeletionJournal`](../server/backend/app/access/original_deletions.py)
supports these as a distinct V3 `asset` collection. A prepared binding must be
supplied to append and match the current primary snapshot. The same asset ID
cannot acquire a second tombstone under another library.

The authorized caller must hold a primary `BEGIN IMMEDIATE` transaction with
`secure_delete` enabled. The existing sidecar-first ordering remains:

1. Prepare and review the exact binding under the primary write reservation.
2. Append the bound V3 record; commit the external journal before changing the
   primary marker or withdrawing the asset.
3. Apply the exact tombstone and commit the primary. No helper commits it.

An internal call sequence, after authorization and quiescence qualification:

```python
candidate = prepare_asset_tombstone(db, asset_id, library_id, occurred_at)
receipt = journal.append(db, 'asset', {
    'id': asset_id,
    'library_id': library_id,
    'asset_binding_json': candidate['asset_binding_json'],
}, occurred_at)
apply_asset_tombstone(db, receipt)
# Caller owns the primary commit and error rollback.
```

The journal stores no authorization grant. A future route/operator operation
must establish authority and bind its reviewed asset identity separately.

## Format upgrade and offline replay

V1/V2 journals reject asset appends. `upgrade_asset_format` is an explicit
offline capability upgrade that requires the reviewed head and matching primary
marker. It preserves every previous sequence, record digest, predecessor digest,
head and primary marker. Legacy upload/memory digest inputs stay unchanged;
family-note entries retain their V2 digest rule inside V3. No format is upgraded
automatically, and old consumers must be qualified before a live capability switch.

After restoring a backup, review and replay the existing external journal
before opening the API or workers. Asset replay requires the exact retained
parent, path fingerprint, hash, size, MIME, library mapping and assigned receipt.
Missing or reused parents and identity/scope changes stop replay atomically.
Matching active or already-withdrawn parents become/remain deleted. Parent,
mapping and immutable vector records survive; no source/vector files are opened
or unlinked. A journal append followed by a primary rollback remains replayable.
Already-applied asset tombstones are also verified during review/replay. A
current marker paired with a revived, reused or changed parent stops recovery;
it cannot be accepted as an up-to-date restored database.

## Cleanup planning and remaining gates

`plan_durable_asset_vector_cleanup` requires a current V3 receipt and a deleted
parent. It independently reads the committed primary marker/status/identity;
changes visible only in the caller's uncommitted transaction are insufficient.
It then uses the bounded all-version vector planner, preserving metadata and
files. A status-only update, stale journal marker or changed source refuses.

This planner performs no physical cleanup. The optional
[derived-vector executor](VECTOR_ERASURE_LIFECYCLE.md) now binds complete ready
and pending-publication file sets to a durable plan, revalidates them under the
primary writer reservation and resumes known quarantine states. It retains
originals, immutable metadata and interrupted task claims. Native Windows journal/
filesystem qualification, additive vector migration, installed producer profile,
protected similarity route and reviewed picker remain delivery gates.
