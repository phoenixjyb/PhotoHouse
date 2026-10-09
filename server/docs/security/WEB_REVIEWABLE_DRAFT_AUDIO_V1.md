# Web reviewable draft audio v1

A generated chapter can be read aloud explicitly while it remains marked as an
AI suggestion for review. This is local text-to-speech over the exact visible
chapter prose. It does not retrieve original recordings, save a chapter, send a
chat turn, generate another draft or project private material to TV.

## User flow

Each nonempty story or memoir proposal chapter has a separate **Read draft
chapter aloud** action, with pause/resume and stop controls while speaking.
There is no automatic start, advance to another chapter or microphone activation.
A directory jump stops the prior voice; the user chooses whether to read the new
chapter. The UI language follows the displayed panel, and the speech voice follows
the target story/memoir language. Only installed voices marked as local are used.

Unavailable voices, invalid/oversized text and native speech failures retain the
complete visible text. The existing limits are 6,000 Unicode characters and
25,600 UTF-8 bytes. Chunking does not truncate the source text. Controls wrap at
narrow widths, use a minimum 44px touch height, and announce state politely.

## Ownership and disposal

This reuses the existing workspace speech controller and its single active voice.
Starting a new authorized voice stops earlier chapter/reply speech and family
original playback. Recording takes precedence. Each proposal control must match
its current account, library, target fingerprint, rendered job, active ideas tab,
render epoch and connected article. An old native callback cannot start another
chunk after its authorization fails.

All chapter disposers join the same render-owned disposer set used by chat replies.
A panel replacement, changed reader or hidden document disposes controls before
the panel is detached. A stale disposer cannot cancel a newer active voice.
Unknown content kinds and UI languages are rejected before controls are mounted.

## Local checks

The existing narration VM harness and memory-community UI contract harness pass.
They cover exact prose, distinct review labels, recording priority, pause/resume,
stop, late callbacks, stale scope and disposal before detachment. The full synthetic
protected browser journey passes 20 checkpoints, including 24 separately mounted
draft audio controls with no autoplay, exact local-voice playback, pause/resume/
stop, directory cancellation, and Chinese/English 390px layouts at 150% text.
Synthetic native speech is used; actual browser voices and family listening quality
remain a separate device check. No Windows deployment or model call is included.
