# Phone v69 candidate: folder selection and upload recovery

Version **69 / `0.69-upload-recovery`**, prepared from the upload recovery branch.
This document describes source scope; it is not a signing or publication receipt.
The installed/published v68 does not contain these changes.

## What changes

- A folder or multiple-file selection waits across session revalidation instead
  of being discarded while private content is covered. The original account and
  destination are checked before reading; recovery opens review without upload.
- A transient OFFLINE foreground-session GET is retried once after 350 ms.
  Private content stays covered; authentication, TLS and HTTP failures retain
  their existing handling. Explicit Retry remains after a second offline failure.
- Empty, unsupported, oversized or over-capacity selections show an actionable
  review error. Start remains disabled when the batch cannot be queued.
- A connectivity change returns to visible metered/unknown-network review;
  a stale Start button cannot grant consent. Interrupted uploads restore paused.

See [the upload behavior and limits](../../../docs/ANDROID_UPLOAD_RECOVERY.md).
No new API, schema, server service, upload policy or media conversion is needed.
The household connection profile and original icon are retained for the release.

## Verification and delivery

Core checks cover the queue, consent and session lifecycle; native synthetic QA
covers the same pending-selection effect used by actual picker callbacks, plus
Chinese/English review states at 150% text size. These checks do not exercise a
Samsung document provider or establish the exact transport cause of the report.

Prepare the configured unsigned APK from a clean pinned source, verify its native
version, all embedded settings and original icon, then obtain operation authority
for original-certificate signing and Windows phone OTA publication. Full HTTPS
readback and a real Samsung folder upload are separate delivery/acceptance gates.
Do not use a physical phone for emulator QA.

## Samsung acceptance after publication

1. Update to v69 and confirm the version in Settings. Select the intended library.
2. Choose the same outing folder. On return, wait for reconnect/review; if both
   reconnect attempts fail, use Retry. The selection should still be available.
3. Confirm supported/skipped counts, destination and total size. Unsupported-only
   selections should explain the limit without crashing. Nothing uploads yet.
4. Tap Start. On metered/unknown networks, read and confirm the separate warning,
   then tap Start. Check queued/uploaded/approved/prepared as distinct stages.
5. Reopen the library after processing and verify the newly received items.
   Report the time and on-screen failure stage if anything fails; no password or
   private media is needed for diagnosis.
