# Returning to a family conversation

Story and memoir conversations have separate selections. Reopening a reader
can return to the conversation selected earlier in the same running client.
The reader shows a short notice after its current messages load successfully.
The composer opens empty; returning does not start recording, create a thread,
send a message or replay a pending request.

## Scope and lifetime

The hint contains only a conversation ID and its scope. Clients retain at most
16 hints in process memory. They write no hint, draft, transcript, recording,
reply or credential to browser storage or an Android persistence store.
Restarting the client discards the hints.

The scope binds the account, library, available membership revision, target type,
target ID and target revision. A memoir also binds its ordered child story IDs
and revisions. An absent or changed membership, changed story, or reordered or
revised memoir cannot restore an old selection.

## Fresh reads remain required

On reopen, the client reads the currently authorized conversation directory.
A remembered ID is eligible only if that directory still contains it. An expired,
deleted or absent conversation falls back to the first currently listed item;
its old ID is not used to fetch messages. The client loads fresh messages before
showing the restored notice. A failed or invalid response must not claim success.

The hint does not extend the directory's existing pagination or retention limits.
An older conversation outside the returned page is not searched automatically.
Account changes, logout and access denial clear hints. Ordinary reader navigation
may preserve the bounded hint while clearing content and composition state.

A pending reply is checked using the existing job/read paths. Restoration does
not resubmit its message. Switching to another conversation still observes the
existing recording, transcript, draft and pending-request controls.

## Development and delivery

The behavior changes client navigation only. It adds no database migration,
model selection, service activation or server mutation. See
[development evidence](DEVELOPMENT.md) for the checked source and synthetic
browser/emulator results and the [phone contract](../clients/android/docs/ANDROID_CONVERSATION_NAVIGATION_2026-10-10.md).
A signed phone update, served Web files and real family
accounts require separate delivery and acceptance evidence.
