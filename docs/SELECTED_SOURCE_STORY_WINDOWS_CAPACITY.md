# Windows story capacity and workload clearance

`WindowsStoryCapacityProbe` is a default-off callable for the optional
[host admission coordinator](SELECTED_SOURCE_STORY_HOST_ADMISSION.md). It reads
capacity and explicit operator evidence. It does not start inference, issue
clearance, discover providers, stop workloads or activate application flags.

## Bound configuration

The frozen probe configuration pins the Windows hostname, process-token SID,
actual disk-volume UUID, target directory, receipt path, required workload-owner
IDs and optional NVML selection. The host resource profile's `capacity_sha256`
binds that configuration, clearance UUID and the trusted receipt SHA. Changing
any of them requires a newly cleared full profile; the old SQLite clearance
cannot silently accept the new probe. Public trust properties are read-only
and the complete digest is rechecked on every pre/post validation.

The expected receipt SHA and owner roster come from separately protected,
trusted operator configuration. They are not accepted from the receipt or a
client/model proposal. There is no receipt-writing API or model tool. Evidence
hashes do not authenticate owner decisions: the operator must inspect the
underlying records and obtain the actual owners' clearance. Use a fresh
clearance UUID and pin for each approved window; rotation requires explicit
configuration and coordinator clearance with no active claim.

The small private JSON receipt has an exact versioned schema, rejects duplicate
fields, and lists every configured owner exactly once with state `clear` and an
evidence digest. It binds the base resource/launch profile and native probe
configuration. Its digest is then bound into the final profile, avoiding a
self-referential hash. Reads verify private owner/DACL, canonical regular-file
identity, single link, bounded length, open-handle metadata and pinned bytes
before and after the native measurement.

A receipt permits at most a 300-second window and must have at least 60 seconds
remaining at both checks. Future issue, expiry, local clock rollback and a
receipt predating the current boot refuse. Boot checking uses native uptime;
clock authority and protected configuration remain operator assumptions. File
replacement, byte changes or a revoked pin refuse. These are admission checks:
expiry never deletes an active host claim or substitutes for process cleanup.

## Native read-only measurements

The Windows implementation reads available physical RAM and disk bytes
available to the calling account, including its quota. It resolves the target's
actual mount point with `GetVolumePathNameW`, then checks fixed-drive type and
volume UUID for that mount, rather than assuming the drive-letter root. It
checks the actual hostname and process-token SID. Network/removable volumes,
identity mismatches and native API failures refuse.

CPU mode never loads NVML. GPU mode requires an explicit physical UUID and
absolute NVML DLL path, file digest and expected link count. The default link
count is one; a protected system-driver layout with multiple hard links must be
qualified and pinned explicitly. The loaded module path and file pins are
checked, DLL search is restricted to its qualified directory and System32, and
NVML selects by UUID, verifies the returned UUID and reads memory counters.
Every initialized call requires shutdown, followed by explicit DLL-reference
release; native failures make that metrics instance unavailable without an
automatic fallback. No ordinal enumeration, CUDA/model API, server call or
weight loading is added.

The operator must qualify write protection of the driver and dependency
locations and the exact driver/build. File hashes and loaded-path checks do not
prove atomic mapped-image identity or dependency contents. An NVML UUID is not
a llama.cpp backend ordinal. Those mappings and actual model memory/latency
still need separate qualification.

## Timing and authority boundaries

The complete probe must finish within half a second, and the coordinator also
checks sample freshness. Python cannot safely interrupt an arbitrary blocked
native call. A stuck call retains its setup thread and SQLite write transaction;
maintenance closure returns busy rather than claiming success. It starts no
story child and cannot grant a claim until the read settles. Service-level
hard bounds and crash/restart behavior remain qualification work. The native
read-only rehearsals run inside a separately bounded Windows Job.

Counters and short-lived owner evidence are snapshots. They neither reserve
resources against uncooperative programs nor enforce another Windows/WSL
owner's maintenance policy. Existing indexing, speech, OCR and recovery jobs
must participate in an agreed policy or inference stays blocked. Generated
receipts in tests certify fixture behavior only; they grant no real inference
window. The probe, provider and story features remain default-off. Deployment,
SYSTEM execution, model/backend/GPU inference and family/device acceptance are
separate gates.

## Source validation

The isolated Windows source run completed **156 affected cases: 153 passed and
three platform-specific cases were skipped**. It covers receipt/configuration
drift, revocation, timing/boot checks, volume mount identity, native API refusal,
UUID-only GPU calls, explicit driver link counts, cleanup and the existing
provider/operation lifecycle. Native-binding unit cases use mocks.

Two additional read-only native checks passed inside a real three-minute /
2 GiB / eight-process Windows Job: actual OS identity/RAM/disk reads and a
generated CPU-clearance probe, plus the explicitly pinned GPU UUID/VRAM read.
The generated CPU probe took about 16 ms and the GPU counter read about 94 ms
in that snapshot; these are not service or model latency guarantees. The
installed system-driver signature/permissions and its two-link layout were
inspected privately. Earlier attempts refused its unpinned link count before
DLL loading and are retained. No inference, real workload clearance, model
loading, production data/task/service mutation or deployment occurred.

All **ten committed-source package/import checks passed on Windows** as well.
