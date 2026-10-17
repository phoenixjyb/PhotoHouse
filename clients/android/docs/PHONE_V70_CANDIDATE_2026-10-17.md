# Phone v70 candidate: historical preparation

This is the historical preparation record for **70 / `0.70-import-status`**.
The phone package has since been signed and published. See the
[v70 release record](PHONE_V70_RELEASE_2026-10-17.md) for package and delivery
evidence, and the [Chinese phone trial guide](PHONE_V70_TEST_GUIDE_ZH.md) for
the remaining physical-phone checks.

At preparation time, version **70 / `0.70-import-status`** was reserved for the
[unified import workspace](../../../docs/PHONE_IMPORT_STATUS.md).
This candidate record describes source qualification and preparation; it is
not the release or family/device acceptance record.

## What changes

- **导入进度 / Import progress** is directly reachable from Add content.
- A compact summary opens into the existing local queue and owned server records.
  Batch lists fold independently; paused/interrupted files retain committed byte
  progress, and cancelled files leave the byte denominator.
- Received, awaiting owner review, added to library and unavailable are distinct.
  Assignment does not claim that photo previews or video playback are ready.
- Loading/unavailable history cannot reuse stale assignment labels. Access changes
  remove unavailable actions. Refresh, Resume, Retry and Start remain explicit.

The v69 upload recovery path and strict history response are retained. There is
no API/schema/worker/model activation in this phone release. The production
connection profile, original certificate and original icon must be verified
against the preceding delivered release before publication.

## Qualification boundary

The UI source passed eight focused JVM cases, six synthetic native scenarios and
seven complete Chinese/English 150% phone-density render inspections. The QA
package was separate from the family app, and the physical Samsung was untouched.
The source and unsigned-package preparation gates listed here were followed by
the signed delivery recorded in the [v70 release record](PHONE_V70_RELEASE_2026-10-17.md).
A real folder upload and family-visible result remain separate acceptance
stages; use the [Chinese phone trial guide](PHONE_V70_TEST_GUIDE_ZH.md).

## 手机试用步骤

1. 更新后在设置确认 **v70**，选择要上传的资料库。请勿卸载旧版。
2. 打开添加内容，点 **导入进度**。查看服务器记录，展开／收起详情和文件批次。
3. 按 [v69 文件夹上传指南](PHONE_V69_TEST_GUIDE_ZH.md) 选择同一个文件夹。
   核对目的地、文件数量和大小；点击开始前不会自动上传。
4. 上传时查看本机进度。暂停后，进度应保留；继续／重试由你明确点击。
5. 点 **检查服务器状态**。核对“已上传，审核状态待确认”“等待主人审核”
   或“已加入资料库”。刷新失败不能触发重传，也不能继续显示旧的已加入状态。
6. “预览与播放准备状态未确认”表示当前接口尚未提供这项证据。回到资料库，
   分别确认新照片缩略图、打开后的照片和视频播放；这些结果与接收记录分开记录。

如果失败，请报告大致时间、失败阶段和屏幕提示，不必发送密码或私人影像。
