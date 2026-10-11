# Speak a story chapter

Status: the phone writing controls are implemented and locally checked at
`5873b44`. Web integration and saved-story phone editing are in progress; live
delivery is pending.

## Writing experience

An author opens an editable story chapter and explicitly chooses to dictate.
Recording begins only after the record action and microphone permission. Stop
sends the bounded recording to the protected ASR service. The recognized words
remain in a separate, editable review field until the author chooses **Add to
chapter** or **Discard**. Adding appends to the chapter's current wording with a
paragraph break, preserving words typed before or during transcript review.

Adding does not save a story or send a chat command. The author still reviews
the chapter and explicitly saves. A combined chapter may contain at most 6,000
UTF-8 bytes; an over-limit insertion keeps both the typed chapter and the full
transcript available. Chinese and English labels explain the pending review and
provide an explicit way to discard it.

This is a writing shortcut. Its ASR recording is transient and is not an
original family-memory audio contribution. To preserve an original voice for
later playback, use the separate family-memory recording flow. Assistant input
receipts retain recognized text and processing status under the existing
30-day troubleshooting policy; they do not turn the audio into a permanent
chapter source. Edited and accepted words become the author's chapter wording.

## Scope and lifecycle

The volatile session belongs to the current account, credential, library,
editor generation, selection revision, chapter ID and ordered chapter media.
A saved story also binds its ID and revision. Ordinary narration edits do not
invalidate that binding, so insertion can preserve the latest typed text.
Read-only chapters and a pending or uncertain save cannot open a dictation
session. Recording, transcription and unconsumed words must be resolved before
saving or replacing the draft.

Closing the editor, backgrounding the app, changing account/library, or changing
the bound revision cancels capture and clears the transient transcript. Late
capability and transcription responses cannot repopulate a different chapter or
clear a newer account's session. Current authentication denial clears the
protected session. Capture teardown releases microphone resources and clears
temporary audio buffers.

## Reused services

The clients reuse protected assistant capabilities and transcription, including
the existing request receipt and recording limits. This feature introduces no
database migration, model download, background inference worker or public
upload route. The maximum recording duration is the smaller of the admitted
assistant capability and the existing 30-second client capture bound.

The phone core helper is independently tested with generated audio and fake
responses. The integrated phone run passed 34 focused JVM tests, three generated
story-review UI journeys and all six shared dictation UI tests on the reused API
36 emulator. Chinese and English 150% renders were inspected. The shared tests
include a rejected oversized edit that remains visible and cannot insert older
recognized words. These overlapping checks are not summed into a full suite.

Final source qualification, serving Web files, signing/publishing the phone APK and a real family
voice turn remain separate delivery gates. See [source choices](CHAPTER_SOURCE_CHOICES.md),
[transcript review](ASSISTANT_TRANSCRIPT_REVIEW.md) and [the roadmap](ROADMAP.md).
