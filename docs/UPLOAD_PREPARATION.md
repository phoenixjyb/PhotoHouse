# Own-upload preparation evidence

The October 19 API release serves `GET /upload-preparation?page=1` alongside the
unchanged `GET /uploads` receipt history. It requires the same current account
and upload eligibility, returns only that account's receipts, and rechecks
current library membership before exposing processing evidence. It does not
provide an operator-wide processing dashboard.

## Response

The version-1 envelope contains `version`, `page`, `page_size` (10), `total`
and `items`. Each item retains the safe receipt fields (`asset_id`, `created_at`,
`bytes`, `kind`, `state`, `library_id`) and adds `processing`. That field is null
unless the receipt is currently available to this account in its library.

Processing contains:

- `stages`: `preview`, `index`, `faces`, `caption`, `video_probe`.
- `records`: booleans `image_vector`, `caption`, `face_detections`.
- `availability`: `preview` and `playback`.

Stage states are `awaiting_review`, `pending`, `running`, `finished`, `failed`,
`dead`, `unknown` or `not_applicable`. The latest task identifiable as matching
that asset and supported task type is authoritative;
an older success cannot hide a newer failure. Unsupported or malformed task
evidence stays unknown. Unattributable malformed task rows are not projected
across other users' receipts. An image embedding must use image modality.
Video probe, video embedding and asset-scoped video caption lifecycles are
reported where present; face processing is not advertised as applicable to video.

Record presence is separate from task state. No captions, identities, task IDs,
payloads, errors, paths or batch/account identifiers are exposed. One read-only
authorized database snapshot supplies each bounded page; it opens no original,
preview, vector or model files and changes no queue or database rows.

## Readiness and delivery

Availability remains `unknown` where this read has no file/manifest validation.
Image playback is `not_applicable`. A finished thumbnail task is not a verified
viewable thumbnail, and a finished video probe is not prepared playback.

The next Web/phone source candidate presents this evidence in the existing
upload-history workspace. Older clients keep the unchanged history contract. This endpoint does not turn a received upload into an approved
or prepared item, retry a failed task, or activate a worker.


## Web and phone presentation candidate

Web and phone v74 source read processing details after a successful receipt-history
read, when opening history or explicitly refreshing it. There is no polling,
second upload queue, task retry or file resubmission. Each response must match the
current page, total and exact receipt identity; account, library, membership and
request-generation changes invalidate it. Evidence is held in memory only.

Rows keep the received/awaiting-review/library assignment label and add a compact
processing summary. Expand **处理详情 / Processing details** for the five allowlisted
stages and record-presence labels. Finished applicable tasks say **处理任务已结束**;
preview and video playback still say **尚未验证**. Failed/stopped processing does
not ask the user to upload a received file again. Actual gallery/viewer access
remains a separate check.

Unsupported older servers (404/405/501), temporary errors and malformed or foreign
responses leave the original receipts visible with a neutral status. Expired
sessions use the existing recovery flow; loss of library access clears protected
details. Closing history or changing page/account/library discards delayed replies.

This candidate is not the currently published v73 APK or served Web bundle.
Signing, OTA publication, Web deployment and real Samsung acceptance remain
separate delivery gates.

## Chinese acceptance guide

1. Open **导入进度 → 服务器记录** on phone, or **我的上传** on Web, using the account that
   uploaded the files. Open/refresh history; no new file selection is needed.
2. Verify the receipt and library label remain visible while processing details
   load. Expand **处理详情** on one image and one video.
3. Check waiting/running/failed tasks against server records. A completed task
   must never turn **预览：尚未验证** into a claim of viewable media.
4. Collapse details, change page, close history and switch libraries. Old details
   must not reappear after returning to another account or library.
5. Open a received item in its gallery separately to confirm the preview and,
   for video, playback. Do not resend a received file to repair a derived task.

Generated browser and QA-emulator checks use synthetic receipt metadata only;
they do not establish physical upload, provider processing or family-media quality.
