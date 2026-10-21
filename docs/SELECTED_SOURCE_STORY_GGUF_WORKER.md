# Optional local GGUF story worker

The [worker](../server/scripts/selected_story_gguf_worker.py) implements the
existing [owned-process file exchange](SELECTED_SOURCE_STORY_PROCESS_BINDING.md).
It runs one selected-source narrative through a local `llama-cpp-python` binding
inside that worker process. It has no server, RPC, cloud fallback, model download,
source lookup, tools, save or sharing capability. It uses the selected caption
and family-memory text; it does not read original photos or perform new visual
recognition. The application remains responsible for identity, current source
access/revisions, final citation validation, review and explicit save.

This is optional source implementation with synthetic tests. A separate
[CPU trial candidate](SELECTED_SOURCE_STORY_CPU_CANDIDATE.md) pins proposed
artifacts; none has been acquired, installed or loaded. Actual model/backend
behavior, language quality, Windows loader and GPU profiles remain unqualified. The ordinary CPU requirements do not install `llama-cpp-python`.
Imports load neither that optional binding nor a model. `run()` defaults to
disabled; the CLI requires `--execute`. No app configuration, API route, feature
flag or environment variable automatically selects this worker.

## Operator-owned launch

Use this command only as the `argv` of an explicitly reviewed
`NativeStoryLaunch` with the existing Windows process-provider factory:

```text
<python> -I -B <package>/scripts/selected_story_gguf_worker.py --execute --model-file <absolute-GGUF> --model-sha256 <reviewed-SHA256> --model-label <explicit-label>
```

Keep the process provider disabled until its separate activation gates pass.
The native parent owns suspended creation, assignment before resume, operation
UUID, cancellation/expiry, Job memory/process limits, reconciliation and private
exchange disposal. The CLI is not a process owner or a standalone sandbox and
does not independently attest that a direct manual invocation is contained.
Pin/protect its interpreter, script, optional binding and native dependencies;
launch arguments/environment must contain no selected words or generated prose.
Use the reviewed minimal environment, private TEMP/TMP and existing reserved
request/response/operation injection. Do not point it at a shared HTTP service.

Model path, label, file digest, context, thread count and GPU layers come only
from the reviewed launch. The worker accepts a regular, single-link `.gguf`
file with the expected SHA-256 and GGUF magic, under direct nonreparse parents
on an absolute non-UNC path. Its dedicated directory must contain only that
file; split-file names, adjacent shards and sidecars are refused. It reads at
most 16 GiB during hashing and detects ordinary identity/size/time changes.
Model storage is not modified. Filesystem permissions must separately protect
the model directory and dependencies against replacement throughout execution.
Preflight hashing and later stat checks do not establish atomic mapped-image
identity or prove the behavior of a native dependency or network-mounted drive.

## Bounded one-request execution

The worker requires the two fixed sibling filenames in one private exchange,
refuses existing output/unknown entries, and reads only the bounded regular
single-link request after owner/DACL and open-identity checks. UUID, exact JSON
scalar types, closed envelope and complete canonical generation payload must
match the host's validated v3 selected-source bundle. It regenerates the host
prompt/schema/options and uses those reconstructed values. Input cannot supply
arbitrary grammar references, executable/import paths or generation settings.

The default context is 8,192 tokens (explicit range 4,096–16,384), two CPU threads
(range 1–8) and zero GPU layers (explicit range 0–128). GPU splitting is disabled.
GPU layers require an explicit `--gpu-device`
backend ordinal (0–15); omitting it is refused. CPU mode rejects a GPU selector.
The operator must qualify the mapping from that ordinal to the intended physical
GPU/UUID under the exact backend build and visible-device environment. NVIDIA
monitoring indices are not assumed to match backend ordinals. CPU configuration
disables
KV and operation offloading. These are requested bounds, not measured runtime
capacity, latency, GPU isolation or proof that a native build touches no GPU.
No inference admission is added here: retain the existing shared application
gate and qualify coordination with other GPU workers before activating offload.
One cold model load per operation is deliberate for this first owned worker;
load/hash time counts against the parent's existing operation deadline. There
is no resident model server, automatic retry or warm-session cache.

