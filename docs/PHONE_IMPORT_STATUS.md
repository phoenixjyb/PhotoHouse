# Phone import progress and server status

Following source, October 17, 2026. These UI changes are not in the published
phone v69 APK. A later package, signing/publication and physical upload trial
remain separate gates.

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

The [v69 folder-upload trial](../clients/android/docs/PHONE_V69_TEST_GUIDE_ZH.md)
remains the baseline for real device acceptance. Generated metadata and emulator
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
No release APK has been signed or published for this following-source UI.
