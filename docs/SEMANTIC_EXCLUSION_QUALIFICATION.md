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
inclusions. Per-language and overall summaries report both exclusion counts
and rates. A relevant first-place result therefore cannot hide a forbidden
candidate that remains in the requested result set.

The output always declares `activation_approved: false`. A scorecard is a
measurement aid, not a model-quality threshold or activation decision. The
input vectors' origin, image identity, label correctness and review process
remain the caller's responsibility. Admission-time refusal of unsupported
exclusions is a separate product safeguard and does not establish that a model
understands negation. Serving bindings, compatible immutable image coverage,
latency/resource limits, protected integration and family/device acceptance
remain separate gates. Semantic search stays disabled until those gates are
independently resolved.
