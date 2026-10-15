# Story companion answer grounding

**Source-only follow-up to frozen v64 source `5480a0c`. This change is not delivered.**

## Contract

The private story and memoir companion response has three kinds: `answer`,
`clarification`, and `proposal`.

- An `answer` must cite at least one unique source ID present in its validated
  input bundle. Unknown, duplicate, or absent IDs make the provider response
  invalid.
- A `clarification` may have no source IDs. Its existing reply and question
  validation is unchanged; the companion does not invent a fallback or retry.
- A `proposal` still requires a nested narrative proposal. Its chapter order,
  evidence references, nonblank narration citations, and review requirement keep
  the existing validation rules.

Citations identify the inputs used for review. They do not prove that a claim is
true, supported, or correctly interpreted.

An invalid provider response is reported as the sanitized `invalid_response`
category with the generic local-model error. The response text is not returned,
and the request is not retried.

This describes source validation and prompt guidance only. It does not qualify a
model, activate generation, or establish live, device, or family acceptance.
