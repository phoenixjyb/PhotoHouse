# Web assistant transcript review

The Web search assistant keeps recording, recognition, transcript insertion and
submission as distinct user actions. It uses the existing transient-audio ASR
endpoint and current authenticated library; it adds no backend or schema change.

## User flow

1. Start recording explicitly, then stop and transcribe.
2. Review the recognized text in its editable field. Text typed into the command
   composer before or during recognition stays intact.
3. Choose **放入搜索框 / Use transcript** to append the reviewed text after a
   newline. A successful, tracked ASR receipt becomes the command's parent only
   at this step. Insertion does not submit the command.
4. Edit the combined command if needed, then choose **查找 / Find** explicitly.
   Alternatively, discard the transcript; this leaves typed words intact and
   clears its parent receipt link.

Recording, transcription and unused review block both the visible Send button
and direct form submission. A new recording cannot replace an unresolved review.
If the combined submitted text exceeds 1,024 UTF-8 bytes, both fields stay
available for editing and the UI explains the limit. It does not truncate text.
The composer allows up to 1,024 UTF-16 code units; the wire byte limit is checked
independently before insertion and submission.

## Scope and lifecycle

Account or library reset clears transcript review and receipt links. Recognition
attempts own their cancellation controller and cleanup: completion from an old
account cannot hide a new account's review or enable its Send button while a new
transcription is pending. Failed, malformed or tracking-disabled responses
cannot provide a tracked command parent. Changing UI language during active work
relabels the temporary conversation trail without moving focus or its scroll.

Recording startup also has its own current-attempt token. Permission wait is
labelled as opening the microphone; the recording label appears only after
setup. A stale permission result stops its tracks before creating an audio
context. Cancellation releases the current resources while context startup is
still unresolved. Stale completion cannot alter a newer attempt or submit audio.
Releasing a hold before recording starts discards the attempt and asks the user
to hold again. The generated capture fixture exercises an actual browser mouse
hold and release as well as explicit cancellation; see the
[recording lifecycle](WEB_RECORDING_LIFECYCLE.md).

The client validates the generated mono 16 kHz PCM WAV header before sending.
The header label check uses numeric byte offsets; a previous indexing error
rejected valid generated recordings. Browser fixtures use generated silence and
synthetic recognition responses to exercise this path. Audio stays transient;
the existing 30-day server troubleshooting records are a separate lifecycle.

## Verification and delivery

The generated browser journey is
[`test_assistant_transcript_browser.cjs`](../server/tests/security/test_assistant_transcript_browser.cjs),
registered in [`tools/check.py web`](../tools/check.py). It covers typed-text
preservation, explicit insertion and linked receipts, byte boundaries, discard,
malformed responses, disabled tracking and overlapping old/current account
requests. It checks English and Chinese 390 px displays at 150% text.

Synthetic browser evidence does not establish served Web bytes, microphone
permission behavior, real recognition quality or family acceptance. Deliver the
reviewed static files through the separately authorized Windows release path,
then test one signed-in voice turn. The phone has its own
[emulator and source evidence](../clients/android/docs/ANDROID_ASSISTANT_TRANSCRIPT_REVIEW_2026-10-10.md).
