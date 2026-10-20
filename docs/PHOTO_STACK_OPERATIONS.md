# Preparing library photo-stack operations

This is source preparation for the [indexed gallery](LIBRARY_PHOTO_STACKS.md).
It does not authorize migration, scheduled-task changes, service control or APK
publication. Another workstream owns the current search API/Web deployment;
finish that release and read its final delivery record before sealing this plan.

## Integration order and ownership

1. Deploy the combined search API/Web source with semantic search off. Preserve
   the newer gallery/upload code and existing feature flags. That release owner
   records the exact API source, action/root, schema, journal and worker states.
2. Prepare the grouping operation against that completed delivery. Verify its
   incumbent API and all upload workers admit f2; do not reuse a pre-f2 rollback
   API merely because it appears in an older release plan. Preserve API files.
3. Qualify the new migration and worker on generated data and an approved native
   candidate. Then review the fixed live operation with its actual library set,
   backups, resource limits, stop controls and ownership checks.
4. After separately authorized migration/index activation, verify Web negotiation
   and private choices. Build the next phone artifact from combined main; signing,
   OTA publication and physical family acceptance remain separate gates.

If the completed search release already includes the indexed-gallery routes and
Web assets, grouping need not replace them. A schema maintenance window may stop
and restart the same verified API action; the new worker can use a separate pinned
source root. Decide this from the actual final source, not a dated directory name.

## Installed launcher compatibility

Runtime schema support is only one layer of admission. Inspect the actual API
entry, worker entry/launcher, manifest, payload guard and runtime dependencies.
A launcher or release plan can still pin a0 even when its imported runtime admits
f2. Never restart an unqualified old launcher against the migrated database.

Prepare a complete new source closure and its matching manifest/entry pins in new
private directories. Preserve configuration, reviewed search artifacts, semantic
search OFF, playback guards, memory limits, stop controls and task non-action
settings. Do not edit installed bytecode, manifests or hashes in place to bypass
admission. Unknown payload compatibility blocks cutover until resolved.

The API package builder and inspector accept an explicit `--schema-revision`
(a0, e7 or f2); both default to a0 for existing preparation paths. For an f2
candidate, select f2 in **both** commands. The inspector reconstructs the exact
archive against that operator-selected target and rejects a target mismatch.
This field is a source-package contract, not database inspection, migration,
launcher qualification or activation. Approved-upload and released-caption
companion packages have their own explicit target and qualification contracts.

The replacement API entry should distinguish an explicit read-only a0 preparation
check from the f2 check/production mode. Its production branch must require f2;
it must not silently accept a0 when an approved migration did not finish. The CPU
readiness launcher, CPU entry and source manifest must agree on f2 together.
Review frozen image/face/video and caption entry chains separately. Existing model
execution and resource protections must survive any replacement.

Only assets with usable time and perceptual hashes can join a similarity group.
Measure coverage before activation. Unindexed photos remain visible individually;
missing hashes are not evidence that photos are dissimilar. A broad hash backfill
needs its own reviewed scope and bounded worker; ordinary approved-upload workers
must not claim unrelated legacy assets or reset historical failures.

## Guarded migration library

[`apply_library_photo_stack_schema.py`](../server/scripts/apply_library_photo_stack_schema.py)
provides `review(...)` and `apply(...)` for an independently bounded operator
controller. There is no default database, automatic startup DDL, journal upgrade,
worker launch or backup restore. The existing e7 controller remains pinned.

The explicit source revision is either `a0c9d2e4f817` or `e7c1a9d5b304`; the target
is `f2a8c5d1e640`. The a0 path follows the nine upstream collaboration tables before
the four stack tables. The e7 path adds only the four stack tables. Existing rows,
columns and objects remain intact; new tables must be empty. Feature flags are
preserved independently, so reserved schema does not enable model processing.

The callable signature is:

```python
apply(primary, primary_backup, journal, journal_backup,
      primary_logical_digest, namespace, expected_sequence, expected_head_digest,
      journal_file_sha256, budget,
      from_revision="a0c9d2e4f817", execute=False, all_writers_stopped=False)
```

The primary digest is the bounded logical fingerprint used by the existing
offline preparation tools; it is not a SHA-256 of the SQLite file. The journal
hash is its file SHA-256. Four separate direct private regular files are required.
Primary and backup must match logically, while journal and backup must match
byte-for-byte with the explicit namespace/head. The full history review must have
zero pending records. Old restored metadata cannot bypass newer deletion history.

Review is read-only. Execution also requires `all_writers_stopped=True`, an
exclusive primary transaction, fresh identity/hash/history checks and the exact
authoritative schema-object delta. It refuses running tasks, WAL/other writers'
sidecars, partial f2 tables, backup drift, changed originals and unexpected backfill.
Its own DELETE rollback journal is expected during the transaction. Failure rolls
back that transaction; it never restores or overwrites a reviewed backup.

