# Phone narration continuity

## Behavior

Chapter and assistant reply narration share the existing local narrator. Reading
starts only after the user presses Read. Pause releases the speech engine, audio
focus and reader audio lease, retaining only the current chunk index in memory.
Resume explicitly reacquires them and repeats the current short segment: at most
180 code points and 720 UTF-8 bytes. The interface explains this possible repeat.
Read starts again at the beginning; Stop clears the paused position.

Recording prevents Resume from allocating a speech engine or taking its lease.
Stop remains available while paused even when other reply actions are disabled.
Backgrounding, navigation, changed reply scope, disposal and provider/focus errors
clear the position. Returning to the foreground never resumes automatically.
Late and duplicate callbacks cannot advance a paused or superseded reader.

Only installed offline voices are selected. This change adds no speech service,
audio upload, stored cursor, schema change, APK version change or publication.

## Evidence and delivery gate

Local checks on 2026-10-05 passed: 10 connected debug unit tests; six distinct
selected instrumentation methods on the existing API 36 phone emulator (nine
executions across three invocations after tightening assertions). The final XML
contains the two final rerun methods, both passing; it is not a six-test XML.
English and Chinese paused/recording views were inspected at 150 percent text.
The tests use fake speech and audio focus adapters, covering bounded replay,
chunk order, stale callbacks, recording conflicts, Stop, scope and lifecycle
clearing, preemption and focus failure cleanup.

There is no claim of audible native speech, physical phone acceptance, a signed
artifact or live deployment. The frozen earlier v41 package does not include this
change. A new candidate build and separately authorized signing/publication are
needed to deliver it.
