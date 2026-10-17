# Phone v72 candidate: recover and explain foreground batch uploads

Reserved: **72 / `0.72-upload-recovery`**. The published phone remains
[v71](PHONE_V71_RELEASE_2026-10-17.md). This source is not a signed or published
APK and does not establish a physical-phone upload or visual acceptance pass.

## Why this follows v71

V71 repaired library-targeted response parsing. Its physical trial reached full
transfer with server receipts, but required several Retry taps. Two reproducible
queue behaviors made recovery awkward: one failed file ended the batch run, and
Retry processed only that file before stopping.

## Recovery and presentation

An explicitly started foreground run retries temporary network errors and HTTP
408/429/500/502/503/504 at most three additional times per file, waiting 2/4/8
seconds or the server's longer Retry-After. A cooldown over 30 seconds ends the
run rather than silently extending it. Security, access and invalid-response
failures never trigger automatic retries. Persistent connection/server failures
stop the run; isolated unreadable/invalid/oversized/unsupported files fail their
own row and allow the remaining selected files to proceed.

Each attempt keeps request, batch and destination identity. Known transfer IDs
are read back before another write, so a lost chunk reply resumes from the
server's committed offset. A completed transfer is adopted without reopening or
resending the original. A fully committed but unfinalized transfer can be
confirmed without reopening its source. Interrupted response bodies are network
failures; malformed complete responses remain protocol failures.

Retry and Resume continue queued files in the selected batch. **重试本批中断项**
retries existing failed members without resetting completed rows or creating a
new batch. Controls cannot mutate a running or completed item through repeated
Retry taps. Restore, history refresh, app foregrounding and network changes do
not start uploads. Pause, account changes and lifecycle interruption fence
backoff and late replies.

The UI shows file checking, server-progress reconciliation, transfer, retry wait
and final receipt confirmation. Pause stays visible with the workspace folded;
retry/resume controls are disabled while a run is active. Full byte progress is
explicitly distinguished from confirmation of every file, review, assignment
and preview/playback readiness. This candidate adds no API/schema/service change.

## Acceptance

Use synthetic dropped replies, cooldowns and bad sources to qualify recovery and
identity preservation. Verify folded/expanded Chinese and English UI at large
text, then separately trial a real Samsung batch after an approved delivery.
A completed v71 batch should never be uploaded again to test this candidate.
