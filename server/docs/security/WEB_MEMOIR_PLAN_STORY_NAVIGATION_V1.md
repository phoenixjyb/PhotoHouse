# Web memoir plan story navigation V1

## Purpose

When a whole memoir exceeds one drafting pass, the saved plan can guide a reader
to an existing story. Opening a plan row is reading navigation only. It does not
create a job, generate text, or change saved story prose.

The per-story `can_draft` value describes whether that story is currently within
the drafting scope and the current member has editing rights. It is not a
read-access flag. Every authorized story may still be opened for reading, while
the separate status explains whether drafting is available. Opening a story
does not promise that a later draft request will succeed; the generation path
continues to apply its own current authorization and context checks.

## Bound navigation

The plan action passes one exact context object to the dedicated reader hook:

```json
{
  "book_id": "<current memoir id>",
  "book_revision": "<current memoir revision>",
  "story_id": "<selected saved story id>",
  "story_revision": "<selected saved story revision>"
}
```

The hook is available only from the active memoir reader. It checks that the
reader remains open, the same reader and memoir are active, the account and
library still match, and the selected child and revisions exactly match the
reader's saved structure. A missing or stale reader produces a localized
unavailable status. It never falls back to reopening a story by ID alone.

The reader then uses its existing in-book story path. That path reauthorizes the
parent memoir and ordered child revisions, attempts the existing read-only
editorial-context refresh, reauthorizes the parent again immediately before
the child read, and verifies
the child response revision before rendering prose. Stale parent or child data
is discarded and shown as unavailable; cached prose is not used as a fallback.
The active handler is cleared when the reader closes or the workspace clears.

## Draft preservation and explicit actions

Opening a chapter inside the current memoir leaves its companion mounted at the
same memoir target. Unsent instructions, the selected memoir form, voice capture
or transcript review, and pending assistant state stay with that companion.
Moving within the book does not prompt to discard those drafts.

The existing **Open this story and family memories** action remains a separate
transition into the story-scoped workspace. Before leaving the memoir it
reauthorizes the parent and invokes the community's existing leave guard. If a
reader cancels that confirmation, the current memoir reader and its companion
drafts remain in place. If the reader confirms, the ordinary protected story
read path loads the story; generation remains a separate user action.

## Verification boundary

The synthetic UI/browser checks cover exact plan context, current-reader
navigation, parent-before-child authorization, stale revision rejection,
preserved companion drafts and forms, cancellation of the explicit exit guard,
and no job or saved-prose mutation. These checks qualify the local source path;
they do not establish Windows runtime, provider, model-quality, or family-device
acceptance.

The October 6 final run passed the JavaScript UI contract harness and 19
synthetic browser checkpoints with zero failures, page errors or external
requests. The integration owner reviewed the opened original story and retained
companion instructions at 390 pixels and 150% text. Reading remains inside the
memoir; the separate story-workspace action still requires the leave decision.
