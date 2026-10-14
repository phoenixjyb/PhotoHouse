# Phone v57 and API/Web delivery

Phone **57 / 0.57-memory-opening** is signed and published on Windows HTTPS
OTA. API/Web source 4b69844e29c9ffc83980da23634c28ca73e4efbe is live.
It includes the v56 saved-memory followups and explicit opening playback.
v56 was qualified but was not published separately.

The original certificate and launcher artwork are preserved. Eight required
tasks are running and enabled; ASR/TTS/OCR process identities are unchanged.
TV OTA remains v30. Physical phone installation and family listening acceptance
remain separate from publication.

## Features to try

Fresh assistant story/memoir cards expose **朗读开篇**. It reads the saved first
chapter narration or memoir introduction, with preparation, confirmed playback
and Stop. Reading ends foreground voice and pending capture; it does not restart
the microphone automatically. Old/recovered history cannot initiate reading,
and changed account/library/parent/source state invalidates audio. The phone
conversation-summary layout is readable at 150% Chinese/English text.

See the [speech contract](../../../docs/ASSISTANT_SAVED_MEMORY_READING.md)
and [fixed candidate qualification](PHONE_V57_RELEASE_CANDIDATE_2026-10-14.md).

## Artifact evidence

- Package: dev.photohouse.connected, version code 57.
- Signed APK: **11,540,856 bytes**, SHA-256
  2826034cb56e67540576033a230b75521c76ef40f83065df5fef2253984e458f.
- Original certificate SHA-256:
  56d7591b2b6c2538d506d1fe51327444f2307736cb12f5beefa08f1c410d6d28.
- Signature, alignment, package/version and unchanged DEX checks pass.
- All 17 embedded build-profile fields match the reviewed configuration; fixture
  and UIQA flags are off. The original 1254 x 1254 mark's pixels match exactly.
- Windows native publication verified the complete APK over trusted HTTPS.
  Independent Mac HTTPS readback also matches the complete size and hash, with
  normal TLS validation, no redirects/proxy and no extra saved APK copy.
  The TV feed response is unchanged.

## API operation and recovery

The source-only package passed native Windows verification of **195 files** and
**eleven synthetic scenario groups**, under five-minute/2 GiB/eight-process
limits and an 8 GiB free-RAM floor. The guarded source switch uses a fresh
stopped-writer backup and preserves schema a0c9d2e4f817, configuration bytes,
originals and providers.

The first switch rolled back after its inherited launcher rejected the new
195-file manifest with an old 194-file count. Worker restoration also revealed
an incorrect assumption that reply speech was disabled on the previous release.
The old API passed HTTPS readback; all five upload workers were restored.

A fresh corrected candidate updates the exact launcher count, executes its full
listener-free validate() against source/configuration and the existing database
before cutover, and checks the same enabled speech configuration for normal and
rollback readback. Fifteen local controller checks and eight native parser checks
pass. The new API then passed static-asset hashes, protected anonymous denials
including the new reading capability, listener/action identity and both OTA feed
checks; five workers were restored. No schema migration, database restore,
model/provider activation, ASR/TTS/OCR restart or original-media change occurred.

The phone delivery controller passed **23 synthetic checks**, including framed
PowerShell transport and exact API prerequisite validation. Phone publication
followed successful API acceptance. At the final service check, all eight required
tasks were running/enabled, preserved ASR/TTS/OCR identities matched and free
physical RAM was about 47.6 GiB. This is a point-in-time observation.

## Phone test steps

1. Open **检查更新** and install v57. Confirm the original icon is retained.
2. Sign in, select a library and search for a saved story or memoir, for example
   **搜索故事 标题关键词**. If none exist, first save a story in its workspace.
3. Tap **朗读开篇** on a fresh result. Check preparation, sound and **停止**.
4. Stop during preparation and playback; confirm no delayed sound or microphone
   restart and that your typed draft remains.
5. Try reading while foreground voice is listening, then an explicit recording
   while reading. Capture and source narration must not overlap.
6. Compare the spoken opening with saved wording. Repeat after changing
   library/conversation and with a member account.

Full chapters, multi-chapter listening and voice-requested narration remain later
features. Hosted CI, physical installation, pronunciation quality and family
owner/member interaction are not implied by synthetic or service checks.
