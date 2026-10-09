# Android memoir instruction dictation UI

The whole memoir panel now opens its own `MemoryDictationStore` only after the user taps **口述整理要求**. Opening checks assistant availability and loads capabilities; it does not request microphone permission or start recording. The existing recorder, permission prompt, audio lease, lifecycle cancellation, transcript review, and transient WAV handling remain in `MemoryDictationInput`.

The memoir-specific instructions explain the sequence: record, review and edit the transcript, insert it into the arrangement instructions, then explicitly check chapters and request a reviewable draft. Nothing is sent automatically. The UI says recordings are temporary and transcription records are kept for 30 days. The voice panel uses its own `MEMOIR_INSTRUCTIONS` purpose, separate from the memoir conversation's dictation state.

An unconsumed memoir transcript blocks instruction/context edits, plan checks, draft requests, and manual editorial changes. Insertion remains available while the transcript is unfinished. If the instruction editor currently has rejected or unsaved local wording, the voice open and insertion actions stay disabled so insertion cannot replace that wording. If the accepted transcript exceeds the instruction limit, it remains in the transcript editor and the UI explains that it must be shortened.

Leaving the book prompts while memoir dictation is loading, recording, transcribing, or holding any unconsumed transcript. The same unfinished state disables manual editorial save and refresh controls. These are source/UI changes only; emulator, installed app, live service, and family acceptance remain separate gates.

The final panel keeps the transcription review compact, supports the keyboard's
Done action, and closes the dedicated voice panel after a successful explicit
insertion. An unsuccessful insertion keeps the complete transcript. The memoir
suggestions disclosure cannot collapse while voice input is unfinished, and the
separate memoir-chat recording state still blocks arrangement actions.

## Verification

Seven helper tests, 53 community integration tests and six editorial integration
tests passed. Two synthetic Chinese/English emulator journeys at 150% text passed,
then passed again after the keyboard/compact-panel correction; debug lint passed.
The final full-screen transcript and inserted-instruction renders were inspected.
These journeys injected a generated WAV through the store and a synthetic ASR
response; they do not prove physical microphone, real Whisper quality, live
generation, signed artifact or family acceptance. No generation or original-memory
write occurred before explicit insertion and request in the fixtures.
