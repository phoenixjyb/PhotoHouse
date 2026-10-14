# Phone v60 and API/Web delivery — October 15

Phone **60 / 0.60-reading-comfort** is signed with the original certificate and
published on the Windows HTTPS OTA feed. API/Web source `53e3954725197906771b6dd6ca470a0d1d58da9d`
is deployed. Original launcher artwork is preserved. TV OTA remains v30.
Physical installation, owner/member journeys and family listening remain open.

## What to try

- Story and memoir prose-size presets, preserving system text scaling.
- Compact phone memoir navigation with more room for the text.
- Explicit retry of the current failed image preview without reopening the story,
  changing its bookmark, saving a draft or restarting speech.
- Assistant first-chapter/memoir-introduction segments, with Continue available
  only after successful actual playback; Stop clears reading progress.
- Unsent assistant drafts across conversation navigation, visible segment progress,
  clearer recovery/followup controls and collapsed client-observed turn timing.

In the phone app, use **检查更新** and confirm `0.60-reading-comfort` after
installation. Refresh WebUI. Follow the [v60 trial](PHONE_V60_TEST_GUIDE_ZH.md)
and its linked assistant scenarios. The
[first-story guide](../../../docs/FIRST_STORY_GUIDE_ZH.md) explains how existing
photo memories relate to saved multi-image stories. The private three-step
first-story prototype remains outside this release.

## Exact artifacts

| Artifact | Identity |
| --- | --- |
| Package | `dev.photohouse.connected`, version code 60 |
| Signed APK | 11,581,816 bytes; SHA-256 `c282fc06cf9e887b289f102234b5872b68a9b6c0a6da55547648ac9f1a6671ee` |
| Certificate | SHA-256 `56d7591b2b6c2538d506d1fe51327444f2307736cb12f5beefa08f1c410d6d28` |
| Immutable artifact source | `53e3954725197906771b6dd6ca470a0d1d58da9d` |
| API source ZIP | 201 files, 3,607,452 bytes; SHA-256 `793a5322400dce1d44de8f673e725fab096210e4fd41574d056751b3cbe3989d` |
| API manifest | SHA-256 `819523c00fe5088a5b45e09c2fdb9397c88e43496350bacf9b1614b6cfdcd7a2` |
| Android subtree | `df7d5e9439e77b50e94beff2d8c6869db8a4984f` |

The [local candidate](PHONE_V60_LOCAL_CANDIDATE_2026-10-15.md) retains unsigned
artifact provenance, profile binding, original-icon checks and full local
qualification. Signing verified package/version, signature, alignment, unchanged
DEX and the original artwork without rebuilding the frozen APK.

## API/Web release evidence

The owner's release instruction covered this exact operation. Bounded native
Windows generated-data qualification passed for all 201 source files, twelve
assistant groups and five experimental oral-history groups / twelve cases.
It used no household database/media, model, network or listening server; its
five-minute, 2 GiB total-job, eight-process and 8 GiB free-RAM limits were retained.
Thirty-two local API delivery-controller checks and native parsing passed;
61 invalid qualification-report mutations were refused.

The guarded switch fenced five upload workers, stopped the API and verified a
fresh stopped-writer backup of the primary database, assistant receipt journal,
original-deletion journal and private workspace, including SQLite companions.
All four copied stores passed integrity checks. The backup receipt SHA-256 is
`bab79c24657e5093054b558687b516e93bc87a7c25928fd37c5339cbc903791d`.
Existing release files remain available for rollback; rollback was not needed.

New served UI assets, the listener/source identity, authenticated-route anonymous
denials and both OTA feeds passed native readback before all five workers were
restored. An independent 07:50 Beijing observation confirmed the accepted
transaction, unchanged enabled states for 66 tasks and only the expected API task
definition change. The enabled 30-second startup trigger is retained. API cutover
completed at 07:48 Beijing; schema remains `a0c9d2e4f817`, with no migration or
configuration change. ASR, TTS, OCR and Home TV were preserved.

## Phone publication evidence

Twenty-three local phone delivery checks passed. A fresh post-switch resolver
bound the active API/configuration and both feed pointers before original-key
signing. Windows publication verified the signed file natively and read the
complete APK back over trusted HTTPS, matching all 11,581,816 bytes and SHA-256.
The TV feed was byte-preserved. Phone publication required no API restart or task,
database or original-media change. Guarded phone-feed rollback was not needed.

The independent Mac trusted-HTTPS check confirmed the v60 manifest and WebUI
response without redirects; a separate full Mac APK download was not run.
No hosted CI, physical installation, audible quality or family acceptance is
claimed by these delivery receipts.

Generation/title suggestions, grouping, editorial processing, long oral-history
intake, permanent erasure and new model/provider activation remain outside this
operation. The experimental five-group oral qualifier is internal evidence;
it does not expose a new production recorder or workflow.
