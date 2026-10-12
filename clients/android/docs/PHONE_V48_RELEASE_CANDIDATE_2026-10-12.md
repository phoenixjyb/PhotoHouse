# Phone v48 saved memoir editor source candidate

Version 48 (`0.48-saved-memoir-editor`) reserves the next phone release identity
on the clean source baseline `f7482b24a70009d403ed31a9fb4539988081e860`. The
saved memoir editor was added in `136a036`; v47
(`0.47-family-memoir-composer`) was previously published to OTA; physical
installation remains a separate acceptance check. This version bump and candidate note are
the current local release overlay and still need source integration before a
build can be pinned.

## User-facing source change

The saved-book reader offers **Edit memoir / 编辑回忆册** only when its current
protected parent permits editing. The editor freshly authorizes the parent and
selected stories, then allows the owner to revise the title, opening, language,
and ordered story list. It preserves drafts on source or revision conflicts,
requires review before saving, and replays the exact update after an uncertain
response. A successful edit reopens current saved data without creating a
duplicate shelf item.

The feature uses the existing protected save contract. It adds no API route,
database schema, provider activation, or TV behavior. See the
[memoir composition and saved-edit contract](../../../docs/PHONE_MEMOIR_COMPOSITION.md)
and the [Android memoir editor qualification](../../../docs/DEVELOPMENT.md#saved-memoir-editing-october-12).

## Local source evidence

The saved-edit slice passed all 822 live-core tests, 17 phone JVM tests, phone
debug/test builds and lint. Six generated API 36 journeys passed at 150% text
in English and Chinese, including unchanged cancellation, detached controls,
remove/add/reorder, committed update with a lost response, exact retry, fresh
saved-book reading and shelf revision replacement. Enlarged-text edit renders
were inspected. These results qualify the source/emulator slice; the package
profile, live service, signing, OTA, installed phone and family acceptance have
separate gates.

## Release preparation gates

This is a source candidate, not a configured family package. Before the unsigned
release build, pin the exact committed source revision and Gradle file hash, JDK,
Gradle distribution, Android build tools and a reviewed private phone profile.
Explicitly pass every phone routing and feature property, clear inherited
`ORG_GRADLE_PROJECT_*` values, and keep `photohouseStoryFixtureEnabled=false`
and `photohousePhoneUiQa=false`. The prior v47 private profile is available for
local comparison, but its revision and profile identities do not automatically
qualify v48. Recheck the current protected service capabilities for the memoir
save path before claiming a live family journey.

Run `:connected:assembleRelease` and `:connected:lintRelease` with the selected
phone profile. Verify package and version metadata, unsigned signature state,
DEX `BuildConfig` values, artifact size and SHA-256; then recheck the source and
profile identities. Keep full private build evidence outside Git. Do not treat
v47 artifact receipts or a successful build task as v48 evidence.

Signing, Windows transfer, publication and physical installation are separate
operations. They require their own authority and exact artifact checks. An
installed package, service response, and owner/member family walkthrough each
remain separate acceptance evidence.

## Family walkthrough after delivery

After a compatible signed release and served capabilities are verified:

1. Open a saved memoir that permits editing. Confirm the editor loads current
   title, language, opening and ordered stories.
2. Close an unchanged edit. Then change the title/opening and reorder, remove,
   and add readable saved stories; confirm discard preserves the saved book.
3. Edit and save, reopen the memoir, and confirm the updated text and exact
   ordered stories are present without a duplicate shelf entry.
4. Exercise an authorized revision/source conflict and confirm the draft stays
   available for review without an automatic overwrite.
5. Exercise a save whose response is uncertain; retry the same update and
   verify the committed edit appears once.
6. Repeat in Chinese and English at enlarged text size. Verify a member sees
   only authorized stories and a revoked account cannot reuse prior editor
   content or controls.

Record installed version, served source and capability state, language, and the
step that failed. Keep family text and media private; use asset IDs and status
rather than copying content into public reports.

No signing, Windows operation, publication, physical installation or family
acceptance is claimed by this source candidate.
