# Selected-story provider bound to an owned process

The [process provider](../server/backend/app/access/selected_story_process.py)
binds one selected-source generation request to the exact worker launched by
its private [native owner](SELECTED_SOURCE_STORY_NATIVE_OWNER.md). It implements
`prepare(bundle, scope)` and `stop_and_reconcile(scope)` for the existing app and
session lifecycle. The [Windows factory](../server/scripts/selected_story_native_owner.py)
adds an explicit `windows_story_process_provider(launch, model)` constructor.
Both constructors default to disabled and perform no I/O or kernel construction.
Staged JSON configuration and default application construction do not select them.

This binding has synthetic and separately pinned native acceptance. The optional
[GGUF worker](SELECTED_SOURCE_STORY_GGUF_WORKER.md) now implements local model
loading inside the owned process, with synthetic tests only. A host must still
review and qualify the exact worker/model/dependency installation and run all
inference/helpers inside the owned Job. A worker that calls an independent
HTTP service or cloud model is outside this contract. Neither loopback nor
repeating a model label proves local execution or owned inference.

## Explicit runtime injection

`RuntimeConfiguration` can now receive an already constructed
`selected_story_provider`, with separate `selected_story_drafts_enabled` and
`selected_story_ui_enabled` flags, both false by default. A provider requires
memory collaboration; API opt-in requires a provider, and UI opt-in requires the
API. Invalid flags/dependencies fail before runtime storage construction. The
builder forwards the exact object to the existing app/session lifecycle without
calling it, loading a model, selecting a factory or changing host admission.

This is a Python injection seam. It adds no serialized recipe, environment
activation, model discovery or download. A Windows owner receipt remains a
short qualification window; the runtime does not create, renew or clear one.
The current receipt policy and participating workload ownership still need an
explicit long-running operator design before household service activation.

## One private exchange per operation

Before any file or process work, the provider checks the selected-source v3
bundle, exact scope UUID, model identifier and deadline. Saved-story/book inputs
are refused. It reuses the unchanged narrative prompt/schema helper and bounded
source limits. There is no model tool, source lookup, URL fetch, shell command
proposal, sharing, persistence into the family library or automatic retry.

For each accepted call, the host creates a fresh private temporary directory,
requests mode 0700, and writes `request.json` exclusively with mode 0600. It copies
the explicit launch configuration and injects two reserved environment variables:

| Variable | Host value |
| --- | --- |
| `PHOTOHOUSE_NATIVE_STORY_REQUEST` | Absolute private request-file path |
| `PHOTOHOUSE_NATIVE_STORY_RESPONSE` | Absolute private response-file path |
| `PHOTOHOUSE_NATIVE_STORY_OPERATION` | Exact opaque scope UUID, supplied by native owner |

An optional `exchange_root` selects an existing private local directory without
changing process-wide temporary-directory settings. Construction only validates
its spelling; after host admission, setup checks its canonical path, permissions
and identity before creating a fresh operation directory beneath it. The provider
never creates or deletes this configured parent. Reads and cleanup recheck its
identity and direct containment; a replaced or uncertain parent retains the
exchange and host claim for reconciliation. These checks do not make filesystem
operations atomic against concurrent replacement.

`exchange_root=None` preserves the existing temporary-directory behavior and
launch digest. An explicit root becomes part of `process_launch_digest` and must
match the host admission profile. A caller cannot reuse a receipt for a different
IPC parent. The Windows convenience factory forwards this option and optional host admission
without initializing a store, probing capacity or constructing a native kernel.
Staged application configuration does not yet expose it. This source change has
synthetic qualification and needs separate native ACL/replacement checks.

The caller cannot prepopulate those reserved keys, including case variants.
Arguments and environment contain no selected source words or generated prose.
The parent does not execute a worker-supplied command, path or endpoint. Only a
trusted, explicit launch description chooses executable/arguments/dependencies.
Native process count, host memory, RAM preflight, suspended assignment before
resume and handle retention remain enforced by the native owner/kernel.

Request JSON is strict UTF-8, at most 128 KiB, with exactly:

```json
{"version":1,"operation_id":"host UUID","generation":{"model":"explicit model","prompt":"bounded data and instructions","stream":false,"think":false,"truncate":false,"format":{},"options":{}}}
```

The `generation` object is the existing narrative payload, including its actual
closed response schema and generation options. It does not authorize an HTTP
call; the worker must perform inference within its containment.

