# Generated Windows CPU checks

Use the existing Python 3.12 development environment and hash-locked development
requirements, then run:

```sh
python tools/check.py windows-cpu
```

This optional profile checks database preparation, full-size preparation,
runtime configuration, extracted API source packages and approved-worker source
packages. It uses generated temporary databases and media, fake providers and
the ordinary CPU test environment. Inherited database/provider/plugin settings
are excluded. It loads no model, opens no listening service, contacts no
production endpoint and starts no scheduled task.

The command is portable; its local Mac run passed 65 tests and 25 subtests.
Running it on a Mac is not Windows evidence. The separate `windows-cpu` job in
the public source workflow runs this cohort on `windows-latest` with a fresh
hash-locked installation and a 15-minute job limit. Its native result belongs
to the exact hosted commit, independently of the existing Windows private-reader
job, full Ubuntu API profile and Android profile.

The first native run at `9154e59` found two fixture portability defects: its
network guard prevented Windows asyncio from creating its internal socket pair,
and one failed-backup check interpreted Windows mode bits as POSIX permissions.
The adapter fixture now initializes a shared test portal before installing the
guards; application socket binding and connecting remain explicitly forbidden.
POSIX mode assertions apply only on POSIX hosts. Windows ACL qualification of
the installed backup directory remains a private deployment check, not a claim
made by this generated cohort.

## What it establishes

- Generated a0 database preparation uses that revision's required tables.
- Generated runtime configurations preserve explicit opt-ins and refuse invalid
  settings before constructing optional adapters.
- An immutable extracted API package imports its current operator closure in a
  fresh child process.
- Worker source packaging retains exact file allowlists and commit selection.

## Remaining native delivery checks

The public runner has neither the household Windows installation nor its
private media, models, database, task definitions or Python environment. This
profile does not qualify GPU inference, real video conversion, filesystem/ACL
bindings in that installation, worker recovery or an API switch. Those need
the exact private package, pinned installed configuration, bounded native
qualification, current resource admission and operation authority.

`tools/check.py all` continues to run the API and Android profiles. Web browser
checks and this smaller Windows-oriented cohort remain explicit choices.
See [development checks](DEVELOPMENT.md) and
[source packaging](SOURCE_PACKAGING.md).

## Optional memory-group upgrade qualification

The generated CPU cohort also checks the e7 qualification runner's refusal,
backup and bounded-controller contracts. A Mac result is portable source
evidence. The separately invoked API-package runner accepts no live database
or media root:

```sh
python -I -B scripts/qualify_memory_groups.py --out <new-absolute-private-output>
```

