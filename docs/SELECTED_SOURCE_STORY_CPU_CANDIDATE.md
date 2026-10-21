# Optional CPU story trial candidate

This is a pinned candidate for the [first generated-source model trial](SELECTED_SOURCE_STORY_MODEL_TRIAL.md).
It changes no application provider, feature flag, deployment or default dependency
profile. The latest Windows checkpoint below records verified model acquisition
and a first real trial that failed before generation was qualified. Earlier
checkpoints are retained as historical evidence.
The first trial measures the existing worker and containment path; it does not
select this small model as the family's production storyteller.

## Exact artifacts

The [candidate manifest](../config/selected-story-cpu-trial-candidate.json) lists
all artifact URLs, byte counts and published SHA-256 pins. The separate
[optional lock](../config/requirements-selected-story-cpu-trial.lock) is for
Windows x64 CPython 3.12 only; it is not included by the API/development locks.

| Item | Candidate |
| --- | --- |
| Runtime source | `8dc414788a522aa0d9cbf6ea3f37a60828991d24` |
| CPU binding | Official `llama_cpp_python-0.3.36-py3-none-win_amd64.whl`, 7,767,370 bytes |
| Binding SHA-256 | `ae5e88a2cf464e5a2dde7c8898c2d5c71cc24d03cac6396bf7509456bde0b9fb` |
| Binding source | `1652066e0af45f2313b339670ef9555e8a54e545`, MIT |
| Model | Qwen's `Qwen2.5-1.5B-Instruct-GGUF`, `qwen2.5-1.5b-instruct-q4_k_m.gguf` |
| Model revision | `91cad51170dc346986eccefdc2dd33a9da36ead9` |
| Model SHA-256 | `6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e` |
| Model bytes/license | 1,117,320,736 bytes; Apache-2.0 |
| Complete download set | 25 wheels plus one model, 1,144,386,947 bytes |

The 25 wheel sizes and SHA-256 values have now been verified against acquired
Windows bytes. The later model-only acquisition also verified the exact GGUF
size and SHA-256. Artifact verification permits the bounded trial; successful
model construction, generation and cleanup need their own evidence. See the [dependency notices](../third_party/selected-story-cpu-trial.md).
Keep the single GGUF alone in its dedicated protected directory;
license records, wheels, reports and other files belong outside that directory.