The worker reads this request once, validates correlation against the operation
environment, writes only `response.json`, closes it and exits with status zero.
It must not create extra exchange entries or persist source/result copies.
Response JSON has exactly these fields:

```json
{"version":1,"operation_id":"same UUID","model":"same explicit model","result":{"version":1,"title":"draft","chapters":[],"questions":[],"needs_review":true}}
```

`result` must satisfy the existing narrative validator for the exact input
chapters/evidence. The illustrative empty chapter list is not valid for a
nonempty request. Unknown/missing fields, wrong UUID/model/version, duplicate
keys, nonfinite JSON, invalid UTF-8 and oversized/truncated output are refused.
Total response is bounded at 128 KiB; narrative result is bounded at 64 KiB.
Citations and human review remain host-owned and do not establish factual truth.

## Completion and cleanup

`wait_for_exit(scope)` waits only for that owner's root, requires exit status
zero and retains its task through cancellation of a waiter. It does not release
handles or certify descendants. The provider then requires exact `True` native
reconciliation before reading output. A root that has exited while a helper is
still running cannot cause early response consumption. Failed exit status,
missing output, failed drain or timeout cannot publish a draft.

Response reads require a regular single-link file and stable open identity;
symlinks/reparse points are refused, with no-follow/nonblocking flags where
available. POSIX owner identity/private directory permissions are checked.
Reads happen only after native cleanup, in retained off-loop tasks. The
provider's work timeout is at most 60 seconds and is also limited by the host
scope deadline. The operation lifecycle fences/cancels `prepare` before calling
cleanup on failure, cancellation, expiry, logout or shutdown.

Cleanup waits for retained setup/read work, closes the native owner and removes
only the two known regular files and directory. It never recursively deletes
unexpected contents. Unknown entries, unsafe links, failed deletion or uncertain
native cleanup retain the exchange and return false. Shared admission stays
held/quarantined and words remain fenced. A later exact proof can release
capacity without clearing sticky quarantine or regenerating. A fresh owner is
not recovery proof. Explicit `close()` blocks new preparation; the host must
first fence/cancel active preparation through the operation lifecycle.

The exchange temporarily contains source words and generated text on disk. A
failed cleanup deliberately retains those private files as unsettled state;
this is not a content-free transport or secure erasure guarantee. No file path
or content is returned in public errors, and no payload logs/cache are added.

## Qualification still separate

Before any household activation, separately qualify Windows temporary-directory
ACLs, ownership and reparse protections, disk quota/retention/erasure, protected
executable/dependency/environment identity, actual Job containment and process
exit behavior, native/GPU driver drainage and crash/restart reconciliation.
The preflight executable hash is still not an atomic image identity mechanism.
Measure model locality (no cloud or independent-server fallback), quality,
latency, memory/VRAM and participating cross-process inference admission. This
binding does not sandbox arbitrary code or prevent a trusted worker from
violating its declared contract. The optional GGUF worker is implemented
separately; its actual backend build, model integration and runtime remain
to be qualified.

[Fault tests](../server/tests/security/test_selected_story_process.py) use fake
kernel handles and synthetic response files. [Lifecycle tests](../server/tests/security/test_selected_story_process_lifecycle.py)
run actual synthetic Python workers that read the exact injected request and
write the response. Their startup gate and Job membership list are simulated;
helper members are test-created rather than OS-verified descendants. They prove
the source protocol and lifecycle behavior, not native Windows containment,
GPU/model behavior, secure filesystem ACLs or family/device acceptance.
Deployment and activation remain separate decisions. Existing API and Web UI
flags, local HTTP adapter and native/process providers remain default-off.

The separate [Windows native qualification](SELECTED_SOURCE_STORY_WINDOWS_QUALIFICATION.md)
now supplies an explicit inert-by-default runner for real Job/IPC cases. Its
results must be pinned to the package, interpreter and intended account; the
remaining model/runtime/deployment gates above still apply.


Optional [host admission](SELECTED_SOURCE_STORY_HOST_ADMISSION.md) injection
now binds the launch recipe to a persistent cooperating-process claim before
exchange/child setup. Reconciliation releases it only after native cleanup and
exchange disposal succeed. It is default-off and does not automatically govern
existing Windows/WSL services; native resource probing and qualified activation
remain separate gates.
