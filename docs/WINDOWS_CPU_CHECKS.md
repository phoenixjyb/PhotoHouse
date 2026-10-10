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
