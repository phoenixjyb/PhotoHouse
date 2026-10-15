# Phone guided first story

This source candidate adds **讲一个故事 / Tell a story** beside the existing full
story editor. The server's current `can_create` response still decides whether a
library editor opens; a local role label does not grant creation permission.
It reuses the existing protected outline, dictation and save contracts.

## Three steps

1. **Choose moments.** Explicitly select 1–24 photos or videos, including from
   albums or reviewed date suggestions. Next prepares an outline; it does not
   save a story. Guided chapter wording starts blank rather than retaining the
   outline's instructional scaffold.
2. **Tell your memory.** Type a remembered sentence, or explicitly record, stop,
   review/edit the transcript and add it to a chapter. One shared memory in the
   opening is enough; other chapter wording can wait. Original family notes and
   AI observations remain distinct source material. Title/source assistance is
   available as a collapsed optional section.
3. **Review and save.** Read a literal, non-editable draft preview with ordered
   frames and chapter text. Back returns to wording. The review checkbox and
   explicit Save story action use the existing immutable save/retry path.
   Reading the freshly saved story still fetches the protected saved version.

The read-only preview fetches thumbnails for the entire selected draft, rather
than relying on only the picker's currently cached page. It is bounded by the
existing image and total-cache limits, scoped to the current editor/account/
library, and clears or rejects late buffers after scope teardown. Missing
thumbnails use the existing visible fallback; originals are not downloaded.

## Keep the user's words

Back from wording preserves title, chapters and chosen moments. Continuing with
the same frames uses the retained draft without another outline request. The
picker remains read-only while that draft is retained. **Change moments and
rebuild** requires an explicit discard confirmation; cancel keeps the wording.
The full-editor action retains the same draft.

Navigation is blocked during composition, unfinished capture/transcription/
transcript review, an active operation or an uncertain save. Source refresh
preserves user wording and returns to the wording step for renewed review.
An uncertain save retries the exact frozen body/mutation ID, never a new create.

Unsaved editor state remains in process memory, but an explicit **Save draft on
this device** action now stores a bounded encrypted record for a new story.
Resume reopens only the matching account and family library after the normal
`can_create` check and a fresh preview of every selected asset. It reattaches
only still-valid source IDs, preserves authored words, and resets review when
the evidence changed. It never fetches or submits automatically. These records
are device-local, do not sync, and remain until explicit deletion or confirmed
publication; logout or scope teardown clears the editor from memory without
exposing another account or library's slot. The UI warns that anyone using the
unlocked device may see a saved draft.

If a saved draft is used for story creation, Android encrypts the exact frozen
request and mutation ID before making the network call. After process death,
Resume offers an explicit retry of that same request; it never creates a new
mutation ID or silently sends it. An unknown save stays as a recovery record
until publication is confirmed or the user deletes it. The encrypted record
contains authored title/chapter words, grouping, selected IDs, scope and
selection revision only. It excludes credentials, audio, thumbnails, cached
evidence and generated preview wording.

## Try after a release containing this source

1. Sign in and choose a library where the server permits story creation.
2. Tap **讲一个故事**, pick a photo and a video, then continue.
3. Add one typed or reviewed dictated sentence. Confirm no Save button is offered
   before the review step.
4. Go back to moments. Open the rebuild confirmation and cancel it. Continue:
   title and wording should be unchanged.
5. Open review. Check literal wording and frame order, return to edit if needed,
   then check the review box and explicitly save.
6. Open the saved story and verify the wording remains. On a failed/uncertain
   save use **再次确认这次保存** rather than starting another story.

Test dictation separately with the live service and microphone. Synthetic test
transcripts do not qualify recognition quality or physical phone behavior.

## Source and release boundary

The implementation is in `StoryWorkspaceStore.kt`, `ConnectedStore.kt`,
`GroupedStoryCreationDialog.kt`, `GroupedStoryReview.kt` and `StoryFirstGuide.kt`.
`StoryFirstGuideStoreTest`, `GroupedStoryCreationStoreTest` and the two bilingual
guide journeys in `GroupedStoryCreationUiTest` cover its source/fixture behavior.
The existing full-editor and dictation journeys remain separate regressions.

No new API route, schema migration, provider activation, release version change,
signing, OTA publication or Windows service operation is included. Integrate
alongside the separate search branch before allocating the next release version.
See the [Web guide contract](../../../docs/STORY_FIRST_GUIDE.md).

## Local verification, 2026-10-15

- 51 focused JVM tests passed: 7 guide, 26 existing story-workspace and 18
  connected grouped-story cases. These include server capability denial,
  multi-page review thumbnails, late-buffer cleanup and exact save retry.
- Seven API 36 emulator journeys passed on the final debug source: Chinese and
  English guided flows, both full-editor journeys, two chapter dictation flows,
  and bilingual uncertain-save recovery. The UI uses 150% text with synthetic
  APIs/media. Captured Chinese/English guide renders were inspected.
- Unconfigured debug app/test assembly and debug lint passed. Lint reports zero
  errors, five existing warnings and one informational issue.
- A fixture-only failure initially rejected the new two-frame cohort; the fixture
  now declares the expected cohort per journey. An existing large-text lazy-list
  test now scrolls the parent list to compose the target item before clicking.
  No acceptance assertion was removed. The guide picker uses compact rows so
  visible selection remains usable alongside the step header at large text.

This verifies local source and a synthetic emulator installation. It does not
qualify a live ASR/TTS model, physical phone, signed release or OTA feed.
