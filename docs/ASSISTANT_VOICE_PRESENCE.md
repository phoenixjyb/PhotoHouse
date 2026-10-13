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

This is source work after the published API/phone v53 release. It adds no backend
route, provider, schema, recording retention or runtime activation. A later
signed phone/API delivery is required; screenshots and emulator fixtures do not
establish microphone, speaker or physical-device acceptance.

Local evidence: the foreground Web voice regression and manual transcript
journey pass, with phone/desktop and 150% text renders inspected. The current
Android core output reports 915 passing tests, connected unit checks report 17,
and three emulator voice-workspace fixtures pass with English/Chinese 150%
renders inspected. These cohorts overlap earlier checks and are not a native
ASR/TTS or physical microphone/speaker test.
