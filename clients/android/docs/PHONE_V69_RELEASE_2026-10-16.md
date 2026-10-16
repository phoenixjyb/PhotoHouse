# Phone v69 release: folder upload recovery

Date: 2026-10-16. Phone HTTPS OTA publishes **69 / `0.69-upload-recovery`**.

## What changed

Folder and multiple-file picker results wait through covered session/gallery
revalidation. They retain the original account and destination, validate current
membership before reading, and discard stale provider completions. Recovery opens
review; uploading requires Start. A foreground session GET retries once after
350 ms for an OFFLINE transport failure. Authentication, TLS, malformed responses
and HTTP errors retain their handling; explicit Retry remains after two offline
failures. No mutation is automatically retried by this change.

Empty, unsupported, oversized and over-capacity selections now have actionable
review errors. A stale Start cannot authorize metered/unknown-network use.
Persisted interrupted uploads restore paused with existing progress. Formats and
limits are unchanged; see the [upload contract](../../../docs/ANDROID_UPLOAD_RECOVERY.md).

## Source and package

Build source: `72f2b76bff13fbc950de67b3e682fde31fa67f28`, Android tree
`0763eb2ecf07ba2c195283630cc4bca4e535bcc0`. PR #75 merged as
`deb83f6a00c7aebfe3b7a911a9ca63fd4d9509c6`. The only later Android difference
is one JVM test updated to wait for both offline attempts. APK input source did
not change, and the verified package was not rebuilt for that test correction.

Signed package `dev.photohouse.connected`: **11,725,176 bytes**, SHA-256
`7d957589de64d3456fd95110a4ea138f08ab27613cc2e8e0cc88a7fa1363deed`.
The original certificate remains
`56d7591b2b6c2538d506d1fe51327444f2307736cb12f5beefa08f1c410d6d28`.
Native signature/alignment passed; signing preserved DEX and original icon bytes.
All 17 embedded settings matched the existing production profile.
The [candidate record](PHONE_V69_CANDIDATE_2026-10-16.md) is historical preparation evidence.

## Verification and delivery

All five CI jobs passed at review head
`0a2fca9f0c01da4b3b4846a8bf8e5b7ae384fcc8`, run **38914467834**.
All **1,095 live-core tests** passed. Nine native synthetic emulator tests covered
picker lifecycle and review; four review cases were repeated after dismissing an
Android OS ANR overlay. Eight fresh, unobscured Chinese/English renders at 150%
text size were inspected; obscured captures were rejected. Debug build/lint and
configured unsigned release build/lint passed. Twenty signing/publication fixture
checks and native PowerShell parsing passed.

Windows native and full trusted HTTPS readback verified the signed package.
An independent Mac HTTPS stream matched every byte and digest at
**2026-10-16 14:27 UTC**, without saving another APK copy. The API task, action,
configuration, process/listener and TV v30 feed remained unchanged. This operation
did not restart the API, alter workers, migrate data, change media or activate a model.

## Device acceptance remains open

This fixes a source failure path matching the v68 report; the exact Samsung
transport cause was not confirmed from logs. The phone was not installed or
operated during this release. On the later follow-up, the user had not yet tried
v69 and no physical ADB device was connected. Update without uninstalling, then
follow the [Chinese folder-upload guide](PHONE_V69_TEST_GUIDE_ZH.md).
A receipt, approval, processing completion and gallery visibility are separate
acceptance stages. Real voice/family acceptance also remains open.
