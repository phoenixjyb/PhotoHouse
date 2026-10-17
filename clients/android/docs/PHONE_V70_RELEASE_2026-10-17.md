# Phone v70 release: import progress

Date: 2026-10-17. Phone HTTPS OTA publishes **70 / `0.70-import-status`**.
The [historical candidate record](PHONE_V70_CANDIDATE_2026-10-17.md) covers
preparation; the [Chinese phone trial guide](PHONE_V70_TEST_GUIDE_ZH.md) covers
physical-phone follow-up.

## What changed

The Add content panel now opens **Import progress / 导入进度**, bringing the
existing local upload queue and owned server history into one workspace. Batch
and file details fold independently. Progress uses committed bytes and excludes
cancelled files from its denominator. Resume, Retry and Start remain explicit.

Server evidence is shown as distinct states: received with approval unconfirmed,
awaiting owner review, added to the accessible library, or currently unavailable.
Assignment does not establish photo-preview or video-playback readiness. The
explicit **Check server status / 检查服务器状态** action reads existing history;
there is no new API field, route, schema, worker or model activation.

## Source and package

The Android source used for the package is commit
`71de7b9df21630c3b76d81b8d0f958da4afa211a`, Android tree
`c6ef733f21d58c9b24afdbd556a6eccf85f81734`. PR #82 merged as
`590ddd7cb3b68709c7e7d24e8c93c41f4e553834` after all five CI jobs passed in
run **38984876123**.

The unsigned package was **11,715,593 bytes**, SHA-256
`37ccacd3bcfc66633391aac8fd36bf5609e2c115e298c869d04df6943cb97109`. The
published signed package is **11,733,368 bytes**, SHA-256
`b6ffb652658c2af4c90f3e24cc4c8f1d85d33ed61a312667b4a540cdc43d71a0`.
Package identity is `dev.photohouse.connected`, version code **70**, version
name **`0.70-import-status`**. All 17 embedded fields matched the existing
production profile. The original certificate fingerprint is
`56d7591b2b6c2538d506d1fe51327444f2307736cb12f5beefa08f1c410d6d28`.
Native package, signature, alignment, DEX and original-icon checks passed;
signing preserved DEX and original icon bytes.

## Verification and delivery

Eight focused JVM cases, six synthetic emulator scenarios and seven inspected
phone-density renders at 150% passed. The configured unsigned release build and
lint passed, as did an independent source/package audit, 20 delivery-fixture
checks, native parsing of both PowerShell controllers, and verification of pinned
Windows tools.

Windows HTTPS OTA publication and full trusted HTTPS readback passed. An
independent Mac full trusted HTTPS stream matched at
**2026-10-17 00:19:33.981635 UTC** without saving another APK copy. The API task,
configuration and listener binding remained unchanged; the TV v30 pointer also
remained unchanged. This release did not restart the API or change tasks,
databases, media or models.

## Acceptance still open

The physical Samsung was not installed or operated during this release. Real
folder upload, provider/network behavior, preview and playback readiness, and
family acceptance remain open. A received or assigned status is not evidence
that media is ready to view. Follow the
[Chinese v70 phone trial guide](PHONE_V70_TEST_GUIDE_ZH.md) and report those
results separately from package and OTA verification.
