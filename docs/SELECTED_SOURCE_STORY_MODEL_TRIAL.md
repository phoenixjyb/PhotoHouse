# First local story model trial

This record covers the bounded generated-source trial through the optional
[GGUF worker](SELECTED_SOURCE_STORY_GGUF_WORKER.md), owned by the existing native
process provider. The application and both story flags remain off. The trial does
not deploy the feature or use family photos, memories, accounts or databases.

A [pinned CPU candidate](SELECTED_SOURCE_STORY_CPU_CANDIDATE.md) records the
candidate artifacts and limits. The initial English runs failed before returning
a draft; the unchanged baseline was eventually measured failing during native
`grammar_init` with `0xC00000FD` (`STATUS_STACK_OVERFLOW`). The separate bounded-
grammar correction at source `8055183` has now completed **one generated English
case** through the real process provider: 32.031 seconds for the case and 44.766
seconds for the outer bounded run. The returned draft passed the existing
validators and requires review; nothing was saved. The same model/backend,
options, context, two CPU threads and 4 GiB limit were retained.

All 54 operator checks passed with zero skips before that run. Independent
source/model/DLL checks, Job and exchange cleanup, zero host claims, preserved
live services/feeds/report assets and explicit lane release followed it. This is
one isolated generation result, with no accepted prose-quality review or native
Chinese/mixed, active-cancellation or expiry result. Both application flags stay
off. See the [corrected-grammar checkpoint](SELECTED_SOURCE_STORY_CPU_CANDIDATE.md#corrected-grammar-first-generated-english-case-2026-10-22)
for measured evidence and the earlier retained failures.

A later language/interruption slate passed its 92-check model-free Windows gate
with zero skips, then stopped on the first Chinese case because the parent could
not validate its native activity witness. No draft was retained and the other
three cases did not run. Cleanup and preservation passed; the witness failure
does not establish a model-language failure or qualify cancellation/expiry.
See the [activity-witness checkpoint](SELECTED_SOURCE_STORY_CPU_CANDIDATE.md#languageinterruption-slate-activity-witness-refusal-2026-10-22).

The default-off synthetic application, protected prepare/cancel, review/save and
`RuntimeConfiguration` injection seams are implemented. Windows completed 12
synthetic native cases for the pinned source and 18 binding-observer checks.
These checks do not qualify the real model. The later `a6b27df` package and its
fixed worker phase codes are now staged in the isolated candidate; all 22 revised
operator/binding-canary checks passed with zero skips. The later private
sanitized diagnostic passed 37 operator checks, including the native canary,
with zero skips after a portable test-only correction. Its optional `exchange_root`
was packaged but not used by this diagnostic, so its Windows replacement/ACL
behavior remains separate qualification. No serialized provider selection or
application activation exists. Keep both flags off.

The next diagnostic tooling passed 54 Windows operator checks with no skips,
including the actual binding patch/restore and owned Job memory canary. The
source correction is separate from that unchanged-baseline diagnostic.

The sections below retain the proposed limits and trial procedure. They do not
authorize another attempt. Each native window needs fresh owner agreement and
controls; the latest run covered English only, with no automatic replay.

## Small first slice

Start with an explicitly selected CPU build and one model. Use two CPU threads,
zero GPU layers, no GPU selector, one operation at a time and no automatic retry.
Keep the existing operation deadline: model hashing, cold loading, tokenization,
generation, model close and native cleanup all count. A deadline failure is a
failed trial; it does not authorize raising production limits or skipping hashes.
The 2 GiB synthetic rehearsal limit is not a measured real-model memory budget.
Choose the real trial's native memory/disk floors from the selected model/build
and available host capacity before execution.

For a small family, qualify one generation slot plus responsive busy/cancel
behavior first. Several signed-in members must retain separate permissions,
selections and operation ownership; simultaneous users do not require a model
instance per person. Resident models, GPU offload and larger queues are later
choices supported by measured demand and latency.

## Pin before installation or loading

Prepare one private operator record with the following exact values. Do not put
household paths, identities or model weights in Git.

| Item | Required evidence |
| --- | --- |
| Source | Full reviewed commit, closed package manifest and file hashes |
| Executor | Windows account, protected interpreter path and SHA-256 |
| Backend | Exact CPU wheel/build, artifact digest, dependency pins, license and native DLL search/dependency review |
| Model | Explicit label, local single-file GGUF path, byte count, SHA-256, provenance/license and protected dedicated directory without sidecars or reparse parents |
| Launch | Complete argv/environment digest, context, two threads, zero GPU layers, fixed native limits and operation deadline |
| Capacity | Actual local volume/account, free RAM and caller-available disk, real workload-owner agreement and fresh bound clearance |
| Output | New private exchange/report paths, fixed report fields and retention owner |

Create a dedicated environment if the chosen backend is absent; do not modify
another workload's interpreter or model store. Neither the qualifier nor worker
installs dependencies, discovers/downloads models, follows an Ollama store alias,
or substitutes a different provider. CPU mode avoids backend GPU-ordinal mapping;
it does not prove an arbitrary native build never accesses a GPU or network.
Review/enforce locality and native dependency trust for the chosen trial.

Installation and model loading are separate runtime operations requiring their
own authority and an agreed window. A native capacity snapshot and a generated
`synthetic-only` clearance are not agreement from other workload owners. Keep
story admission blocked while another owner's maintenance or recovery is active.

## Execute and assess

1. Verify the source, backend, interpreter, model and launch pins again. Check the
   intended account and current workload/window evidence. Refuse drift.
2. Run the synthetic native rehearsal below. It must pass before the real trial,
   under the intended identity. An interactive-user result is not SYSTEM proof.
3. With explicit runtime authority, run one generated English request through the
   actual worker and native owner with host admission. Record context-fit
   success, total elapsed time, exit status and native tree/exchange cleanup. Publish no
   result before reconciliation; unexpected or uncertain cleanup keeps the claim.
4. Repeat sequentially with generated Chinese and mixed-language memories. Check
   real grammar support, complete source citations, no invented people/events,
   preservation of original wording and useful review questions for missing facts.
   Schema validity alone is not language or factual quality.
5. Cancel during proved native inference and exercise the real total-operation
   deadline using the evidence requirements below. Require native root exit,
   zero Job members, exchange disposal and admission release before a subsequent
   attempt. Do not reclaim a claim by age, PID or free RAM.
6. Record pass/fail per exact build/model/account/launch and retain private failure
   evidence. Any change to those pins needs renewed qualification. Keep the
   application disabled after a passing trial.

Do not log selected words, prompt text, generated prose or original media in
shared reports. Use generated case IDs and fixed outcomes. A real CPU trial does
not qualify GPU mapping/VRAM, service restart recovery, live retention/egress,
model residency, deployment, voice interaction or family/device acceptance.

## Language and active-inference evidence

For Chinese and mixed-language cases, inspect the returned chapter narration.
An input containing Chinese, an echoed title or a valid JSON response does not
establish a Chinese draft. A character-presence check can reject an obvious
language mismatch, but cannot accept fluency, factual grounding or usefulness.
Review those separately against the generated source memories and citations;
retain `needs_review` and leave both drafts unsaved.

Worker resume establishes process execution only. Before describing cancellation
as active-inference cancellation, obtain a request-bound, content-free witness
after a successful native decode and token-sampling call within the same
completion. Forward the backend's original arguments and return values, record
no token or prose, and restore all observation hooks on success and failure.
Observation failure must prevent a successful qualification result.

The parent must validate the witness against the exact private request and its
owned root handle, PID and creation identity. It must also observe that the root
is alive and preparation is outstanding before sending cancellation. PID
existence, CPU use, model loading or a completion that already won the race are
insufficient. Report missing evidence or a completion race as failed or
inconclusive, without publishing a draft or automatically repeating the case.

For expiry, use the existing real monotonic total-operation deadline, including
hashing, cold loading and cleanup. After the native-work witness, verify the
same root and outstanding preparation near that fixed deadline. Expiry before
inference starts, or during cleanup after generation ends, does not establish
active-inference expiry. Do not delay the backend, substitute a clock, extend
the deadline or retry automatically to manufacture overlap.

Use a separate request-bound completion-exit marker before diagnostic or worker
cleanup. Require it absent at the interruption checks and after the interrupted
root settles; require a valid marker for normal generated results. Any completion
exit, including an exception, makes the interrupt case failed or inconclusive.
This excludes observed post-generation cleanup from the active-inference result.
It remains sampled evidence: forceful termination in the short interval between
backend return and marker creation cannot establish instruction-level ordering.

Both interrupt cases must produce no draft and settle the preparation task.
Reconcile the retained native owner, observe root exit and zero Job members,
dispose the owned exchange and release its exact admission claim. Uncertain
cleanup retains ownership and blocks reuse. Keep execution reports private and
content-free; these evidence requirements do not activate a provider or qualify
service-account behavior, protected UI, recovery or family use.

## Composed synthetic rehearsal

The explicit [Windows qualifier](../server/scripts/qualify_selected_story.py)
now composes the GGUF worker protocol with real nested Jobs, private Windows
ACL/file exchange, persistent host admission and native CPU capacity reads.
Its generated GGUF bytes are a fixture, and its backend is an injected synthetic
engine. It does not import `llama_cpp`, load model weights or clear other owners.

In addition to the existing native cases it verifies:

- A fresh blocked host store refuses before exchange allocation or child setup.
- A successful synthetic worker result retains the host claim until native
  reconciliation and exchange disposal; another coordinator can then acquire.
- Failed model close creates no response; native cleanup and disposal still
  release the exact owning claim before a new operation can acquire.

Use the existing explicit command and package checks in the
[Windows qualification guide](SELECTED_SOURCE_STORY_WINDOWS_QUALIFICATION.md).
The generated fixtures and private blocked stores remain in the owned report
folder for inspection. No normal application import or CPU test invokes native
qualification automatically.
