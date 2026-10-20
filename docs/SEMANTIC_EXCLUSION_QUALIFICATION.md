# Offline semantic exclusion scorecard

`server/scripts/semantic_exclusion_cases.py` is a pure evaluator for reviewed
contrast and absence cases. It accepts an explicitly labeled candidate set and
caller-provided normalized image/text vectors. It performs no file access,
model or provider work, service calls, downloads, configuration reads, vector
persistence or activation. It does not change the existing
`photohouse.semantic_scene_cases.v1` contract.

The separate `photohouse.semantic_exclusion_cases.v1` input has exactly
`schema`, `images` and `cases`. `images` is a list of 4–64 unique stable IDs.
Each case has exactly `id`, `relevant_images`, `forbidden_images` and `queries`.
Relevant and forbidden IDs must be nonempty, unique, known and disjoint.
`queries` contains exactly `en`, `zh` and `zh-en`; each query is trimmed,
single-line UTF-8 text up to 512 bytes. IDs and exact query bytes, along with
the schema and labels, feed the dataset fingerprint. The contract contains no
paths or private image content.

Call `evaluate(dataset, image_vectors, text_vectors, dimension=..., top_k=5)`
with exact maps from image IDs and `<case-id>:<language>` keys to finite,
unit-normalized vectors. The dimension must be 512 or 768. Every vector must
have the selected exact dimension and a norm within `1e-3` of one. `top_k` is
an integer from 1 to 64 and is clamped to the candidate count.

For every case and language, the report gives the pessimistic rank of the best
relevant image, whether any forbidden image scores at least `best relevant -
1e-7`, and whether a forbidden image could appear in the requested top-k. The
existing scene evaluator's pessimistic relevant-rank tie policy is reused. For
top-k inclusion, a forbidden candidate counts when fewer than k candidates
score strictly above it by more than `1e-7`; this counts ties as possible
inclusions. Per-language and overall summaries count queries with each type
of violation and report their rates, rather than counting individual images.
A relevant first-place result therefore cannot hide a forbidden
candidate that remains in the requested result set.

Nine generated-vector tests cover ranking, near-ties, top-k inclusion,
multilingual differences, 512/768 dimensions and invalid inputs. This scorecard
was initially tested only with generated vectors. The earlier multilingual
model screen did not report this explicit forbidden-candidate scorecard.
The source-only staging package includes the helper and verifies it imports
without optional ML packages or a checkout fallback; no native run is implied.

The pinned offline SigLIP2 runner now accepts an explicit
`--exclusion-dataset ABSOLUTE_PRIVATE_JSON` alongside its existing `--run`,
`--configuration` and `--output-directory` arguments. Its existing closed
configuration and scene-dataset schemas are unchanged. Planning mode refuses
the extra path without reading it. Before loading a model or creating output,
the label file must be a closed `photohouse.multilingual_exclusion_labels.v1`
envelope with exactly `schema`, `scene_dataset_sha256` and `dataset`. The
`dataset` is the existing exclusion schema above; `scene_dataset_sha256` must
match the reviewed scene dataset's content fingerprint, including candidate
image hashes. Reusing stable IDs with changed candidate bytes is refused.
The adapter also requires the same reviewed candidate IDs, complete case IDs,
relevant labels and exact original English/Chinese/mixed query bytes as the
scene dataset. Candidate and case order may differ; query normalization,
missing cases and substituted labels are refused.

The adapter scores the same in-memory 768-dimensional image and text vectors
used for scene metrics. It uses top-five inclusion and the evaluator's
conservative tie policy. Its separate
`photohouse.multilingual_exclusion_measurement.v1` report records the
exclusion-dataset and bound-label fingerprints, evaluator source hash, original/input query
hashes, image hashes and vector checksums. The ordinary measurement schema
remains unchanged when no exclusion dataset is supplied. Neither mode saves
vectors, query text, an index or a serving binding. Adapter tests cover exact
binding, pre-model refusal, output privacy and the scorecard's execution on
stub encoder outputs; these tests alone do not qualify the real model.

The output always declares `activation_approved: false`. A scorecard is a
measurement aid, not a model-quality threshold or activation decision. The
input vectors' origin, image identity, label correctness and review process
remain the caller's responsibility. Admission-time refusal of unsupported
exclusions is a separate product safeguard and does not establish that a model
understands negation. Serving bindings, compatible immutable image coverage,
latency/resource limits, protected integration and family/device acceptance
remain separate gates. Semantic search stays disabled until those gates are
independently resolved.
