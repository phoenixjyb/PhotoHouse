# Approved worker memory lifetime

The image embedding supervisor, approved face pipeline and video embedding
supervisor share one Windows memory envelope for each worker invocation.
The CPU thumbnail/hash worker has its own independent envelope. Video probing
and keyframe preparation retain their existing separate process-tree limit.

## Contract

On Windows, the shared inference envelope is one verified 4,096 MiB Job Object
with `JOB_OBJECT_LIMIT_JOB_MEMORY` and no breakaway flag. Its handle stays open
through provider verification, recovery, task claims and supervised children.
Before each child launch, the worker verifies the current PID and the exact
configured limit. Image/video claims and face recovery/claims also verify the
active envelope before changing task state. If the envelope is unavailable,
the worker stops before taking another task; that admission failure must not
spend retries across the remaining files.

The 8 GiB available-RAM floor and existing child RSS, duration, disk, output,
approval, source/checkpoint and provider/device guards still apply. A committed
memory limit is not a measurement of resident RAM or GPU VRAM. CUDA identity
and GPU memory admission remain separate checks. There is no unbounded fallback.

Previously, `run_supervised` created a self-attaching Job for every child and
then closed its handle. A Windows process remains associated with a Job while
it is alive; closing a handle does not undo that membership. Repeating the
operation creates nested memberships instead of fresh independent child limits.
The lifetime envelope removes that repeated assignment. See Microsoft's
[Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)
and [nested jobs](https://learn.microsoft.com/en-us/windows/win32/procthread/nested-jobs).
A generic `hard_child_memory_cap_unavailable` record alone does not identify
which Win32 operation failed and does not prove physical RAM exhaustion.

## Model-free qualification

The portable fake tests cover repeated child launches, exact policy and PID
checks, cleanup, envelope reentry refusal, and admission failure before recovery
or claims. Caller tests cover both default provider probing and execution.

On an explicitly selected Windows source installation, use a dedicated process:

```text
python -I -B server/scripts/qualify_image_worker_memory_lifetime.py --execute --children 120
```

The qualifier launches 120 sequential tiny Python children under exactly one
worker Job. Each child waits on stdin until its parent proves membership in the
exact active Job, then returns fixed bytes. The qualifier checks the configured
4 GiB policy and restores its temporary launch hook and Job factory on failure.
It has a 180-second internal deadline and retains the worker's resource guards.
It opens no database, media or model; it performs no inference or network calls
and creates no files. Run it in a dedicated process because a process cannot
leave its Job by closing the handle. The opt-in integration test uses that
separate process and is skipped off Windows.

A private operator may add a tighter outer Job/process-count/watchdog envelope
and audit denials for database, model, network and file writes. Such a check
proves synthetic lifetime and child membership only. It does not establish
production provider quality, service ownership, task recovery or family UI
acceptance.

## Recovery and delivery

1. Read the actual worker action, source manifest and current failures. Legacy
   runtime packages may differ from the current monorepo's vector-publication
   contract; do not replace them with a complete newer worker by assumption.
2. Qualify the exact candidate and installed provider/device configuration.
   Preserve its source manifest, stop controls, diagnostic output and Job proof.
3. Obtain authority for the concrete worker switch/start and any exact failed
   task selection. Keep the API, completed tasks, originals and unrelated
   services outside that operation unless explicitly included.
4. Recheck task/source ownership before stopping or changing an existing worker.
   Capture stopped-writer task evidence and conditional retries in a durable
   receipt. Do not reset all failed tasks or silently retry completed media.
5. Verify actual worker/source/PID/Job ownership and useful progress after
   activation. An initial Running state alone is not continuing readiness.

A stopped face worker needs its own exit evidence; sharing the supervisor is
not proof that it failed for the same reason as image indexing. Ensure startup
and terminal failures are captured by the operator's private launcher.

Broad caption activation is separate. The released-caption runner requires an
exact digest-bound release selection; an automatically approved upload batch
must not reuse a prior manual batch's receipt or task IDs. Provider startup,
resource budgets and exact new batch intake need their own reviewed operation.

## October 19 source and synthetic acceptance

The focused image/face/video caller and qualifier cohort passed 49 tests and
31 subtests on the source workspace; the opt-in native integration test was
skipped there. A separate read-only in-memory Windows diagnostic projected only
the reviewed memory-lifecycle functions onto the hash-checked frozen runtime
worker. It completed 120 real child launches in one 4 GiB worker Job, with exact
per-child membership proof, inside a tighter outer 2 GiB/eight-process Job.
The audit reported zero database/model/network/file-write denials and exactly
120 allowed child launches. This qualifies that frozen projection and shared
memory-lifecycle design; it does not qualify the complete newer monorepo worker,
perform GPU inference, switch services or retry production tasks.