Primary sources: [official CPU release](https://github.com/abetlen/llama-cpp-python/releases/tag/v0.3.36),
[CPU wheel index](https://abetlen.github.io/llama-cpp-python/whl/cpu/llama-cpp-python/),
[pinned binding project metadata](https://github.com/abetlen/llama-cpp-python/blob/1652066e0af45f2313b339670ef9555e8a54e545/pyproject.toml),
[official model revision](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/tree/91cad51170dc346986eccefdc2dd33a9da36ead9),
and [model license](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/blob/91cad51170dc346986eccefdc2dd33a9da36ead9/LICENSE).

## Checks completed before acquisition

The source review confirms the pinned binding exposes the worker's constructor
options, context/tokenizer calls, JSON-schema grammar, token-list completion and
model close. This is source API compatibility, not native ABI/DLL compatibility.
The [base instruction model card](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct)
describes Chinese/English support; that is not evidence of this quantization's behavior under our plain
prompt and grammar. The trial must measure it.

Metadata checks resolved the repository's pinned API contract imports plus NumPy
2.3.4, diskcache 5.6.3 and Jinja2 3.1.6. Each chosen wheel has a compatible Windows
CPython 3.12 tag and Python requirement, every applicable non-extra dependency
is present at a matching version, and existing API wheel hashes match the API
lock. Wheel METADATA and native DLL contents still require post-acquisition
inspection; publisher metadata alone does not prove the artifact contents.

The worker currently imports application contract modules, so its dedicated
trial environment includes the pinned API runtime dependencies. Installing these
packages does not authorize starting an API, database migration or model server.
Use no shared site-packages, existing environment upgrades, source builds,
provider substitutions or automatic dependency resolution during installation.
Acquire only the closed wheel set, inspect it, then install offline with hashes,
`--no-index`, `--no-deps` and `--only-binary=:all:`. Do not resolve `latest`.

## Proposed bounded Windows operation

The private operator record pins paths, account/interpreter identity, source and
script hashes, actual capacity/owner evidence and fresh output directory. Those
household details are deliberately absent from this public manifest.

- Acquire the exact closed set and create a new dedicated environment under a
  new private root. Do not modify an existing service environment or model store.
  Acquisition/installation is separately bounded to 900 seconds, 2 GiB and eight
  processes. A failed/partial download is retained; do not retry or use a mirror.
- Inspect installed wheel metadata, native DLL inventory/dependencies and pins
  before importing the optional binding. Refuse unexpected files or dependency
  drift. A valid artifact hash is not complete native dependency qualification.
- With a fresh approved workload window, use one CPU generation slot, two threads,
  context 8,192, zero GPU layers and no GPU selector. Keep the 60-second operation
  deadline, including hashing/cold load/generation/close. Each model Job is capped
  at 4 GiB and four processes. Require 12 GiB free RAM and 8 GiB caller-available
  disk before admission. These are proposed limits, not measured sufficiency.
- The complete sequential trial has a maximum 360-second, 6 GiB, eight-process
  outer Job, shortened to fit the remaining approved window and cleanup reserve.
  Use generated English, Chinese and mixed-language sources, then cancellation
  after observed native resume and a shorter expiry. Stop on the first failure.
  Native resume does not prove the model reached active token generation.
- Retain generated outputs privately for prose review only after native and
  exchange cleanup. Keep shared reports content-free. Require exact host claim
  release and zero owned descendants before another operation. Unknown cleanup
  keeps admission closed; no age/PID-based reclaim or deletion of its store.

No real family data, GPU inference, service control, feature activation or
deployment is included. Capacity samples and idle-looking processes do not clear
other Windows/WSL owners. Installation/loading requires runtime authority; the
first model trial does not close the later service, egress/retention, quality,
GPU or family/device acceptance gates.

## Preparation validation

Thirteen operator preparation checks passed on Mac and Windows, with zero skips,
errors or failures. They cover inert defaults, artifact/source pin refusal, ZIP
bounds and owned partial files, CLI forwarding, receipt/window/deadline checks
and all three generated bundles against the real product validator. Windows
ran these under an actual 180-second / 2 GiB / eight-process outer Job with a
12 GiB RAM floor and native limit/membership proof. Final operator/source input
hashes matched; at that preparation checkpoint, the new environment directory
was absent and no owned test Python process remained.

These are preparation tests. They do not execute the installer, optional binding
or real model runner, and they grant no workload clearance. Real artifact and
native/model qualification require their own runtime evidence.

## Historical Windows acquisition and partial qualification, 2026-10-21

The owner approved the pinned acquisition, new private environment, native
inspection and generated-source CPU trial. The operation acquired all 25 wheels
with the exact candidate sizes and SHA-256 values. It stopped before creating
the environment or model file. The bounded child's standard streams were
discarded, so its original failure reason was not recovered. A separate bounded,
headers-only request to the same pinned model endpoint timed out. That supports
an acquisition blocker, but does not establish the original exception or cause.
No download was retried and no mirror, alternate model or provider was used.

The verified wheels allowed a first offline installation in the approved new
environment without replaying acquisition. It used the closed hash lock,
`--no-index`, `--no-deps`, `--no-compile` and `--only-binary=:all:`; `pip check`
passed. This installation had a 360-second / 2 GiB / eight-process outer Job,
independent native membership/limit proof and a 12 GiB free-RAM floor. The model
directory remained empty. Existing environments and model stores were not used
as installation targets.

All seven synthetic PE-parser checks passed on Mac and Windows. Static inspection
identified 42 AMD64 DLL/PYD files and no GPU-named static imports. The packaged
auxiliary `bin/llama-common.dll` has unresolved `libcrypto-3-x64.dll` and
`libssl-3-x64.dll` imports. It remains unqualified; no unrelated installation was
searched for substitute DLLs. The five libraries in `llama_cpp/lib` have no
unresolved static imports against the inspected candidate, base Python and
System32 inventories. API-set names are Windows contracts, not resolved file
paths; this scan is not a complete loader or egress qualification.

A separate 60-second / 2 GiB / four-process Job imported binding version 0.3.36
under the new interpreter, with independent native proof and no model
construction. Its environment excluded CUDA/HIP and library-root overrides,
and supplied only the private interpreter, base Python and System32 on `PATH`.
Observed DLL-directory additions were limited to `llama_cpp/lib` and
`numpy.libs`. The child module snapshot showed the expected core libraries at
the candidate paths with matching installation hashes, no `llama-common.dll`
and no GPU-named modules. The binding reported no GPU-offload support. On-disk
hashes and a module-path snapshot are not atomic proof of mapped image bytes.
No `Llama` object, GGUF, token generation or model close was exercised.

The public synthetic qualifier also passed all 12 native cases under the new
environment at runtime source `8dc414788a522aa0d9cbf6ea3f37a60828991d24`.
This covers default-off behavior, cancellation, expiry, descendant cleanup,
private exchanges and the composed host-admission/close-failure cases. Its
engine and GGUF bytes were generated fixtures; it did not import the real
binding or load the real model. This was an interactive-user run, not SYSTEM
qualification or installed-service acceptance.

At that checkpoint, final readback found no owned Python processes, zero claims in both synthetic
host stores with maintenance closed, an empty real-model directory and all
274 staged source-file hashes unchanged. All six mapped candidate DLL file
hashes matched their installation pins. These are endpoint observations, not
continuous service availability or atomic mapped-image verification.

At that checkpoint, the real English/Chinese/mixed generation and real-model
cancellation/expiry trial had not run. No real-trial owner receipt, admission window or packet was
issued. Preserve the acquisition failure and private reports; obtaining the
same pinned model is the next blocker, followed by a freshly confirmed workload
window. Application flags remain off. No production database, family media,
GPU inference, service/task control, deployment or activation was part of these
operations.

## Model acquisition and first real trial, 2026-10-22

A separately initiated, model-only acquisition obtained the same pinned GGUF:
1,117,320,736 bytes, with the candidate SHA-256 verified in full. The Windows
origin connection timed out; a headers-only request to the immutable publisher
URL supplied its official CDN redirect, which the bounded Windows downloader
used without changing OS networking, mirrors, models or providers. There was no
automatic retry or reinstall. The license remains outside the single-file model
directory. No model bytes were copied to the Mac source workspace.

The revised private observer passed all 18 operator checks on Windows, with no
skips. Its binding-only canary used no GGUF and reconciled the native Job. It
observes only process handles verified as members of the exact owned Job,
including the Python child behind the virtual-environment launcher. It does not
scan for processes to adopt. Core library paths and installation file pins were
observed; this is not atomic mapped-image or network-egress proof.

Fresh status reads showed grouping and retrieval working locally after closing
their previous Windows runs. The native preflight found no candidate-related
Python process, about 40.9 GiB free RAM and 144 GB caller-available disk. These
were observations, not a future resource reservation. A new, at-most-300-second
owner receipt bound the exact interpreter, runtime source `8dc4147`, model and
launch recipe for the generated-source trial.

The first real trial stopped at its English case: the worker exited with code
2 after 6.578 seconds. The inner trial took 12.891 seconds and the complete
bounded invocation took 19.172 seconds. All four expected core libraries were
observed with no module-policy violation. The generic exit does not establish
which model step failed; model construction, context fit, successful generation
and model close are not qualified. Chinese, mixed-language, cancellation and
expiry cases did not run after that first failure. No automatic replay occurred.

Independent readback found no owned Python processes, disposed exchange files,
zero host claims, maintenance closed and all 274 staged source hashes unchanged.
The failed receipt, packet and reports are retained. The source now has fixed, content-free
failure phases for a further diagnostic; that change is separate from the
recorded runtime source. Application flags remain
off; production databases/media, GPU inference, tasks/services, activation and
deployment were outside this trial.


## Phase-aware diagnostic and preservation, 2026-10-22

The separately reviewed `a6b27df` package was staged into a fresh isolated source
folder; the original `8dc4147` package and reports were retained. All 22 revised
operator checks passed on Windows with zero skips, including the binding-only
native canary. That canary reconciled its owned Job without opening the GGUF.
The base interpreter and its two Python DLLs matched their fixed file pins.

One manually initiated diagnostic used a fresh owner receipt and the same model,
backend, CPU/context settings and limits. Its English worker exited with code
17 (`generation`) after 6.344 seconds; inner and outer elapsed times were 12.890
and 19.234 seconds. The other four cases did not run, and no replay occurred.
The fixed phase shows that construction, tokenization, the context check and
Python grammar construction returned before the completion call failed. Model-bound
grammar setup, evaluation, sampling and response construction still occur inside
that call; the phase alone cannot identify its exception or root cause. No
model-close failure was reported. Successful generation, real cancellation/expiry,
language quality and normal completion remain unqualified.

Independent readback verified both 274-file source packages, the model's full
size/SHA-256 and all 13 recorded installed DLL pins. The failed case recorded zero
Job members and exchange disposal; the independent store read showed zero claims
and maintenance closed. A final independent process check found no owned Python
or control observer. Existing runtime identities, tasks, gateway/site/API
processes, listeners and phone/TV feed hashes matched their preservation baseline.
All 69 furniture-report assets were available with matching hashes before and
after the trial. These are endpoint checks, not continuous availability or browser
rendering acceptance. The coordinated Windows lane was explicitly released only
after cleanup verification.

The source includes the optional exchange parent and runtime injection seams,
but this diagnostic used the existing private-qualifier temporary-directory path.
It does not qualify explicit exchange-parent replacement on Windows, a serialized
provider recipe or household service activation. Production services, settings,
databases/media and feature flags were not changed.
