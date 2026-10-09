# Model and provider architecture

This page maps model-backed capabilities to their current application adapters and
describes how an inference implementation can be replaced. It is an inventory and
design boundary, not a deployment procedure. Source code may contain an adapter
without a corresponding installed model, checkpoint, qualified endpoint, or active
runtime.

## Inventory and configuration

[`models/catalog.json`](../models/catalog.json) is an offline inventory of provider
roles and their source-level adapters. The catalog verifier checks that inventory
against source symbols; it does not import the application, inspect a machine,
contact an endpoint, install dependencies, download weights, or prove runtime
availability. [`models/providers.example.json`](../models/providers.example.json)
is a disabled configuration example. Neither file selects or deploys a provider.
The separate private deployment manifest records declared runtime/artifact/provider
choices and role bindings; see the [manifest guide](MODEL_DEPLOYMENT_MANIFEST.md).
An explicit typed bridge can now project selected assistant and memory roles into
private in-memory configuration copies. It is not consumed automatically at app
startup or worker launch, and projection does not establish runtime readiness or
activate the provider.

Run `python3 tools/model_catalog.py --json` for the offline inventory check.
It verifies source-defined adapter symbols, the complete role inventory and
disabled placeholders; it rejects model-weight files in the source models directory.
It neither validates a private installation profile nor changes runtime selection.

The development [`tools/doctor.py`](../tools/doctor.py) checks the pinned local
development toolchain. It is not a model, GPU, checkpoint, or endpoint doctor.
Run `python3 tools/check_model_deployment.py --manifest /absolute/private/path --json`
for the private metadata graph check. To inspect a target mapping, add
`--project assistant|memory-contributions|memory-narrative --platform windows|linux|macos`
and, when that feature is already opted in, `--feature-enabled`. Its redacted
`configuration_valid` or `projection_valid` report does not probe runtimes, verify
artifacts, resolve tokens, evaluate quality, or activate bindings. For
deployment-manifest schema 2, `--platform` names the application host; each
projection report also lists role execution-platform and placement-kind enums.
Those safe fields omit WSL instance names. Schema 1 keeps its native-only field
shape. Runtime health
and quality qualification are separate evidence. The CLI reads no existing
application or worker configuration, so its projection report does not check for
conflicts with legacy provider settings.

## Current source map

