# Edit a saved family story on the phone

Status: implemented locally at `6e3bfc8`; live API availability and signed phone
delivery remain separate gates.

## Author experience

An editable saved story has an explicit **Edit saved story** action. Entry reads
the current saved chapters and the complete, same-revision family-memory link
map before opening the editor. An unavailable or mismatched link map offers a
retry; it is never treated as an empty set of links.

The editor retains the story's ordered photos and videos, chapter arrangement,
theme and language. Authors can revise the story title, chapter titles and their
own narration. Reviewed chapter source choices remain attached to the saved
policy. [Chapter dictation](STORY_CHAPTER_DICTATION.md) appends explicitly
accepted words to the current chapter; it does not save automatically. Accepted
family contributions keep their existing IDs and attribution.

## Save and recovery

Saving requires an explicit review confirmation. The update binds the saved
story ID and base revision. An uncertain response keeps an immutable request:
the same wording, source policy, contribution links, query profile and mutation
ID are used for confirmation. It cannot create another story.

A conflict leaves the unsaved words visible. **Reload latest saved story** asks
before replacing them. The phone retains the conflicted draft while checking
the fresh story and all chapter links; a failed read leaves that draft available
for another attempt. Only a validated replacement discards the old words and
requires a new review confirmation.

An idempotent retry may confirm the earlier update and return a newer family
revision. The phone explains this outcome and opens the current saved story.
The first successor must match the submitted media; a later revision may contain
subsequent family changes. Story identity, library and response validity remain
required in both cases.

## Scope and delivery

Account, credential, library, access generation, reader epoch and editor request
bind every read and write. A delayed response from a closed or replaced editor
cannot reopen it or clear a newer session. Current access denial clears protected
content. Dictation also binds the saved story revision and chapter media; disposal
of an older input cannot close a newer chapter's helper.

This source slice uses the existing story update and contribution-reference
contracts. It adds no schema migration or background model request. Local
qualification, a signed APK, OTA publication and a real family editing journey
remain separate evidence tiers. See [source choices](CHAPTER_SOURCE_CHOICES.md),
[reader navigation](STORY_READER_NAVIGATION.md) and [the roadmap](ROADMAP.md).

## Local evidence

The focused store cohorts passed 22 story-workspace and 14 connected-creation
tests; the repository retry cohort passed nine tests. Two generated saved-edit
UI journeys passed on the reused API 36 emulator. Chinese and English renders
at 150% text size were inspected, including chapter navigation. The reload
follow-up passed main and Android-test Kotlin compilation. These are local
fixtures, not evidence of an installed release or household voice turn.
