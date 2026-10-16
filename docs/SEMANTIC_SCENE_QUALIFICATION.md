# Private natural-scene retrieval measurements

The [October 16 native diagnostic](SEMANTIC_SCENE_BENCHMARK_2026-10-16.md)
measured the current local pair on 32 public photos and 48 matched queries.
Its Chinese deficit keeps bilingual activation unqualified; source tests below
remain distinct from that actual model measurement.

`server/scripts/qualify_semantic_scenes.py` evaluates one explicitly selected
local image/text checkpoint against an owner-selected private image set. Each
case has English, Chinese and mixed Chinese-English wording with the same
reviewed relevant images. It measures rankings, including multiple valid
matches and distractors, without changing assistant behavior or runtime config.

The [generated shape canary](SEMANTIC_PAIR_QUALIFICATION.md) remains a separate
baseline. This runner does not select images from a library, inspect a database,
download a dataset or weights, publish vectors, create a joint-space binding,
start a listener, sign a release or enable scene search. No-argument planning
reads no private files and imports no optional ML packages:

```sh
python server/scripts/qualify_semantic_scenes.py
```

## Select and label the set

Keep the dataset JSON, images, provider config and reports outside source, in
owner-private storage. Select individual local JPEG or PNG files explicitly;
there is no directory discovery or recursive scan. Use neutral IDs so reports
do not contain people's names. Every image has a distinct SHA-256. Files and
their parents must satisfy the existing private-file/DACL checks; links,
junctions and hard-linked images are refused. UNC image paths are refused.
No live library permission or account mapping is changed by selecting a set.

For a useful first measurement, choose 24–64 distinct natural scenes and 8–32
matched cases. Cover activities, objects, indoor/outdoor settings, lighting and
loose remembered impressions. Include visually similar distractors: a beach
without people playing, a playground without the requested activity, or an
indoor meal instead of an outdoor picnic. Label every valid match before
looking at model rankings; a case can have several. Reword all three language
queries to express the same intent. Keep names, dates and kinship conditions
out of these scene-only prompts; those use the existing protected hard filters.

The accepted format is `photohouse.semantic_scene_cases.v1`, with exactly:

- `schema`: the schema string above.
- `review`: exactly `natural_scenes` and `labels_reviewed`, both booleans.
  Execution requires both true. These are curator declarations; the program
  does not independently verify image authenticity or label correctness.
- `images`: 4–64 objects containing only `id`, absolute local `path` and
  lowercase 64-character `sha256`. IDs, paths and digests must be distinct.
- `cases`: 2–32 objects containing only `id`, `relevant_images` and `queries`.
  Each ID is distinct. `relevant_images` names one or more known image IDs,
  without repeats, leaving at least one nonrelevant candidate. `queries` has
  exactly `en`, `zh` and `zh-en`, each a nonblank, trimmed, single-line string
  of at most 512 UTF-8 bytes. Nothing is truncated. The pinned tokenizer's
  independent token limit still applies during execution.

