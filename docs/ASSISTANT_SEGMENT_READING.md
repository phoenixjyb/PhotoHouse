# Read a saved narrative section in segments

**October 15 source work, not a Windows or APK delivery.** The assistant can
offer a separate action to read the complete first chapter of a fresh saved
story, or the complete introduction of a fresh memoir. Later chapters remain
in the ordinary reader. This does not generate, polish or replace saved words.

## Interaction contract

One explicit tap requests one segment. The client shows preparation, actual
playback, Stop and the segment position. Only the exact player's successful
completion can offer **Continue / 继续朗读**. Another tap requests the next
segment; nothing automatically starts the next segment, changes chapter or
opens the microphone. The final segment shows completion instead of Continue.

Stop, failure, foreground/lifecycle interruption, account/library/result/source
replacement, capability refresh or recovered history invalidates continuation.
Progress is local to the fresh result and playback session, with no persistent
bookmark or audio cache. The existing Read opening action and approved voice
opening behavior keep their separate contracts.

## Optional protected transport

The separate capability probe is:

`GET /assistant/workspace/v1/saved-memory-segment-reading-capabilities?library_id=...`

Its exact response is `{version: 1, available: boolean}`. It uses existing
workspace, saved-memory reader and local reply-speech readiness. Older servers
can leave it unavailable; no field is added to their strict base capability
response and their existing opening route is unchanged.

Each segment uses:

`POST /assistant/workspace/v1/threads/{thread_id}/requests/{turn_id}/memory-cards/{ordinal}/segments/{segment}/speech`

The exact body is `{library_id, expected_revision}`. Fresh speech and parent-turn
UUIDv4 values use the existing request headers. Card ordinals are canonical
zero-based 0–11; segment ordinals are canonical 0–127. No caller prose, title,
source identifier, digest or generated replacement wording is accepted.

Successful private WAV responses include:

| Header | Meaning |
| --- | --- |
| `X-PhotoHouse-Reading-Segment` | Canonical requested zero-based segment, 0–127 |
| `X-PhotoHouse-Reading-Segment-Count` | Canonical total count, 1–128; greater than the segment |

Clients reject missing, duplicate, malformed or mismatched metadata before
exposing audio, and refuse a changed count during the same continuation session.
The successful tracked receipt also requires
`X-PhotoHouse-Playback-Tracking: enabled`, so completion can use the same owned
playback outcome path.
These headers contain no narrative text. Privacy, request receipts and playback
reports use the existing protected speech machinery.

## Exact source and bounds

The server resolves the current first story chapter or memoir introduction from
the complete owned saved-card cohort. It segments at Unicode code-point
boundaries, preferring sentence or word boundaries after 60 code points. Every
segment is at most 120 code points and 360 UTF-8 bytes; concatenating all segments
recovers the exact source spacing and order. The complete section is bounded to
6,000 UTF-8 bytes and 128 segments. Empty, malformed or pathological
whitespace-only sections are unavailable rather than silently rewritten.
All segments use the language inferred from the complete section, so a
Latin-only prefix of a Chinese section does not unexpectedly change narrator.

Smaller inputs do not guarantee a speech duration. Every provider WAV must still
pass the existing 30-second and 2-MiB validator. A failure withholds audio and
does not retry or split again invisibly.

Membership, feature/dependency identity, latest completed turn/revision, the
whole ordered reference cohort and the exact complete section are checked again
after synthesis. Source changes outside the selected segment also withhold the
response. Source prose is transient provider input; it is not copied into the
assistant troubleshooting input/transcript fields or new database records.

## Remaining acceptance

Seventeen generated backend segment cases and the sixteen existing opening cases
passed. Eight disposable-qualifier checks passed; its twelve scenario groups now
include a complete three-segment synthetic story and private receipt metadata.
The Web controller passed seventy Node tests and twenty-six browser checkpoints,
including delayed replacement cleanup for both opening and segment requests.
Phone focused core cohorts passed thirty-three store and nineteen wire cases;
nine simulator cases passed on the reused API 36 device. Chinese/English 150%
phone and browser renders were inspected, including an actual click on Stop.
These scopes overlap and are not summed.

Source tests, browser/emulator renders, immutable package qualification, native
Windows TTS behavior, live API delivery, signed APK publication and physical
family listening are separate evidence. This source increment grants no live
operation authority. See [opening speech](ASSISTANT_SAVED_MEMORY_READING.md),
[voice timing](VOICE_TURN_TIMING.md) and [the roadmap](ROADMAP.md).

## October 15 compact controls and Web status

The phone's explicit reader actions have a minimum 48 dp target; Web's primary
saved-memory reader controls have a minimum 48 px target. The followup chips use
short visible labels (Summary, Chapters and All memories, localized on phone
and Web), while their accessibility descriptions retain the complete scoped
prompt. Choosing a chip still inserts the unchanged prior request wording into
the editable draft. Segment reading remains one explicit request per tap, with
no automatic chapter advance.

A late Web capability-probe race fix is in progress. The Web Node and browser
counts above are pre-fix baseline evidence and do not qualify the current Web
followup lifecycle. Re-run the focused delayed-capability/current-result checks
after that fix before treating this Web path as accepted. These source notes do
not establish native TTS, live API, package, physical-device or family
acceptance.
