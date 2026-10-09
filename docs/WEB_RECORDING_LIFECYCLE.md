# Browser recording lifecycle

Recording has distinct permission/setup, active capture and review stages.
Only the user can start a microphone attempt. Recognition, transcript insertion,
command submission and saving an original recording retain separate actions.

```text
explicit Record → opening microphone → recording → explicit Stop → review
                         ↓                 ↓
                  cancel / scope loss → discard and release resources
```

## Ownership and cancellation

Each recording attempt belongs to the account, library and view that started it.
The shared capture helper receives both a current-owner check and an abort
signal. The check refuses stale results; the signal releases resources while
permission or audio-context startup is still unresolved. Closing a view,
changing its target, leaving the tab, backgrounding or explicitly canceling
invalidates that view's attempt. Cancellation never means keep, upload or ASR.

JavaScript cannot dismiss a browser microphone permission prompt. If cancellation
happens while permission is pending, the caller can still settle immediately.
Any stream delivered later must have its tracks stopped without creating an
audio context. Cancellation during context startup stops the current tracks,
disconnects nodes, closes the context and clears buffered samples. Late startup
completion cannot resume capture, update a replacement view or submit audio.
Cleanup is idempotent across cancellation, errors and explicit stop.

Releasing a search assistant's hold before setup completes discards that attempt
and explains that recording has not started. Once setup completes, releasing
the hold stops capture and requests recognition for review. Keyboard-operated
record/stop controls retain their explicit actions.

## The surfaces that use capture

| Surface | Stop/review destination | Scope loss |
|---|---|---|
| Search assistant | Editable recognized text; explicit Add, then Find | Clear, account/library reset, cancellation |
| Photo/upload note | Original WAV draft; explicit save and separate processing consent | Note dialog close or account/library/view loss |
| Story contribution | Original WAV draft; explicit contribution review/save | Target/tab change, close, background, cancellation |
| Story chat dictation | Editable recognized text; explicit insertion and Send | Target/conversation/tab change, close, background, cancellation |
| Story idea dictation | Editable recognized text; explicit insertion and proposal request | Target/tab change, close, background, cancellation |

These rules apply to client resource lifetime. Saved family originals retain
their own owner-controlled lifecycle; transient assistant recordings and
30-day troubleshooting records are separate. See
[transcript review](ASSISTANT_TRANSCRIPT_REVIEW.md) and
[architecture](ARCHITECTURE.md).

## Saving a photo or folder note

An original-note save freezes the reviewed text/file, target, language and
processing consent until its response settles. Recording setup and active
capture block saving; Stop stays usable. A successful receipt clears only the
exact saved draft. An uncertain or failed response preserves the draft and
mutation identity for an explicit retry. Detached composers cannot save into a
reopened dialog, and closing the dialog disposes its capture listener.

## Qualification

Generated browser tests must hold permission and context startup across
cancellation, confirm immediate cleanup before releasing the deferred operation,
then verify a replacement attempt remains usable. Successful ordinary capture
still needs explicit stop, review and submit/save. Synthetic audio APIs establish
state and resource behavior; actual microphone, browser permission UX, installed
provider and family acceptance remain separate checks.
