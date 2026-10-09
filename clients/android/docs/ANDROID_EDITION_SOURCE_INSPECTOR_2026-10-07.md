# Saved memoir editions: original source inspection

## Reader experience

The independent saved-edition reader now includes **核对原始材料**. Opening
the memoir, edition, chapter or reference disclosure makes no source-detail or
recording request. A reader explicitly chooses a chapter reference or loads the
edition's metadata catalog (16 items per page, up to 96 sources).

Materials distinguish family words, family recordings with AI transcripts,
photo notes, family or AI captions, memoir introductions and existing chapter
wording. AI descriptions and editorial narration are labeled separately from
independent family accounts. A current original, derived transcript and exact
drafting excerpt are separate fields; a truncated text is identified as an
excerpt. The original recording requires a separate load action and then an
explicit play action. It never plays on loading. Nothing is written to a local
audio file or persistent source cache.

These are current, freshly authorized materials, not historical source snapshots
saved with an edition. Server-built provenance determines source authority;
client source IDs and model citations are only selectors.

## Contract and lifetime

The optional `MemoryBookEditionSourceApi` uses three authenticated HTTPS GET
operations documented in [the version 1 contract](MEMOIR_EDITION_SOURCES_V1.md).
Both C2 editions and original-contribution feature gates are required. Reading
does not require generation, editorial rights or a retained private model job.
The existing capability, proposal, edition save, metadata and reader wire shapes
are unchanged. There is no unbound contribution/audio or Home TV fallback.

The strict decoder checks exact keys, six origin/identity combinations, immutable
edition receipt revision, current child scope, unique bounded page rows, strict
UTF-8 byte limits, truncation flags, and no material in invalidated responses.
Transport retains protected origin, bearer, MIME, body limits and no-store rules.

The separate repository and GET coordinator fence account, credential identity,
library, generation, book and ordered child revisions, edition and request epoch.
All owned response arrays are wiped after parsing, including malformed or late
audio. A new catalog/detail request clears prior text and closes prior audio
before awaiting a reply. During an explicit audio load, its current transcript
may remain visible; the old recording is already closed and cannot be reused.
Failures clear material. Source conflict/change invalidates the parent shelf
and hides the generated manuscript. Its visible notice is announced and brought
into view when the long inspector collapses, rather than leaving the reader at
an unrelated scroll position. Chapter changes, close, background and
scope disposal cancel reads and close audio. Local read-aloud and recording use
the existing reader audio coordinator.

Dirty, composing, rejected input and uncertain edition saves block source
requests. These read operations cannot alter an editor draft, pending body or
mutation identity. Older injected APIs remain compatible through the optional
interface; no source inspector appears when it is unavailable.

## Qualification

Source begins from `808a201`. Offline JDK 17, existing Gradle caches and the
existing emulator are reused with empty configured service origins.

- **226 affected JVM tests passed**, zero failures/errors/skips: edition,
  source wire/coordinator, community, ConnectedStore and HTTPS transport scopes.
  New source wire/coordinator tests cover all six origins, raw/derived separation,
  Unicode bounds, foreign identity, immutable receipt, explicit requests, paging,
  original byte wiping, failure/conflict and late account/library/credential/
  child/edition responses.
- Debug app and instrumentation builds passed. Debug lint passed with no errors;
  5 warnings and 1 informational finding remain separate from feature acceptance.
- Four distinct Chinese/English 150% font emulator journeys passed: two source
  inspectors and two existing editor/save-retry flows. The source journeys use
  17 synthetic catalog items and synthetic WAV, verify no automatic requests or
  playback, original/transcript labels, paging, failed-read clearing, chapter
  disposal and parent manuscript invalidation. Editor journeys verify source
  actions remain blocked during an uncertain save with its frozen body preserved.
- Synthetic rendered source, audio, failure and invalidation states are inspected
  separately from semantics assertions. The final two source journeys passed
  again after the invalidation scroll/announcement fix (74.599 seconds), with
  the notice asserted visible and both rendered notices inspected. Manual-audio
  controls were also inspected in both languages. Reruns are not additional
  unique journeys; app-node captures avoid stale system-compositor frames.

This source has not been production-signed, published over OTA, installed on a
physical device or qualified against the Windows service. Synthetic WAV does
not establish real listening, ASR/model quality or family acceptance. C2 remains
default-off pending all source-type physical erasure, paired restore and native
worker/runtime qualification. This increment adds no migration or retention
change and does not refresh the older video preparation checkpoint.
