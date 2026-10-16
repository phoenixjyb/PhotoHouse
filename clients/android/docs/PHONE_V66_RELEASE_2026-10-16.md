# Phone v66 release: reviewed chapter proposal adoption

Date: 2026-10-16
Version: **66 / `0.66-proposal-review`**
Source: PR #53, merge `752be3abd318052178d263bd32613e059b0c504e`
Tree-equal build/review source: `6d11ac1d1dbb5fab248cf4d5f26055687d0be39c`

## Delivered

Phone v66 lets an authorized editor explicitly select reviewed AI chapter
proposal text and, optionally, its title for an unsaved existing story. The
client checks the current story revision, proposal job and chapter source links,
retains existing links, and places selected wording in the editor. Saving remains
a separate explicit action. The feature does not turn on provider/model story
generation or change the server schema.

The original signing certificate and icon were retained, and DEX bytes were
unchanged by signing. The signed APK is **11,684,216 bytes** with SHA-256
`eedc499fad5fe8e9abe0ce7ed159cbda9d46a59bc5695f113d36f692a6c3d262`.
The Windows HTTPS phone OTA feed publishes v66; native package/signature checks
and complete HTTPS APK readback passed.

## Qualification evidence

All five source CI jobs passed in run `38843947505`. Configured release
build/lint, all 17 embedded build-field checks, original icon verification,
native package identity and unsigned-artifact checks passed. Signing checks
confirmed the original certificate, aligned APK, unchanged DEX and unchanged
icon bytes. Five signing fixtures, 15 publication fixtures and one synthetic
plan-graph check passed. The preceding proposal-adoption source qualification
recorded 74 focused JVM checks and eight QA-emulator journeys; six Chinese and
English renders at 150% text size were inspected.

Native full HTTPS APK readback passed. Independent Mac trusted HTTPS streaming
also verified all 11,684,216 bytes against the signed APK digest without saving
a second APK copy. Windows postflight matched the active API task, configuration,
process and listener binding, retained `update_root`, and verified the v30 TV
pointer and manifest unchanged. This postflight did not inventory all eight
root tasks. The operation did not restart the API or change the database
schema/data, scheduled tasks, TV feed or model configuration.

## Acceptance boundary

No physical phone installation or family test occurred during this release.
Device and family acceptance remain open. Use the [Chinese v66 test guide](PHONE_V66_TEST_GUIDE_ZH.md)
for an owner/member trial of proposal review, chapter/title selection, unsaved
editor behavior, explicit save and reopen. Keep source/CI, signed package, OTA
readback and physical family use as separate evidence. The PR #50/#51 scene
search source is not claimed as part of this phone delivery or as deployed
API/Web work.
