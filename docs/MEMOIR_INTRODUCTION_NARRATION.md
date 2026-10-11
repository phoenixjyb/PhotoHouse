# Explicit memoir opening narration

A saved memoir opening can be read aloud independently of its chapters.
The control appears only for a nonblank saved opening; it does not read an
unsaved editor draft, assistant reply, generated manuscript or original
family recording. The visible text remains available without a voice engine.

## User actions

Opening a book mounts an inert control. **Read introduction aloud / 朗读开篇**
starts speech only after a tap. Pause, Resume and Stop remain explicit.
Completion leaves the current story, chapter, media frame and saved reading
position unchanged. It never starts a chapter, queues an assistant turn,
queries a model or changes a saved memoir.

The utterance contains the saved opening words only. It uses the book's saved
Chinese or English language, independently of the interface locale. The same
bounded local speech helpers used for chapters provide chunking and status.
Android chooses an installed voice that does not require a network connection;
Web requires a browser voice marked as local. No speech provider is downloaded
or configured by opening this control. An unavailable local voice leaves the
full text readable.

## Ownership and departure

The speech snapshot binds the account/session, library, reader instance, book
ID/revision, ordered story revisions, exact opening and language, and current
story/chapter/frame location. Navigation, replacement, close, backgrounding
or logout invalidates the old control and stops its speech. A delayed old
completion cannot restore controls or move the new reader. Android manual
Read/Resume additionally require the current enabled control and a resumed
foreground lifecycle. The button keeps its rendered action identity, so a delayed
Pause cannot become Resume when the phase changes. Active Pause and Stop remain
available when new playback is disabled. Returning to the foreground starts
nothing automatically.

Opening, chapter and companion narration share the existing audio coordinator.
Starting one stops the previous speech. Recording reserves the microphone and
stops playback before capture; speech cannot start while that microphone is
owned. Releasing a recording does not automatically retry a blocked read action.
The user chooses Read again. A valid microphone attempt stops speech before
permission, so a denied attempt also leaves it stopped. A request already
invalid or aborted at preflight has no playback side effect.

This audio is synthesized speech, not a family's preserved original voice.
Original contribution playback keeps its separate identity, authorization and
retention controls. [Introduction dictation](MEMOIR_INTRODUCTION_DICTATION.md)
is also separate: it reviews transient ASR text before explicit Add and Save.

## Qualification and delivery

The source pin and generated bilingual browser/emulator results are recorded
after integration in [the development record](DEVELOPMENT.md). Tests use fake
local voice adapters and generated memoirs. They qualify explicit actions,
text/scope binding, cleanup and layout; they do not establish pronunciation,
voice quality, installed voice availability or family acceptance.

Served Web files, a private phone build profile, signed OTA distribution and
a family walkthrough remain separate delivery gates. There is no Windows
service, model, media or database change in this client feature.
