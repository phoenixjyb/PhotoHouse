# Phone v57 saved-memory opening playback candidate

Status: now signed and published; see the
[delivery record](PHONE_V57_RELEASE_2026-10-14.md). The evidence below preserves
earlier unsigned qualification. Backend/Web/Android source is fixed at
`4b69844e29c9ffc83980da23634c28ca73e4efbe`.
v56 was qualified separately and superseded by this delivery. Preparing the
candidate did not change live services or data; later deployment is recorded
in the linked release report.

## Changes

Fresh assistant story/memoir cards offer **朗读开篇 / Read opening**. The action
reads the saved first chapter's narration or memoir introduction, bounded to
240 Unicode code points and 600 UTF-8 bytes. It does not rewrite the source or
read the entire book. The server validates the owned parent and complete source
cohort before and after synthesis. Source wording is transient TTS input and is
not copied into private assistant receipt input/transcript fields.

Web and phone stop foreground voice and pending manual capture before speech,
show preparation and confirmed playback, expose Stop, and never automatically
resume listening. Recovered/history cards have no reading action. Scope,
parent, source and capability changes invalidate old audio; old callbacks cannot
read a replacement card at the same ordinal. Explicit microphone capture stops
opening audio. Only one phone panel owns its player.

The phone current-conversation summary stacks its management action beneath
full-width metadata, fixing English midword wrapping at 150% text. Chinese and
English enlarged renders were inspected. The original artwork is preserved.
See the [speech contract](../../../docs/ASSISTANT_SAVED_MEMORY_READING.md).

## Fixed artifacts and checks

The API source-only ZIP contains **195 files**, **3,432,792 bytes**, SHA-256
`bcd73e338f30933418d70177644f8cfff44e17e9277217bbffbb6838cb0d9937`.
Every extracted file matches its manifest; eleven generated qualification groups
passed from the extracted source on Mac. No provider/model, real database/media,
network, listener or worker was used. This is not native Windows qualification.

Phone package: `dev.photohouse.connected`, version code **57**, name
`0.57-memory-opening`. The unsigned APK is **11,522,169 bytes**, SHA-256
`135baaf07e1d2466b6acd6a2797cdfa029fd06a5029a53b10c113aa20a03b407`.
Release assembly/lint passed; native APK metadata and all 17 embedded profile
fields match the retained reviewed phone configuration, with fixture/UIQA off.
Signature verification rejects the unsigned APK as expected. The packaged
1254 × 1254 mark's RGBA SHA-256 remains
`f5e55b4fe45566cf53911d6fb1be20f357f29a8e02d4d1a1e26364dac227c673`.

The affected checks passed: 16 server opening cases; the assistant cohort ran
196 cases (195 passed, one skipped); Web transport 63 and generated browser 18;
Android core 70, connected UI logic 17 and emulator flows four. Final debug QA
build/lint passed. The shared capture regression passed seven browser checks,
and the WAV encoder/shared microphone reservation check passed. These scopes
overlap and are not summed. [Development](../../../docs/DEVELOPMENT.md) records
route, qualifier, package and source-ledger checks. No hosted CI is claimed.

## Delivery and family acceptance

Native Windows qualification, the authorized API/Web switch, original-certificate
signing and phone OTA publication are completed in the linked delivery record. No schema or
model change is required. No physical Samsung installation or listening quality
acceptance has been performed for v57.

After this candidate is delivered:

1. Search for a saved story or memoir in the selected library; use a fresh result.
2. Tap **朗读开篇**. Verify preparation changes to playback only when sound starts.
3. Tap **停止** during preparation and playback. Confirm no delayed sound or
   microphone restart; the message draft remains intact.
4. Try with foreground voice active; reading must end listening first. Try an
   explicit manual recording while reading; narration must stop before capture.
5. Repeat with a member account and after changing library/conversation. Old
   cards must not trigger speech. Recovered history must have no Read action.
6. Check pronunciation and compare the spoken passage with the saved opening.
   Full chapters, multi-chapter listening and voice-requested reading are later
   features; this candidate offers the explicit opening action only.
