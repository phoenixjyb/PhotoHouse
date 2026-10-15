# Phone v48 saved memoir editor source candidate

Version 48 (`0.48-saved-memoir-editor`) was built from clean source
`88b23b6c48083eec53bd8f6a8dee804d71057197`, signed with the existing phone
certificate, and published to the Windows HTTPS phone OTA feed on October 12.
The saved memoir editor was added in `136a036`. Physical installation and the
family walkthrough remain separate acceptance checks.

## Delivered artifact

- Signed APK: 10,086,720 bytes; SHA-256
  `12e569ba22f7e6c69a4437a370274f9db7f1c03711db3e195db8f4d68bd4f260`.
- Configured release build/lint, all 17 DEX profile fields, native package,
  alignment and original signing certificate checks passed.
- Windows and an independent Mac check each read the complete served APK over
  trusted HTTPS and matched its size and hash. TV OTA remained version 30.
- No API restart, service-task change, schema migration, media modification or
  physical-device installation was performed for this publication.
- The first native attempt correctly rejected a signing receipt whose copied
  version fields still said v47. Native metadata proved the APK itself was v48.
  The original evidence was retained, a corrected receipt was hash-pinned, and
  publication continued with the same signed APK. Three regression checks cover
  receipt/package consistency and preservation of the native guards.

The central personal assistant and continuous voice session belong to subsequent
source development; they are not included in this published v48 artifact.

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

The following gates were used for this release and remain required for future
packages. Before the unsigned
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

Package and OTA delivery passed as recorded above. Installed-device and family
acceptance remain pending.
