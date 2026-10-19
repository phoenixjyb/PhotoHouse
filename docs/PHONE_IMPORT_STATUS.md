# Phone import progress and server status

**October 20:** [Phone v74 and matching Web UI](../clients/android/docs/PHONE_V74_RELEASE_2026-10-20.md)
are delivered. Expand **处理详情** in server history for account-owned preparation
records; receipt, library assignment and actual media readiness remain separate.
Samsung lock-screen transfer and real-media acceptance remain open.

**October 17 upload recovery update:** [Phone v71 is published](../clients/android/docs/PHONE_V71_RELEASE_2026-10-17.md)
and its owner trial produced complete server transfers and receipts after repeated
Retry taps. Review/assignment and media readiness remain separate. The following
[v72 candidate](../clients/android/docs/PHONE_V72_CANDIDATE_2026-10-17.md) adds bounded
foreground recovery, same-batch continuation and clearer final-confirmation feedback.
[V72 was subsequently published](../clients/android/docs/PHONE_V72_RELEASE_2026-10-17.md).
Earlier delivery snapshots below retain their dated scope.

Delivered in [phone v70](../clients/android/docs/PHONE_V70_RELEASE_2026-10-17.md),
October 17, 2026. Signing and full Windows/independent HTTPS readback passed;
physical folder-upload acceptance remains open.

## Library upload repair delivered in v71

The [v71 release](../clients/android/docs/PHONE_V71_RELEASE_2026-10-17.md)
fixes a valid-response rejection in v70: targeted resumable upload responses
include destination/approval fields that the old exact-six-field parser refused.
The repaired parser accepts the documented fields and the queue verifies the
original destination at every response boundary. Interrupted items show safe,
localized explanations. Explicit retry keeps the existing request and batch;
restoration and history refresh do not restart uploads. V71 is published.

The [v72 recovery candidate](../clients/android/docs/PHONE_V72_CANDIDATE_2026-10-17.md)
adds bounded recovery within an explicit foreground run and same-batch continuation;
it was subsequently [published](../clients/android/docs/PHONE_V72_RELEASE_2026-10-17.md).

## One view of the existing flow

The add-content panel exposes **Import progress / 导入进度** directly. One
workspace presents the existing account-owned upload queue and server history.
It does not create another queue, poll automatically, resume transfers on mount,
resend a received file or change upload/network consent.

The workspace starts as a compact summary with an explicit Details control. A
newly started batch or the add-content entry opens the workspace. The local
section also folds batches and their file lists. Byte progress uses committed
offsets, including paused/interrupted files, rather than optimistic sent bytes.
Cancelled files do not remain in the progress denominator. Resume, Retry, Cancel
and descriptions remain explicit actions; existing upload recovery guards apply.

## Labels follow their evidence

| Evidence | Display | What it does not establish |
| --- | --- | --- |
| Completed local transfer without usable matching history | Received; approval not confirmed | Approval or prepared media |
| Current owned history says `awaiting_review` | Awaiting owner review | Automatic approval |
| History says `available`, matching accessible library | Added to library | Photo preview/video playback readiness |
| Unavailable/unknown/revoked history or destination mismatch | Currently unavailable | A specific failure reason or access to another library |

Matching queue/history rows requires the same asset, media kind and size. A
loading, failed or closed history cannot reuse stale rows to claim assignment.
The caller supplies the current account's queue/history and available memberships;
account/session generations clear UI expansion and existing store request fences
reject late responses. Opening/describing a history item requires current library
access; unavailable library names/actions are not shown.

**Check server status / 检查服务器状态** performs an explicit existing history
read. It confirms neither thumbnail nor playback preparation. The UI says that
preparation is unconfirmed, rather than inferring it from receipt, membership or
an upload completion percentage. A received upload and final family-visible
result remain separate acceptance stages.

## Compatibility and next work

The strict v69 history response is unchanged. No field, state, route, schema,
worker or model switch is added. A richer preparation API must be negotiated
separately so v69 continues to parse its current response. The next server slice
needs current authorized preparation evidence and an explicit unknown fallback.

The [v70 phone trial](../clients/android/docs/PHONE_V70_TEST_GUIDE_ZH.md) retains
the v69 folder-upload baseline and adds the new progress/status controls. Generated metadata and emulator
UI checks do not establish Samsung provider/network/upload behavior.

## Source qualification

Eight focused JVM cases cover status projection, committed progress and unchanged
strict history parsing. The QA debug app/test APKs and lint pass. Six synthetic
native scenarios cover Chinese/English status at 150% text, stale/failed history,
access withdrawal, explicit resume, batch/workspace folding, pagination and the
real app entry point. Complete native captures are inspected at normal phone
density; emulator OS overlays are rejected rather than counted as visual passes.

These checks use generated metadata and the separate QA package. They do not
upload family files, use a live service or establish physical Samsung acceptance.
The delivered v70 package preserves the original certificate, icon and profile.
See the release record for exact source/package identity and delivery evidence.
