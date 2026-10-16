# Offline local scene-query translation — October 16, 2026

Translating Chinese and mixed Chinese-English scene queries with the existing
local Qwen model substantially improved retrieval on the frozen
[32-photo diagnostic](SEMANTIC_SCENE_BENCHMARK_2026-10-16.md). One translation
also changed the intended meaning. This experiment supports further evaluation;
it does not qualify automatic translation or activate scene search.

## Matched comparison

The same 16 cases, 32 public COCO128 photos, relevance labels, English queries
and pinned `ViT-B-32` image/text encoder were used. Only Chinese and mixed query
inputs were translated. The translator received each original query separately,
without images, relevance labels or the parallel English query. Outputs were
saved once, without retries or post-score edits.

The language columns below identify the **original user-input cohort**. Adapted
Chinese and mixed queries were encoded as derived English text.

| Original cohort | Direct top-one | Translated top-one | Direct top-five | Translated top-five | Translated MRR | Translated recall at five |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| English, unchanged | 15/16 | 15/16 | 16/16 | 16/16 | 0.9583 | 0.9792 |
| Chinese | 2/16 | 14/16 | 5/16 | 16/16 | 0.9271 | 0.9792 |
| Chinese-English mixed | 11/16 | 15/16 | 13/16 | 16/16 | 0.9583 | 0.9792 |

All three cohorts retrieved a relevant image first in 14/16 matched cases,
compared with 2/16 before adaptation. Overall top-one rose from 28/48 to 44/48;
top-five rose from 34/48 to 48/48. After adaptation, the bicycle case ranked
third in every cohort (direct ranks were 3, 16 and 5). The Chinese food case
still ranked second after translation.

An independent assistant text review compared all 32 translations and eight
additional wording guards with their original inputs. In the food case, wording
intended as food ready to eat became wording suggesting ongoing preparation.
Two other translations chose a singular noun where the parallel English case
used a plural; those were plausible readings of number-neutral Chinese, but
expose imperfect equivalence between the cohorts. Awkward English occurred in
one activity description. These findings were retained, without correcting or
regenerating the measured outputs.

All eight guard outputs preserved their stated negation, uncertainty, counts
and spatial relations; a sign containing an instruction remained quoted sign
content. These are text checks only. They do not establish that the image/text
encoder honors negation, that a model resists arbitrary instructions, or that
translation preserves vague intent generally.

## Helper contract and provenance

`server/scripts/semantic_scene_translation.py` provides offline helpers only;
there is no serving route, configuration switch, provider startup or dataset
writer in this module.

- `LocalSceneTranslator` requires an explicit loopback HTTP chat endpoint and
  model name. It uses one in-flight request, no retries, no environment proxy,
  no redirects and no history. A bounded response and cooperative deadline
  reject malformed, incomplete or tool-call responses with fixed diagnostics.
- Each original query is supplied as quoted data under a fixed translation
  prompt. Generation uses temperature zero, 128 output tokens, a 2048-token
  context, disabled thinking and an exact one-field JSON schema. Structural
  validation requires bounded printable English output; it cannot verify meaning.
- `derive_dataset` requires exactly one translation per Chinese and mixed case.
  It returns a new dataset, preserving original images, hashes, labels and English
  queries. Callers retain the original dataset separately. The derived copy's
  existing review flags describe the original relevance labels; its separate
  receipt explicitly leaves translation review and activation unapproved.
- The receipt binds source and derived dataset fingerprints, each translated original and
  derived query hash, and the adaptation recipe. The recipe includes module and
  prompt hashes, generation options, output schema and provider/model identity.
  It contains no endpoint, input paths, query text or vectors.

The derived dataset can be passed to the existing
[scene evaluator](SEMANTIC_SCENE_QUALIFICATION.md) under a separate private run
configuration. Its measurement must stay alongside the translation receipt and
original dataset. This does not revise an encoder binding or approve a serving
preprocessing recipe. A future serving integration must bind adaptation itself,
retain original user wording, and preserve authorized person/date/place/text
conditions independently of visual ranking.

## Native execution

The translation helper source was
`66f3a479d1dbeca6d809d3dfc8186fd4d0e539c1`. The already-installed local
`qwen3.5:9b-q4_K_M` ran through Ollama 0.40.0 in a temporary loopback-only
provider owned by a bounded Windows Job. The signed provider binary, manifest
and every model blob were hashed before and after generation. No model or
dependency download was performed. The model manifest fingerprint was
`56671c2ab9385f9cfcb404638e32cd62d88e3501d44822208363c010179a3c90`.

The translation Job allowed at most 16 GiB RAM, 12 processes and 900 seconds,
with a 16 GiB free-RAM floor. The selected RTX 3090 had over 23 GiB free before
the run, exceeding the 10 GiB floor; provider inspection confirmed full GPU
placement with the requested context. One cold warmup took 83.281 seconds.
The 32 benchmark calls and eight guard calls then completed without retries;
the largest measured benchmark-query interval was 0.641 seconds. These are
serial offline observations, not serving concurrency or peak-memory evidence.

An initial setup refused the provider before startup because a generic
checkpoint reader compared Windows' inferred executable permission bits between
path and open-handle stat results. A private experiment-only binary check then
verified the regular file, stable identity and full digest; model/blob checks
remained unchanged. No application checkpoint reader was relaxed.

After generation and saved-output verification, the Job supervisor returned
from bounded cleanup, then failed an immediate port-bind check. Its numeric
worker exit code was not persisted. A later independent readback verified all
saved outputs and that the private port was released. The translations were
not rerun; this missing wrapper receipt remains an execution limitation.

Scoring reused evaluator source
`878ab0562981f6175dcc5f2bea588947ab175de4` and the original CPU encoder
configuration. A separate Windows Job enforced 4 GiB RAM, four processes,
300 seconds and an 8 GiB free-RAM floor. It exited successfully in 55.594
seconds, including 44.109 seconds of model loading. Limits were supplied by
the private outer Job controller; the evaluator itself reports no CLI-enforced
resource limits. All 32 image-vector
checksums, the text probe and English metrics matched the baseline exactly.
The image preprocessing recipe was identical apart from its dataset fingerprint.

| Evidence | SHA-256 |
| --- | --- |
| Original dataset | `7915b1a53fe214ceacf65998df29d27093cf863358f4c74429e72acdb5f5178f` |
| Derived dataset | `a99645128892a566887c85df5d85a2e022965f16d352ef3b281d2fac6bb8ff20` |
| Adaptation recipe | `d89fe71971c8ca0e64601320403be0707a2b8f0f9ea17e6a45cbb9e81bea6f01` |
| Translation receipt file | `3a106df11f0250864c3514fe4464817912c6f0b12f74bbadbad4d14442a33dfc` |
| Adapted measurement file | `6e547397725957492c300f97c40850b49e19c77f73f665ca72d7a4073cf4bf73` |

Raw queries, images, paths, translations, resource records and reports remain
private. This small assistant-curated set may overlap model training; there is
no held-out, human/family, dialect or ASR acceptance. No library database,
kinship mapping, memberships, live service, vector publication or signed package
was changed. The runtime scene gate remains off.

## Next qualification

Evaluate untouched scenes and more ambiguous bilingual wording, with separate
translation-faithfulness and retrieval review. Include number, readiness,
negation and relationship distinctions that this sample cannot settle. Any
serving proposal still needs an adaptation-aware binding, compatible immutable
image-vector coverage, measured native serving limits and family/device review.
