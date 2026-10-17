# Phone v72 delivery — October 17, 2026

Phone **72 / `0.72-upload-recovery`** is published on the operator's Windows
HTTPS OTA feed. The [candidate contract](PHONE_V72_CANDIDATE_2026-10-17.md)
describes its bounded foreground recovery, same-batch continuation and receipt
confirmation. TV remains v30.

## Immutable artifact

- APK input source: `72dbc80dde20f824b5b4c82f3e0509a2df6f1407`.
- PR #86 merged at `6979c339913e8ecbbe6bd7d87ef938a8fdae7008` with the same
  Android tree: `1bd3a14fddfb3b74cc6351b32dead6119410d48c`.
- Signed APK: 11,745,656 bytes; SHA-256
  `12cd43702d746206fc4a61c0014729461870509eb8c195110abe6aa12c21f615`.
- Original certificate, icon and 17 release-profile fields were verified.
  Signing preserved DEX and icon bytes.

## Qualification and delivery

All five hosted CI jobs and 1,122 core cases passed for the fixed source. The
configured unsigned APK build and 21 delivery-protection cases passed. The local
combined lint invocation timed out; hosted Android CI passed separately. Do not
report a local lint-release pass.

After the owner's explicit one-time merge/sign/publication approval, native
Windows signature/alignment/package checks and full trusted HTTPS readback
passed. An independent Mac full HTTPS stream also matched at
**2026-10-17 07:40:46 UTC**. API task/configuration and the TV OTA pointer were
preserved. This operation did not restart services, migrate data or install an
APK on a physical phone. Its one-time delivery authority is consumed.

## Acceptance still needed

The emulator instrumentation did not reach its scenarios because of startup
ANR/crash. Native UI and physical v72 folder-upload acceptance remain unverified.
The earlier v71 owner trial established complete server transfer receipts after
repeated Retry taps; it does not establish v72 recovery behavior.

Use the existing batch rather than selecting the same completed folder again.
Receipt, owner approval, library assignment, preparation and actual display are
separate outcomes. The subsequent approved offline acceptance and processing
start are described in the [upload journal contract](../../../docs/UPLOAD_REVIEW_JOURNAL_CONTEXT.md).
They did not deploy the general API approval-context repair.
