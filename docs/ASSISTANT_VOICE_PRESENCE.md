# Voice presence and turn-taking UI

The phone and Web source show a persistent, readable status card for the
assistant. Idle entry states that the microphone is off and waits for an
explicit start. Foreground voice sessions distinguish these stages:

| Stage | User cue | Microphone |
|---|---|---|
| Opening microphone | Wait for the listening cue; grant permission if asked | Not yet confirmed |
| Listening | Your turn; say what you want to find | Confirmed capture started |
| Recognizing speech | Recognizing the completed utterance | Off |
| Finding memories | Searching the current authorized context | Off |
| Preparing speech | Preparing or downloading reply audio | Off |
| Speaking | The player has actually started the reply | Off |
| Paused | Read the reason; explicitly resume or end | Off |

Phone capture confirmation follows successful `AudioRecord.startRecording`,
outside its lifecycle lock. Playback confirmation comes from ExoPlayer's
`onIsPlayingChanged(true)`. The store accepts those callbacks only for the exact
foreground account/library, session and operation binding. Observation flags
do not advance the semantic controller; transitions clear them. Legacy platform
overloads do not invent a start confirmation.

Web listening requires its current capture object to be ready; speaking requires
the current player's `play()` promise to resolve. Deferred permission and speech
downloads therefore have separate preparation states. Manual dictation, typed
requests and explicit reply playback also update the same presence card.

Phase color, text, microphone labels and restrained decorative animation work
together. Animation is not an audio-level meter or model progress estimate.
Reduced-motion preferences disable Web animation; Android's disabled animator
setting suppresses its confirmed-activity pulse. Pause/End stay visible while
results scroll, including narrow layouts and enlarged text. Starting, resuming,
capture limits, cancellation and actual-ended admission rules are unchanged.

The API/Web source `52c4c81` is served and phone v54 is published on Windows
HTTPS OTA. See the [delivery record](../clients/android/docs/PHONE_V54_RELEASE_2026-10-13.md).
This release adds no backend route, provider, schema or recording retention
change. Screenshots, emulator fixtures and live package readback do not establish
physical microphone, speaker or family acceptance.

Local evidence: the foreground Web voice regression and manual transcript
journey pass, with phone/desktop and 150% text renders inspected. The current
Android core output reports 915 passing tests, connected unit checks report 17,
and three emulator voice-workspace fixtures pass with English/Chinese 150%
renders inspected. These cohorts overlap earlier checks and are not a native
ASR/TTS or physical microphone/speaker test.

## Following phone source: failure recovery guidance (October 16)

The phone status card now distinguishes three paused failures in Chinese and
English: a recording that could not be recognized, a request that could not
finish, and audio playback that did not finish. Recognition guidance invites an
explicit Resume and a fresh utterance; request guidance directs the user to the
on-screen message; playback guidance keeps the visible content useful and says
that Resume returns to voice search.

This is display-only guidance. Rendering never starts recording, submits or
retries a request, replays speech, or restores the previous reading intent.
The existing uncertain-request receipt check and its blocked Resume action stay
unchanged. Shared paused controls keep the microphone-off label and explicit
Resume/End actions. This following source is not included in the released v67
APK; signing, publication and real audio/family acceptance remain separate.
