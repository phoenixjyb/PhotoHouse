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

New clients explicitly opt into `chapter_sources_v1`. Protected story GET and
save requests use `source_review=1`. A profile GET or save response has an extra
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
each chapter as `{id, narration, evidence_ids}`. The title context uses only the
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

This is local development. It does not enable live groups, change Windows
services, run an installed model, publish an APK or publish private stories to TV.
See [shared-memory evidence](SHARED_MEMORY_STORY_SOURCES.md) and the
[delivery roadmap](ROADMAP.md).
