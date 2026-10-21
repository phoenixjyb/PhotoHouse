# Selected-source story host admission

This default-off layer supplements the bounded application queue with one
persistent claim shared by cooperating processes on one host. It is intended
for occasional overlap among a small family, with immediate `busy` responses
across processes rather than a second durable queue. It does not activate a
provider, load a model, coordinate existing services automatically or deploy.

## Explicit setup and clearance

`initialize_host_admission(directory, enabled=True)` requires a fresh, empty,
private directory and creates a blocked SQLite store. It refuses an existing
store rather than overwriting it. The operator must qualify a protected local
filesystem path and its ancestors; network shares and cross-host coordination
are unsupported. The normal application does not create or clear this store.

An explicit `HostResourceProfile` identifies CPU or a qualified GPU UUID,
minimum free RAM/disk/VRAM, and the exact native launch recipe digest. CPU mode
requires zero VRAM; a GPU profile requires a positive VRAM floor. The digest
covers executable identity, argv, environment, working directory and native
limits before operation-specific exchange paths are appended. It contains no
source words; the store records no tokens, family identifiers or story prose.
Any backend ordinal-to-UUID mapping remains separately qualified under the
exact backend build and visible-device environment.

The trusted operator seam `set_maintenance(False, clearance_id=...)` requires
no active claim and an explicit clearance identity. It pins the complete
profile. A changed launch recipe or capacity threshold requires renewed
clearance. This is not a client API, model tool, environmental toggle or automatic
recovery action. `set_maintenance(True)` can block new starts while preserving
an existing claim. A busy transaction can delay closure; closure is established
only when the call succeeds, never when it is merely requested.

Each admission needs a trusted injected `HostCapacity` probe with the exact
resource and clearance identities, a sample no more than two seconds old,
sufficient free RAM/disk/VRAM and explicit external-workload clearance. Invalid,
missing, stale, busy or failed evidence denies launch. Probe completion must
fall within half a second. The probe implementation itself must be bounded:
Python cannot interrupt an arbitrary blocked thread. A stuck probe retains its
setup task and SQLite lock, and starts no child; it does not establish timely
maintenance closure. The
[native Windows probe](SELECTED_SOURCE_STORY_WINDOWS_CAPACITY.md) now implements
counter reads and pinned owner-clearance checks. SYSTEM/service, model and
competing-workload qualification remain separate work. Free capacity samples
are point-in-time evidence; they do not reserve resources against uncooperative
programs or prove CPU/I/O isolation.

## Ownership and cleanup

SQLite immediate transactions serialize maintenance, acquisition and release.
There is one claim per store, bound to operation UUID, random owner token,
resource identity and launch digest. Claims have no time-to-live. Reopening a
store, process death, elapsed time, an idle GPU, or maintenance clearance cannot
release them. A new process cannot adopt a claim by operation/PID alone.
Unknown schema, corrupt storage, nonprivate/replaced files and uncertain I/O
fail closed. SQLite uses FULL synchronization; this is not a guarantee against
storage failure, backup rollback or privileged modification.

`ProcessSelectedStoryProvider(..., host_admission=...)` validates the launch
binding and acquires inside its retained setup task before allocating an
exchange or child. Cancellation retains that task until its result is known.
Only successful native process-tree reconciliation **and** exchange disposal
allow the owning permit to release the persistent claim. Unknown cleanup or
release outcomes keep the operation unavailable and preserve the claim. The
existing app-level permit and quarantine remain independent safeguards.

Host contention maps to the existing protected `busy` response. It remains
retryable under the same exact request/session and source fingerprints; no
worker has started for that denied attempt. Maintenance or invalid resource
evidence returns unavailable. Permission and source validation remain with the
application. The coordinator is an optional injected dependency and all story
features remain default-off. Any future host-enabled deployment must require
this dependency; `host_admission=None` exists for existing synthetic adapters
and is not whole-host admission proof.

## Recovery and qualification

After a process crash, preserve the store and reconcile the owned process tree,
exchange files, model residency and external workload state offline. This module
has no stale-claim deletion, PID adoption, lease breaking or force-clear API.
Never delete the store merely to make admission pass. Any operator recovery or
profile activation needs its own reviewed evidence and authority.

Existing Windows/WSL inference, indexing, OCR, speech and recovery jobs are
external owners. They must participate in an agreed maintenance/resource policy
or keep story inference blocked. This coordinator neither stops them nor claims
they obey its SQLite store. Protected directory/ACL behavior, actual process
containment, model/backend locality, competing-workload capacity, quality,
latency, service crash recovery, deployment and family/device use remain
separate acceptance gates.

Synthetic checks cover independent-process contention and abrupt exit,
maintenance ordering, launch/profile and capacity mismatch, uncertain cleanup,
cancellation during acquisition and protected operation error/retry handling.
See [the worker contract](SELECTED_SOURCE_STORY_GGUF_WORKER.md) and
[process binding](SELECTED_SOURCE_STORY_PROCESS_BINDING.md). No runtime model or
production data is needed for these tests.

Windows source validation used synthetic providers/processes inside an actual
three-minute / 2 GiB / eight-process outer Job: **115 affected tests passed with
two platform-specific skips**, plus **ten committed-source package/import tests
passed**. The real synthetic child uses the existing simulated inner kernel;
the outer Job is native. These are interactive source checks, not SYSTEM service
or real model/GPU qualification. No production workload was controlled.

All **14 check-runner tests also passed on Windows**, including a portable
assertion for Windows environment-key normalization.

Windows-specific profiles now bind `capacity_sha256` to the native probe's
immutable host/account/volume/driver/owner configuration and trusted receipt pin.
Receipt rotation changes that full profile and requires explicit renewed
clearance. Plain synthetic profiles can retain `None`; Windows probes require
the binding. Fingerprints from earlier source versions must be reconciled
explicitly; no store migration, stale-claim clearing or activation is automatic.
