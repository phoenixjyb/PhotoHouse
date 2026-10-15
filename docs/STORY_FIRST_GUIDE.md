# Guided first-story creation

This source change adds an optional Web flow in the existing story workspace:
**Choose moments → Tell your memory → Review and save**. It does not add an
Android screen, API route, schema migration or model invocation. This document
records source behavior; deployment and family/device acceptance are separate.

## Entry and permissions

“讲一个故事” / “Tell a story” appears only after a successful saved-story shelf
response confirms `can_create` for the current account and library. An empty,
unfiltered shelf offers the same entry. Loading, failed or denied shelf responses
do not advertise it. The ordinary full editor remains available.

The guide starts with no frames selected. Use the existing picker to choose up
to 24 moments and arrange them. The next step requests the existing evidence
outline; it does not save anything. Instructional outline wording is cleared in
this guided path so it cannot be mistaken for the narrator's own memory.

## Wording and review

Write at least one remembered sentence, or use the existing chapter dictation:
record → stop and transcribe → review/edit → explicitly add the transcript.
Capture and pending transcript review must finish before moving between steps.
Transcription is an input method; this flow does not attach the original audio.

Back preserves title, frame selection and chapter wording. Returning forward
without changing the frames reuses the draft. Deliberately changing the selected
frames uses the existing draft-replacement confirmation. The full-editor action
keeps the current selection and draft.

The review step renders literal user text, ordered frames and chapter wording.
Reader preview opens the existing reader without saving. Only the existing
“保存到相册库” / “Save to library” action writes the story. A shared memory can
live in the opening; every chapter need not repeat it. Photo notes, source quotes
and AI observations remain separate; the guide does not propagate story text
into individual photos.

## Recovery and scope

The existing save protocol retains the exact pending payload and mutation ID
when the outcome is uncertain. Retry that same save; starting another story
cannot replace it. Success returns to the full editor for the saved story.
Account/library teardown invalidates pending outline responses and closes the
guide. Drafts are session-only; this change adds no browser persistence.

## Source and verification

- `server/backend/app/ui/access/story-workspace.js`: guide state, existing
  picker/editor/reader/save integration and current-scope guards.
- `server/backend/app/ui/access/index.html` and `styles.css`: accessible progress,
  step headings, responsive navigation and review presentation.
- `server/tests/security/test_story_first_guide_browser.cjs`: real UI against a
  closed ASGI bridge and synthetic SQLite, including a committed save whose
  response is lost, byte-identical retry and reopening the saved text.
- `tools/check.py web`: includes the focused browser suite. See
  [development setup](DEVELOPMENT.md) for the shared browser prerequisites.

The browser suite uses generated media only. Desktop, 390 px and 320 px layouts
and enlarged text are separate fixture checks, not physical-device acceptance.
See the [Chinese first-story guide](FIRST_STORY_GUIDE_ZH.md) for the user flow.

### Local checkpoint, 2026-10-15

The focused guide suite passed six reported checkpoints: eligible empty shelf,
stale outline isolation, draft/back/review/reader behavior, lost-response save
retry, actual viewer permissions, and reopening the saved story. It also checked
IME navigation fencing, a theme change returning to frame selection, and literal
markup rendering. Responsive assertions covered 1200 px, 390 px and 320 px,
including 150% text; screenshots were inspected separately.

The existing editor browser suite passed 30 reported checkpoints, including
chapter dictation and source-refresh/save recovery. All 13 tool-command tests
also passed. The source verifier accepted 1,295 files, and the local Markdown
link check found no errors (882 links, including 34 fragments).
No microphone, transcription provider, Windows service, Android build or physical
family/device test is implied by this synthetic Web checkpoint.

## Integrating alongside search work

This increment is based on `c4cac82` and lives on
`codex/story-first-guide-20261015`. Integrate it after reviewing the other active
session's changes. Shared files include `tools/check.py`, `docs/README.md` and
`docs/feature-source-changes.json`: retain both feature registrations and reconcile
source-ledger before/after hashes against the final combined source. Re-run the
focused guide suite and source verifier after resolving a shared-file conflict.
Do not replace the active checkout or treat this source commit as a live release.
