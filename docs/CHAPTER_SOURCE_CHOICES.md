# Reviewed chapter source choices

## Family experience

Story authors can explicitly choose which picture-linked family notes and AI
observations may inform each chapter. A source can be checked for one chapter
and unchecked for another. Choosing none is valid. Sharing one original memory
with several pictures keeps one canonical source and its original attribution.

The chapter's own wording and separately consented, accepted family contributions
remain distinct context. Unchecking a picture reference does not erase words
already written into a chapter. Original notes, recordings, transcripts and AI
captions remain in their existing stores; source selection neither copies nor
changes them. Suggestions still need family review before a save.

## Compatibility and wire contract

`GET /story-workspace/source-capabilities?library=...` requires current library
read membership and returns the exact version-1 policy, per-chapter limit and
review requirement. An older server's unsupported response keeps the original
writing experience available without claiming source-selection support.

The old closed route boundary uses 403 for an unknown route. Before treating
that response as unsupported, the clients recheck the current session and the
selected library's availability through the existing session endpoint. Confirmed
revocation clears the protected editor; a late check cannot clear a newer account
or library. An uncertain check disables the optional controls. A 401 remains an
authentication failure.

New clients explicitly opt into `chapter_sources_v1` for the whole story and
review the checked sources in each chapter. Protected story GET and save requests
use `source_review=1`. A profile GET or save response has an extra
`source_policy` field: null for a legacy story, or `chapter_sources_v1`. A profile
save requires that exact policy in the string-valued body. Its existing chapter
`evidence_ids` arrays become the allowlists, with at most 12 unique current
sources attached to that chapter's selected pictures or videos. Empty arrays
mean no picture-linked sources. The selection revision and story revision must
still match; mutation retries retain the exact body and query profile.

Default GET and save responses retain the existing wire shape so strict older
clients can read stories. An older client's narration-only edit preserves an
already reviewed policy. Changing media or source IDs on that story requires the
reviewed-source request; a legacy request cannot silently add excluded material.
Absent policy on stored stories retains the original all-current-item-evidence
behavior. Unknown stored policies fail closed instead of reverting to that
behavior. The policy lives in existing story JSON and requires no migration.

Opted-in title requests use `source_review=1`, include `source_policy`, and send
each chapter as `{id, narration, evidence_ids}`. To retain manually arranged
chapters, the profile may also include `asset_ids` on every chapter. There must
be one to six chapters with one to four items each; flattening their item lists
must exactly match the authorized, ordered media selection. Mixed, reordered,
duplicate or foreign layouts are refused. Omitting these lists keeps the preview's
original four-item grouping. The title context uses only the
chosen current item sources and explicitly supplied chapter text. Legacy title
requests keep the original shape and source behavior. Library, full media
selection and source revision are checked before and after provider I/O.

## Runtime and review

Narrative and conversation context honor the policy per story, including every
child of a memoir. Current source digests filter edited or withdrawn references;
replacement words are not selected automatically. Canonical shared notes are
deduplicated across the prompt while each chapter retains its own allowed IDs.
Source policy and current dependencies remain part of the job fingerprint.
Proposals cannot cite an excluded or foreign source.

Web and phone controls require explicit opt-in, clear the review confirmation
when choices change and invalidate delayed title suggestions. Frozen uncertain
saves keep the policy, sources and mutation ID together for retry. Switching
account or library clears the volatile editor. An existing reviewed draft cannot
silently fall back to a legacy save after a capability or network failure.
Draft JSON exports retain the explicit policy and selected IDs after opt-in;
legacy exports keep the original shape. Choosing sources preserves typed wording
and does not ask to discard the draft.

## Local qualification

The backend policy and closed route inventory are committed locally. The 13
policy tests and two subtests cover selected/empty/legacy contexts, source
changes, scoped title requests, memoir children and delayed generation. The
later combined contribution-reference and policy run passed 29 tests and seven
subtests, including a prose update that preserves accepted family links while
choosing no item evidence. These overlapping cohorts are not summed.

A subsequent title-policy run passed 39 tests and 40 subtests, including a manual
chapter partition and refusal of cross-chapter source references. The HTTP
profile also exercises the explicit layout without changing legacy requests.
The complete local API profile at `d0d8a34` passed 1,208 tests and 687 subtests,
followed by the generated demo. It uses disposable fixtures and no installed
model or household runtime.

The phone title adapter at `23a09fe` and Web adapter at `db6eead` now supply the
actual chapter media in opted-in title requests. The Web's 25-checkpoint journey
includes a manual one-frame-per-chapter layout, per-chapter source choices and
a delayed title result discarded after that layout is replaced.

Phone controls at `8be679d` passed the preceding 659-test core run, followed by
affected transport/repository/store tests after the membership recheck. Debug
assembly, lint and one generated API 36 UI journey passed; Chinese and English
150% renders were inspected. Web controls at `a1d3c8e` passed 15 generated browser
checkpoint groups, including IME focus, keyboard use, 150% text, identical retry,
reopen, exports, real revocation and a stale access check. The full 19-suite Web
profile subsequently passed at `5991695`, including spoken chapters and canonical
attributed shared-source fixtures. The complete Android profile remains a
separate qualification gate.

This is local development. It does not enable live groups, change Windows
services, run an installed model, publish an APK or publish private stories to TV.
See [shared-memory evidence](SHARED_MEMORY_STORY_SOURCES.md) and the
[delivery roadmap](ROADMAP.md).
