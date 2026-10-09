# Family-note original erasure and journal version 2

Local source contract, October 8, 2026. Requires the additive D1 identity schema
`d1f6a8c3e920` and a separately selected version 2 deletion journal. This contract
has synthetic database/HTTP evidence; it does not activate a live service.

## Separate owner action

`DELETE /stories/{note UUID}/original?library={library}` accepts exactly
`{"revision":"1"}` with a canonical positive decimal revision. The existing
`DELETE /stories/{note UUID}` remains soft removal and retains revision history.

The permanent operation is default-off through `family_note_erasure_enabled` in
application, runtime and strict staging configuration. Enabling it requires a
configured journal/namespace pair and journal version 2. The request transaction
freshly checks the account, current library owner role, active asset membership,
original identity and expected revision. It additionally requires current owner
membership in **every recorded historical library**, since the operation purges
editions across those scopes. A library move grants no erasure authority.
Browser cookie requests require existing same-origin and CSRF protection; native
clients use the existing HTTPS bearer transport. Anonymous Home TV gets no route.

A stale revision returns 409; unavailable, unqualified or altered storage returns
503 without raw content. An exact committed retry reauthorizes the same scopes
and returns the receipt without another journal entry or audit. After an external
append followed by primary rollback, normal requests remain closed until offline
replay; they cannot bypass the journal watermark to retry deletion online.

## Content-free durable record

The new collection is `family_note`, with text kind, note UUID, current library,
asset ID, current text SHA-256 and canonical `family_binding_json`. The binding
contains version 2, immutable identity UUID, registry hash, expected revision,
revision projection hash, and a bounded list of cumulative library-ledger hashes.
No title, byline, original text, audio, transcript or manuscript is copied into
the journal. Identifiers and hashes are still private metadata.

The revision hash includes all current note fields except `library_id`; library
history is bound separately. This permits a backup before a sanctioned move,
which changes library but does not edit the raw revision. Equal-revision content
changes still refuse replay. Older mutable revisions are eligible only when
immutable registry fields and the entire surviving library history match a
prefix of the tombstone. Missing identity, newer revision, conflicting history,
extra later scopes and partial or altered required schema refuse replay.

Version 1 remains the initializer default. Version 2 adds a nullable binding
column; existing upload/contribution rows keep null bindings and their exact
original hash projection. The genesis stays anchored to version 1. A full old
chain is checked before the explicit `upgrade_family_format` primitive rebuilds
the journal table atomically; old sequence, row digests, head and primary marker
are preserved. Family records use a version 2 digest domain. Startup, reads and
erasure never perform that upgrade automatically. An older binary rejects the
version 2 journal; restoring an old API alone is not a compatible rollback.

The fresh offline initializer accepts `--format-version 2` only with D1 storage,
empty upload/contribution tables and edition/identity history, an identical
separate backup, and its
existing stopped-writer execution controls. It reports the selected capability.
The upgrade primitive is source infrastructure, **not yet a qualified native
stopped-writer upgrade controller** for an existing live journal.

## Append before purge

The live operation holds `BEGIN IMMEDIATE`. It preflights trusted identity,
complete typed dependent edition closure and bounded AI cleanup targets before
appending. Foreign-key corruption refuses the live operation before append.
The external ledger commits durably first; only then does the primary marker
advance inside the caller transaction and the source purge run.

The common [eraser](../../backend/app/access/family_note_deletions.py) requires an
active transaction, foreign keys, SQLite `secure_delete=ON`, DELETE journaling,
and exact required note, identity and edition schema. It removes all current
note and raw revision rows, retaining content-free identity and scope records
so the UUID remains reserved. Every dependent whole manuscript is nulled, its
edition state becomes `source_invalidated`, and its entire normalized source
closure is removed, including uncited inputs and historical book revisions.
Dependency discovery does not join a current note or book. An unbound old C2
`family-UUID` source refuses rather than being silently adopted.

Known story/book AI jobs are found from current and historical asset/story
membership and immutable edition targets. Their private input/output, errors,
leases and associated AI turn replies are scrubbed; pending jobs are cancelled.
User-authored questions, story/book text, independent contributions and media
originals remain. Jobs without provable target lineage are not guessed from
opaque strings; their qualification is a separate lifecycle obligation.

Restore replay uses the same helper in a secure exclusive transaction and fully
validates the mixed journal chain. An absent note parent with a trusted identity
still has its revisions and dependent prose purged. Read-only review permits
only exact pending note-revision orphan repair; unrelated missing book, account,
asset or other parents remain corruption. If a later check fails, all primary
purges and marker updates roll back together. Replay must precede service/worker
startup after restoring a backup.

`secure_delete` evidence concerns the tested SQLite file. It does not erase old
backups, filesystem snapshots, SSD storage history, exported copies or independent
manual text. Offline paired backup/replay and native Windows qualification remain
required. Caption, asset-membership, book-introduction and child-narration original
erasure are separate unfinished contracts; C2 stays default-off.

## Existing version 1 journals

The [offline upgrade controller](ORIGINAL_JOURNAL_UPGRADE_V2.md) qualifies a D1
primary and its matched backup alongside the bound V1 journal and its identical
backup. Review is read-only; explicit execution requires stopped writers and a
locked recheck before journal DDL. This controller has synthetic evidence, not
live Windows acceptance.

## Source evidence

- [Journal and backup tests](../../tests/security/test_family_note_deletions.py)
- [Replay refusal boundaries](../../tests/security/test_family_note_deletion_boundaries.py)
- [HTTP ownership, CAS, retries and CSRF](../../tests/security/test_family_note_erasure_api.py)
- [Original journal implementation](../../backend/app/access/original_deletions.py)
- [Immutable identity prerequisite](FAMILY_NOTE_IDENTITIES_V1.md)
- [Remaining lifecycle work](../MEMOIR_SOURCE_LIFECYCLE_PLAN_2026-10-07.md)
