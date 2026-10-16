# AI-assisted story completion

This increment closes source-level gaps in the saved-story drafting journey.
Production generation remains off. Browser fixtures use fictional stores and a
fake narrator; transport fixtures do not establish native model compatibility,
factual quality, performance or family acceptance.

## Author journey

Choose moments, add remembered wording and explicitly save the story. A clean,
confirmed saved story offers a route to the existing drafting form. Opening the
form neither generates nor saves anything. A fresh capability check explains
whether drafting is enabled for the current library; it does not certify a
healthy worker or model. An unsaved or uncertain edit must be saved or resolved
before drafting can use it. Generation always uses the saved server context.

After an explicit request, the queued/running job keeps its submitted wording
and blocks duplicate generation. A terminal failure, cancellation or stale result
retains the author's instructions in the current private reader. A deliberate
new attempt creates a new mutation and checks current context. An uncertain
POST retries its original immutable payload and mutation; it cannot become a
second generation. Scope changes clear private state. No new durable prose
storage is introduced.

The result remains a proposal. Review its chapter wording, sources and uncertain
details, explicitly select wording to import into an unsaved edit, then explicitly
save and reopen. Original family text/audio and existing source links remain
separate. See [first-story creation](STORY_FIRST_GUIDE.md),
[proposal review](STORY_PROPOSAL_WORDING_REVIEW.md) and
[phone proposal adoption](PHONE_STORY_PROPOSAL_ADOPTION.md).

## Provider boundary

The application continues to use the narrator's narrative/companion contract.
Ollama-specific HTTP stays inside `LocalMemoryNarrator`; no engine is selected or
activated by importing it. The adapter supplies a fresh structured-output schema
for each validated bundle: closed response objects, current chapter/source IDs,
chapter counts, kind-specific companion content and mandatory review flags.
This uses Ollama's documented [schema-valued format parameter](https://docs.ollama.com/capabilities/structured-outputs).

The schema is a generation constraint, not a fact check. The independent server
validators remain authoritative for chapter coverage/order, per-chapter citation
membership/uniqueness, narration citations, UTF-8 byte bounds and total output.
They reject unsafe output even if a provider ignores the schema. Source words,
record author labels and family details are not copied into the schema itself;
allowed identifiers already belong to the same authorized model bundle.
No model response can save, publish or execute an action.

The asynchronous narrative worker retains its 30-second default. An explicit
`ollama_timeout_seconds` setting in narrative mode may request up to 120 seconds,
clipped to the remaining bounded-run allowance. This also applies to companion
jobs handled by that worker. ASR and contribution transcription/polishing remain
capped at 30 seconds; the job lease stays at 300 seconds. No deployed timeout is
changed. Socket reads retain the adapter's documented deadline limitation, so
these request limits do not replace an independent process/resource supervisor.

For the current Windows installation, retain Ollama as the first deployment
candidate. vLLM is a separately measured Linux/WSL2 option for sustained concurrent
serving. Its official [installation guide](https://docs.vllm.ai/en/stable/getting_started/installation/gpu/)
does not offer native Windows support, and its [GGUF guidance](https://docs.vllm.ai/en/stable/features/quantization/gguf/)
labels that path experimental. This recommendation is not an engine benchmark.
Model compatibility, quantization and context budget must match a concrete trial;
no new runtime, model weights or provider service is installed by this increment.

For an engine comparison, first measure an Ollama baseline with one in-flight
request, an explicit context/output budget and separately observed cold/warm
model residency. Use the same bilingual search and story cases for a later
vLLM trial, then add concurrent requests. Compare first-response and completion
latency, queued throughput, schema/citation failures, RAM/VRAM peaks and impact
on the existing photo workers. Match checkpoint, prompt and generation settings;
record quantization differences rather than attributing them to the engine.
vLLM's GGUF path requires a separate plugin, so the existing Ollama model store
is not an assumed drop-in installation. A future engine switch must retain
library isolation, server-side validation and explicit review/save behavior.
Neither engine determines language understanding by itself; model quality and
the authorized evidence supplied to it remain separate acceptance questions.

## Private provider timing evidence

The narrative/companion adapter now retains a detached copy of six allowlisted
[Ollama response metrics](https://docs.ollama.com/api/generate): `total_duration`,
`load_duration`, `prompt_eval_duration`, `eval_duration`, `prompt_eval_count` and
`eval_count`. Durations remain provider-reported nanoseconds; counts are tokens.
Only exact nonnegative signed-64-bit integers are retained. Missing or malformed
fields are omitted. Metadata resets at each request, including a refused input,
and a valid envelope can retain timing even when the generated wording fails
validation. This metadata never changes the story/companion return value.

The quality canary writes a nonempty `ollama_metrics` map only into its private
`record.json`, including failed requests when available. Public reports, proposal
bytes and output hashes remain unchanged. The review reader accepts old records
and strictly validates the optional metrics; its existing record hash binds them.
Metrics are not added to the rendered review page or family UI.

These values separate reported loading, prompt evaluation and output evaluation;
they do not establish factual quality, measured peak resources, first-token
latency or a warm service. Warm evidence requires another explicit request while
the same verified model remains resident. No extra request, retry, preload or
model invocation is introduced by collecting metadata.

## October 17 Windows runtime maintenance

The owner-approved update replaced the installed Ollama 0.40.0 application with
[official stable 0.40.5](https://github.com/ollama/ollama/releases/tag/v0.40.5).
The cached installer matched its published SHA-256 and a valid Ollama Inc.
signature. An independent readback confirmed the new client version and binary
identity. The desktop app reopened in its original interactive session; no
Windows restart was required. Eight model-manifest identities, 66 PhotoHouse task
definitions, the API process and checked configuration hashes matched the
pre-update baseline. The prior application remains available for recovery.

This maintenance made no model inference request and changed no family-generation
flag. API/Web delivery, native schema/prose/latency qualification and family
acceptance remain open. The installed client being current does not establish an
active or qualified inference service.

## Remaining completion gates

- Run all eight pinned fictional quality cases with a qualified installed model;
  the empty-title case should make no model request. Preserve failures without
  automatic retry and keep generated output beside its exact sources for review.
- Measure cold startup separately from warm request/generation latency, including
  structured-output success, actual RAM/VRAM use and impact on other workloads.
  The previous roughly eighty-second cold sample is not a warm-service benchmark.
- Review unsupported facts, attribution, conflicting memories, similar-photo
  separation, chronology, bilingual prose and title quality. Citation validity
  does not establish these qualities. See the [native story trial](STORY_MODEL_TRIAL_2026-10-16.md).
- Qualify the current worker, schema/recovery and delivery before enabling family
  generation, then verify the complete Web/phone journey with the family.

The retained trial profile uses a conservative 24 GiB free-system-RAM admission
floor. That is an operator test policy, not an intrinsic Ollama requirement.
The October 16 read-only check found about 8.5 GiB free; the October 17
post-update readback found about 5.7 GiB. Both are below that profile.
A measured resource profile is needed before revising its budget. A desktop
Ollama process alone does not establish an active inference worker. No running
application is stopped to make a trial fit.
