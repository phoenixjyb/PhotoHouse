# Phone v74 and Web preparation-status release — October 20, 2026

Phone **v74 / `0.74-upload-preparation`** (`dev.photohouse.connected`) is published
on Windows HTTPS OTA. API/Web serves immutable source
`9e39ebd8cdabb2ee2726a5938a6b97d4df7203d4`; Android tree is
`e35e896038c4031abbc18d807360b9899b5bbd66`. PR #97 merged as
`8e53d77ac14e1501430f5c0f6e94ea1ab65136bf` after all five CI jobs passed.
The merged tree matches the qualified build source. The rollout preserves the
newer search release, the current private configuration and reviewed people scope.

## What changed

Open **导入进度 → 服务器记录 → 处理详情** on phone, or **我的上传 → 处理详情** on Web.
Account-owned receipts now show expandable preview, search, face, description
and video-inspection processing records. Receipt and library labels remain
visible when a preparation read is unavailable. Opening details does not upload,
resubmit files, retry tasks or activate workers. There is no automatic polling.

**处理任务已结束** is task evidence. Preview/playback availability still says
**尚未验证** until actual media viewing is checked. Existing similar-photo stacks,
background transfer service, search and voice features remain available.

## Verification and delivery

- 1,146 core JVM tests, release build/lint and original icon/settings checks passed.
- 13 generated QA-emulator preparation/import cases passed. Four new enlarged-text
  cases were recaptured after dismissing an emulator System UI ANR; clean Chinese
  and English 150% renders were inspected.
- Focused Web preparation and existing upload-history browser journeys passed;
  63 relevant API tests / 28 subtests and seven merged-source package checks passed.
- Native Windows qualification passed nine generated API-route cases and two
  bounded child-process proofs. Only synthetic data was used for that qualification.
- Live rollout verified four stopped-writer backups and four on-disk restore
  rehearsals. All nine captured runtime states were restored, and the other
  78 task definitions were preserved. No migration or production database restore.
- Windows and independent Mac HTTPS checks matched the served HTML, JavaScript
  and CSS to the fixed source. Protected routes denied anonymous access.
- Original signing certificate, alignment, unchanged DEX and original icon verified.
  Native Windows, Windows trusted HTTPS and independent Mac full APK reads matched.
  OTA publication did not restart the API; TV remains v30.

Signed APK: **11,782,576 bytes**. SHA-256:
`90fa01f05cf24143462795d80270081cd17c67f3aefb92eb8a988da3b19e5ae4`.
Unsigned SHA-256:
`381c76f55cb878cc1e2ac8156664f708b3ceab6f1b3c4920a2fe41d45f8def15`.

## 家庭测试

1. 在手机“设置 → 检查更新”安装 v74，确认原图标保持一致。
2. 用原上传账号打开“导入进度 → 服务器记录”，不用重新选择或上传文件。
3. 展开一张照片和一个视频的“处理详情”，核对回执、相册归属和阶段记录。
4. 回到相册实际打开缩略图、大图和视频；任务结束不代替这一步。
5. 如果测试锁屏上传，使用一小批文件并保留上传通知和中断提示；不用重传大视频。

No physical phone was installed by this release operation. Signed-in owner/member
journeys, Samsung background/lock-screen transfer behavior, real-media viewing
and family grouping quality remain separate acceptance checks.

See the [preparation contract](../../../docs/UPLOAD_PREPARATION.md) and
[source qualification](PHONE_V74_CANDIDATE_2026-10-19.md).
