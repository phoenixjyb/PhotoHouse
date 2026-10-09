# Continuing when the assistant needs more detail

A ready story or memoir reply with kind `clarification` shows a localized
“AI would like to know more” cue and explains how to continue. It invites the
reader to add detail in their own words. Suggested questions remain editable
drafts; choosing one never sends it or starts recording.

The cue is passive. It does not replace a draft, move focus, create a thread,
call a provider, insert a transcript or apply a story proposal. Existing explicit
record, review, insert and Send controls remain in charge of those actions.
A normal answer keeps its existing presentation.

## Current reply and scope

The cue requires a nonblank, bounded ready reply and valid current reply metadata.
Failed, queued, running, stale or incomplete replies do not show it. Questions
and source references use the existing bounded metadata contract; they do not
establish that a cited statement is true.

Web history metadata must contain valid question and source-reference fields.
If both fields are absent, only the exact current matching ready job can supply
them. Partial or malformed history cannot be repaired silently by job fallback.
Account, library, target, conversation and render scope must still match.
Phone uses its existing revision-bound `memoryReplyContext` guard.

An empty composer may accept a suggested question. Existing text, unfinished
recording/transcription, an uncertain send, or an active reply task keeps that
selection blocked. The user may instead write their own response, review it,
and explicitly send it. No context or retention boundary changes.

## Delivery

This is a client presentation change. It adds no route, database migration,
provider setting or service activation. Generated Web/browser and phone
emulator evidence is recorded separately in [development](DEVELOPMENT.md).
Served files, a signed phone update and family/device review remain their own
acceptance gates.
