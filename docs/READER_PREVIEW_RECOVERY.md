# Story and memoir preview recovery

This is the next v60 source slice. It improves recovery inside the reader;
package, native deployment and physical-device acceptance remain separate.

## User interaction

A failed selected story image or memoir image offers an explicit **Retry
preview / 重试预览** action with a 48 dp phone / 48 px Web target. Retrying
stays on that image. It does not reopen the story/book, switch chapters, save a
reading position, submit contribution text, start narration or open a microphone.
Text, source disclosures, dates and explicit photo/video opening remain readable.

Loading is visible and repeated taps during an active attempt do not start
duplicate reads. Failure remains retryable; success restores the preview. There
is no timer or automatic retry loop. A healthy image does not acquire a retry
action or perform extra reads merely because controls were rendered.

## Scope and lifecycle

Each action belongs to the rendered account, session generation, library,
reader/source revision, chapter and selected image. Memoir actions also retain
their parent book and ordered child-story binding. Detached or superseded
actions cannot change the replacement reader. Late image events are ignored
after their attempt or reader is replaced.

The phone uses the existing protected detail-preview transport. A malformed,
nonnull cached image must be replaceable after explicit retry, even though it
was initially accepted as bytes. The memoir path preserves its resume offer and
bookmark; image recovery is separate from frame selection.

Web repeats its existing preview-then-thumbnail fallback only after an explicit
retry. It replaces the image area without remounting the reader or community
editor. The memoir retry is outside its media-opening button. Keyboard focus
recovery may follow only the exact still-focused current retry action, without
scrolling or taking focus from a user who moved elsewhere.

## Boundaries

This action does not fetch original photos or video playback and does not create
server processing tasks. It can recover a transient failure or reread a repaired
derived file; it cannot regenerate a missing or damaged preview on the server.
Use the separately scoped media-preparation workflow for that repair.

## Qualification

Focused checks passed: 24 phone store cases, debug lint, four bilingual API 36
emulator retry cases, six Edge story checks and eight Edge memoir checks. They
cover corrupt image bytes, held attempts, explicit recovery, unchanged reader
state, bookmark neutrality and stale callbacks. Chinese/English enlarged renders
were inspected. Complete integrated profiles are recorded separately in
[Development](DEVELOPMENT.md).
The [v60 reading trial](../clients/android/docs/PHONE_V60_TEST_GUIDE_ZH.md) provides
the physical phone/Web follow-up after delivery.
