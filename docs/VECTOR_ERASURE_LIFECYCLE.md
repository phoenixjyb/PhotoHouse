# Derived vector erasure and recovery

**Status:** optional internal source contract. No migration, HTTP route,
installed cleanup task or Windows filesystem qualification is included.

[`VectorErasureStore`](../server/backend/app/access/visual_vector_erasure.py)
removes only known versioned image-vector files after a committed
[V3 asset withdrawal](ASSET_WITHDRAWAL_LIFECYCLE.md). It retains original media,
contributions, immutable artifact/publication records and task claims. This is
filesystem cleanup, not a guarantee of physical-sector erasure.

## Reviewed maintenance boundary

The caller supplies a dedicated primary SQLite connection, the actual external
deletion journal and an explicit private vector root. Foreign keys and SQLite
`synchronous=FULL` must be enabled. Each operation reserves the primary writer
with `BEGIN IMMEDIATE`. Receipt verification independently reads committed
primary status, source/library binding and the current journal marker; a
status-only update or uncommitted withdrawal is insufficient.

All trusted publishers must use this primary database and reservation. The
internal publisher additionally refuses inactive/deleted parents before invoking
its authorization callback. Direct SQL or filesystem writers are outside the
contract: qualify a quiescent maintenance window before live cleanup. The root
and quarantine must deny access to untrusted identities. Concurrent same-owner
filesystem edits are not supported.

## Immutable complete plan

`prepare(asset_id)` reads the complete union of ready artifacts and prepared or
committed publication intents, capped at 128 records; it refuses overflow instead
of truncating. A committed intent must exactly match its ready row. A prepared
intent cannot already have a ready row. The plan includes only their canonical
final names and, for intents, the exact `.staging/<record-id>.npy` name. No
directory scan, inference, source-media access or legacy-vector guess is used.

Every present file must be a complete bounded float32 NPY with matching file and
component checksums and unit normalization. Symlinks/reparse points, partial or
corrupt bytes and extra hard links refuse the entire plan before filesystem
mutation. Only the exact stage/final pair for the same record may share an inode;
two independently valid copies are also supported. Missing known files are
recorded as absent; they must not appear later.

The optional primary `image_vector_erasures` journal commits a canonical manifest
before any filesystem change. It binds the withdrawal receipt, full immutable
metadata, root fingerprint, ordered names and observed file identities. The
manifest digest is the job ID. SQL triggers preserve the binding and allow only
one-file forward progress; they prohibit deletion and progress rewind. Existing
plans are revalidated rather than silently replaced.

## One-file execution and process recovery

`step(job_id)` verifies the whole remaining cohort before acting. It creates a
private same-volume `image-vectors/.erasing/<job-id>/` directory, then:

1. Atomically hard-link the source to its exact quarantine name. Existing
   destinations are never overwritten.
2. Verify all known names, complete bytes, bound identities and exact link counts.
3. Remove the verified source name, then verify again.
4. Remove the verified quarantine name and sync affected directory entries on
   POSIX. Verify absence before committing the next ordinal in SQLite.

A crash can leave source plus quarantine, quarantine only, or neither name.
Recovery accepts these states only under the committed immutable plan. A missing
source does not hide a corrupt or unexpected quarantine file. A failed commit
after unlink leaves pending progress that can safely verify absence again.
Completed names must stay absent. Unexpected metadata, bytes, aliases, root
changes or later records stop recovery; questionable files remain for inspection.
No task claim is reset and no prepared intent is silently marked completed.
Interrupted publication tasks require separate explicit reconciliation; keeping
the evidence can intentionally block optional producer startup.

## Delivery gates

Generated local tests establish source and process-interruption behavior only.
Before Windows activation, qualify native hard-link behavior, private directory
ACL inheritance, stable file birthtime and filesystem/process recovery. Python
does not provide Windows directory fsync, so power-loss durability is a separate
gate. Then review additive schema/backup restore compatibility, exact installed
producer profile and task reconciliation. Any real cleanup needs the reviewed
asset set, backup/recovery plan and operation-specific authority.
