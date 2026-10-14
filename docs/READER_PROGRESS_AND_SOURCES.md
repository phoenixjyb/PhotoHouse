# Reader progress and source status

**October 15, 2026: local source and synthetic/emulator checks.** These changes
do not imply a served Web release, signed APK or physical listening acceptance.

## Web memoir source checks

The current memoir chapter shows source-check status beneath its heading, even
when the original-source disclosure is collapsed. Chinese/English states cover
checking, available linked sources, no saved links and unavailable verification.
A failure exposes a keyboard-accessible **重试核实来源 / Retry source check**
button with a minimum 44-pixel target.

Retry fetches only the existing revision-bound contribution-reference endpoint.
It does not load original text/audio, save a story, navigate or start playback.
Account/library/book/chapter/revision and request-epoch guards discard delayed
responses after scope changes. Opening originals remains a separate action.
“Source checked” means a currently accessible link was checked, not that the
story's historical facts were verified.

The focused browser suite passed 13 checkpoints with 115 generated requests and
no page errors. Inspected renders include 390×844 Chinese at 150% text and
English source status. Fixtures contain no family media.

## Phone manual chapter speech

The manual chapter reader displays **朗读分段 x/y / Narration segment x of y**
during preparation, speaking and pause. The value follows the immutable speech
chunk list and current cursor. Pause/resume keeps that cursor and explains that
the current short segment restarts and may repeat some words.

Progress is ephemeral. Stop, completion, failure, scope change and lifecycle
interruption clear it. It is not a persisted bookmark, an automatic chapter
advance or an extension of assistant opening speech. Existing current-source,
audio-focus and explicit playback controls remain authoritative.

The focused Android instrumentation class passed 18 tests on the reused API 36
phone emulator; Kotlin compilation and debug lint passed. Chinese active,
paused and resumed states were inspected at 150% text. Tests use fake TTS/focus;
real voices, headset routing, speaker echo and signed delivery remain separate.
