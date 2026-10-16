# Untouched-photo scene intent diagnostic — October 16, 2026

The unchanged local translation recipe improved Chinese and mixed retrieval on
32 additional public photos. Vague requests remained weaker than literal ones,
and four translated outputs raised meaning-preservation concerns. This extends
the [first translation experiment](SEMANTIC_SCENE_TRANSLATION_2026-10-16.md);
it leaves automatic translation quality and live scene activation unqualified.

## Frozen sample and comparison

Selection was the lexicographically next 32 photos (positions 33–64) in the
same [Ultralytics COCO128 distribution](https://docs.ultralytics.com/datasets/detect/coco128/).
Member IDs and image bytes do not overlap the earlier 32-photo diagnostic.
This is an untouched evaluation set for our development work, **not** evidence
that model training excluded these public COCO training images.

Before any model call, assistant visual curation and independent assistant
review established 32 cases, each with English, Chinese and mixed wording and
one or more relevant images. The frozen categories were 12 literal descriptions,
12 vague impressions and eight contrasts. Review added missing kitchen and
transit positives, removed an ambiguous activity label and aligned language
wording before freezing. Some impressions, including calm, relaxed, holiday-like
and appetizing, retain subjective labels. There was no human/family review.

The translator received only each Chinese or mixed query, with no image,
relevance label or parallel English wording. Its prompt, options, model and
recipe were unchanged from the previous experiment. The 64 translations were
saved once; neither queries, labels nor outputs changed after scoring. Direct
and adapted measurements used the same 32 candidate images and encoder.

| Original input cohort | Direct top-one | Adapted top-one | Direct top-five | Adapted top-five | Adapted MRR | Adapted relevant-image recall at five |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| English, unchanged | 30/32 | 30/32 | 32/32 | 32/32 | 0.9688 | 0.9563 |
| Chinese | 2/32 | 28/32 | 12/32 | 32/32 | 0.9323 | 0.9302 |
| Chinese-English mixed | 14/32 | 29/32 | 28/32 | 32/32 | 0.9479 | 0.9458 |

Adapted Chinese/mixed inputs were English text; the cohort names identify the
original input language. A top-five hit requires one relevant image, while
recall considers every labeled relevant image. The evaluator retains its
pessimistic treatment of nonrelevant near-ties.

| Frozen category | Cases | English top-one, direct → adapted | Chinese top-one, direct → adapted | Mixed top-one, direct → adapted |
| --- | ---: | ---: | ---: | ---: |
| Literal | 12 | 12 → 12 | 0 → 12 | 6 → 12 |
| Vague | 12 | 11 → 11 | 1 → 9 | 5 → 10 |
| Contrast | 8 | 7 → 7 | 1 → 7 | 3 → 7 |

Overall top-one increased from 46/96 to 87/96; top-five from 72/96 to 96/96.
All three languages retrieved a relevant image first in 27/32 cases, versus
2/32 directly. Across 96 matched query rows, 47 ranks improved, one regressed
and 48 stayed equal. Forty-two rows gained a top-one result, while one lost it:
the mixed travel/vehicle request moved from rank one to rank two. These gains
do not establish open-ended vague-intent understanding or hard exclusion rules.

## Meaning review is separate from ranking

An independent assistant reviewed all 64 translated outputs and eight extra
ambiguity checks before seeing retrieval scores. Four outputs were flagged:

- A Chinese travel request lost the waiting state when the vehicle became parked.
- A Chinese snowboard phrase acquired an explicit single-object quantity.
- A mixed wine-gathering contrast changed being alone into being placed separately.
- A mixed snow-free-field phrase left the scope of the negation ambiguous.

These include state/relation changes, unsupported specificity and ambiguity;
they are not a calibrated translation error rate. Several other Chinese generic
nouns became singular in English, but number-neutral Chinese did not establish
a definite count error. The remaining outputs were broadly faithful in this
small assistant text review.

The unsupported snowboard quantity and the changed wine contrast both improved
their labeled retrieval rank to one. A good retrieval score can therefore hide
a translation problem. The travel request's mixed translation retained waiting
but still lost top-one retrieval. Neither a text review nor a rank score can
substitute for the other.

The eight extra checks preserved their core readiness, uncertainty, alternatives,
negation and condition boundaries; an embedded instruction remained sign text.
Those checks had no image-retrieval labels and do not qualify encoder negation,
arbitrary instruction resistance, dialect comprehension or ASR.

## Reusable comparison helper

The [cohort comparison helper](SEMANTIC_SCENE_QUALIFICATION.md#compare-frozen-intent-cohorts)
validates evaluator reports, recomputes rank aggregates and compares each frozen
category and language separately. Its membership fingerprint prevents silent
reassignment of cases under unchanged category names. It reports losses as well
as gains and emits no reconstructed subset recall. It performs no file/model
work and grants neither translation faithfulness nor activation approval.

The native controller separately verified unchanged image records/vector
checksums, relevance labels, original English queries, text probe, CPU encoder
configuration and preprocessing recipe apart from the dataset fingerprint.
The source and derived datasets reproduce the saved adaptation receipt exactly.

## Native evidence and limits

The experiment used source `b6c9525165b2519baac19f5f684ba2dfdd3da0a4` for
comparison preparation and the unchanged translation helper. Encoder/evaluator
source remained `878ab0562981f6175dcc5f2bea588947ab175de4`, reusing its verified
233-file source package. Existing model weights and installed dependencies were
reused, with no model download or new source-package copy.

The same local Qwen/Ollama identity and every model blob were checked before
and after generation. Preflight found sufficient free RAM and GPU memory; the
temporary provider confirmed full residency on the selected RTX 3090 with a
2048-token context. The outer Windows Job enforced 16 GiB RAM, 12 processes,
900 seconds and a 16 GiB free-RAM floor. It exited zero after owned-descendant
cleanup in 87.203 seconds. One fixed warmup took 6.141 seconds and the maximum
of 64 measured query intervals was 0.750 seconds, with zero inference retries.
Cache state differs from the previous run; these are not serving latency,
concurrency or observed peak-memory qualifications.

The wrapper now persists the numeric exit before testing listener absence, so
the earlier post-cleanup port-probe failure cannot erase that exit evidence.
An initial readback hit Windows stdout encoding; a read-only UTF-8 readback
verified the saved outputs without rerunning inference.

Direct and adapted CPU scoring ran sequentially in a separate outer Windows
Job with 4 GiB RAM, four processes, 300 seconds and an 8 GiB free-RAM floor.
It exited zero in 45.078 seconds. Model loading took 12.671 and 3.125 seconds
respectively; cache and process state make these unsuitable for a startup-speed
claim. The evaluator CLI itself does not enforce these Job limits. Independent
readback verified both measurement digests, unchanged encoder configuration
and release of the temporary translation port.

| Evidence | SHA-256 |
| --- | --- |
| Original dataset | `603706a383a1cb6937eb30eb340189995ab9075ad8e54609c6521602ad6886ad` |
| Derived dataset | `90ba871f30d9fa7c36d005284aee320de9f7f21dc53c744d0c9c664adf2cb4fb` |
| Frozen cohort membership | `49cb0d4ff3733202b1d42cc0cd773b69fdd8fcde70b0b0943bf8648f901ab878` |
| Adaptation recipe | `d89fe71971c8ca0e64601320403be0707a2b8f0f9ea17e6a45cbb9e81bea6f01` |
| Translation receipt file | `83a420de087ff19ff71f92f12e781c7179dcee20b5bd03373a45d09f4357f440` |
| Direct measurement file | `f4b7f0c067c266da4404bfd8b86fc82eadc80f6fa2098cd1a7b9161f77d4d596` |
| Adapted measurement file | `ba6ab6acf7efa8f7090c47b0abcd8ab19d3e072e4e6fcb8ec746890750c53494` |

Raw photos, queries, translations, input paths and reports remain private.
No family media, library database, kinship mapping, memberships, live service,
published vectors or signed package changed. No serving binding was created;
the runtime scene gate remains off. Faithfulness safeguards, an adaptation-aware
binding, native serving limits, compatible immutable vector coverage and
family/device acceptance remain work before activation.
