# Selected-source story editor

This is a default-off Web source feature for one small family workflow:
choose photos/videos and their family memories, prepare chapter wording, inspect
sources, edit, review and explicitly save. It uses the existing story workspace
and [protected prepare/cancel API](SELECTED_SOURCE_STORY_DRAFT_CONTRACT.md#protected-http-v1).
Synthetic fixtures qualify the source flow; no native model or deployment is
included.

## Explicit configuration

`create_app(selected_story_ui_enabled=True, selected_story_drafts_enabled=True,
selected_story_provider=...)` also needs the existing protected access runtime
and collaboration opt-in. Both new flags default to false. Provider injection
alone enables neither the UI nor its HTTP preparation surface. There is no
URL, browser-storage, environment or client-side switch that grants authority.

`GET /story-workspace/drafts/capabilities?library=...` always requires current
`library.read`, even when disabled. Its exact response is
`{"version":1,"enabled":false,"can_prepare":false,"source_policy":"chapter_sources_v1"}`,
with boolean readiness values for the current configuration. `can_prepare` also
requires an approved owner/contributor role. A viewer can read capability
availability without receiving write authority. Prepare, cancellation and Save
independently reauthorize their own capabilities and current sources.

## Family workflow

1. Open the existing story editor, choose up to 24 photos/videos and arrange
   their chapters. The initial version prepares new, unsaved stories. When the
   editor opens from selected private-assistant results, the author may
   explicitly copy the latest user message as a starting point for writing
   direction. The assistant checks account, library, thread and revision at
   handoff. This carries one user-authored message only; it does not resume the
   conversation in the editor. The field is blank by default, never includes
   assistant wording or full history, and does not overwrite direction already
   typed.
2. Opt into chapter source review and check the family notes or captions to use
   for each chapter. An empty choice supplies no evidence; it never means all
   sources. Family wording, family-edited captions and AI observations remain
   distinct. Recorded/transcribed and accepted contribution sources retain their
   existing separate workflows and are not silently added to this profile.
3. Choose **Prepare story draft**. The request contains references and writing
   direction, not copied source text. Preparation uses the shared nonqueued
   inference gate. Existing manual wording is kept as a volatile restoration
   snapshot; nothing is saved automatically. AI wording fills chapter bodies;
   the family keeps its story and chapter titles. Questions are shown for review
   alongside the citations and are not silently added to the saved story.
4. Inspect citations and original family wording/bylines, then edit chapter
   narration in the existing editor. Generated words are labelled as AI wording
   pending review. **View original wording** expands the chapter's pre-generation
   text beside the editable proposal. It is collapsed by default, works with the
   keyboard, and makes no request or save. **Keep this chapter’s original
   wording** restores that chapter and removes its generated citations from
   review. Other proposed chapters stay editable and need a fresh review
   confirmation. Keeping the original in the last remaining chapter clears the
   proposal. Cancel, expiry, a replacement outline or changed source selection
   clears the comparison with the proposal. These actions use the existing
   temporary copy of the original wording.
   Any edit clears the review confirmation. Changes to selected
   sources, chapter/media layout or source revision invalidate the old proposal
   rather than rebinding its words to new evidence.
5. Check the review confirmation for the exact current proposal and explicitly
   choose **Save to library**. The existing `source_review=1` save path owns
   permissions, current source/selection revisions and mutation idempotency.
   No new publication or TV-sharing action is introduced.

## Retention and uncertain outcomes

Generated words and citation/review metadata are volatile. The fixed server
expiry is checked on delivery and before Save; the UI clears expired generated
wording, closes an open AI preview and restores the earlier draft. Scope changes, logout and explicit
cancellation fence late responses. Cancellation keeps native cleanup ownership
on the server; abandoned prepared results are also cancelled. The UI never
presents cancellation as native stop proof.

A failed or busy preparation offers an explicit retry of the frozen request ID
and body. Editing stays frozen for that retry; **Cancel** releases it. A pending
preparation blocks Save. Local draft saving and JSON export are unavailable
while preparation or its volatile proposal is present, so generated wording is
not serialized without its review context. It does not switch providers or
retry inference automatically. When
cancellation reaches the server before preparation registers, the client still
fences its own logical intent and repeats cancellation after a late outcome.

A Save response can be lost after the write commits. Preserve the existing
frozen save body and `mutation_id` and use **Retry same save**. Do not regenerate,
change the mutation, restore the previous draft over that pending request or
claim that an ambiguous response means nothing was saved. The existing Save
service rechecks authority and resolves the same mutation idempotently.

## Source checks and remaining gates

- [Capability tests](../server/tests/security/test_selected_story_ui_capabilities.py)
  cover default-off configuration, roles, fresh membership, credentials and query
  restrictions with generated SQLite data.
- [Browser fixture](../server/tests/security/story_draft_browser_bridge.py) uses
  generated images, an actual family-note API record, and the
  [async local adapter](SELECTED_SOURCE_STORY_LOCAL.md) with in-memory synthetic
  HTTP/native ownership through the real protected ASGI application. It opens no
  listening server and uses no model.
- [Browser journey](../server/tests/security/test_story_draft_preparation_browser.cjs)
  exercises selection, reference inspection, edits/review, explicit Save,
  ambiguous-save retry, foreign citation rejection, frozen preparation retries,
  changed source choices/revisions, cancellation/expiry, delayed capability
  negotiation, scoped assistant-direction opt-in and Chinese/English layout
  checks. The November 24 increment passed 18 generated checkpoints, including
  original/proposal comparison, keyboard
  disclosure, enlarged phone reflow and clearing without automatic generation or
  saving. This is local browser evidence, not a Windows/model qualification.

Native locality, quality/latency, ASR/TTS, cross-process GPU coordination,
physical family-device acceptance and deployment remain separate. The HTTP
capability response is readiness negotiation, not evidence for those gates.
