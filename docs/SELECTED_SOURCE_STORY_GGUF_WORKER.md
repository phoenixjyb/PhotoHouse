# Optional local GGUF story worker

The [worker](../server/scripts/selected_story_gguf_worker.py) implements the
existing [owned-process file exchange](SELECTED_SOURCE_STORY_PROCESS_BINDING.md).
It runs one selected-source narrative through a local `llama-cpp-python` binding
inside that worker process. It has no server, RPC, cloud fallback, model download,
source lookup, tools, save or sharing capability. It uses the selected caption
and family-memory text; it does not read original photos or perform new visual
recognition. The application remains responsible for identity, current source
access/revisions, final citation validation, review and explicit save.

This is optional source implementation with synthetic tests. No GGUF model,
backend wheel/build, language quality, Windows loader or GPU profile is selected
or qualified. The ordinary CPU requirements do not install `llama-cpp-python`.
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
(range 1–8) and zero GPU layers (explicit range 0–128). GPU splitting is disabled;
an explicit GPU configuration targets device zero. CPU configuration disables
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
