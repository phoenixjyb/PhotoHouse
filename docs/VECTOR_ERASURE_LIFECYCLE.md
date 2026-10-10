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

## Independent catalog and older-primary restoration

The optional [`VectorErasureCatalog`](../server/backend/app/access/visual_vector_erasure_catalog.py)
stores a complete canonical plan outside SQLite and outside the vector root.
With `catalog=` configured, `prepare` first commits the primary plan, then
exclusively creates, syncs and reads back the exact digest-named private archive.
Every cleanup step verifies that archive before changing a vector name. Archive
failure retains the primary plan and all vectors. An interrupted partial archive
refuses cleanup and is never silently overwritten; an exact complete retry is
synced again. There is no catalog scan or inferred job identity.

After restoring an older primary, replay the external V3 journal and commit its
withdrawals first. Under explicit offline maintenance, `restore(reviewed_job_id)`
can then import the archived missing artifact/publication records and cleanup
job. All three optional schemas must already exist. Current records must be an
exact subset of the archived closure, apart from an exact prepared intent which
the catalog proves committed. Conflicting/newer rows, source/library changes,
wrong roots and corrupt known files refuse. Imports and final filesystem
preflight share one SQLite writer transaction; failure rolls back all imports.
Existing matching progress is retained. Missing progress restarts at zero and
verifies all known source/quarantine names; no original or task row is changed.

The original primary-only internal mode remains available for its earlier
source fixtures. It does not close the backup gate: withdrawal replay alone
cannot recover lost cleanup manifests or publication metadata. Activation must
use the qualified catalog path and independently preserve its files. An older
primary backup alone cannot establish that every derived file has been removed;
this executor never guesses or scans for orphans. Catalog relocation, a different
vector volume, missing optional schemas and task reconciliation require separate
operator planning.

## Generated qualification runner

[`qualify_vector_erasure.py`](../server/scripts/qualify_vector_erasure.py) creates
only new synthetic databases, PNG/NPY files and archives beneath an absent
absolute `--out` directory with an existing private parent. It has no real
database, model, media or endpoint argument. Fixtures are retained for inspection.
It checks complete hardlink closure, child process death after quarantine linking,
older-primary replay/catalog restoration and corrupt-quarantine refusal.

On Windows the normal CLI uses the existing Job supervisor: a 15-minute limit,
2 GiB Job memory, at most four processes and an 8 GiB free-RAM admission floor.
The child receives a clean environment, isolated Python flags and a generated
child marker. Nonzero child exit or an unexpected report refuses qualification.
Private directory/ACL inheritance and stable Windows file birthtime are exercised
by the actual source functions. A Mac run reports `native_windows=false` and
cannot establish Windows acceptance. See [Windows checks](WINDOWS_CPU_CHECKS.md).

The runner now refuses generated Windows paths which exceed legacy limits
before creating output or launching a child. Choose a short private candidate
and output name; no registry change or extended-path alias is required. A
failed fixture attempts to retain an exclusive, bounded, content-free failure
receipt, which the supervisor validates before reporting its phase and Windows
error code. Diagnostics cannot replace the original failure or count as a pass.

The October 11 native attempt with source `1db984c` verified all 172 packaged
files and passed PowerShell parsing, but the generated child failed before the
first vector file existed. Its computed filename needed 294 characters and the
host's long-path setting was disabled. The old supervisor suppressed the child's
error, so the exact exception was not captured. This attempt does not establish
native recovery acceptance; the shorter layout and diagnostic changes require
a fresh bounded qualification.

## Delivery gates

Generated local tests establish source and process-interruption behavior only.
Before Windows activation, qualify native hard-link behavior, private directory
ACL inheritance, stable file birthtime and filesystem/process recovery. Python
does not provide Windows directory fsync, so power-loss durability is a separate
gate. Catalog restoration now has generated source evidence; native catalog
durability and independently preserved backup coverage remain open. Then review
additive schema/backup restore compatibility, exact installed producer profile
and task reconciliation. Any real cleanup needs the reviewed
asset set, backup/recovery plan and operation-specific authority.
