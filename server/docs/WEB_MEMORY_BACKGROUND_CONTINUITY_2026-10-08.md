# Web companion: preserve submitted replies across backgrounding

## Behavior

A story or memoir question is submitted only by the user. Switching the browser
page to the background pauses foreground checks, ends microphone capture and
playback, revokes original-audio URLs, aborts requests and clears protected reader
material. It does **not** cancel a job already accepted by the server and never
resends the question.

The complete WebUI still clears its protected readers on hide. After returning
and fresh session/library authorization, reopen the same saved story or memoir:
its private conversation history and pending-job lookup recover the reply.
Reopening selects the first server-listed conversation; the previously selected
thread is not retained, so select that conversation if it is not the default. This
change does not preserve an unsent reader draft across that full-page cleanup or
automatically reopen a reader. In a still-mounted standalone community reader,
foreground return checks the same current job; its unsent composer remains in
memory. Account/library/reader fences remain in place.

Pre-hide status responses cannot restart polling or replace later state. Manual
Cancel and ordinary reader/scope disposal retain their existing cancellation
rules. The change applies to already-known chat and narrative jobs; it adds no
background microphone, client network loop, new worker or provider call.

The Web conversation also explains the model window: current source material,
the current question and at most seven preceding exchanges. Earlier retained
messages remain readable but are not automatically included in the next reply.
There is no automatic conversation summarizer or new retention behavior.

## Implementation

- [Top-level page lifecycle](../backend/app/ui/access/app.js): only visibility
  cleanup passes `cancelMemoryJobs:false`; normal invalidation retains its default.
- [Reader cleanup](../backend/app/ui/access/story-workspace.js): propagates the
  background disposition while clearing private material and closing readers.
- [Community lifecycle](../backend/app/ui/access/memory-community.js): pauses
  foreground work without DELETE, uses visibility epochs for late status reads,
  refreshes a still-current job on return, and keeps explicit cancellation.
- [Worker context](../backend/app/access/memory_processing.py): unchanged eight
  selected turn rows include the current question, leaving at most seven prior
  exchanges. Reading history does not extend the model context.

No HTTP wire, schema, feature gate, retention, permission or model adapter changed.
The [community contract](security/MEMORY_COMMUNITY_V1.md) documents these rules.

## Local evidence

The [UI harness](../tests/security/test_memory_community_ui.cjs) passes background
no-DELETE, no-resend, polling pause, hidden late-read rejection, fresh visible job
lookup, standalone draft preservation and background cleanup of private material.
Existing explicit-cancel/retry, old account/library response fencing, recording,
IME, editor and audio-disposal checks also pass. Its stale read-only fixture was
updated to negotiate the independent edition capability without requesting story
contributions with a book identity.

[Local narration checks](../tests/security/test_story_narration_ui.cjs) pass for
explicit starts, capture priority, disposal and draft/revision boundaries.
The [protected synthetic browser journey](../tests/security/test_memory_community_browser.cjs)
passes the actual top-level lifecycle: no job or conversation DELETE on hide,
fresh lookup and bounded polling for the same job after reopening, ready reply,
no duplicate message POST, and one DELETE from explicit Cancel. Its complete
journey has no browser errors or external requests. Chinese/English 390px
conversation controls and context-help renders, plus the recovered desktop reply,
were inspected. The controls also passed their existing 150% text checks; the
context-help paragraph uses its ordinary readable size in those renders.

Run the two direct CJS harnesses above with Node. Run the browser CJS with an
existing `PH_BROWSER_PYTHON`, `PLAYWRIGHT_MODULE`, `PH_BROWSER_EXECUTABLE` and
`PH_BROWSER_ARTIFACTS` configuration; its ASGI/SQLite, microphone and narrator
fixtures are synthetic. No dependency or model installation is needed for this
increment's recorded checks.

These are local source and synthetic UI checks. Windows serving, actual model
processing while the user switches apps, browser microphones and family usage
remain separate acceptance. No API switch, worker run, schema migration, signed
APK or OTA publication is part of this increment.
