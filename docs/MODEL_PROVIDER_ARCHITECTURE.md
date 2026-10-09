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
Provider selection remains with the explicitly configured application runtime and
the existing per-feature settings.

Run `python3 tools/model_catalog.py --json` for the offline inventory check.
It verifies source-defined adapter symbols, the complete role inventory and
disabled placeholders; it rejects model-weight files in the source models directory.
It neither validates a private installation profile nor changes runtime selection.

The development [`tools/doctor.py`](../tools/doctor.py) checks the pinned local
development toolchain. It is not a model, GPU, checkpoint, or endpoint doctor. A
provider-specific doctor should remain an offline configuration check: validate
the declared role, adapter, runtime and artifact metadata, enabled state, and
resource budget without making model calls. Runtime health and quality qualification
are separate evidence.

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
| `face_embedding` | Face recognition vectors through [`face_embedding_service.py`](../server/backend/app/face_embedding_service.py): FaceNet, InsightFace, LVFace direct/HTTP/subprocess, and stub implementations. The approved worker records versioned artifacts in [`run_approved_face_worker.py`](../server/scripts/run_approved_face_worker.py). | Treat detector/alignment, checkpoint, normalization, dimension, and model version as one artifact identity. Existing face vectors cannot be mixed with a replacement merely because dimensions match; shadow and compare a new version before any explicit migration. |
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

For every deployable provider, its private deployment record should link to the
adapter and external implementation, source revision, model card/license and
permitted use, immutable checkpoint digest, runtime/dependency versions,
preprocessing and response contract, data handling policy, device/resource limits,
and rollback target. Keep weights, family media, embeddings, endpoint values, and
tokens out of this repository. Code licensing does not establish model or data
licensing rights.

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

Provider selection is not yet unified behind the catalog: application adapters
still use explicit runtime construction and feature-specific settings, while
approved workers receive their model and version through their own arguments and
receipts. The catalog remains descriptive until a separately reviewed manifest
connects those choices with strict validation and rollback semantics. Any such
integration must preserve current explicit opt-ins, local endpoint restrictions,
and per-feature contracts; it must not imply that inventory metadata proves a
model is installed or qualified.
