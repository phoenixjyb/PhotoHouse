# Own-upload preparation evidence

This source candidate adds `GET /upload-preparation?page=1` alongside the
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

Web/phone negotiation, localized stage presentation, failed/unknown recovery
journeys and live delivery are follow-up work. Older clients keep the existing
history contract. This endpoint does not turn a received upload into an approved
or prepared item, retry a failed task, or activate a worker.
