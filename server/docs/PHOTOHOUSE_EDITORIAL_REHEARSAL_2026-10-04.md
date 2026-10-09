# Reproducible memoir rehearsal

The rehearsal tools prepare and qualify synthetic source in a disposable folder.
They do not deploy an API, switch a task, enable editorial processing, or open a
family database. Native staging and execution need authority for the concrete
operation and a reviewed, privately pinned operator.

## Complete source closure

The previous 213-file offline archive is preserved. Tests run from the complete
checkout did not establish its extracted fixture closure: it omitted four test
fixtures imported by the editorial cases:

- `test_memory_stories.py`
- `test_library_reads.py`
- `test_access_foundation.py`
- `test_original_deletion_integration.py`

`scripts/build_editorial_rehearsal_package.py` reads only pinned Git blobs. It
checks the exact reviewed baseline archive digest, expands local `test_*` fixture
imports, includes the separate editorial dependency lock and rehearsal tools,
and writes only to a new absolute output. The resulting archive has a per-file
SHA-256 manifest and explicit runtime/publication-off boundaries. Qualification
must use the extracted archive, not the original source checkout.

```sh
python scripts/build_editorial_rehearsal_package.py \
  --repo /absolute/source/repository --commit FULL_ACCEPTED_COMMIT \
  --baseline /absolute/prior/source-b1-offline.zip \
  --output /absolute/new/source-rehearsal.zip
```

The baseline archive is a locally retained review input; it is not included in
public source. Future maintainers may review a new source allowlist, but should
not silently remove the digest check or reuse an earlier execution intent.

## Fixed synthetic groups

Use the [isolated CPU test environment](PHOTOHOUSE_EDITORIAL_TEST_PROFILE_2026-10-04.md),
with no inherited server configuration or model paths. Create an empty results
directory alongside the extracted source. Each invocation runs a fresh process:

```sh
python -I -B /absolute/candidate/source/scripts/run_editorial_rehearsal_group.py \
  --source /absolute/candidate/source --output /absolute/candidate/results --group 1
```

Repeat groups 2 through 6. Unlike a bare isolated pytest invocation, this wrapper
explicitly adds only the candidate backend and test-fixture import paths. It
disables dotenv and automatic workers, directs SQLite defaults and temporary
files into the candidate, and refuses Python-audited external network access or SQLite
connections outside that candidate. Windows asyncio requires the stdlib TCP
socketpair for internal wakeups: a thread-scoped guard allows only an ephemeral
loopback bind and a connection to that same listener, never an arbitrary local
or household endpoint. The actual Windows 3.12 stdlib fallback was checked
read-only. This audit check is not an OS sandbox and
does not qualify arbitrary untrusted code. The frozen source and clean child
environment remain required.

Each group writes an exclusive result directory, JSON counts and a JUnit report.
Success requires zero failures/skips, a zero pytest exit status and exactly
47 / 12 / 8 / 14 / 7 / 15 collected tests. Retry by preparing a new results root;
never overwrite or merge evidence from an earlier run. The complete extracted
fixture source passed all 103 tests through this wrapper on macOS CPython 3.12.
Those results do not prove Windows execution.

## Windows resource and cleanup controller

`scripts/bounded_windows_job.py` is an import-only native helper. An authorized
operator supplies the exact executable, argument vector, clean Unicode environment
and working directory. Children start suspended; job assignment and limit readback
precede resume. Only the NUL standard handle is inherited. The helper requires the
single owned suspension, waits for the parent and every descendant, terminates
only its owned job/process handles on failure, and reports cleanup/close failures.
It never scans or terminates unrelated processes by PID.

Default limits are 2 GiB aggregate committed job memory, 16 active processes and
an 8 GiB free-RAM floor. These are not GPU/VRAM limits. The native operator must
also enforce the overall deadline and reject failed group receipts. See
[Microsoft Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)
for inheritance and kill-on-close semantics. Fresh virtual environments should
be created on the target using the pinned base Python rather than copied from
another platform; see [Python venv](https://docs.python.org/3.12/library/venv.html).

Eighteen portable controller/guard tests passed, covering suspended assignment,
timeout, residual descendants, partial creation, low RAM, handle-close failure (including an unreturned suspended child),
environment binding and network/database denial. They do not execute Win32 jobs.
Read-only native ABI inspection likewise cannot replace a bounded timeout/child
canary and actual synthetic tests on Windows.

## First native attempt and fixture correction

The authorized October 4 attempt passed private staging, the real timeout /
descendant cleanup canary, fresh Windows venv creation, hash-checked offline
installation and exact environment inventory. Group 1 collected 47 cases and
stopped with 14 failures; groups 2–6 were not started. All failures originated
in the preexisting fixture mock that prohibited `socket.bind` during Windows
asyncio's internal stdlib TCP socketpair. This does not establish native
editorial acceptance. Preserve the failed candidate and its execution intent.

`test_network_guard.py` replaces only the fixture bind/connect mocks with a
thread-scoped socketpair allowance. It calls saved real methods for one
ephemeral loopback listener and its exact peer. Normal connections, a second
listener and other threads remain denied; exception/nesting cleanup restores
previous mocks. Process and shell execution mocks remain in the two fixtures;
the rehearsal's independent database/network audit remains active. Six portable
regressions passed, including IPv6's omitted zero scope/flow fields. The adjacent
foundation/library checks passed 48 tests and 17 subtests on macOS. Native
acceptance requires a newly reviewed candidate and operation authority.

The readback also found four synthetic temporary objects carrying Windows
`OWNER_RIGHTS` alongside Administrators and SYSTEM, with trusted Administrator
ownership. This arises from secure temporary-directory creation, not a family
access grant. A successor ACL verifier must accept that precise temporary
pattern while retaining strict root/source/wheel ACLs and rejecting all other
identities. It must not change permissions on the preserved failed candidate.
See [Python mkdir](https://docs.python.org/3.12/library/os.html#os.mkdir) and
[Microsoft OWNER_RIGHTS](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-dtyp/81d92bba-d22b-4a8c-908a-554ab29148ab).
