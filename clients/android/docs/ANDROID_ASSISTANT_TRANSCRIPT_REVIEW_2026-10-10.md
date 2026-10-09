# Explicit assistant transcript review

The phone search assistant keeps returned ASR text in a review card. Recognition
does not insert text or submit a command. The user chooses **加入消息 / Add to
message**, edits the message if needed, then explicitly sends it. Existing typed
words are preserved with a newline before the recognized words. Discard leaves
the typed draft intact and clears the recognition link.

The combined draft must fit the existing 512 Unicode codepoint limit. An
overflow disables Add, preserves both texts and explains how to continue;
nothing is truncated. While recording, transcribing or reviewing an unused
transcript, Send stays blocked. A new recording also waits for review or discard.

The store accepts only the exact current transcript object for the current
generation and library. A tracked successful transcription becomes the command's
parent receipt only after that explicit acceptance. A stale, busy or pending
reader cannot accept it. No API contract or audio retention policy changes.

## Synthetic qualification

- `ConnectedStoreTest`: 102 JVM tests passed, including exact acceptance,
  stale/replaced scope, discard and parent receipt behavior.
- `AssistantDraftTest`: three tests passed for preserved wording, overflow and
  Unicode codepoint limits.
- Phone lint, QA debug build and Android-test assembly passed with cached
  Gradle 8.10.2 and JDK 17.
- Six focused API 36 emulator journeys passed, including bilingual Add/send,
  discard, overflow, recording guards and uncertain receipt recovery.
- Both bilingual capture journeys passed again to preserve the rendered
  evidence; they overlap the six journeys and are not added to the total.
  Original-resolution 150% text captures were inspected. The review card,
  recognized text, Add/Discard, typed composer and disabled Record/Send controls
  are visible; unclipped geometry is checked inside the assistant list.

Fixtures use a separate unconfigured QA application ID and fake adapters.
Initial fixture scrolling, repeated Compose setup and assertion errors are
retained separately from the final passing run. No microphone, ASR provider,
physical phone, release signature, Windows server or OTA feed is qualified by
these results. The owned emulator was stopped after inspection.
