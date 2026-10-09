# Story and memoir conversation previews

Local source increment, 5 October 2026. Base:
`859efc909de0ce1356ed1e8f3c3f91d62d32f87e` on
`codex/phone-v29-candidate-20260929`. Backend contract source:
`502d015f0ad74bf631c6235d4039e4854a5c76c8`.

## Family interaction

Story and memoir conversation selectors show the date and the beginning of the
first retained user message. A new empty conversation keeps its date without
inventing a preview. The preview uses at most two lines with ellipsis, within a
bounded chip; large text wraps the selector rows. Changing threads preserves
each unsent draft through the existing reader state.

Previews come from the normal server conversation list. Sending a message does
not invent a local preview, fetch every thread's turns, or label a thread using
its most recent message. The next normal list refresh updates the selector.

## Optional protected contract

The existing authenticated conversation-list route adds `preview=1`. The legacy
request and exact legacy row decoder remain supported. Preview rows contain the
same three fields plus `first_message_preview`, with consistent row shapes per
page, at most eight distinct conversation IDs, at most 80 Unicode codepoints
and 320 UTF-8 bytes per preview. Control characters, malformed Unicode and
noncanonical whitespace are rejected. An empty preview is valid.

An older server's HTTP 400 permits one legacy list request, only while the
originating reader, account/library binding and coroutine remain current.
Other failures and invalid responses do not trigger fallback. A stale reader
starts neither the preview nor legacy request. Rechecks between awaited reads
prevent follow-on reads after navigation or access changes. Both paths retain
the trusted HTTPS origin and protected membership checks.

## Evidence and delivery

- Focused decoder, mock HTTPS and repository checks passed; after the final
  freshness repairs, repository 11/11 and community store 46/46 passed.
- Two synthetic API 36 emulator journeys passed, with zero failures or skips.
  The story journey verifies distinct first messages after normal list refresh,
  an 80-codepoint preview, an empty thread and draft restoration. The memoir
  journey verifies its first retained message after list refresh.
- Root reviewed the 150% story selector renders: both distinct labels remain
  readable; the long label uses two lines with ellipsis.

No version bump, release build, signing, OTA publication or physical-device
installation is included. The previously frozen unsigned v41 APK remains
unchanged and does not contain this increment. The backend preview route is
source-tested, not yet deployed. Live generation remains a separate gate;
the selector does not establish that story generation is available.

## Unified public source integration

The nine Android code and test files are imported byte-for-byte from source
commit `a4583c147192dc0cda3d5b0a3f57285b0974cc1e`. The source note was placed at
`clients/android/docs/ANDROID_CONVERSATION_PREVIEWS_2026-10-05.md`; this section
records the unified repository result. The client consumes the optional backend
contract documented in the [server preview contract](../../../server/docs/security/MEMORY_CONVERSATION_PREVIEWS_V1.md).

The public unified-layout targeted JVM runs passed 168 tests across five distinct
suites: HTTPS adapter (6), wire decoder (8), repository (11), connected store
(97) and memory community store (46). These were filtered local JVM runs; they
did not run an emulator or produce an APK. The separately recorded source-
workspace evidence includes 11 repository tests, 46 community-store tests and
two API 36 emulator journeys at 150% text with
root-reviewed renders. Those emulator journeys remain source-workspace evidence,
not public-candidate emulator evidence.

The earlier unsigned phone v41 artifact predates this increment. No signed
package, OTA publication, physical-device installation or live backend result
is included.
