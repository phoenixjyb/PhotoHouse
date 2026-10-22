# Selected-story native process owner

The [process owner](../server/backend/app/access/selected_story_native.py) is an
explicit, default-off primitive for one private native story process tree. The
[Windows factory](../server/scripts/selected_story_native_owner.py) reuses the
existing [Windows Job kernel](../server/scripts/bounded_windows_job.py). Import
and default construction perform no process, network or model work. No app
setting, route, environment switch or default provider selects this owner.

## Ownership and cancellation

The host supplies an immutable launch description: absolute executable and
working-directory paths, expected SHA-256, bounded arguments, explicit copied
environment, memory/process limits and minimum available RAM. Only the opaque
operation UUID is appended to the environment. Source text and generated words
are never retained by this owner or added to its launch arguments/environment.
The host must not place family content or secrets in the launch configuration.

`begin(scope)` accepts the exact host `PreparationScope` with a canonical UUID
and finite deadline. One owner permits one unsettled launch, uses one event loop,
and retains its native handles and launch task even when the awaiting caller is
cancelled. Launch checks cancellation between native steps. The Windows kernel
creates the root suspended, assigns it to a private verified non-breakaway Job,
and resumes it only after assignment. It does not adopt an existing PID or stop
a process by name. Job limits bound host memory and process count, not VRAM.

`stop_and_reconcile(scope)` accepts only the original scope object. It stops the
private Job, or the owned root if assignment failed before resume. Success needs
both root exit and zero Job members, followed by successful handle closure.
A termination acknowledgement, root exit alone, empty Job alone or completed
Python waiter does not prove cleanup. Cleanup polling is bounded (five seconds
by default, maximum ten); a blocked native launch remains retained and must not
be mistaken for a timed-out-and-forgotten operation.

Cleanup tasks survive cancellation of their waiters. False proof permits a later
reconciliation attempt while retaining the same ownership; it does not permit a
new launch. Unknown/partial creation receipts stay unproven. An uncertain handle
close is sticky: closing the same possibly recycled handle again is refused.
`close()` closes admission and reconciles the active scope. The host must own
this shutdown path; it is not automatically installed into the app.

Through the existing operation/provider contract, uncertain cleanup keeps the
shared inference permit held and quarantines admission. Later exact proof can
release capacity but cannot publish fenced words or reset sticky quarantine.
Constructing a new owner or gate is not recovery proof.

## Provider binding is still a gate

This owner's `proof_domain` is `owned_process_tree`. It proves only termination
of the process containment it actually created. The
[HTTP adapter](SELECTED_SOURCE_STORY_LOCAL.md) explicitly refuses this primitive
as its direct native owner. An arbitrary loopback model endpoint may run outside
that Job or forward elsewhere. Emptying this Job cannot prove that endpoint's
inference stopped.

The [default-off process provider](SELECTED_SOURCE_STORY_PROCESS_BINDING.md) now
binds a bounded private file exchange to this owner and reconciles it on success,
cancellation, expiry, logout and shutdown. It has synthetic source acceptance;
a production model worker, Windows IPC/containment and native inference still
require separate qualification. It does not change the HTTP adapter restriction.
Keep the prepare API, Web UI, local adapter and native owner default-off pending
that qualification and a separate activation decision.

The executable digest is a preflight check, not atomic image identity proof:
the current Windows kernel hashes then launches by path. Qualification must
establish a protected executable directory and path components (including
reparse points), plus trusted dependencies, environment and working directory,
or add an atomic identity mechanism. A writable/replaced path can defeat the
preflight digest. This source chunk does not qualify that boundary. Hard host
crash/restart recovery, orphan discovery without unsafe PID adoption, native
Windows ABI/Job behavior, GPU/driver drainage, model locality and retention,
cross-process inference coordination, latency/quality and family devices remain
separate gates. No weights, runtime data, service controls or deployment change.

## Checks and their limits

- [Controller tests](../server/tests/security/test_selected_story_native.py) use
  fake handles to exercise cancellation races, uncertain receipts, failed
  inventory/termination/close, launch refusals and default-off behavior.
- [Process and operation tests](../server/tests/security/test_selected_story_native_processes.py)
  launch real synthetic Python subprocesses with temporary paths, discarded
  output and unconditional fixture teardown. They use an application startup
  gate and a simulated Job membership list maintained by the test controller.
  Helpers are test-created members, not OS-verified descendants. These tests
  verify retained ownership, process reaping, unrelated-process isolation and
  application admission/quarantine behavior; they do not validate Windows
  suspension or OS containment, GPU activity or an installed model.
- The extracted source-package check imports the Windows factory and constructs
  it disabled without instantiating the platform kernel. Existing Windows
  kernel CPU tests remain distinct from an actual Windows runtime canary.
