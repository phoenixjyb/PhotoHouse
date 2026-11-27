# Operations and release boundaries

This is the portable workflow and evidence map, not a household launcher or an
instruction to execute a service change. Windows owns live data, models and GPU
runtimes; the source checkout contains application code, contracts and tools.
[Project Status](PROJECT_STATUS.md) is the dated installation snapshot.

## Current operating reference

[October 29 release](RELEASE_2026-10-29.md) records the Windows main/UI/voice
rollout and 15-minute SYSTEM photo-stack refresh. It is dated evidence, not an
instruction to restart a service or reuse an old claim. The October 29 work
window is closed; production services were retained and experimental cleanup
completed. Physical microphone/speaker testing was deferred by the user.

GitHub Actions remains cost-paused. Use local checks and [the CI policy](CI.md);
this documentation task authorizes no push, deployment, migration or task change.
Keep rollback available until actual API, Search, grouping and refresh checks pass.

## Release sequence

1. **Pin source and artifacts.** Record repository/branch/commit, clean/dirty state,
   API manifest, [canonical package inspection](API_PACKAGE_INSPECTION.md), APK profile and Android subtree. A docs commit is not a rebuilt
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

## Shorter Windows cutovers

The November 27 Jude rollout took 35 minutes 35 seconds. Roughly 23 minutes
elapsed between the successful new-API check and the scheduled grouping run.
The launcher also recorded 134.6 seconds for its startup playback check and
the controller spent three minutes verifying cleanup. The records did not
measure the stop-to-ready outage separately. The old launcher bound static UI
files at API startup, so even a compatible UI package followed the API switch
and grouping sequence.

### Static UI releases

The optional live UI selector separates compatible Web assets from the API
process. Install it once in the protected API launcher by calling
`bind_live_access_ui_overlays(ui_module, release_root, expected_api_commit=...)`
before the listener starts. Use a private, direct Windows release directory on
D: that only the deployment identity can write and that the API identity can
read. Initialize the selector with the current qualified UI first. Keep the
existing API manifest and grouping-worker identity in the startup controls.
This path still needs qualification on Windows before enabling it there.

1. Build the candidate with `server/scripts/build_access_ui_overlay.py` from
   its full commit. Stage the verified package in a new subdirectory named by
   its manifest SHA-256, then check the changed behavior before selection.
2. Run `server/scripts/select_access_ui_overlay.py` with the release root,
   exact running API commit, candidate UI commit, candidate manifest SHA-256,
   and current manifest SHA-256. It refuses changes to application code outside
   the approved asset set, staged bytes that differ from Git, and concurrent
   or stale selections. Initialization uses `--expect-current none`.
3. Check HTTPS, the uncached shell, the referenced hashed assets, and the
   changed signed-in behavior. The API process keeps serving and retains the
   preceding asset version for clients using the old shell. Roll back by
   selecting the prior verified manifest, using the failed selection's digest
   as the expected current value. Retain the prior package for this rollback.

### API and worker releases

Prepare and validate artifacts while the incumbent serves. Record the times
for stopping the old API, binding the new listener, passing HTTPS and the
changed-feature check, observing scheduled jobs, and closing the deployment
process. Report when the API is serving and when scheduled jobs are verified as
separate milestones. If grouping's binding changes, retain its protected
transition, natural-run verification and rollback. A schema/data change
continues to require its matching writer fence and backup.

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

## Browser access on the home network

Use the same HTTPS PhotoHouse URL on the home network and away from home. On a
router or local DNS server you manage, point the existing PhotoHouse hostname at
the Windows server's LAN address. Home devices that use that DNS server can
then connect directly while keeping the same sign-in and certificate hostname.

An operator can check the direct route before changing DNS. Replace the example
values with the already configured hostname, HTTPS port and LAN address.

```sh
curl -q --noproxy '*' --fail --connect-timeout 5 --max-time 15 \
  --resolve 'photos.example.net:8443:192.168.1.20' \
  'https://photos.example.net:8443/ui'
```

Open the regular PhotoHouse URL on a phone or tablet after the local DNS change
and confirm that it resolves to the LAN address on that network. Certificate
validation should succeed throughout. Removing the local DNS record restores
the normal hostname resolution for that network.

## Reviewed video moments

The protected staging launcher can load an operator-reviewed video-moment
catalog alongside prepared playback. Leave the catalog flags unset to keep
moment search off. Set both `--video-moment-catalog` and
`--video-moment-sha256` alongside the existing `--prepared-index`,
`--prepared-root` and `--prepared-sha256` flags to select an exact catalog.

Use a direct private file outside the application config, prepared media,
originals and database. The UTF-8 JSON object has `version` set to `1` and a
`moments` array with up to 32 reviewed rows. Each row contains the numeric
`asset_id`, `label`, `start_sec` and `end_sec` in playback seconds, and the
matching prepared entry's `source_identity`, `duration_ms` and
`playback_sha256`. The catalog may occupy up to 64 KiB. `--check-config`
validates flag syntax and path separation. `--serve` verifies the catalog
hash and prepared-entry bindings before opening the listener. Only current
library members with playback access can retrieve an interval. Treat catalog
replacement as a new reviewed configuration.

## Reboot, tasks and workers

The October 29 rollout preserved existing task contracts and verified the new
SYSTEM refresh after selection. Earlier v58/October 14 startup and worker counts
are historical, not a current process inventory. Home TV has
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
