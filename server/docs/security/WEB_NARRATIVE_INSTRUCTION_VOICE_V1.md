# Web narrative instruction dictation v1

## Scope

The story and memoir **Draft suggestions** panel may accept an explicitly requested voice recording as a temporary source for its instruction field. This adds no API route or saved audio record. The existing authenticated memory voice capability, browser capture, and transcription adapter are reused.

## User flow

1. The user clicks **Record instructions**. Only this click can begin microphone capture. Starting it stops family playback and story narration through the existing audio coordination event.
2. The user clicks **Stop and transcribe**. Stopping remains busy until capture settles, then the recording is passed to the existing transcription adapter and discarded by this feature. The transcript record follows the existing 30-day assistant retention policy; the UI discloses this separately from transient audio.
3. The complete transcript appears in a separate editable review field. It remains isolated from chat messages and original family contributions.
4. The user explicitly clicks **Add to instructions**. The current instruction text and the full transcript are joined with one newline and placed in the instructions field. This action does not submit a job.
5. The user reviews the combined instructions and explicitly submits **Generate draft suggestions**.

## Limits and state

- Instructions are validated as well-formed UTF-8 at 4096 bytes when inserted and again before a new narrative job is frozen. If the combined text exceeds the limit, the existing instruction and full transcript remain separately editable; neither is truncated, and no request is sent.
- Capture, transcription, and an unconsumed transcript block both editorial context changes and job submission. A transcript can only be inserted or discarded explicitly.
- Dictation cannot overlap family contribution capture, chat dictation, family playback, or reader narration. Page hiding, reader close, tab changes, logout, target changes, account/library changes, and revision changes stop capture and invalidate late capture or ASR results.
- The client fences asynchronous results by capture generation, reader epoch, account/library owner, target identity/revision, active ideas tab, and visibility. A stale result cannot appear in a newer reader or target.
- Reader navigation prompts before discarding unsent instructions or pending voice work. Changing away from the ideas tab also asks before stopping and clearing pending voice work.
- Rendering during composition is deferred. Focus and caret are restored when the active instructions or transcript field is rebuilt.
- Failed narrative submission continues to use the existing immutable pending-job body and mutation ID on retry. Dictated text is never appended to a retry body.

## Evidence boundary

The focused harness covers delayed stop, no second capture or job during stop, malformed and oversized text retention, explicit insertion, target fencing and the final input event after Chinese IME composition. The synthetic ASGI/browser suite passed 17 checks; the owner reviewed the simplified 390px/150% dictation layout. These are source and generated-fixture evidence. They do not establish microphone behavior on a family device, ASR quality, Windows service health, or deployment acceptance.
