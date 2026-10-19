# Phone v74 preparation-status candidate

Version: **74 / `0.74-upload-preparation`**. This is source and local qualification,
not a signed or published release. The current delivered phone remains v73.

## Change

The existing import workspace reads the protected own-upload preparation endpoint
after upload history succeeds. Expand **处理详情** on an available receipt to see
preview, search, face, description and video-inspection task states. Opening or
closing details performs no upload, task retry or server write.

Receipt, library assignment and processing remain separate. **处理任务已结束** does
not mean a preview or playback works; availability remains **尚未验证** until the
media is checked separately. Older or unavailable servers keep receipt history
visible. Full receipt identity, page, account and generation checks reject late
or unrelated evidence. Nothing is added to persistent client storage.

## Qualification

- 1,146 live-core JVM tests passed, including strict v1 wire parsing, older-server
  fallback and stale-response/receipt binding.
- Unconfigured QA app and instrumentation APK built; debug lint passed.
- 13 generated QA-emulator preparation/import UI tests passed, including four
  new Chinese/English 150% text tests. Initial screenshots were obscured by an
  emulator System UI ANR; those images are not accepted visual evidence. After
  dismissing that emulator dialog, all four new tests passed again and clean
  Chinese/English large-text renders were inspected.
- Existing system TLS, separate Home transport and Keystore-only persistence
  boundary checks passed.
- Backend upload/preparation/closed-application/package contracts: 63 tests and
  28 subtests passed. These do not prove real upload processing or model quality.

The [preparation contract and Chinese trial](../../../docs/UPLOAD_PREPARATION.md)
also describes the Web candidate. Review/CI, pinned configured unsigned build,
original-certificate signing, OTA publication and a real Samsung trial remain
separate delivery gates. No physical phone was installed or controlled by this
candidate's checks.
