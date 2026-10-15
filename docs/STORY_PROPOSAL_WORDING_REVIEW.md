# Review wording changes in a story proposal

October 15 Web/phone source increment after v63. This extends the existing
chapter comparison. It does not enable a provider, generate a story or publish
a new release.

## Family experience

A story suggestion shows a short summary of chapters with different wording,
matching wording and wording that cannot currently be compared. The initial
view shows every chapter. **只看正文变化 / Focus on changed wording** collapses
only the suggested prose and current-text comparison for exact matches.
**显示全部正文 / Show all wording** reverses that local view choice.

Chapter headings, source references, title, follow-up questions and existing
review/adoption controls remain available. Different or unmatched chapters stay
visible. Even when every chapter matches, references and questions remain
reviewable. Matching prose does not establish matching citations or factual
accuracy; title, references and questions require their own review.

## Scope and invariants

- Comparison uses exact chapter narration and unambiguous chapter identity in
  the current reader, bound to the ready job's base story revision. Duplicate
  identities, missing current chapters or a revision mismatch are unavailable,
  never matching. Empty narration can match another empty narration.
- The summary counts chapter wording only, without semantic similarity, factual
  judgments or source validation. It does not compare the proposal title.
- Changing a reader, scope, revision, job or proposal resets the local filter.
  Retained/detached controls cannot change a replacement Web reader. Existing
  source, conversation and current-story access fences continue to apply.
- Filtering does not generate, fetch, adopt or save content. Web stops prior
  read-aloud before changing visibility and refuses the action during capture.
- Source wording and suggested wording remain separate. Existing Web adoption
  still rechecks the ready job and opens an unsaved editable draft; phone
  proposal review remains read-only. Ordinary story saving stays explicit.
- This applies to story proposals in chat and narrative review. It does not
  change memoir editions, whole-book drafting or manuscript publication.

## Checks and delivery

The focused Web component fixture covers mixed, all-matching, empty, unavailable
and duplicate-ID cases, retained sources/questions, exact wording, keyboard
activation, unchanged reader/job data, zero new requests, scope/revision fences
and Chinese/English narrow-screen large text. The existing actual-ASGI community
journey checks compatibility with chat, contributions, proposal adoption and
memoir flows. Focused Compose checks cover the equivalent source behavior and
private generated renders. All four focused QA-emulator cases passed after
correcting fixture assertions, using the actual PhotoHouse theme. Generated
Chinese/English 150% Web and emulator renders were inspected. The focused Web
fixture passed five groups; the full actual-ASGI community journey also passed.
QA APK and instrumentation builds passed; no physical phone was used.

These checks use synthetic data and no model. Hosted CI, Windows delivery,
signing/OTA, actual model quality and family acceptance remain separate gates.
No database schema, route, provider, permission or recording-retention change
is included.
