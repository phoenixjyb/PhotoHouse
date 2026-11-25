# Windows playback startup query budget

The playback startup check queries two preserved scheduled tasks before the API
serves requests. Its original task reader used a 15-second PowerShell timeout.
Two November 24 UI rollout attempts failed in that query path and restored the
previous deployment.

## Changed behavior

[The preparation tool](../server/scripts/playback_task_query_timeout.py) accepts
one source byte string and its expected SHA-256. It recognizes the nested
`OnlyPinnedTaskQuery.run` call, inserts a module-level helper before `main`, and
replaces that one call. All other bytes remain unchanged. Removing the helper
and restoring the call must reproduce the original AST.

The helper keeps the original query, executable, arguments, environment and
result handling. It copies the call options and gives each query at most 45
seconds within the existing 900-second parent budget, reserving 90 seconds for
final checks. It refuses when fewer than the original 15 seconds remain. It
makes one call, reports a closed timeout code, and propagates other failures.
There is no automatic retry.

Prepare a new file in an approved development directory; the tool refuses to
overwrite an existing output:

```console
python server/scripts/playback_task_query_timeout.py --source <worker.py> --expected-sha256 <pinned-sha256> --output <new-worker.py>
```

On Windows, use the approved private D: workspace. The command prepares source;
it does not install a worker, edit a live control file, or restart the API.

## Evidence from November 24

The 19 focused local tests exercise the actual generated helper: argument and
environment forwarding, unchanged caller options, one-call exception handling,
clock and deadline refusal, source identity, nested scope, UTF-8 byte offsets,
and preservation of all other source bytes. Two CLI cases also verify successful
preparation and closed, path-free I/O refusals. The CLI-only extension leaves the
Windows-qualified helper and patcher AST unchanged.

A bounded Windows component check executed the eight original read-only queries
with the new helper. All eight returned the same task metadata. Seven took
about 9.7–10.0 seconds; one took **35.0 seconds**, exceeding the old 15-second
limit. The component completed in 104.109 seconds under a 20% Job CPU cap,
1 GiB memory cap and eight-process limit, with no GPU or model request. The
preserved tasks remained disabled and their historical results 0 and 2 stayed
unchanged. No task was started or modified.

The owned Job drained to zero processes, all five parent handles closed, the
transport streams joined, and the 180-second offline/local-owned audit completed.
This qualifies the changed query component under the approved SSH principal.
It does not establish SYSTEM startup or UI rollout acceptance.

## Startup revision integration

The original work window closed with source and component evidence only. The
owner then authorized continuation. A create-only Windows operation has prepared
and verified the complete new startup chain; its Job and transport closure and
180-second offline audit passed. This staging result is not SYSTEM startup or
UI delivery acceptance.

The revision preserves both actual guard layers: the pinned loader wrapper and
its playback-check implementation. New worker and child-template code pins refer
to the qualified bytes. New controls, wrapper, delegate, anchor and gateway
references are immutable revisions; the previous files remain available for
rollback. The existing stop marker, runtime owner, model settings, data paths,
schema, native binaries and sharing configuration remain unchanged.

The existing ingress policy continues to validate its original control and
release. An explicit adapter first checks that the active candidate control and
gateway configuration differ only in the declared startup source references.
The original release is not relabelled as acceptance of the new startup chain.
The matching grouping adapter updates source path, hash and byte count together.

The HTTPS checker now obtains its stage, launcher hash and plan hash from the
same sealed operation record. Pin, import, plan-load and HTTPS failures publish
an atomic closed receipt. Six isolated local cases cover the three controller
labels and deliberate launcher-pin, plan-pin and verification failures.

The later November 24 recovery and delivery passed actual SYSTEM startup and
closed playback checks using this revision. Existing UI/private-denial HTTPS
checks and the new bilingual roadmap route passed; the owner confirmed the
roadmap in their browser. The original failed attempts and transport-output
loss remain recorded separately. The scheduled grouping binding passed its
natural SYSTEM run but returned `REFRESH_DEFERRED`, zero updates; this is not a
complete grouping sweep or household-quality acceptance. See the [Web review](WEB_DESIGN_REVIEW_2026-11-24.md)
and [roadmap](ROADMAP.md) for source, runtime and family-review boundaries.
