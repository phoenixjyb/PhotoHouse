# Narrative quotation grounding v1

The local memory drafting adapter sends the same common safety prompt for both
`narrative` and `companion` tasks. That prompt now says:

- Do not invent dialogue or quotations.
- Include a direct quotation only when its wording matches verbatim text in a
  family-authored source and that source has an available author attribution.
- Treat speech transcripts as AI-produced renderings of audio, not as the
  speaker's authored wording. Do not present transcript text as an exact quote,
  even when the speaker is identified. Supported transcript content may still
  be paraphrased with attribution.
- Grounded paraphrase and sensory details supported by sources remain allowed.

This is a model instruction, not a validator guarantee. The existing response
validator continues to validate shape, chapter identity, source references,
size, and review status; it does not establish that prose is factually grounded
or that a model followed quotation rules. Generated drafts still require human
review.

The common prompt change affects both legacy narrative generation and editorial
generation, and both `narrative` and `companion` requests. The provider prompt
payload therefore changes; this is not byte-identical to the prior legacy
provider payload. The wire schema, bundle schema, default feature gates, and
provider configuration are unchanged.

The offline transport tests intercept the adapter request for both tasks and
assert that the quotation rules are present. They make no external provider
calls.