Known journal V1–V4 formats are preserved. Indexing only reads deletion history,
so it needs no journal capability upgrade. Family-note erasure's V2 requirement
remains separate; the report exposes that format readiness without enabling it.
History files are limited to the 64 MiB bounded inspection profile. Primary size,
SQL work, streaming fingerprints and deadlines use the caller's explicit `Budget`.

An exclusive SQLite transaction cannot prove all external processes have stopped
or prevent a process from reconnecting after commit. Shutdown remains an operator
attestation supported by fresh task/process/listener and queue evidence; the
report deliberately says `operational_quiescence_verified: false`.

## One-sweep worker

[`run_photo_stack_worker.py`](../server/scripts/run_photo_stack_worker.py) defaults
to read-only preflight. All paths and 1–32 distinct active library IDs are explicit.
Example placeholders, to be replaced by verified local operator inputs:

```sh
python -I -B server/scripts/run_photo_stack_worker.py \
  --database /private/photohouse/primary.sqlite \
  --journal /private/history/original-deletions.sqlite \
  --namespace 11111111-1111-4111-8111-111111111111 \
  --library reviewed-library-id \
  --stop-file /private/controls/photo-stack.stop
```

Add `--execute` only inside the approved operation. One invocation performs one
sweep; it never installs or modifies a scheduler. The API schema must already be
f2. Missing schema, unselected libraries or stale history are not repaired. No
original image/audio/video file, model or general processing executor is opened.

Execution uses a nonblocking lock beside the selected primary. The primary parent
and stop-control parent must be private; selected inputs must be direct regular
files. It rechecks the primary inode for each connection and pins the journal
inode. The journal handle is strictly read-only. The primary cap is 8 GiB and the
history cap 64 MiB; source and pair limits remain 100,000 assets/10 million pairs.

Windows execution always supervises an isolated child in a Job: 240 seconds,
2 GiB per process tree, eight processes and an 8 GiB free-RAM admission floor.
The internal work deadline is 225 seconds to allow cleanup. Database/provider
environment variables are not forwarded. There is no caller-marked child CLI
bypass. Non-Windows runs are portable source evidence, without a claimed Windows
memory envelope; the eventual native operation must qualify locks, ACLs and Jobs.

Stop-file presence, SIGINT/SIGTERM and the internal deadline cancel the sweep.
CPU clustering and SQL poll the stop condition; publication checks it before
commit. An interrupted library keeps its previous complete generation and private
preferences. Libraries already committed earlier in the sweep remain committed.
The report distinguishes `completed`, `stopped`, `waiting`, `unchanged`, `updated`,
and `changed_retry`; none proves that a preview or original media is usable.

Runnable scoped pHash work defers refresh. Failed tasks are retained, not reset or
retried. New or changed source is rebuilt only when its fingerprint changes;
unchanged sweeps are no-ops. A source/generation conflict keeps the old index for
a later separately scheduled sweep. Poll cadence, boot recovery and any recurring
Windows task are operator choices for the later reviewed deployment.

## Live operation checklist to prepare

- Record the completed search release as the incumbent, with exact source/member
  hashes, API action/settings and the current schema/journal format and head.
- Identify every primary writer, active upload, worker and companion store. Fence
  admission, drain and stop the reviewed writers, then verify shutdown. Do not
  compete with the search release or assume an older queue snapshot is current.
- Make fresh stopped-writer backups and on-disk restore rehearsals for the primary,
  external journal and other affected stores. Keep the original paired copies.
- Run the bounded migration review/apply, with fresh native preservation checks.
  No feature flag, private search index, semantic provider or face assignment
  changes belong in this operation.
- Preflight and run the exact pinned worker for the selected libraries. Verify its
  process envelope, stop path, derived rows, original/task/history preservation and
  exclusion from other library scopes before deciding recurring-task settings.
- Restart only the approved incumbent API/worker states. Verify HTTPS and existing
  OTA feeds, v2 gallery negotiation, all member assets, both accounts' private
  choices and fallback when an index is absent. Physical phone testing follows its
  separately delivered APK.
- On ownership drift or uncertain dispatch, inspect durable receipts; do not
  blindly replay. Hold only operation-owned workers as the recovery plan requires.
  Do not restore production databases as routine rollback. Populated f2 tables
  intentionally refuse downgrade; recovery needs a reviewed forward/restore plan.

## Evidence boundaries

The earlier native rehearsal proved the preceding generated candidate and its
ten cases. The guarded-controller and one-sweep candidate at source `094435d`
subsequently passed all twelve generated cases on Windows, with independent
readback of all 258 unchanged source inputs. That operation did not activate any
production schema, task or service. Retain the exact input/report hashes when
carrying this evidence forward; changed launcher or companion code needs its own
qualification. A new package target does not itself requalify its runtime.

Unit tests, extracted-package checks and native generated fixtures do not establish
production quiescence, real-data similarity quality, family usability, production
restore/replay or power-loss recovery, or deployment completion.
