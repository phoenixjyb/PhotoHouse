# Read a saved narrative section in segments

**October 15 source work, not a Windows or APK delivery.** The assistant can
offer a separate action to read the complete first chapter of a fresh saved
story, or the complete introduction of a fresh memoir. Later chapters remain
in the ordinary reader. This does not generate, polish or replace saved words.

## Interaction contract

In the default manual flow, one explicit tap requests one segment. The client shows preparation, actual
playback, Stop and the segment position. Only the exact player's successful
completion can offer **Continue / 继续朗读**. Another tap requests the next
segment; nothing automatically starts the next segment, changes chapter or
opens the microphone. The final segment shows completion instead of Continue.
The separate Web opt-in continuation below can accept a spoken request for one
next segment; manual controls and the phone behavior stay explicit per segment.

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

The late Web capability-probe race now has a deterministic held-response
journey: 27 Edge checkpoints passed with exact current-result binding, no focus
movement, no duplicates and no automatic submission. A separate held session
restore exposed premature voice startup; the current source blocks capture until
that restore completes and shows a localized setup state with the microphone
off. Its focused voice and recovery journeys pass. Complete integrated profiles,
native TTS, live API delivery, physical-device and family acceptance remain
separate evidence.

## Web voice continuation (October 16 following source)

This Web-only increment follows the published phone v66 and last verified live
API/Web. It is not an APK, Windows deployment or provider-quality claim. Phone
voice continuation and automatic advancement to later chapters remain future work.

1. Retrieve a fresh saved story or memoir and play its first manual segment.
2. After that exact player's successful completion, if another segment remains,
   the card offers **语音继续 / Continue by voice**. Its adjacent explanation
   explicitly says that it turns on the microphone. The button is absent from
   the visible controls while preparing/playing or when voice is unavailable.
3. Select that button to start foreground listening for this exact current
   memory. No audio or chat request starts from that selection alone.
4. Say **继续朗读** or **continue reading**. This consumes the recognized command
   locally and requests exactly one next segment through the existing protected
   segment endpoint. It adds no assistant search/chat turn or generated reply.
5. Only actual successful playback completion returns to listening. The last
   segment pauses the session with the microphone off. Later chapters stay in
   the ordinary story reader; Resume returns to general voice search.

The complete continuation vocabulary is 继续朗读, 继续读, 读下一段,
continue reading, read the next part and read the next segment. Normalization is
limited to the [existing exact-control rules](VOICE_SESSION_SPOKEN_CONTROLS.md).
A bare “继续”, negation, quoted text or additional words is not this command.
An exact continuation without the eligible source pauses with selection guidance;
it does not guess a story, synthesize a new opening or submit a search.

The anchor contains the current account/library/generation, exact result and
card/ordinal, thread revision, completed segment and expected count. Existing
server validation checks the saved source and full reference cohort again before
and after synthesis. An observed source/capability replacement or rejected/stale
response withholds playback and pauses. Retained history cannot create an anchor.

Selecting the explicit voice action brings Pause into focus and scrolls its
status panel into view, clear of the inline sticky navigation. Pause and End
keep a minimum 48 px target. Conversation management is disabled during active or
paused voice and becomes available again after End; it does not wait for a new
server response to update those controls.

The shared microphone adapter may retain only this completed, released player's
source identity when it starts the next capture. It must still stop unrelated
playback; it cannot preserve an active speaker or overlap microphone and audio.
The existing Pause, End, local Stop, permission/lifecycle and scope fences clear
the anchor and progress. Resume never restores that old reading intent. Starting
ordinary voice or asking an ordinary question also clears it. There is no audio
cache, persistent bookmark or automatic chapter navigation.

The protected ASR request follows existing input/receipt retention. Its exact
control transcript is consumed locally and cannot become the parent of a later
chat turn. No new server endpoint, schema, provider or recording retention is
introduced. Source/UI fixtures and CI, immutable package qualification, Windows
ASR/TTS behavior, live delivery and family listening remain separate evidence.

Local qualification for this increment: all 31 synthetic saved-memory browser
checkpoints, the standard voice-session browser regression, five exact-control
Node groups and the shared microphone/WAV checks passed. Chinese/English active
listening at 390 px and 150% text was inspected, including the Chinese assistant
workspace; status hit-testing checks that sticky navigation does not cover the
instructions. These fixtures do not exercise a live ASR/TTS provider or family
audio. No Android source or installed device changed in this increment.