Image and case IDs use 1–64 ASCII letters, digits, periods, underscores or
hyphens, beginning with a letter or digit. A case looks like this (image IDs
must also be declared in the dataset's `images` list):

```json
{
  "id": "scene-001",
  "relevant_images": ["image-003", "image-011"],
  "queries": {
    "en": "Children splashing in shallow water at the beach",
    "zh": "孩子们在海边浅水里玩水",
    "zh-en": "孩子们在 beach 的浅水里玩水"
  }
}
```

The small structural minimum is suitable for fixture checks. Top-five retrieval
on four candidates is always trivial; it does not qualify natural-scene search.
Do not repeatedly tune prompts or labels on the held-out measurement set and
then describe the result as unseen evaluation. Changing labels, query bytes,
image identities or review declarations changes the dataset fingerprint.
Relocating identical image files preserves it. Query language labels are also
curator declarations, not automatic language recognition. No Shanxi/Jin dialect
phrases or aliases are inferred, and no ASR/audio is measured.

## Explicit execution

Use the existing [pinned local provider](LOCAL_SEMANTIC_TEXT_PROVIDER.md) with
`binding: null`. Its full checkpoint, BPE, exact text-package versions and
`cpu` or `cuda:0` device remain explicit. This runner reuses that one loaded
checkpoint's image and text towers; it does not add a model implementation or
change the installed provider. The private run JSON has exactly:

```json
{
  "schema": "photohouse.semantic_scene_run.v1",
  "provider_configuration": "/absolute/private/provider.json",
  "dataset": "/absolute/private/scenes.json",
  "image_package_versions": {
    "torchvision": "EXACT_INSTALLED_VERSION",
    "Pillow": "EXACT_INSTALLED_VERSION",
    "numpy": "EXACT_INSTALLED_VERSION"
  },
  "max_elapsed_seconds": 600
}
```

Select an existing private output parent and a new output directory. Existing
destinations are never overwritten. Configuration, package versions, image
byte budgets, file hashes and private identities are checked before loading
the model. The output is reserved once and `started.json` is saved before the
load, so a failed run retains evidence:

```sh
python server/scripts/qualify_semantic_scenes.py --run \
  --configuration "/absolute/private/scene-run.json" \
  --output-directory "/absolute/private/new-scene-measurement"
```

Run only in an explicitly selected native environment with independently
bounded process/RAM/GPU resources. `max_elapsed_seconds` is a cooperative
30–1800-second budget covering model loading and measurement. It cannot
preempt an in-progress decoder or GPU call and is not an OS resource limit.
Each encoded image is at most 32 MiB, the input set at most 256 MiB, and each
decoded image at most 16,777,216 pixels with each side at most 8192 pixels.
Animated/multipage formats are refused. JPEG/PNG bytes are verified, EXIF
orientation is applied, and RGB pixels without metadata feed the observed
evaluation resize/crop/normalization pipeline. That recipe has its own digest;
it does not impersonate a production worker or qualify legacy vectors.

## Read the result

The private `measurement.json` records the dataset fingerprint, exact model
probe, observed preprocessing/package/source identities, image/vector hashes,
per-case ranks, separate language summaries and timings. Input/model/source
pins are checked during the run and fully rehashed at the end. The report
contains no image paths, raw queries, image bytes or raw vector components.
Standard output contains only a bounded aggregate summary and report digest.
Dependency diagnostics are suppressed; failures emit a fixed error.

Every query is compared with every selected image. Each language and the
overall summary report query count, top-one/top-five hit counts, mean reciprocal
rank and mean recall at five over all labeled relevant images. The report also
includes candidate count, effective top-k and matched-case summaries showing
whether all three languages retrieved a relevant image first and each case's
worst language rank. Inspect these separately; strong English results cannot
establish Chinese or mixed-query quality.

A nonrelevant candidate within `1e-7` of a relevant score counts ahead of it;
relevant near-ties use stable ID order. This pessimistic policy gives a collapsed
encoder no arbitrary top-one credit. Recall at five is the fraction of labeled
relevant images with conservative ranks at most five, averaged across queries.
Scores/ranks are relative retrieval measurements, not factual labels or
probabilities. No automatic relevance threshold or activation decision is made.

Generated CPU tests exercise validation, ranking, multilingual failures,
multiple labels, constant encoders, input changes, limits and failure privacy.
They do not provide an independently reviewed real-scene set or a native model
measurement. Before enabling a family pilot, review that actual measurement,
qualify compatible immutable image-vector coverage, establish native serving
latency/memory limits, and review runtime activation. Family/device acceptance,
hard-filter authorization, and dialect/ASR quality remain separate evidence.

The [offline local translation experiment](SEMANTIC_SCENE_TRANSLATION_2026-10-16.md)
uses a separate derived dataset and adaptation receipt with this evaluator.
Its improved Chinese/mixed diagnostic scores do not approve translation
faithfulness or a serving binding; the original inputs remain separate.
