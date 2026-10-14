# Operations and release boundaries

This is the portable workflow and evidence map, not a household launcher or an
instruction to execute a service change. Windows owns live data, models and GPU
runtimes; the source checkout contains application code, contracts and tools.
[Project Status](PROJECT_STATUS.md) is the dated installation snapshot.

## Release sequence

1. **Pin source and artifacts.** Record repository/branch/commit, clean/dirty state,
   API manifest, APK profile and Android subtree. A docs commit is not a rebuilt
   package; source, package and served identities may differ deliberately.
2. **Qualify offline.** Use [CPU/Web/Android profiles](DEVELOPMENT.md), exact
   extracted-source and native synthetic checks. Provider inference/resource and
   human-quality qualification are separate from package validation.
3. **Prepare the exact operation.** Inventory task actions/settings/triggers,
   processes and ownership; bind paths and hashes; prepare fresh private stages,
   stopped-writer backup, verification and rollback. Refuse drift or reused stages.
4. **Obtain operation authority.** Service/task changes, schema/data changes,
   original-certificate signing and public OTA publication each need their stated
   scope. Reuse a grant for its covered steps and necessary guarded recovery.
5. **Fence writers and back up.** For an API/database switch, stop only identified
   writers, verify they stopped, and make/verify a fresh paired backup of all affected
   stores. Synthetic backup rehearsal is not a live stopped-writer backup.
6. **Switch and verify.** Change only the authorized action/config/schema. Preserve
   task triggers and settings. Verify listener identity, trusted served bytes,
   anonymous denials, feature/schema gates, OTA feeds and rollback behavior.
7. **Restore and observe.** Restore writer definitions and running states. Retain
   old immutable releases and failed records. Confirm the family/device experience
   separately before treating delivery as product acceptance.

## Data and recovery inventory

| State | Recovery requirement |
| --- | --- |
| Primary SQLite | Matched schema and stopped writers; verified backup and deliberate migration/restore |
| Family original text/audio and original media | Preserve raw source, identity and attribution; do not replace it with a derivative |
| Original-deletion journal | Independently durable identity/sequence and matching replay evidence; an old primary restore must not resurrect withdrawn access |
| Assistant receipt journal | Separate 30-day troubleshooting data; unavailable receipts do not authorize replay of committed effects |
| Private assistant workspace | Independent format/revision, account ownership, requests/context and 30-day retention; paired native backup/admission |
| Derived previews/videos/vectors/indexes | Exact source/provider/preprocessing identity, checkpoint/publication closure and no-overwrite recovery; incomplete output is not ready |
| Model installations and secrets | Separate runtime inventory/lock/checkpoint/license identity; never include weights or secrets in a source ZIP |
| OTA APKs and pointers | Original certificate, exact bytes/hash/channel; atomic phone/TV pointer handling and guarded rollback without clobbering a newer publication |

Consult [source packaging](SOURCE_PACKAGING.md), [native assistant qualification](PRIVATE_ASSISTANT_NATIVE_QUALIFICATION.md),
[model qualification](MODEL_QUALIFICATION.md), [video recovery](VIDEO_SOURCE_RECOVERY.md),
[asset withdrawal](ASSET_WITHDRAWAL_LIFECYCLE.md),
[vector erasure](VECTOR_ERASURE_LIFECYCLE.md) and the relevant schema/journal
contracts before preparing a specific operation. Backups of one SQLite file do
not establish recovery of the complete multi-store system.

## Reboot, tasks and workers

The v58 deployment preserves the approved 30-second API startup trigger. The
October 14 snapshot shows five upload workers and ASR/TTS running. Home TV has
an interactive desktop dependency and was Ready; feed/APK publication does not
make that media listener available. Validate the relevant identity and startup
path after reboot rather than starting every old task.

Workers claim only their supported approved tasks under configured limits. Resume
unfinished conversions without scanning/re-encoding already-ready outputs; keep
failed-source evidence. Queue counts, free RAM and GPU residency require fresh
observation and are not durable architecture facts.

## Portability gap

The public source contains portable package, configuration, queue and qualification
primitives. This installation's signing/cutover/rollback controllers and exact
host/task identity receipts remain private operator artifacts. A clean clone is
not yet a one-command household deployment. Converting those controllers into
reviewed generic tools is an explicit [roadmap](ROADMAP.md) item; it must preserve
one-use claims, private ACLs, admission limits, task ownership, rollback and paired
store recovery. Do not copy private controllers verbatim into public Git.