After operation authority, use the pinned Windows interpreter and an extracted,
manifest/hash-checked candidate package. Its existing output parent must have a
private inheritable DACL. The native CLI supervises only generated fixtures,
with 15 minutes, 2 GiB Job memory, four processes and an 8 GiB free-RAM floor.
Review `qualification-report.json` and its retained generated databases; a fixed
success report is required. Preserve failed candidates and their safe receipts.
The [full contract](../server/docs/security/MEMORY_GROUPS_V1.md#generated-upgrade-qualification)
lists the exact cases and intentionally damaged audit-only fixture. Upload
workers, vectors, installed providers and live migration remain separate gates.

## Optional vector cleanup qualification

The separate [generated vector qualification runner](VECTOR_ERASURE_LIFECYCLE.md)
is included in the pinned API source package. It is not automatically run by
`windows-cpu` or enabled as a service. The ordinary API source tests check its
generated cases and supervisor arguments on the host which runs that profile.

After review and operation-specific authority, extract the exact hash-checked
package into a new private candidate directory and invoke its
`scripts/qualify_vector_erasure.py --out <new-absolute-directory>` with the pinned
Windows Python interpreter and isolated `-I -B` flags. The output's existing
parent must have a private inheritable DACL; the runner verifies created children
with the native private-storage check and does not change existing ACLs. Do not
point it at a database or media root; those arguments do not exist.

Use a short candidate directory and output name. Before creating fixtures or
launching the child, the runner checks every known generated filename, SQLite
sidecar, directory and launch path against the legacy Windows path limits,
counting UTF-16 units. It does not depend on or change `LongPathsEnabled`.
A long destination refuses with `windows_fixture_path_too_long` before any
output is created. Keep a failed candidate intact and prepare a fresh destination.

If a fixture fails after this run creates its output, it attempts to retain
`qualification-failure.json` there. The receipt contains only a fixed phase,
allowlisted exception class and numeric Windows error code, with synthetic-only
status. It never contains exception messages, tracebacks or private paths.
The supervisor validates the bounded receipt before surfacing it on failure;
a missing, malformed or unwritable receipt never turns failure into acceptance.

The Windows CLI supervises a generated child for at most 15 minutes, with a
2 GiB Job limit, four-process cap and 8 GiB free-RAM admission floor. Review the
complete exit/report and retained generated files. A pass establishes only the
named process-crash, file binding, private-directory and catalog restore cases
for that package/filesystem. It does not establish power-loss durability,
installed producer/model qualification, task reconciliation or live cleanup.

## October 11 memory-group native result

The approved generated e7 qualification passed on Windows:

| Binding | Value |
|---|---|
| Source commit | `665bed58650aafcd31ec8569976e0b2111da226c` |
| API ZIP SHA-256 | `3740c5121a9027b44b690678480dc653327802516638e90f1e99621839f10e45` |
| Report SHA-256 | `e2d9e71f950886c236c7939fd245e0f187846467abd17a52fea4bf3125f88c64` |
| Source files verified | 180 before execution and during independent readback |
| Generated upgrade | `d1f6a8c3e920` → `e7c1a9d5b304` |
| Bounded child profile | 15 minutes, 2 GiB Job memory, four processes, 8 GiB free-RAM floor |

All five named cases passed: injected DDL-interruption rollback, additive
preservation, original-note attribution and group retry, pre-/post-group backup
restoration, and nonempty downgrade refusal. The Windows interpreter/package
identities and absent destinations were checked before staging; the existing
interpreter was retained. Only new private candidate/transfer directories and
generated fixtures were written.

Independent read-only inspection checked the complete report and six generated
databases. The five healthy files pass integrity and foreign-key checks. The
restored d1 backup matches its 56-table schema and rows; the restored e7 backup
matches its 58-table schema and rows, including one group, two group revisions,
the edited original note and original attribution. Upload receipts, pending
task and caption remain intact. Both restored backup files also match their
respective saved file digests.

The sixth file deliberately removes the current group while retaining two
orphaned history rows. It has exactly the two expected foreign-key violations;
the downgrade still refuses and retains those rows. It is an intentionally
damaged refusal fixture, not a healthy restore result.

The first independent readback launcher exceeded Windows' command-line length
limit. Its failed receipt remains retained. A hash-checked readback script and
short launcher completed the same read-only verification; the qualification
was not rerun. No production database, family media, installed worker/model,
service, task or APK feed was changed. Native companion-worker execution,
installed vector provenance/coverage, guarded live migration/backup planning,
activation, phone release and family acceptance remain delivery gates.

## October 11 vector catalog native result

The explicitly approved corrected synthetic run passed on Windows:

| Binding | Value |
|---|---|
| Source commit | `b8f103be05c02965b087172893ee3b8a42b475c5` |
| API ZIP SHA-256 | `bb44437d1b1c723ae0cedf020303a39b1982d5e17b3ead7f63ba703621c90c7e` |
| Source files verified | 172, before execution and during readback |
| Report SHA-256 | `d3a8333f392d07e5bae257bca7a19c82058d3e9fb3c19feb07c246187878ac97` |
| Limits | 900 seconds, 2 GiB Job memory, four processes, 8 GiB free-RAM floor |
| Longest generated vector path | 246 UTF-16 units; no host registry change |

Native PowerShell parsing and package/interpreter identity checks passed before
execution. The normal isolated CLI used the verified Windows Job supervisor,
exited with code zero and produced `native_windows=true` and `source_only=true`.
Independent readback checked private storage, the exact source/report digests and
the known synthetic SQLite/catalog/filesystem outcomes:

| Generated case | Readback outcome |
|---|---|
| Complete manifest and process death after quarantine linking | Both known vector names and quarantine names absent; progress 2 of 2 |
| Older-primary withdrawal replay and archived closure restoration | Restored artifact/publication metadata and cleanup job; progress 2 of 2; both vector names absent |
| Corrupt quarantine refusal | Both vectors and corrupt quarantine retained; progress stayed 0 of 2 |

Every generated original retained its exact bytes. Catalog readback verified each
full immutable plan. Synthetic databases were opened read-only for inspection;
the failed earlier candidate and both runs' evidence remain retained privately.
No live database, original media, model, scheduled task or service was changed.
The result reports `models_loaded=false`, `services_changed=false` and
`power_loss_qualified=false`. This closes only the three named native generated
cases. Additive schema/restore compatibility, independent catalog backups,
installed producer/model qualification, interrupted task reconciliation and any
real cleanup still require their own evidence and authority.

## Guarded full-chain and companion worker candidate

The API package now includes `scripts/qualify_memory_group_workers.py` and the
CPU/video worker closure. Its only inputs are a new private output directory and
explicit existing ffmpeg/ffprobe binaries:

```sh
python -I -B scripts/qualify_memory_group_workers.py \
  --out <new-private-directory> --ffmpeg <direct-ffmpeg> --ffprobe <direct-ffprobe>
```

The mandatory Windows supervisor caps the entire process tree at 900 seconds,
2 GiB and eight processes, with an 8 GiB free-RAM admission floor. It generates
all media and databases. It checks the guarded a0→e7 chain, interrupted full-chain
rollback and immutable backup, then d1→e7 approved CPU/video preparation,
decoded JPEGs, exact task counts/asset bindings, pending inference queues, source
and approval preservation, SQLite integrity and foreign keys. No model runs.
Portable worker tests mock native worker subprocesses, so a passing local suite
is not a native worker result. The earlier native d1 qualification above does
not qualify this new full-chain guard or companion execution. See the
[guard contract](../server/docs/security/MEMORY_GROUP_SCHEMA_APPLICATION.md).

## October 11 full-chain and companion native result

The approved candidate at `18eb1cc415771977c95dff8513cd176d07f6310d`
passed one Windows generated qualification and a separate read-only verification.
The qualification was not rerun.

| Binding | Value |
|---|---|
| API source ZIP SHA-256 | `ddb7b46afbb0a4e74ebbc88006577ca023016cfd7067b83171f036766380a650` |
| Companion source ZIP SHA-256 | `7f500f99b3cc5262bd924dc0792ac78106dedc8662053b6f0306f116c2a61f32` |
| Report SHA-256 | `145316b26e4dc3fdb42686c52e10e4ebbb5c1ed75d63e32f8e4ec30c0faee09b` |
| Source readback | 185 API files and 33 companion files; 17 shared paths have identical bytes |
| Native limits | 900 seconds, 2 GiB Job memory, eight processes, 8 GiB free-RAM floor |

The actual guarded a0→e7 upgrade preserved all old rows and objects and added
nine empty tables. An injected interruption during d1 rolled back the complete
chain, including earlier editorial/edition DDL. The separate backup retained
its bytes; independent readback compared the backup schema and rows
against the upgraded generated primary.

A separate d1→e7 generated image/video fixture ran the actual thumbnail,
perceptual-hash, video-probe and keyframe worker CLIs. Both JPEG thumbnail sizes
and four JPEG keyframes decoded. Readback confirmed six exact task rows: four
finished preparation tasks and two pending inference tasks, with correct asset
bindings. Both original files retained their database hashes, the original note
retained its wording and author, and one group with two revision rows remained.
All three generated databases passed integrity and foreign-key checks.

The result reports no family media or production database access, model loading,
GPU work, service change or APK publication. Injected DDL interruption does not qualify process death or
power loss. This closes the named synthetic guard and CPU/video
worker cases. It does not qualify installed model workers, automatic vector
coverage, a live backup/restoration, live schema/worker/API activation or family
and device use. See the [maintenance sequence](../server/docs/security/MEMORY_GROUP_SCHEMA_APPLICATION.md).
