# Phone v73 release — October 19, 2026

Phone v73 (`0.73-background-upload`, package `dev.photohouse.connected`) is
published on the configured Windows HTTPS OTA feed. The release was built from
`d0be1bfbf5702745e54ddd118d674d705523b477`, Android tree
`aabcba03d4bf1d50790cc227c18311f2ea8fff44`; PR #94 merged as
`4459ad8d9d6cf40ec719d48301cc507204a974c5` after all five CI jobs passed.
The coordinated API/Web rollout serves immutable source `f2041c1`.

## Changes

- [Similar-photo stacks](../../../docs/SIMILAR_PHOTO_STACKS.md): show a cover and
  count for conservative current-page suggestions, expand/collapse, choose a
  temporary cover, separate a suggestion or show all photos. Originals and the
  complete gallery item list are retained. Choices reset on reload/scope change.
- [Background batch upload](PHONE_BACKGROUND_UPLOAD.md): a user-started,
  non-exported foreground transfer service separates ongoing batch uploads from
  Activity pause/lock-screen handling, with notification and explicit controls.
  Samsung behavior still requires a physical lock-screen upload trial.
- Existing protected HTTPS settings, search/voice features and original icon
  are retained. TV publication and persistent/cross-page grouping are separate.

## Verification and artifact

- All five hosted checks passed: API, Android, generated Web browser, Windows
  CPU and Windows private readers.
- Production-configured release lint/build passed. All 17 embedded settings
  matched the reviewed profile; QA/story fixture settings were off.
- Three focused emulator/store methods passed: enlarged-text stack controls,
  page-scope reset and independent full-screen navigation. Chinese/English 150%
  synthetic screenshots were inspected. The native set does not directly test
  opening a stack member and traversing that stack's viewer sequence.
- Original certificate, alignment, DEX preservation and original icon pixels
  verified. No physical phone was installed by this operation.
- Windows package checks, full trusted HTTPS download and independent Mac full
  download matched. The API binding and TV v30 feed stayed unchanged during OTA
  publication; publication required no API restart.

Signed APK: **11,770,288 bytes**. SHA-256:
`3b6d92ffa56eea586a5a0de076c1766c1e022f3ee1b05b890f3f64d699e5dca3`.
Unsigned SHA-256:
`11fc7c132ae25fbe0bf641abe35f67ed20b7810fd8ee0bcb4c29ee24466c42c2`.

## 家庭测试步骤

1. 手机进入“设置 → 检查更新”，安装 v73；图标应与之前相同。
2. 打开有连拍/相似照片的一页，查看封面下方数量，试“展开”、“收起”、
   更换封面、“分开显示”和“显示全部照片”。这些操作不会删除原件。
3. 点开照片检查大图与前后浏览；换页、刷新或切换资料库后临时选择会重置。
4. 选一小批测试照片开始上传，确认出现上传通知；锁屏片刻再解锁，检查
   进度和服务器回执。无需再次上传大视频。若中断，请保留提示和大致时间。
5. Web 刷新后也可使用封面/数量和展开控件。分组目前限当前页；缺少可靠
   元数据或不够相似的照片会保持单独显示，真实分组质量仍需家人反馈。

Server receipt, approval, processing completion and actual preview/playback
readiness remain distinct. The preparation endpoint is live, but client-side
stage negotiation/presentation is a subsequent feature.
