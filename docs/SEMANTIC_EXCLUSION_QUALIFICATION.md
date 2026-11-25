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

## October 20 real-model diagnostic

The adapter was run on Windows against the pinned local SigLIP2 model at
source `64a169594`. It reused the earlier frozen 16 public photos and six
queries per language: three positive/negative contrast pairs about a dog's
location and a held/unheld phone. Each query received one explicit forbidden
counterpart from the opposite side of its reviewed pair. The bound labels
were frozen before this run, with independent assistant review. The earlier
model results were already known: this is a repeated diagnostic, not an
untouched holdout or human-confirmed family relevance evaluation.

| Query language | Variants | Forbidden ahead of/tied with best relevant | Forbidden possible in top five |
| --- | ---: | ---: | ---: |
| English | 6 | 3 | 6 |
| Chinese | 6 | 3 | 6 |
| Mixed Chinese/English | 6 | 3 | 6 |
| Total | 18 | 9 | 18 |

All nine negated variants placed the forbidden counterpart ahead of or tied
with the intended image; the intended image ranked second under the
pessimistic tie policy. All nine positive variants ranked their intended image first, but a
forbidden counterpart could still occur in their top five. The earlier
top-five relevance result therefore concealed exclusion failures. These
counts demonstrate concrete failures on three contrasts; they do not estimate
a general error rate or qualify an arbitrary similarity threshold.

A separate replay through the current admission guard required clarification
for all nine negated variants and for none of the nine positive variants.
That evidence qualifies those guard decisions, not the encoder's understanding
of negation. The offline diagnostic intentionally bypasses admission so the
model weakness remains visible; production must retain the guard.

The successful inference job used two CPU threads, an 8 GiB Windows Job Object,
four-process limit, 600-second timeout and 16 GiB free-memory floor. The child
proved its limits before ML imports. An independent readback verified the
257 packaged source hashes, 16 image receipts, 18 original/lowercased query
receipts, bound labels, measurement hash and Job proof. Python socket denial
and offline hub settings are not an OS firewall qualification. No raw vectors
were persisted. Active API task/listener/config and phone/TV feed pointers
were unchanged; semantic search remained disabled.

Focused source checks passed 87 tests and 17 subtests; seven committed-source
staging/extraction checks also passed. These do not establish serving latency,
GPU behavior, Android installation or family acceptance. Private packet,
failure/launch evidence and measurement receipts remain outside Git.

The output always declares `activation_approved: false`. A scorecard is a
measurement aid, not a model-quality threshold or activation decision. The
input vectors' origin, image identity, label correctness and review process
remain the caller's responsibility. Admission-time refusal of unsupported
exclusions is a separate product safeguard and does not establish that a model
understands negation. Serving bindings, compatible immutable image coverage,
latency/resource limits, protected integration and family/device acceptance
remain separate gates. Semantic search stays disabled until those gates are
independently resolved.


## October 25 admission phrase repair (policy 3, source only)

A generated endpoint replay found eight explicit exclusions that reached
approximate ranking: Chinese prohibitions such as `不得有其他人`, `不准出现狗`
and `甭有狗`, exception clauses such as `除狗之外`, and English `excepting`
and `free from`. Each returned a result and invoked the fixture provider. A
similarity score could not establish these negative conditions.

The shared admission guard now recognizes these bounded prohibition and
exception forms, English omission verbs and `omission of`, and simplified,
traditional and mixed wording. The request asks for a complete revised positive
search before any vector read or encoder call. Literal text inside a supported
`find photos containing "..."` request stays opaque to this guard; an unframed
quoted visual scene does not. Positive controls include `不倒翁`, `无锡`,
`没落的建筑`, `不得了的美景` and `freeform`.

This is a conservative cue guard, not a general negation grammar. Ambiguous
`除了...` wording and `不准时` can request clarification; `photos, videos
excepted` also clarifies rather than silently extending the closed media rewrite.
These restrictions preserve uncertain conditions. They do not prove the model
understands absence or qualify Shanxi/Jin dialects or ASR.

Exclusion policy version 3 participates in the semantic extension binding so
prior bound rankings must refresh. The focused literal-plan, pending-context,
intent, semantic endpoint, initial-search and refusal suites passed 132 tests
and 423 subtests. Authorization-before-guard and server-snapshot admission are
retained. This source change is later than the `605ff8d` full API check and the
`4254107` Windows measurement; those results do not qualify these new bytes.
No deployment or activation is included. Semantic search remains OFF.
