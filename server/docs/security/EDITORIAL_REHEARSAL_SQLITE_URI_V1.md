# Editorial rehearsal SQLite URI admission

The October 5 139-case Windows attempt stopped in group 1: 47 collected,
44 passed, three failed. The failures occurred at the audit hook for
`sqlite3.connect`, after private journal storage was accepted. Each rejected
URI selected a generated journal inside that attempt's candidate directory.
Groups 2–8 did not run. Staging, the owned descendant timeout canary and the
fresh offline environment passed; no household database or service was changed.

The old guard removed the `file:` prefix and passed `///C:/...` to native
filesystem resolution, which does not represent the intended local drive.
SQLite specifies that `/X:/` at the start of an absolute URI path selects a
Windows volume. The repaired guard parses the URI, decodes its path once and
removes that single leading slash only for the Windows drive form before
resolving the native path against the candidate root. POSIX paths retain it.
See [SQLite's URI path rules](https://www.sqlite.org/uri.html).

The guard accepts blank or `localhost` authority and the supported `mode`,
`cache` and `immutable` options. It rejects remote authorities, drive-relative
URIs, duplicate/unknown options, malformed escapes, invalid UTF-8, controls and
URI backslashes. Encoded traversal, sibling-prefix paths, other volumes and
symlinks outside the root remain outside the candidate. Auxiliary VFS/file
options such as `modeof` are excluded from this rehearsal. Memory database
admission recognizes the exact decoded `:memory:` filename.

Twelve focused tests cover Windows drive conversion without Windows filesystem
access, native generated paths, single percent decoding, Unicode, traversal,
authorities, options and symlink escape. Existing audit/socket/Job controller
tests remain separate. The tests open no database or model. The source builder
includes this suite and the runner adds it as the ninth fixed group, making
the successor 151 cases. Local passing tests are not native qualification.

The failed candidate, its authority, intent and result remain unchanged. A
successor needs a new directory, pinned source/payload and actual operation
authority; no guard fix retries the spent attempt. The application's API and
worker delivery packages are not altered by this rehearsal-only repair.
