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

## Web gallery thumbnail recovery

A failed photo or video thumbnail now leaves a localized **Preview unavailable /
预览暂不可用** message in the same thumbnail area. The media label and the
existing card action remain available, including keyboard opening. A failed
thumbnail is not retried automatically or used to load original media; the
existing protected viewer handles a separate explicit card action. Detached
old-gallery errors cannot change a replacement card.

The synthetic browser fixture returns 503 for photo and video thumbnails and
checks the preserved label, keyboard action, absence of original requests and
stale-card guard. The Edge Web profile passed 65 tests, including native codec
playback. Chinese 390×844 at 150% and English desktop renders were inspected.
This Web fallback does not change protected phone detail previews or optional
Home TV's separate published catalog and explicit publication boundary.

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

## Voice recovery actions

The phone's paused, uncertain voice session now offers **查询回执 / Check receipt**
in the session card when a pending turn exists. Resume stays disabled and End
remains visible. Receipt queries use the existing callback; they do not resend
the question. A query in progress disables the action and shows its real state.

For Web manual recording, keyboard focus on Stop is handed to the editable
transcript after a successful current-scope transcription, or to the explicit
microphone retry control after an error. Moving focus elsewhere suppresses this
handoff, as does changing account/library or replacing the attempt. Recognition
does not submit a turn or restart capture automatically. Continuous voice
session behavior is unchanged.

## Completed Web voice-turn timing

The explicit foreground assistant session has a collapsed **Last turn timing /
上轮用时** disclosure. Four client-observed values cover recognition, the
assistant request, speech preparation and playback. They appear only after
confirmed playback completion and the loop returns to listening. Pause, End,
new turns, scope changes and lifecycle invalidation clear the values; failed or
unfinished work does not publish partial timings. Opening the disclosure makes
no request. Values stay in page memory and carry no transcript, reply, audio or
source identifiers. They include network and local startup time, so they do not
claim provider latency. See [voice-turn timing](VOICE_TURN_TIMING.md) for the
source evidence and the separate Android checks.
