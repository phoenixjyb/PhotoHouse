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

The Windows CLI supervises a generated child for at most 15 minutes, with a
2 GiB Job limit, four-process cap and 8 GiB free-RAM admission floor. Review the
complete exit/report and retained generated files. A pass establishes only the
named process-crash, file binding, private-directory and catalog restore cases
for that package/filesystem. It does not establish power-loss durability,
installed producer/model qualification, task reconciliation or live cleanup.
