# Native scene-retrieval diagnostic — October 16, 2026

The current pinned local `ViT-B-32` image/text pair retrieved a relevant image
first for 15/16 English queries, 2/16 Chinese queries and 11/16 mixed queries.
This diagnostic does **not** support enabling direct bilingual scene search.
The runtime scene switch remains default off; no serving binding was created.

## Measurement

The [scene evaluator](SEMANTIC_SCENE_QUALIFICATION.md) compared every query
against the same 32 public natural-scene photographs. Sixteen matched cases
each had English, Chinese and mixed Chinese-English wording and the same one
or more relevant images. These included broad scene impressions, activities,
objects, indoor/outdoor distinctions and visually similar distractors.

| Query cohort | Correct image first | Correct image in first five | Mean reciprocal rank | Mean relevant-image recall at five |
| --- | ---: | ---: | ---: | ---: |
| English | 15/16 | 16/16 | 0.9583 | 0.9792 |
| Chinese | 2/16 | 5/16 | 0.2373 | 0.2396 |
| Chinese-English mixed | 11/16 | 13/16 | 0.7340 | 0.7917 |

Only two matched cases retrieved a correct image first in all three languages.
Overall top-one was 28/48 and top-five was 34/48; those aggregate counts hide
the substantial Chinese deficit. Top-five hits and recall differ: a hit needs
one relevant image, while recall considers all labeled relevant images.
Nonrelevant near-ties count ahead, as documented by the evaluator.

The images were the lexicographically first 32 photographs in the public
[Ultralytics COCO128 distribution](https://docs.ultralytics.com/datasets/detect/coco128/),
which uses images from [COCO](https://cocodataset.org/). Selection was fixed
before image-content or model inspection. Assistant visual curation and an
independent assistant review established the labels before scoring; one
motorbike was removed from bicycle positives during that review. The final
dataset fingerprint is
`7915b1a53fe214ceacf65998df29d27093cf863358f4c74429e72acdb5f5178f`.

This is a small, assistant-curated diagnostic, not a human/family-reviewed or
held-out evaluation. These public training-set images may overlap model
training. The set does not establish general multilingual recall, family-photo
quality, person identity, kinship, dialect comprehension or ASR accuracy.
No labels or queries were changed after the measurement to improve the scores.
Images, queries, input paths and raw reports remain outside public source.

## Native execution and evidence

The measured source was `878ab0562981f6175dcc5f2bea588947ab175de4`.
Its 233-file source-only package included the two evaluator modules that had
previously been missing from the portable source allowlist. An isolated
extraction regression checks that the packaged evaluator can plan without
checkout fallback, optional ML imports or private-input reads.

The existing full local checkpoint was used without a new model or dependency
download. Checkpoint identity was
`f807d82432eb6c926694b401cb55d5e40fad5a7df507e6a12cf9a83e7ac81ab0`.
The unbound provider configuration and exact installed versions matched:
OpenCLIP 3.1.0, Torch 2.8.0+cu126, torchvision 0.23.0+cu126, Pillow 11.3.0,
NumPy 2.2.6, ftfy 6.3.1 and regex 2025.7.34. The CUDA-capable package versions
do not mean this run used a GPU.

The offline Windows CPU child ran with two compute threads in a Windows Job
with a 4 GiB memory cap, four-process limit, 8 GiB minimum free RAM and a
300-second timeout. It completed successfully in 59.328 seconds, including
47.063 seconds for model loading. The maximum measured per-image interval was
0.203 seconds and per-query interval 0.125 seconds. These observations are for
this bounded offline run; they are not warm serving-latency, throughput,
observed peak-memory or GPU qualification.

The native controller initially stopped during setup because its private
supervisor read UTF-8 Chinese JSON using Windows' default GBK encoding. No
model-start record or model outputs existed. A guarded resume used explicit
UTF-8, verified all already-extracted source bytes and required an empty image
directory and no prior model run. The failed setup evidence was retained.
The application evaluator's strict UTF-8 private-document reader was unchanged.

An independent readback verified the saved measurement digest
`20479fc129a4a770f9d6d1f83ab45b55c558e24adce8a33d0ef0f822180d3854`
and confirmed that the provider configuration was unchanged. Model, input and
implementation pins were checked during measurement and fully rehashed before
completion. No family media, library database, memberships, kinship mapping,
live task/service, signed package or OTA pointer was changed. No listener was
started and no vector publication or scene activation occurred.

## Development consequence

The English result suggests that language input is a useful next investigation
for this particular model; it does not prove that an automatic translator will
preserve vague intent. The next model experiment should compare a qualified
multilingual encoder or local scene-query adaptation against frozen labels,
with additional unseen natural scenes before making an activation decision.

Any query-adaptation path must preserve the original user wording, record the
derived model input separately, and include adaptation in the preprocessing
identity and binding. It must not substitute translated bytes while claiming
the original encoder recipe, turn an impression into a factual filter, or
weaken people/date/place/text scope or library authorization. Native serving
resources, compatible immutable image-vector coverage and family/device
acceptance remain separate gates.

The subsequent [local translation experiment](SEMANTIC_SCENE_TRANSLATION_2026-10-16.md)
kept this dataset and encoder frozen. It improved Chinese/mixed retrieval while
exposing a meaning shift, and remains offline with a separate derived-input
receipt.
