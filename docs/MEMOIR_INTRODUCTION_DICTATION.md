# Reviewed memoir introduction dictation

Memoir introductions can be written directly or built from reviewed dictation.
The phone [new memoir composer](PHONE_MEMOIR_COMPOSITION.md) and Web memoir
editor use the existing protected assistant transcription adapter. This shortcut
saves introduction text only; it does not attach or retain an original family
recording. Original family audio has its own contribution and retention flow.

## Web actions

Opening or expanding the memoir editor does not request voice capabilities,
record audio or invoke transcription. **Dictate introduction / 口述开篇**
explicitly checks availability. **Record introduction**, **Stop and transcribe**,
editable transcript review, **Add to introduction** and **Discard dictation** are
separate actions. No introduction is added or saved automatically.

The introduction textarea stays mounted and editable while ASR is pending.
Add reads the latest typed introduction and the currently reviewed transcript,
joining nonempty texts with one newline. A combined introduction must be valid
text within 6,000 UTF-8 bytes. Overflow or unsupported characters leave both
complete texts available for correction; they are never truncated. ASR output
must be nonblank, well formed and bounded before it enters review.

Save is blocked during availability checks, capture startup, recording,
transcription and unresolved transcript review. Explicit discard resolves that
pending input without clearing the typed introduction. An uncertain memoir save
freezes its existing mutation and blocks a new dictation; retry still sends the
same title, language, introduction, story order, revision and mutation ID.
Existing memoir language is preserved independently of the editor's UI locale.

## Binding and cleanup

The helper binds the account/library, membership revision, book identity and
revision, and exact rendered form. New forms, collapsed editors, shelf refresh,
backgrounding, clear and session/library replacement invalidate it. Delayed
availability, microphone and transcription completions cannot populate a new
form. A microphone handle arriving after invalidation is stopped without
retaining audio. Old cleanup cannot stop a replacement capture. The Web adapter reserves the
shared microphone before permission/startup, rejects an existing chapter,
assistant or original-note capture, and releases only its matching reservation
or handle.

Capture is limited to the advertised duration, clamped to 1–30 whole seconds.
A recording that exceeds its bound is discarded without automatic ASR; typed
words remain. Explicit Stop submits at most 2 MiB of transient audio and passes
an abort signal to the protected request. Discard and departure cancel current
capture/request work. A current authorization denial invokes the established
access-failure path; an obsolete denial is ignored.

Rendered controls require their current form and phase. Direct form submissions
also recheck the mounted editor and unresolved voice state. Adding recognized
words does not save a memoir, send a conversation turn, generate prose or play
speech. The phone and Web continue to use explicit turn boundaries.

## Source and verification

- Phone composition and introduction voice: `e157679`.
- Protected visual phone shelf: `61847c7`.
- Web shelf current-card and delayed-denial guards: `a6bae31`.
- Web introduction dictation, shared microphone reservations and current-form
  story-order guards: `bd8f6b6`. Final browser and source-profile qualification
  are recorded separately in the development record.

The generated Node UI checks cover bilingual controls, typed edits during ASR,
reviewed insertion, explicit save, UTF-8 overflow, malformed output, discard,
uncertain retry, current versus obsolete denial, membership replacement and
background cleanup. These use synthetic capture/ASR adapters, not household
recordings or a real model. Served Web, signed phone distribution, provider
quality and a family walkthrough remain separate delivery gates.
