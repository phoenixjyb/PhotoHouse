# Guarded memory schema application

This is an operator tool, separate from the product UI. The tool defaults to
read-only review. It does not stop services, create or restore backups, install
source, enable HTTP routes, load a model or start a worker.

## Source revision is an explicit choice

The deployed source head is not the database revision. A read-only October 11
runtime query found the live primary at `a0c9d2e4f817`, with none of the later
editorial, edition, family-note identity or group tables. This point-in-time
observation must be refreshed before any maintenance operation.

`apply_memory_group_schema.py` accepts these exact starting revisions:

| Explicit starting revision | New tables through e7 |
|---|---:|
| `a0c9d2e4f817` | 9 |
| `b1d7e4a9c230` | 7 |
| `c2e6b8a1d490` | 5 |
| `d1f6a8c3e920` (default) | 2 |

It never detects a starting revision and silently chooses a migration path.
All four steps are additive; they have no historical note, identity or edition
backfill. The original records remain in their existing tables.

## Review and execution contract

Supply direct private local files for the primary and a separate stopped-writer
backup, an exact reviewed logical fingerprint, a size budget and deadline.
The fingerprint is the existing streaming schema-and-row digest from
`rehearse_fullsize_database.py`, not a raw file SHA-256. Keep both digests in the
private controller receipt. A hardlink, symlink, public file, sidecar, non-DELETE
journal, different backup, wrong revision or running task causes refusal.

```sh
python -I -B scripts/apply_memory_group_schema.py \
  --database <private-primary> --backup <separate-private-backup> \
  --reviewed-backup-digest <reviewed-logical-sha256> \
  --from-revision a0c9d2e4f817 --max-bytes <reviewed-budget> \
  --timeout-seconds <reviewed-deadline>
```

Execution additionally requires `--execute --all-writers-stopped`. This assertion
is not proof that processes or schedules are stopped. An independently approved
controller must fence every writer and retain its original configuration.

Under `BEGIN EXCLUSIVE`, the tool rechecks primary and backup identities,
revision, schema objects and every existing row. It supplies the exact SQLite
connection to Alembic, so `DATABASE_URL` cannot redirect the operation. Before
commit it verifies every old column, object and row is preserved, the new tables
are empty, and the only new objects are the authoritative builders' exact tables,
indexes and triggers, including d1's two triggers on the old story table.
Integrity, foreign keys, backup preservation, file identity and deadline are
checked before commit. A failure rolls back the whole chain. A lost controller
result requires inspection; a retry against an already upgraded primary refuses.

## Qualification and activation sequence

1. Build a pinned API package and matching companion worker package. The API
   qualification package includes the two CPU/video worker entrypoints and their
   media/resource helpers; it does not register tasks.
2. Run `qualify_memory_group_workers.py` in a fresh private generated directory.
   It first creates a real a0 fixture, injects failure during d1 after the earlier
   steps, verifies full rollback, then runs the guarded a0→e7 upgrade. Separately,
   a real d1→e7 media fixture exercises approved thumbnail, perceptual-hash,
   video-probe and keyframe tasks, exact follow-up queues, decoded derivatives,
   original hashes, source attribution and group preservation.
3. Native Windows CLI execution always uses a Job with a 900-second deadline,
   2 GiB memory cap, eight-process cap and 8 GiB free-RAM floor. No child bypass
   argument is exposed. Portable worker tests mock that native execution boundary;
   they are not installed-worker or GPU acceptance.
4. Before live activation, separately approve a pinned maintenance controller:
   refresh schema/source/task actions and process identities; fence all writers;
   drain or reconcile running tasks; stop the API; create and verify fresh private
   primary, assistant-journal and original-deletion-journal backups and restoration
   rehearsal; execute the guard; preflight compatible API and all five companion
   workers; switch their exact actions; verify routes and OTA feeds; restore the
   recorded schedules. Missing ownership, backup or resource evidence blocks this
   operation. Family/model processing and vector suggestions remain off unless
   separately qualified and explicitly enabled.
5. If migration fails before commit, keep writers fenced and inspect rollback.
   If activation fails after commit, do not run an old incompatible worker or
   destructively downgrade populated tables. A separate reviewed restoration plan
   must preserve new writes and independent journals before restoring backups.

The generated qualifier and local tests do not authorize any live operation.
Phone signing/publication and family acceptance are later delivery gates. See
[shared groups](MEMORY_GROUPS_V1.md) and
[Windows qualification](../../../docs/WINDOWS_CPU_CHECKS.md).
