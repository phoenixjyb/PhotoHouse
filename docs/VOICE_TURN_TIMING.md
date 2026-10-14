# Voice turn timing

**October 15, 2026: local source and synthetic browser evidence.** This is a
small, ephemeral Web and phone diagnostic for the explicit foreground voice session. It
uses the existing microphone and playback events; it adds no data endpoint or request,
recording, transcript, reply, source identifier or persistent timing record.

## What the user sees

The collapsed **Last turn timing / 上轮用时** disclosure contains four
client-observed durations after a full turn completes:

1. Recognition: transcription preparation/request to the assistant-request stage.
2. Assistant request: assistant-request stage to speech preparation.
3. Prepare speech: speech preparation to confirmed playback start.
4. Playback: confirmed playback start to successful completion.

The turn must start with confirmed capture, observe every intervening stage and
finish actual playback before timings appear. Recording duration is excluded.
Opening the disclosure is explicit and does not send a request. Pause, End, account/library scope changes,
and lifecycle invalidation clear the values. Unfinished or failed stages do not
publish partial timings. The existing Pause and End controls remain available.

These are client-side elapsed intervals. They include network waiting and
local startup; they are not server/provider timings or a speech-quality claim.
Values are held only in the current page/store session and contain no spoken
words or audio. Web clears the previous summary when the next transcription
starts; phone retains the last completed summary while observing the next turn,
until completion replaces it or interruption/failure clears it. Both label the
disclosure **Last turn**, rather than presenting unfinished timings as current.
The Web helper is served as a new static UI asset, not a telemetry service.

## Source checks

The focused synthetic Web voice browser journey passed with fake microphone,
transcription, private reply and speech fixtures. It checks the playback gate,
failed/delayed playback, Pause/End and account-scope clearing, all four values in
English and Chinese, no extra request on disclosure, and the English desktop and
Chinese 390×844 at 150% renders. Fake stage responses can round to `0.0`; these
fixtures prove gating and formatting, not real latency.

The Web browser profile passed 65 tests in Edge, including native codec playback.
The gallery failure fixtures return synthetic 503s for photo and video
thumbnails. The localized fallback keeps the media label and card open action,
and does not load original media or start an application retry. It is a Web
thumbnail state only: protected phone detail/preview access remains separately
authorized, while optional Home TV continues to use its separate published
catalog and publication controls. No Windows source/runtime, Home TV, or phone
publication changed in this round.

Android evidence is separate: the broader Kotlin profile passed 966 tests before
the timing-store additions; the timing-store class then passed 19 tests. The
focused phone voice journey passed 8 tests. The two final label cases also
passed individually on the existing API 36 emulator, with bilingual 150% renders
inspected. Seven pure Web timing tests include older-account scope rejection.
These source/synthetic checks do not establish Windows
runtime behavior, physical phone audio quality or family acceptance.
