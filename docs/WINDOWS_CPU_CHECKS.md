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

The command is portable; its local Mac run passed 64 tests and 25 subtests.
Running it on a Mac is not Windows evidence. The separate `windows-cpu` job in
the public source workflow runs this cohort on `windows-latest` with a fresh
hash-locked installation and a 15-minute job limit. Its native result belongs
to the exact hosted commit, independently of the existing Windows private-reader
job, full Ubuntu API profile and Android profile.

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
