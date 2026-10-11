# Continuing a full memory conversation

**Status: accepted source behavior, October 12, 2026.** The backend, Web, and
Android paths let a member continue a full story or memoir conversation in a
new thread after an explicit user action. The original conversation and its
history remain available. Continuation never sends the question, starts
recording, transcribes audio, or speaks a reply automatically.

## Server limit and public error

`server/backend/app/access/memory_jobs.py` defines a 128-turn limit. The 128th
turn is accepted. A new turn after that limit is rejected before a job or turn
is inserted, with HTTP 429 and the exact public response:

```json
{"detail":"Start a new conversation","code":"memory_conversation_full"}
```

An identical retry of the accepted 128th turn still resolves to its existing
job. Other rate limits do not carry this discriminator. The transport layer
allowlists `memory_conversation_full` only for status 429 in
`server/backend/app/access/transport.py`.

## Client behavior

### Web

The request helper in `server/backend/app/ui/access/app.js` reads an error body
only for HTTP 429, only when its content type is JSON, and only up to 4 KiB. It
uses fatal UTF-8 decoding and accepts only an object with exactly `code` and
`detail`, the allowlisted code, and a nonblank string detail. It does not show
the server detail or raw body. Oversized, malformed, stale, unrelated, or
non-JSON errors remain ordinary rate-limit failures.

`server/backend/app/ui/access/memory-community.js` offers **Continue in a new
conversation** only for the recognized full-conversation response bound to the
current target, thread, and rendered panel. The refused question remains
available in the editable composer. The member can edit those words before
continuing. The old conversation stays in the conversation
list; no turn is sent as part of continuation.

Thread creation uses one UUID across retries after an uncertain create. Before
replacing the selected thread, Web reads and validates page one of the new
thread’s history. A failed or invalid read leaves the old thread and rejected
question in place for a retry with that same UUID. Only after the new thread
and history are verified does Web move the latest editable composer text into
the new, unsent composer. It does not send that text or start ASR/TTS.

### Android phone

`HttpsMemoryCommunityApi.kt` recognizes only the exact JSON error envelope for
HTTP 429, with one `Content-Type`, a body no larger than 1 KiB, valid UTF-8,
exactly `detail` and `code`, and a nonblank string detail. The phone retains
only the typed `MEMORY_CONVERSATION_FULL` discriminator; it does not surface
the raw server detail. Other 429 responses remain generic rate limits.

`ConnectedStore.kt` and `MemoryCommunityPanel.kt` provide an explicit
continuation action for story and memoir chats. The action is bound to the
account, session generation, library, reader scope, selected target and
revision, rejected turn, and conversation. Memoir scope also includes the book
revision and ordered child story IDs/revisions. Active requests, unfinished
dictation or contribution work, and other conflicting edits block continuation.
The phone validates the created conversation, fetches its first history page,
and refreshes the conversation list before replacing the selected thread.
Creation retries reuse the pending conversation request. The refused question
and current draft are retained together as editable text, subject to a combined
4,096-byte UTF-8 limit; over-limit text is kept for the member to shorten, not
truncated. No send, recording, ASR, or TTS starts automatically.

This continuation action remains separate from memoir composition. A memoir’s
optional introduction has its own explicit **Dictate introduction**,
record/stop, transcript review, and **Add to introduction** controls. It does
not send chat text or begin automatically during conversation continuation;
see [Phone memoir composition](PHONE_MEMOIR_COMPOSITION.md) for its scope and
save rules.

## Source references

- Backend accepted source: `e042544`.
- Web accepted source: `54f323b`.
- Android accepted source: `e157679`.
- Backend limit and refusal: `server/backend/app/access/memory_jobs.py`
  (`MAX_TURNS`, `memory_conversation_full`)
- Backend error-code allowlist: `server/backend/app/access/transport.py`
  (`TRANSPORT_ERROR_CODES`)
- Web bounded error parsing: `server/backend/app/ui/access/app.js`
- Web continuation and verified-history flow:
  `server/backend/app/ui/access/memory-community.js`
- Android bounded error parsing: `clients/android/android/live-core/src/main/kotlin/dev/photohouse/connected/core/HttpsMemoryCommunityApi.kt`
- Android typed error contract: `clients/android/android/live-core/src/main/kotlin/dev/photohouse/connected/core/PhotoHouseApi.kt`
- Android scope, retry, and draft handling: `clients/android/android/live-core/src/main/kotlin/dev/photohouse/connected/core/ConnectedStore.kt`
- Android explicit controls: `clients/android/android/connected/src/main/java/dev/photohouse/connected/MemoryCommunityPanel.kt`
- Memoir introduction voice controls: `clients/android/android/connected/src/main/java/dev/photohouse/connected/MemoryBookComposerPanel.kt` and `MemoryDictationInput.kt`
- Memoir introduction voice scope and save guard: `clients/android/android/live-core/src/main/kotlin/dev/photohouse/connected/core/MemoryBookCompositionDictationStore.kt` and `MemoryBookCompositionStore.kt`

## Qualification and delivery boundary

The accepted source qualification reported for this change was:

- Backend: full suite passed, **1,210 tests and 692 subtests**.
- Web: full **19-suite** profile and **30 focused checks** passed.
- Android: **four generated story/memoir × English/Chinese journeys** passed at
  150% text in **90.928 seconds**; the generated renders were inspected.

These are synthetic/source and emulator qualification results. They do not
establish signed-package distribution, a served deployment, live backend
behavior, real family data, or physical-device acceptance. Those remain
separate delivery gates.

The counts above apply to conversation continuation, not memoir introduction
dictation. Its generated-WAV fixture does not establish actual microphone or
provider qualification; no such result is claimed here.
