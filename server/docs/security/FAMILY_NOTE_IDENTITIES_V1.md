# Family-note original identities · version 1

## Source scope and activation

The additive Alembic revision `d1f6a8c3e920` follows `c2e6b8a1d490`. It adds
three content-free tables and required integrity triggers. The existing C2
edition/source tables and every existing row are preserved. No note, caption,
edition, revision, account or library is backfilled or deleted.

This is implemented source qualified with disposable SQLite fixtures, not an
approved live migration or a permanent-erasure API. C2 remains default-off.
The new source runtime still supports the previous compatible database revisions.
An older API binary will reject the new database revision: rollback is not an
API-file swap after this migration. Empty identity tables can be downgraded;
populated lineage requires reviewed offline backup restoration.

## Private original identity

`access_family_note_identities` holds a server-created UUID distinct from the
public note UUID, the unique reserved note UUID, immutable asset and original
author identifiers, origin library and creation time. It holds no wording,
byline, recording or transcript. The private author identifier is not an API
display field. Identity rows have no foreign key to deletable notes, accounts,
assets or libraries and reject UPDATE/DELETE. Retaining an identity after parent
content removal reserves the UUID; INSERT or renaming another note into it fails.

`Stories.save` creates the identity and initial scope immediately after a new
note is inserted, within the existing authorized write transaction. Mutation
retry returns its existing note without minting another identity. Failure of
revision persistence rolls back note, identity, scope and audit together.
Normal text edits and soft removal retain their current raw revision behavior.
Changing a bound note's UUID, original author, asset or creation time is refused.

Older unbound notes remain readable/editable under existing authorization. Their
current UUID/library/digest does not establish historical identity. The new code
does not automatically adopt them into the registry, including on retry or move.

## Library scope history

`access_family_note_scopes` records ordinal zero for creation and each approved
library move: previous/current library, reviewed plan ID/digest and time. It is
append-only and contains no source words. Triggers require sequential moves from
the immediately previous scope and current note library. A bound note's library
can only be updated to the latest ledger scope.

The existing promotion review HMAC includes identity and every scope row within
its existing row/byte budgets. Applying a stale review refuses before moving the
asset. `reassign_assets` appends lineage and updates asset/note library in its
caller-owned transaction; failures roll back all three. A same-library action
adds no move. Raw note history, UUID, author, asset and original identity stay fixed.
Unbound legacy notes can still move but do not acquire invented lineage.

Fresh identity resolution requires a transaction, exact installed schema, current
note/active asset/library membership, frozen original fields and complete scope
history from ordinal zero. It checks at most 4,096 scope entries; a move beyond
that bound is refused before writing. Current-row scope alone is insufficient.

## Complete saved-edition bindings

At the new revision, memoir provenance resolves every `family-<note UUID>` from
the freshly authorized database context. Each typed pointer binds original
identity, canonical note/asset, current library and scope ordinal. The pure
provenance builder checks these fields and includes them in the closure digest,
including inputs omitted from model citations or chapter evidence lists.

`access_memory_book_edition_family_notes` adds a separate immutable binding per
normalized C2 source ordinal. Its insert guard checks the matching family source,
asset, edition library and recorded scope. Foreign keys target the normalized
source and historical identity/scope; there is no dependency on a current note or
book for future identity-based erasure lookup. Removing normalized closure rows
cascades these bindings; identity/scope history remains.

Save writes bindings in the same transaction as the edition. Reads rebuild fresh
typed pointers and require exact persisted bindings. Missing or changed bindings
hide manuscript and source details. A legacy unbound family input refuses typed
proposal/save/read with a bounded 503; there is no automatic C2 provenance backfill.
Existing C2 calls remain explicitly unbound and retain their old schema contract.

## Runtime, initialization and remaining work

The new revision requires all three tables and exact required table/index/trigger
definitions; partial or drifted installation returns generic unavailability and
does not repair storage at startup. Original-deletion journal initialization
recognizes and fingerprints this schema but refuses a new bind with any retained
identity/scope/binding rows, even if original note parents are gone. Old C2/f7
qualification behavior remains covered independently.

The existing deletion journal still supports only `memory` and `upload`.
This increment does **not** add a family-note tombstone, eraser, restore replay,
owner erasure endpoint, legacy qualification/backfill or activation permission.
The next slice must define a versioned journal record, owner/expected-revision
checks, append-before-purge, secure all-revision deletion, historical/orphaned
edition manuscript nulling and complete closure removal by immutable identity.
Absent-parent replay, append/primary rollback retry and conflicts must be proved
atomically with synthetic backups before any native operation.

Deployment also needs an offline stopped-writer migration controller and matched
API/approved-upload worker packages, native schema/backup/restore qualification,
and explicit operation authority. Earlier C2 packages or API switches do not
qualify this revision. Generic legacy caption/face launchers keep their existing
revision gates; the matched approved-upload lanes have separate source evidence.

See the [lifecycle plan](../MEMOIR_SOURCE_LIFECYCLE_PLAN_2026-10-07.md) and
[architecture](../architecture/PHOTOHOUSE_ARCHITECTURE_2026-10-07.md).
