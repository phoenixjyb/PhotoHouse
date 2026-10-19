# Offline semantic-scene translation fidelity

The translation helper has two separate identities. The frozen v1 recipe
(`legacy_translation_recipe_v1`) reconstructs the identity used by historical
R24 outputs. It does not change or regenerate those translations. New offline
translation work uses v2, whose prompt and source digest differ. R24 ranking
results remain evidence about their original, unchanged derived dataset; they
do not become evidence of reviewed translation fidelity.

`derive_dataset` still returns a fresh derived dataset and a private-safe
receipt. It preserves the original dataset for the caller, leaves English
queries, image records, labels and paths alone, and binds the source and derived
dataset fingerprints plus per-query source and output hashes. A derivation
without a review record remains unreviewed and cannot count as fidelity
qualified.

To mark a new derivation reviewed, the caller supplies an exact
`photohouse.semantic_scene_translation_fidelity_review.v1` object. It binds the
source dataset fingerprint and current v2 recipe fingerprint. Its
`reviewer_type` must truthfully identify `assistant` or `human`. Its
`reviewed_pairs` map must contain every translated case/language key, with the
SHA-256 of that exact source query, the SHA-256 of that exact English output,
and the decision `faithful`. Missing, extra, stale, malformed, or mismatched
records are rejected. The receipt stores the review digest and pair count, not
queries, translations or reviewer identity. Reviewer type is an explicit claim
in this offline artifact; the helper does not authenticate it.

Before accepting the review, the helper checks a small set of explicit
quantity, action/state, contrast relation, and negation cues. It rejects
detected disagreement or unsupported added specificity. These checks are
deliberately narrow: they cannot resolve arbitrary Chinese-English meaning,
implicit counts, dialect, vague intent, or all paraphrases. One narrow refusal
catches the known ambiguous snow-field compound. A passing check is not proof
of fidelity. The complete, hash-bound review is still required, and assistant
and human review records remain distinct.

The v2 prompt calls out explicit quantity, action/state distinctions,
negation scope, uncertainty, and contrastive relationships. It adds no example
scene facts. Prompt wording, lexical checks, or retrieval rank do not establish
universal translation fidelity. Semantic serving remains disabled; this
offline contract does not grant activation approval.
