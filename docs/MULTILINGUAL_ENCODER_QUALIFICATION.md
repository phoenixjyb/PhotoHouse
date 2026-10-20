# Offline multilingual encoder qualification

Semantic search stays disabled while a direct multilingual encoder is evaluated.
The offline runner adds no serving provider, binding, database migration, vector
publication or activation path.

The candidate is [Google SigLIP2 base, patch 16, 256 pixels](https://huggingface.co/google/siglip2-base-patch16-256)
at revision `3f9f96cb90da5dbc758b01813f2f6f1aee24c1ab`. The official FixRes
configuration declares `model_type: siglip`: it uses `SiglipModel` and
`SiglipProcessor`, rather than the NaFlex API. The checkpoint and tokenizer have
seven exact byte/hash pins. This model produces 768-component image/text
features; existing OpenCLIP vectors have 512 components and cannot be reused.

`server/scripts/qualify_multilingual_scenes.py` prints a plan with no arguments.
That path reads no private files and imports no optional ML packages. Execution
requires `--run --configuration ABSOLUTE_PRIVATE_JSON --output-directory
NEW_ABSOLUTE_PRIVATE_DIRECTORY`. Do not put these private inputs in the checkout.

The closed `photohouse.multilingual_scene_run.v1` configuration contains exactly:

- `schema`, `model_directory`, and `dataset` (the existing reviewed scene schema).
- `artifacts`: the seven official filenames, each with exact `bytes` and `sha256`.
- `package_versions`: the exact dependency versions named by the runner.
- `max_elapsed_seconds`: an integer from 30 to 1800, a cooperative deadline.

The runner requires private canonical local paths, verified single-frame images,
and an exact model file set. It loads safe tensors locally on CPU with remote
code disabled. It records source/model/image hashes, original-query hashes,
token counts, preprocessing, normalized vector checksums and ranking metrics.
It saves neither feature arrays nor query text in the measurement. Original
Chinese, English and mixed queries reach the candidate without translation.
The model input is explicitly lowercased, with both original and model-input
hashes retained. The pinned tokenizer declares only input IDs, so no attention
mask is supplied. Overlength text is rejected before fixed-length padding;
truncation is disabled.

The parent operator must enforce hard resource limits and offline networking.
The CLI deadline cannot interrupt a hung native model call. For the first native
screen, the frozen private plan specifies two CPU threads, an 8 GiB Job Object,
four processes, 600 seconds per job and a 16 GiB free-RAM floor. The child must
prove its assigned Job before importing model packages. Model acquisition is a
separate public download operation on Windows; inference must use local files.
No model artifacts are downloaded to the Mac source workspace.

Compare the unchanged earlier public scene set as a regression and a separately
reviewed, frozen public scene set for this development round. Keep English,
Chinese and mixed results, literal/vague/contrast cohorts, and individual losses
visible. The public photos may have appeared in model training: this is a
holdout from this application's earlier evaluation work, not a training holdout.
Assistant visual/text review is not family or human acceptance. Freeze labels,
queries, resource budgets and screening criteria before any model scoring.

A completed screen does not establish production readiness. Broader negation,
count, relationship and ambiguity evaluation, private-family relevance,
compatible immutable vector coverage, protected serving integration, serving
latency and device acceptance remain separate gates. Translation-based
comparisons must also satisfy the [fidelity review contract](SEMANTIC_SCENE_TRANSLATION_FIDELITY.md);
a high retrieval score cannot establish that a translation preserved meaning.

## Native screening result — October 20, 2026

The native path completed on source `8bc6f43665ff17596e4ba8aaaef4efaf407c52e7`,
using the pinned model and installed dependencies above. The candidate passes
the frozen directional multilingual screen, but **does not qualify for
production activation**. Direct negation and mixed-language contrasts remain
weak. Semantic search remains disabled.

Sixteen additional public COCO128 photos (positions 65–80) were selected before
model inspection. Sixteen matched cases have English, Chinese and mixed
variants: eight literal, four vague and four contrast cases. An independent
assistant reviewed the photos and wording before scoring; two review corrections
were applied before the final freeze. There was no human/family review.

| Fresh set, top-one / 16 | English | Chinese | Mixed |
| --- | ---: | ---: | ---: |
| Existing OpenCLIP, direct queries | 15 | 2 | 8 |
| SigLIP2, direct queries | 15 | 15 | 15 |

SigLIP2 top-five was 16/16 in each language; the earlier encoder scored
16/16, 9/16 and 14/16 respectively. Fifteen cases ranked correctly first
in all three languages, compared with two cases for OpenCLIP. The remaining
fresh contrast missed in all three languages. These small public-image scores
do not establish family relevance or open-ended vague-intent understanding.

On the unchanged 32-photo earlier regression, SigLIP2 direct top-one was
29/32 English, 23/32 Chinese and 23/32 mixed; top-five was 32/32, 32/32 and
30/32. Literal descriptions were 12/12 in all languages. Vague cases were
11/12, 6/12 and 9/12; contrasts were 6/8, 5/8 and 2/8. This earlier set
is a regression, not a fresh development holdout.

A separate diagnostic used three positive/negative pairs on the same 16
candidate photos, with all three language variants. Its queries and labels
were independently reviewed and frozen before that diagnostic was scored.
This reuses photos and is not an additional untouched-photo holdout.
All nine positive variants ranked their intended photo first. All nine
negative variants ranked their intended photo second; none of the nine
pair/language combinations retrieved both sides correctly first. All 18
variants still had a top-five hit, illustrating why top-five relevance cannot
establish that an exclusion was honored. The diagnostic establishes concrete
failures, not a calibrated general negation error rate.

Four successful inference jobs used two CPU threads, an 8 GiB Job Object,
four processes, a 600-second ceiling and a 16 GiB free-RAM floor per job.
Each child proved its Job limits before model imports. Source files, model
artifacts, images and dataset identities were checked around execution; an
independent readback checked all 248 packaged source hashes and the measurement
hashes, Job proofs and SigLIP2 original/lowercased query hashes. The older
OpenCLIP measurement format has no per-query hash receipts; its direct-query
provenance rests on the inspected runner, pinned dataset and source hashes.

The worker denied Python socket connection/listening calls and used offline
hub settings. This is not an OS-firewall qualification. These CPU measurement
timings do not qualify serving/network latency, concurrency or peak memory.
No serving binding or compatible immutable index was created. Live health
checks before and after the runs confirmed the semantic flag off, no semantic
provider configuration, healthy HTTPS and protected anonymous boundaries.

Translation v2 now rejects detected cue changes at the provider-response
boundary and binds declared review to exact source/output and recipe hashes.
All four earlier flagged outputs are rejected by the guard; four manual
assistant-reviewed corrections pass it. This does not qualify the complete
earlier 64-output translation dataset or guarantee arbitrary translation
faithfulness. Raw datasets, corrections, resource receipts and measurements
remain outside Git.

The next gate is reliable exclusion/relationship handling with explicit
constraints or clarification before ranking. Compatible 768-dimensional image
coverage, protected serving integration, serving latency and family/device
acceptance also remain outstanding. No GPU, ASR or Shanxi dialect acceptance
is claimed.

Validation on that unchanged source passed 2,573 API tests and 2,520 subtests,
including package dependency/planning checks, plus the generated no-listener
application demo. The focused encoder/translation suites passed 110 tests.
The later result-record commit changes documentation and its source ledger only.