| Role | Current purpose and adapter source | Replacement boundary |
| --- | --- | --- |
| `vlm_caption` | Image captions through [`caption_service.py`](../server/backend/app/caption_service.py): HTTP, subprocess, built-in VLM, and stub adapters. The external caption worker is maintained separately from this application. | Preserve the caption response contract, attribution, bounded inputs, and configured fallback policy. Keep each VLM runtime and its large dependencies isolated from the API environment. |
| `assistant_asr` | Transient assistant audio through [`assistant_speech.py`](../server/backend/app/access/assistant_speech.py) (`LocalAssistantAsr`); selected through explicit assistant runtime configuration. | Preserve the raw-WAV request and bounded transcript response contract. Assistant opt-in and its current local-only URL validation remain required; an unavailable provider must not become an unconfigured cloud call. |
| `memory_asr` | Audio retained as a memory contribution is handled by the separate annotation path in [`annotation_local.py`](../server/backend/app/access/annotation_local.py) (`LocalAnnotationModels`). Audio retention and derived transcript review are distinct from transient assistant recognition. | Preserve the multipart-audio protocol, retention policy, source-to-derivation links, size/language limits, and failure state. Do not substitute the transient assistant adapter without preserving these semantics. |
| `annotation_polish` | Local wording/tag proposals in [`annotation_local.py`](../server/backend/app/access/annotation_local.py), using a local Ollama-compatible text generation endpoint after recognition. | Treat output as a reviewable proposal, preserve source text and attribution, and retain the loopback-only URL restriction. It is not the ASR provider and cannot establish facts. |
| `narrative` | Reviewable memory-story proposals and grounded conversation through [`memory_narrative.py`](../server/backend/app/access/memory_narrative.py) (`LocalMemoryNarrator`). | Preserve structured output, source IDs, uncertainty, and human review. Generated text must not silently become a saved or published source. |
| `title_suggestions` | Story title suggestions through [`story_titles.py`](../server/backend/app/access/story_titles.py) (`LocalStoryTitleSuggester`), also using a local text-generation endpoint. | Preserve the title schema, source citations, limits, and review requirement. This is a distinct task contract even when it uses the same model service as narrative generation. Factory injection exists; staging/provider wiring and live qualification remain pending. |
| `assistant_tts` | Server-side reply audio through [`assistant_speech.py`](../server/backend/app/access/assistant_speech.py) (`LocalAssistantTts`) and [`windows_tts.py`](../server/backend/app/access/windows_tts.py) (`WindowsSystemSpeech`). The bridge is started by [`serve_windows_tts.py`](../server/scripts/serve_windows_tts.py). | Preserve explicit assistant opt-in, bounded output, cancellation/yield behavior, and no automatic playback. This is separate from native Android/browser read-aloud. Windows system speech is an OS speech engine, not a checked-in model. |
| `face_detection` | Face boxes and landmarks through [`face_detection_service.py`](../server/backend/app/face_detection_service.py): stub, MTCNN, or InsightFace/SCRFD implementations. | Record detector package/model-pack identity and effective device. Strict mode must continue refusing an unsuitable provider; a stub or fallback is not equivalent detection evidence. |
| `face_embedding` | Face recognition vectors through [`face_embedding_service.py`](../server/backend/app/face_embedding_service.py): FaceNet, InsightFace, LVFace direct/HTTP/subprocess, and stub implementations. The bounded approved path is [`run_approved_face_pipeline.py`](../server/scripts/run_approved_face_pipeline.py), which verifies its selected detector/embedder hashes and records shadow artifacts. | Treat detector/alignment, checkpoint, normalization, dimension, and model version as one artifact identity. Existing face vectors cannot be mixed with a replacement merely because dimensions match; shadow and compare a new version before any explicit migration. |
| `image_embedding` | Image vectors through [`vector_index.py`](../server/backend/app/vector_index.py) and the approved versioned image worker [`run_approved_image_embed_worker.py`](../server/scripts/run_approved_image_embed_worker.py). Strict inference requires an explicitly existing local checkpoint. | Preserve preprocessing, normalization, model/checkpoint identity, dimension, and index version. A replacement needs a separately versioned vector set and compatibility evaluation. |
| `video_embedding` | Video-derived vectors through [`run_approved_video_embed_worker.py`](../server/scripts/run_approved_video_embed_worker.py), which uses the selected image embedding implementation over sampled frames and records its model version. | Preserve frame sampling and image-model identity as well as vector metadata. Video vectors are not interchangeable with vectors from a different model or sampling contract. |
| `image_tags` | Optional HTTP image-tag suggestions through [`image_tag_service.py`](../server/backend/app/image_tag_service.py) (`HTTPImageTagProvider`), with a legacy stub fallback. | Preserve bounded response and proposal labeling; an available endpoint or stub does not establish approved tag processing. |
| `text_embedding` | Text vectorization is provided by the text path in [`vector_index.py`](../server/backend/app/vector_index.py), including sentence-transformers/CLIP-compatible implementations. | Record text preprocessing, tokenizer/model identity, normalization, and version. Text and image vectors do not share a space by assumption; equal dimensions do not make them comparable. |

The optional legacy image-tag HTTP/stub integration is included as `image_tags`.
It has a source adapter but no approved tag worker qualification is claimed.
Deterministic image utilities and media probes are workers, not learned-model
providers. FFmpeg supplies media decoding/encoding; it is not a model. A separate
OCR or dedicated video foundation-model adapter is not established by this
inventory; future capabilities need their own contract and reviewed adapter.

## Runtime and replacement rules

Schema 2 separates execution OS from application host through a required
three-field runtime `placement`. Native placement keeps them equal. The WSL2
case is restricted to Windows-hosted Linux `loopback_http` runtimes and the
protected ASR, TTS, and text HTTP roles. Loopback endpoint rules still apply.
This is declared topology metadata; it proves neither that WSL is installed nor
that a listener, port forwarding, provider, or model is available. The
[`deployment.wsl.synthetic.json`](../models/deployment.wsl.synthetic.json)
example keeps every binding disabled and contains only synthetic values.

