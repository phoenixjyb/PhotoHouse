# Phone v68 release: clearer voice recovery

Date: 2026-10-16. Phone HTTPS OTA publishes **68 / `0.68-voice-recovery`**.

## What changed

Recognition, confirmed request failure and audio playback failure now have
distinct Chinese/English guidance. Paused sessions show microphone-off and
explicit Resume/End controls. Resume after playback failure returns to voice
search. Uncertain requests retain their separate receipt-check path. This
release does not add automatic retries, background listening or new consent.
Existing saved-section voice continuation remains available.

## Source and package

Build source: `8de94671b230f389060ec3858c619d42e9b08a94`. PR #71 merged at
`1bc6432a0f5556838dbf5ed1e4aa7594f2dbb342`; both have the identical Android
subtree `1c4bb02ce8a4d84caa800add72ed12df8cd5aa6d`. Later server-only search
changes were preserved during integration without rebuilding the phone APK.

Signed package `dev.photohouse.connected`: **11,716,984 bytes**, SHA-256
`d35ec97f6d9c36cd7cbf8df43463e419b8cee75602b97e0a488d0ea1d82d4953`.
The original certificate remains
`56d7591b2b6c2538d506d1fe51327444f2307736cb12f5beefa08f1c410d6d28`.
Native signature and alignment passed. All DEX and packaged original icon bytes
were unchanged by signing. The unsigned candidate and historical preparation
checks are recorded in the [candidate record](PHONE_V68_CANDIDATE_2026-10-16.md).

## Verification

All five CI jobs passed at integrated review head `a279b11`, run `38886108884`.
Configured release build/lint, native package/version/unsigned-state checks,
all 17 embedded settings and original icon pixels passed. All six new messages
and both helper markers were found in the release DEX.

The PR #70 implementation passed two synthetic emulator tests; all six clean
Chinese/English native failure renders at 150% text size were inspected. Earlier
captures obscured by Android system dialogs were rejected. The existing AVD was
reused without a data wipe or physical-device action. Seven emulator-controller
checks passed. Release preparation passed eleven profile tests, five signing
fixture tests and fifteen publication fixture tests; two PowerShell controllers
parsed natively. These results do not establish physical audio acceptance.

## Delivery and runtime boundary

Windows native publication and full trusted HTTPS readback verified every byte
of the signed APK. An independent Mac HTTPS stream verified the same full digest
at **2026-10-16 10:29 UTC**, without saving another APK copy. The TV v30 feed
remained unchanged. Pre/postflight API task, action, process/listener and
configuration bindings matched; no API restart, task change, database migration
or model activation occurred in this phone operation.

Read-only reconciliation confirmed the separate search deployment's live
API/Web source `54394ed`, schema `a0c9d2e4f817`. Its running entry matches that
session's deployment evidence. Later main source is not automatically deployed;
optional intent/scene providers and story generation were not activated here.

## Next acceptance

The phone was not installed or operated as part of this release. Update through
“检查更新” without uninstalling, then follow the
[Chinese v68 trial guide](PHONE_V68_TEST_GUIDE_ZH.md). Real microphone/ASR/TTS,
latency, owner/member access and family acceptance remain separate.
