# Development storage admission

New bulk development outputs on native Windows must use a fixed local data
volume, with D: as the default. Live runtime paths are a separate operational
contract. This policy does not move existing data, activate a runtime, change
models, or permit service/task operations.

## Integrated producers

`server/backend/app/work_storage.py` is the shared policy. These entrypoints use
it directly, including calls to their snapshot/rehearsal and packaging functions:

- `server/scripts/rehearse_fullsize_database.py`: snapshot and rehearsal;
  the rehearsal budgets both candidate and restore copies before reading data.
- `tools/package_source.py`: Git archive, rewritten archive and publication
  overlap, based on source sizes and ZIP/header allowances.
- `server/scripts/build_staging_package.py`: the CLI admits the complete API
  archive before creating its output. The in-memory archive builder does not
  allocate disk output.
- `server/scripts/build_editorial_rehearsal_package.py`: archive size plus ZIP
  and manifest allowances. New packages include the policy and private ACL helper.
- `server/scripts/run_editorial_rehearsal_group.py`: requires an explicit
  `--max-work-bytes` for all generated fixtures, runtime and temporary data.

Omitted package/snapshot output paths use a new UUID directory under
`D:\PhotoHouseWork\runs`. A rehearsal without an explicit restore path uses
`restored.sqlite` beside its new candidate. An explicit `PHOTOHOUSE_WORK_ROOT`
may select another suitable data volume. An unavailable or unsuitable root
refuses; there is no fallback to the system drive or ambient temporary directory.

Explicit outputs still require an existing private parent. Every existing path
component is checked before resolution can hide a junction. System-volume
identity comes from Windows volume APIs, not a caller-supplied drive letter.
Network/device paths, reparse points, unsafe Windows names, escapes and output
collisions refuse before payload allocation. Native Python 3.12.4 or newer is
required to create restricted Windows directories; actual owner/DACL checks
verify privacy before payload writes.

## Peak space and closure

Plans aggregate components by actual volume and add a 1 GiB reserve per volume.
Database operations use their explicit maximum database size for each copy,
journal and sort/temporary allowance. A later restore phase checks free space
again. Source reads and live WAL growth are not a new database-copy destination.

On Windows, integrated bulk operations hold a nonblocking per-volume lock under
`<volume>\PhotoHouseWork\admission`. A competing process refuses rather than
claiming the same free space. Nested operations in the owning thread reuse its
lock. This lock coordinates these producers; unrelated software can still consume
space. The policy is admission control, not a filesystem quota or sandbox for
arbitrary programs. Producers must retain their existing size/resource limits.

During an operation, TEMP/TMP/TMPDIR/SQLITE_TMPDIR and Python's temporary-directory
selection point at private scratch on the admitted volume. Prior process values
are restored on exit. No global or live-service environment is edited.

Private per-operation receipts retain UUID, state, output mapping, planned
components/reserve and aggregate final bytes. Normal closure records `closed`;
exceptions, interrupted work and final over-budget output record
`failed_uncertain`. Partial outputs are retained. A hard process termination may
leave a `running` receipt; process exit releasing the lock does not prove closure
or permit archival. Recorded bytes describe that observation, not current disk
usage. No automatic archive/deletion command is installed.

## Native entrypoint and installation

Use the existing development venv; no new dependencies or weights are needed:

```powershell
.\.venv\Scripts\python.exe -B tools\windows_work.py install
```

The installer prints a private versioned launcher under
`D:\PhotoHouseWork\tools\storage-policy-<digest>\PhotoHouse-Work.ps1`.
It is linked to the current checkout and existing development Python. Each launch
verifies pinned policy/producer/Python hashes. Source changes require review and
a new installation; the launcher never silently follows changed code.

The launcher supports `snapshot`, `rehearse`, `package-source`, `api-package`,
`editorial-package`, and `editorial-group`, forwarding each producer's arguments.
It also supports:

```powershell
# Read-only admission; the output's private parent must already exist.
.\.venv\Scripts\python.exe -B tools\windows_work.py plan `
  --output D:\PhotoHouseWork\runs\example-output `
  --component database=1048576 --component restore=1048576 `
  --component temporary=2097152

# Receipt summary only; never infers that an operation is disposable.
.\.venv\Scripts\python.exe -B tools\windows_work.py report
```

## Remaining conversions and acceptance boundaries

This is the first storage milestone, not universal prevention of C: growth.
The ordinary `tools/check.py` launch environment, Android/package-manager caches,
downloads and POSIX agent-probe scratch still need integration. Existing shared
tools/models require version/hash/layout verification before reuse; this change
does not download or relocate them.

Historical qualification packets and C:-bound private SYSTEM task launchers are
immutable and have not been relabeled or executed. Their successor plan generator
and consumer must be updated together with D: paths, ACLs, budgets and exact
producer/source bindings before claiming installed qualification enforcement.
Use an isolated frozen candidate to inspect older source; do not package a dirty
working tree as if it were the frozen commit.

Dependency-aware archival and a fresh remaining-C: inventory are later milestones.
Current runtime, known-good rollback, failed/uncertain operations and retained
dependencies remain protected. GitHub Actions stays disabled; installation and
generated-file tests do not authorize production operations.