The API-facing adapter defines the capability contract. Inference can live in a
separate process, service, or repository, provided that the adapter validates the
same inputs and outputs and preserves the feature's privacy and review rules.
Keep VLM, speech, face, and embedding dependencies in separately managed runtimes
where their package, accelerator, or memory requirements differ. A shared giant
ML environment couples unrelated upgrades and resource failures. Worker launchers
should state their own device, concurrency, memory, timeout, and artifact needs;
GPU access should be serialized or budgeted where workers share a device.

Private endpoints and credentials belong in operator configuration outside the
public catalog. Existing private application adapters validate loopback URLs in
[`annotation_local.py`](../server/backend/app/access/annotation_local.py). Do not
broaden that boundary to cloud URLs or add silent cloud fallback. A stub fallback
may be useful in tests or an explicitly selected development mode, but it is not
successful model inference and must not be reported as such.

The private deployment manifest records the provider graph, dependency lock and
artifact identities, device/resource budgets, vector-space identity, role bindings,
and rollback bindings. Its report deliberately omits endpoint, model, path, and
credential-reference values. Keep weights, family media, embeddings, endpoint
values, manifests, and tokens out of this repository. Code licensing does not
establish model or data licensing rights.

## Qualification and migration gates

Use separate evidence for each stage: source adapter exists; declared runtime and
artifact are available; the endpoint reports the expected identity and effective
device; bounded synthetic inputs pass schema and safety checks; quality and
resource use are reviewed; a new model version runs in shadow with outputs tied to
that version; and an owner explicitly activates it. A health response alone does
not prove useful recognition, safe narrative quality, or family/device acceptance.

Embedding or face-provider changes require new versioned outputs and a planned
reindex/re-embedding comparison. Preserve the old version for rollback until the
new one passes the relevant retrieval, recognition, and resource checks. Do not
blend vector spaces based on dimension alone.

The explicit projection methods in
[`model_binding.py`](../server/backend/app/access/model_binding.py) map assistant
and memory selections into copies of the current `RuntimeConfiguration`, staging
configuration, or worker configuration. The assistant target allows a partial
selection of ASR and TTS, but the existing assistant feature opt-in must already
be enabled. The memory contribution target requires both memory ASR and
annotation-polish bindings; narrative requires its own binding. Memory projection
also requires a caller-supplied processing opt-in. These feature flags are
independent and the bridge never changes them.

The source API requires the intended application-host platform explicitly and
refuses a selected runtime on another host. Schema-1 and native schema-2 runtimes
use their execution `platform` as the host; WSL2 uses
`placement.host_platform`, while its execution platform remains Linux. Credential references are resolved only
from an explicit `credential_values` dictionary supplied by the caller; the
bridge and CLI do not read ambient environment variables. If existing endpoint,
model, token, or timeout settings conflict with the selected provider, projection
refuses. Clear old provider fields deliberately before replacement. Rollback is
an explicit projection from the declared rollback bindings; it is not automatic
failover. Reports omit model names, endpoints, credential references, and token
values.

Projection returns configuration values only. It does not build or serve the app,
open worker storage, start a worker, contact providers, verify model/runtime
artifacts, or evaluate quality. It maps request timeout limits (assistant at most
60 seconds; memory provider requests at most 30 seconds) but does not enforce
declared RAM, GPU, or concurrency budgets. Existing worker limits remain in force,
including the 32-item and 1,800-second run bounds. The API staging package
allowlist includes the bridge and manifest loader, while the source catalog is
still stored in the monorepo; packaging a private manifest/catalog for independent
deployment remains future work. Provider activation still requires measured
runtime/artifact and resource checks, bounded quality evaluation, shadow outputs,
and an explicit owner decision.
Human judgments can be entered through the private
[review worksheet workflow](MODEL_QUALIFICATION.md#enter-human-judgments-with-a-private-worksheet).
It binds each judgment to the original evidence and exact case/input/output
identities, preserving observations in a new evidence copy. This records a
reviewer's assertions; it does not establish installed-provider identity or
independently verify quality.
