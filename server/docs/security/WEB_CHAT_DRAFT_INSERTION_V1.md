# Web conversation draft insertion v1

Selecting an opening prompt or an assistant follow-up question edits an empty
message draft. It does not submit a turn, invoke a model, start audio playback
or automatically create a conversation.

Both entry points use the same current editor and insertion checks. They refuse
an existing draft (including actual textarea content before an input event),
active or unsettled IME composition, capture/transcription or a pending transcript,
an uncertain send, conversation operations and queued/running chat work. The
opening buttons also reject detached renders and a hidden document. A localized
status explains why insertion was refused. Successful insertion focuses the
message and places its caret at the end.

Completed IME composition with its final input committed permits insertion
again. It does not remain blocked merely because a completed composition state
exists. A deferred render must settle first.

The UI harness covers existing text, empty Chinese composition, completed
composition, detached language renders, active capture and transcript review.
The generated protected-browser journey checks the same user-visible states,
retains explicit Send and follows the existing multi-turn conversation checks.
These are synthetic source checks; live ASR, provider replies and device behavior
have separate acceptance records.
