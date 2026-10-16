# Phone: review a proposal in an unsaved story edit

Implemented 2026-10-16. This is following source work, outside the published
phone v65 release. Story-generation activation and human model-quality review
remain separate gates.

## User flow

1. Open an editable saved story and a ready narrative or conversation proposal.
2. Compare suggested wording with the existing chapters and inspect references.
3. Select the chapters to use. Adopting the suggested title is optional and off
   by default. Confirm that the selected wording, sources and questions were reviewed.
4. Choose **将所选建议导入未保存的编辑稿**. The phone freshly reads the story,
   complete chapter contribution links and proposal before opening the editor.
5. Edit and review the draft, then explicitly confirm and save. Import alone does
   not write a story or submit a background task.

This preserves chapter titles, media order, grouping, evidence, family-memory
links and attribution. Only selected chapter narration and an explicitly chosen
title change. Questions stay visible as questions; they are not inserted as facts.
Original family text/audio remain separate from AI wording.

## Scope and refusal rules

The entry point belongs to the current account, library, story reader and ready
job. It requires an editable story, complete revision-bound contribution links,
no unsent family input and no editor already open. Closing, switching accounts
or libraries, or changing the reader invalidates late results.

The fresh story revision and selection fingerprint must match the reviewed
proposal. The fresh job must match its ID, kind, base revision and result. A retry
keeps the same chapter/title selection; it cannot silently fall back to an
ordinary story edit.

For each chosen chapter, citations must already be linked to that chapter:
frame evidence IDs, `contribution-<UUID>` references, or the chapter's current
editorial reference. Unknown, unlinked or cross-chapter citations refuse import.
The user can explicitly link the appropriate accepted family memories using the
[chapter chooser](CHAPTER_FAMILY_MEMORY_CHOOSER.md), then request and review a
fresh proposal. This flow never fetches or plays original recordings automatically.

The import and provenance notice are process-memory-only. Existing uncertain-save
recovery and revision-conflict checks govern the later explicit save. If the app
closes before save, this unsaved imported edit is not a durable saved story.

## Verification

Local validation passed **74 focused JVM tests**, phone compilation, lint and
QA app/instrumentation assembly. Pure validation, store and reader-integration
tests cover
selected wording, title choice, link preservation, stale proposals/revisions,
retry, late completion and unsent input. **Eight explicit emulator journeys passed**, covering adoption choices,
reader-scope reset, read-only mode, existing wording review and uncertain-save
recovery. Six Chinese/English 150% renders of the selection, compact provenance
card and reachable editor/save controls were inspected. The QA runner addressed
only `emulator-5554` and the separate `dev.photohouse.connected.qa` packages.

These generated checks do not establish live model or family acceptance. No
Windows write, model request, service change, signing, OTA publication or
physical-device write was performed in this source round.