The optional binding uses its documented
[local constructor, tokenization and completion API](https://llama-cpp-python.readthedocs.io/en/latest/api-reference/).
The entire prompt is tokenized once with BOS and without special-token
interpretation; those token IDs are passed to plain completion. No chat template,
tool API or model-discovery API is invoked. The full prompt plus the host's
2,048 output tokens must fit the actual context, or the request fails without
truncation. The freshly reconstructed JSON schema constrains sampling. A length
finish, invalid usage counts, oversized text, malformed JSON or invalid narrative
is refused. Shape/citation checks cannot certify facts or suitable family prose;
the selected model must separately demonstrate this plain-prompt/grammar mode.
The host's `think:false` field is a protocol invariant, not independent proof
about internal model reasoning.

The model must close successfully before response creation. The request is
rechecked unchanged, the model identity is rechecked, and the response is opened
exclusively. Actual inherited file privacy is checked before writing any words;
the file is flushed, synced and closed before zero exit. A late collision is
preserved. Any failure exits nonzero with a fixed content-free CLI error; the
parent fences the output, drains its Job and disposes only known exchange files.
A failed write can leave a partial private file for that existing cleanup path.

## Evidence and remaining gates

[Synthetic tests](../server/tests/security/test_selected_story_gguf_worker.py)
cover inert import/default refusal, protocol/type/schema/scope rejection,
private/exclusive exchange behavior, model pins/sidecars, token context boundaries,
truncation/usage/output rejection, request/model mutation and failed model close.
A real Python child runs this worker code with an injected synthetic engine and
round-trips through the existing process provider. Its Job kernel is simulated;
the optional binding calls are mocked. No real model, optional wheel or GPU is
used by these checks.

The earlier [Windows native rehearsal](SELECTED_SOURCE_STORY_WINDOWS_QUALIFICATION.md)
qualifies its recorded source pin and synthetic native provider; it predates
this loader and does not qualify it. Before activation, separately pin and test
the actual GGUF and backend build, Windows DLL/Job/CPU/GPU behavior, schema
support, Chinese/English quality, input limits and load latency, memory/VRAM
admission across processes, crash/restart behavior and disk/erasure policy.
Deployment and family/device acceptance remain separate. Both story flags,
all provider factories and this worker remain default-off.

## Windows source repair and host admission

The synthetic worker process initially failed on Windows while importing
`asyncio` because the test launch contained only PATH. Its minimal test
environment now preserves Windows platform basics (including SYSTEMROOT) and
excludes live provider settings. The real-process expiry fixture now observes
a resumed/live worker before advancing its injected monotonic clock past the
operation deadline; it retains the no-publication, reaping, exchange-disposal
and admission-release assertions. It gives native cleanup two seconds inside
a separate four-second operation cleanup allowance. Product deadline and
cleanup/quarantine rules are unchanged.

These source repairs were developed in a separate Windows source export and
tested with synthetic providers and an actual bounded outer Job. They are
interactive-development checks, not SYSTEM service, real GGUF/backend or GPU
qualification. No existing environment, service, task or model was changed. The Windows repair
run completed 118 affected cases: 115 passed and three platform-specific cases
were skipped. All ten committed-source package/import checks also passed. These
final runs used the unmodified subprocess class; optional binding calls were
mocked and worker protocol roundtrips used a synthetic engine.

A separate default-off [host admission coordinator](SELECTED_SOURCE_STORY_HOST_ADMISSION.md)
now implements one persistent claim across cooperating processes, maintenance
closure, explicit profile clearance and fresh capacity evidence. Optional
provider injection acquires before exchange/child setup and retains the claim
until native cleanup and exchange disposal both succeed. There is no automatic
expiry, stale-claim clearing or adoption of another process's work. The existing
application queue and quarantine remain in place.

Synthetic Windows tests qualify the coordinator and ownership integration. The
[native capacity probe](SELECTED_SOURCE_STORY_WINDOWS_CAPACITY.md) now implements
read-only metrics and bound clearance checks. Actual workload-owner agreement,
backend/model qualification and an approved window remain required before
activation. Follow the [first CPU model trial](SELECTED_SOURCE_STORY_MODEL_TRIAL.md)
before considering GPU mapping or application activation.
